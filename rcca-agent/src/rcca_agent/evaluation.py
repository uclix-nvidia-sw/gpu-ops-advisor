"""Separate acquisition, interpretation and review within the existing attempt."""

from copy import deepcopy
import time
import json

from agent_common.parsers import parse_health
from agent_common.contracts import now, incident_source

from .analysis_review import (
    review_prompt,
    analysis_draft,
    review_analysis,
    review_payload,
    review_reserve,
    WITHHELD_VERDICT,
)
from .evidence_interpretation import inspection_context, interpret_evidence, SENSITIVE
from .synthesis import synthesize, reserve_review_budget
from .combined_synthesis import generate, author_prompt
from .synthesis_context import bounded_context, encoded_size


BASE_LIMIT = "관측·권고는 원인 확정, 조치 수행 또는 업무 복구를 의미하지 않습니다."
REVIEW_LIMIT = "LLM 검토는 정답을 보장하지 않으며 원본 증거와 남은 불확실성을 함께 확인해야 합니다."
INTERPRETATION_LIMIT = "증거 의미 해석을 완료하지 못해 해석 결과는 미검토 상태입니다."
UNRESOLVED_LIMIT = "검토에서 해결하지 못한 주장은 제외하고 관련 권고는 보류했습니다."
# Code-authored limitations; model-authored ones stay in diagnostics only.
FIXED_LIMITS = (BASE_LIMIT, REVIEW_LIMIT, INTERPRETATION_LIMIT, UNRESOLVED_LIMIT)


def collection_status(planned, collected, fast_path=False):
    rows = []
    for query in planned:
        entries = collected.get(query, [])
        for entry in entries or [None]:
            rows.append(
                dict(
                    query_id=query,
                    execution_status="executed" if entry else "skipped",
                    tool_status=entry["tool_status"] if entry else None,
                    complete=bool(
                        entry
                        and entry["tool_status"] in {"ok", "empty"}
                        and entry["quality"].get("complete")
                    ),
                    reason=entry["quality"].get("reason") if entry else "not_executed",
                    evidence_refs=[entry["id"]] if entry else [],
                )
            )
    if fast_path or not planned:
        status, reason = (
            "not_requested",
            "fast_path" if fast_path else "no_planned_queries",
        )
        rows = []
    elif all(row["complete"] for row in rows):
        status, reason = "complete", None
    elif any(row["tool_status"] in {"ok", "empty", "partial"} for row in rows):
        status, reason = "partial", "collection_incomplete"
    else:
        status, reason = "failed", "no_successful_collection"
    return dict(
        status=status,
        reason=reason,
        query_results=rows,
        evidence_refs=list(
            dict.fromkeys(r for row in rows for r in row["evidence_refs"])
        ),
    )


async def evaluate_analysis(
    obs,
    data,
    profile,
    health,
    payload,
    assemble,
    llm,
    state,
    round_no,
    allowed,
    *,
    review_enabled=True,
):
    """Keep model judgments out of verified facts and review the final assembled draft."""

    def record(kind, body, status="ok"):
        metadata = {"round": round_no, "stage": kind}
        if not review_enabled:
            metadata["workflow"] = body["workflow"] = "single_collection"
        if combined:
            metadata["generation_mode"] = body["generation_mode"] = "combined"
        metadata.update(
            {
                k: body[k]
                for k in (
                    "execution_status",
                    "reason",
                    "analysis_id",
                    "started_at",
                    "completed_at",
                    "elapsed_seconds",
                    "attempts",
                    "action",
                    "model",
                    "usage",
                    "failure_reason",
                    "request_checks",
                )
                if k in body
            }
        )
        if kind == "rca_synthesis":
            metadata.update(
                execution_status="complete"
                if body["status"] == "complete"
                else "skipped"
                if body["status"] in {"unconfigured", "no_usable_evidence"}
                else "failed",
                reason=None if body["status"] == "complete" else body["status"],
            )
        if kind == "analysis_review":
            metadata["verdict"] = (
                body["review"]["verdict"] if body.get("review") else None
            )
            body["rubric_version"] = rubric
        return obs._evidence(
            kind,
            None,
            data["time_range"],
            deepcopy({"round": round_no, **body}),
            status,
            metadata,
        )["id"]

    combined = payload.get("generation_mode") == "combined"
    rubric = "2" if payload.get("decision_assessment") else "1"
    checks = []
    parse_health(
        obs.evidence,
        profile.get("health_contracts", {}),
        profile.get("queries", {}),
        checks,
    )
    payload.update(inspection_context(data, obs.evidence, health, checks))
    payload["observation_refs"] = sorted(
        set(payload["observation_refs"])
        | {ref for row in payload["raw_excerpts"] for ref in row["evidence_refs"]}
    )
    validation_id = record(
        "evidence_validation", {"checks": payload["evidence_checks"]}
    )
    interpretation, interpretation_id = None, None
    interpretation_diag = {"execution_status": "skipped", "reason": "combined_author"}
    if not combined:
        interpretation, interpretation_diag = await interpret_evidence(llm, payload)
        interpretation_id = record(
            "evidence_interpretation",
            {
                **interpretation_diag,
                "validation_evidence_id": validation_id,
                "interpretation": interpretation,
            },
            "ok" if interpretation is not None else "unavailable",
        )
        if interpretation:
            payload.update(
                {
                    "interpretation_" + key: rows
                    for key, rows in interpretation.items()
                    if key != "criterion_assessments"
                }
            )
    # This bounded source view is retained with the draft; the critic sees sources too.
    view = bounded_context(payload, 6000)
    rule_sources = [
        e for e in obs.evidence if e["query_id"] in {"runbook", "incident_snapshot"}
    ]
    view["rule_sources"] = []
    view["context_selection"]["omitted_rule_sources"] = 0
    for entry in rule_sources:
        selected_source = (
            {
                k: v
                for k, v in entry["snapshot"].items()
                if k
                in {
                    "claim",
                    "recommendations",
                    "applicability_conditions",
                    "required_evidence",
                }
            }
            if entry["query_id"] == "runbook"
            else {
                "verified_facts": incident_source(entry["snapshot"]).get(
                    "verified_facts", {}
                ),
                "target": data.get("target", {}),
                "incident_time": data.get("incident_time"),
            }
        )
        row = {
            "id": entry["id"],
            "query_id": entry["query_id"],
            "snapshot": selected_source,
            "selection": "selected_fields_only",
        }
        previous_refs = view["input_evidence_refs"]
        view["rule_sources"].append(row)
        view["input_evidence_refs"] = sorted(set(previous_refs) | {entry["id"]})
        if encoded_size(view) > 10000 or SENSITIVE.search(
            json.dumps(selected_source, ensure_ascii=False)
        ):
            view["rule_sources"].pop()
            view["input_evidence_refs"] = previous_refs
            view["context_selection"]["omitted_rule_sources"] += 1
            view["context_selection"]["complete"] = False
    if combined or rubric == "2":
        for key in tuple(view):
            if key.startswith("interpretation_"):
                view[key] = []
    synthesis_diag = {}
    review, review_diag, draft = None, {}, None
    review_ids = []
    stop_override = None
    feedback_review = None
    unattributed = False
    revision = 0
    while True:
        old_reserve = getattr(llm, "reserved_tokens", 0)
        if review_enabled:
            base_candidates, base_recommendations = assemble([])
            base_limits = [BASE_LIMIT, REVIEW_LIMIT]
            if interpretation is None:
                base_limits.append(INTERPRETATION_LIMIT)
            baseline = review_payload(
                analysis_draft(
                    base_candidates, base_recommendations, base_limits, view
                ),
                view,
                allowed,
            )
            output = getattr(
                getattr(llm, "settings", None), "llm_default_max_tokens", 4096
            )
            # Preserve the actual rule draft, full review output and existing 512 margin.
            floor = (
                old_reserve
                + encoded_size(baseline)
                + len(review_prompt(view).encode())
                + output
                + 512
            )
            reserved, allocation = reserve_review_budget(
                llm,
                payload,
                review_reserve(view, llm),
                floor,
                **({"prompt": author_prompt(payload)} if combined else {}),
            )
            allocation.update(
                review_floor_basis="rule_draft_full_output",
                review_baseline_input_bytes=encoded_size(baseline),
                review_output_tokens=output,
            )
            synthesis_diag = {"budget_allocation": allocation}
            llm.reserved_tokens = reserved
        else:
            # The single-collection report has no critic or critic token reserve.
            synthesis_diag = {}
        started_at, started = now(), time.monotonic()
        before = dict(getattr(llm, "usage", {}))
        request_limit = getattr(llm, "request_attempt_limit", 3)
        llm.request_attempt_limit = 1
        try:
            if combined:
                authored = await generate(llm, payload, synthesis_diag)
                status, model_candidates, limits = (
                    authored["status"],
                    authored["candidates"],
                    authored["limitations"],
                )
                interpretation = authored["interpretation"]
                interpretation_diag = {
                    "execution_status": "complete"
                    if interpretation is not None
                    else "failed",
                    "reason": None
                    if interpretation is not None
                    else synthesis_diag["error_code"],
                }
                view = {
                    **authored["input_view"],
                    "rule_sources": view.get("rule_sources", []),
                }
                view["input_evidence_refs"] = sorted(
                    set(view["input_evidence_refs"])
                    | {row["id"] for row in view["rule_sources"]}
                )
            else:
                status, model_candidates, limits = await synthesize(
                    llm, payload, synthesis_diag
                )
        finally:
            llm.reserved_tokens = old_reserve
            llm.request_attempt_limit = request_limit
        synthesis_id = record(
            "rca_synthesis",
            {
                "status": status,
                **(
                    {
                        "generation_mode": "combined",
                        "interpretation": interpretation,
                        "interpretation_status": interpretation_diag[
                            "execution_status"
                        ],
                    }
                    if combined
                    else {}
                ),
                "diagnostics": synthesis_diag,
                "started_at": started_at,
                "completed_at": now(),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "model": llm.settings.model_for("synthesis")
                if getattr(llm, "settings", None)
                else None,
                "usage": {
                    k: v - before.get(k, 0)
                    for k, v in getattr(llm, "usage", {}).items()
                },
                "input_evidence_refs": synthesis_diag.get(
                    "repair_input_evidence_refs",
                    synthesis_diag.get("input_evidence_refs", []),
                ),
                "hypotheses": model_candidates,
                "limitations": limits,
            },
            "ok" if status == "complete" else "unavailable",
        )
        if combined:
            interpretation_id = synthesis_id
        candidates, recommendations = assemble(model_candidates)
        limits = list(
            dict.fromkeys(
                [BASE_LIMIT, *([REVIEW_LIMIT] if review_enabled else []), *limits]
            )
        )
        if review_enabled and interpretation is None:
            limits.append(INTERPRETATION_LIMIT)
        draft = analysis_draft(
            candidates,
            recommendations,
            limits,
            view,
            interpretation if combined or rubric == "2" else None,
        )
        record("rca_analysis_draft", {**draft, "input_view": view})
        if not review_enabled:
            # Retain the historical result envelope without inventing a verdict.
            review_diag = {"execution_status": "skipped", "reason": "not_requested"}
            break
        review, review_diag = await review_analysis(llm, draft, view, allowed)
        review_id = record(
            "analysis_review",
            {**review_diag, "analysis_id": draft["analysis_id"], "review": review},
            "ok" if review is not None else "unavailable",
        )
        review_ids.append(review_id)
        if not review or review["verdict"] != "revision_required":
            if not review and review_diag.get("reason") in {
                "llm_input_size_exceeded",
                "llm_token_budget_exhausted",
            }:
                stop_override = (
                    "analysis_unresolved"
                    if review_diag["reason"] == "llm_input_size_exceeded"
                    else "llm_budget_exhausted"
                )
            break
        if combined and revision == 0 and status == "complete":
            # One semantic revision on the same evidence, followed by a fresh
            # independent review. The feedback is not additional evidence.
            revision += 1
            payload["review_feedback"] = {
                "previous_analysis_id": draft["analysis_id"],
                "previous_claims": deepcopy(draft["claims"]),
                "issues": deepcopy(review["issues"]),
                "criteria": deepcopy(review["criteria"]),
                "instruction": "Revise only supported claims using the original evidence. "
                "Do not treat review feedback as evidence or invent missing observations.",
            }
            record(
                "investigation_decision",
                {
                    "action": "revise",
                    "reason": "independent_review_feedback",
                    "analysis_id": draft["analysis_id"],
                    "revision": revision,
                    "evidence_refs": [review_id],
                },
            )
            continue
        record(
            "investigation_decision",
            {
                "action": "withhold",
                "reason": "revision_limit_reached"
                if revision
                else "same_evidence_rewrite_blocked",
                "analysis_id": draft["analysis_id"],
                "evidence_refs": [review_id],
            },
        )
        # Known-invalid assertions cannot survive exhaustion or an unrepairable rule claim.
        affected = {issue["claim_id"] for issue in review["issues"]}
        unattributed = None in affected
        assertions_valid = all(
            review["criteria"].get(key, {}).get("status") == "pass"
            for key in ("grounding", "identity_time")
        )
        # Unattributed critiques (alternatives, wording, completeness) do not make
        # grounded, correctly targeted assertions invalid; keep them as feedback.
        if assertions_valid:
            affected.discard(None)
        global_issue = None in affected
        removed_findings = set()
        if interpretation is not None:
            if global_issue:
                interpretation = None
                interpretation_diag = {
                    "execution_status": "failed",
                    "reason": "review_rejected_interpretation",
                }
            else:
                interpretation = deepcopy(interpretation)
                caveat_removed = False
                for section in ("findings", "unknowns", "conflicts", "limitations"):
                    retained = []
                    for index, row in enumerate(interpretation.get(section, [])):
                        claim_id = f"interpretation:{section}:{row.get('id', index)}"
                        if claim_id in affected:
                            if section == "findings":
                                removed_findings.add(row["id"])
                            else:
                                caveat_removed = True
                        else:
                            retained.append(row)
                    interpretation[section] = retained
                for row in interpretation.get("criterion_assessments", []):
                    if (
                        "criterion:" + row["criterion_id"] in affected
                        or caveat_removed
                        or removed_findings.intersection(row["finding_refs"])
                    ):
                        row.update(status="unknown", finding_refs=[], evidence_refs=[])
        candidates = [
            c
            for c in candidates
            if not global_issue
            and "cause:" + c["id"] not in affected
            and not removed_findings.intersection(c.get("finding_refs", []))
            and not (combined and interpretation is None and "finding_refs" in c)
        ]
        recommendations = [
            dict(r, eligibility="withheld", reason="analysis_review_unresolved")
            if affected
            else r
            for r in recommendations
        ]
        limits = list(
            dict.fromkeys([BASE_LIMIT, REVIEW_LIMIT, *([] if global_issue else limits)])
        )
        if affected:
            limits.append(UNRESOLVED_LIMIT)
        draft = analysis_draft(
            candidates,
            recommendations,
            limits,
            view,
            interpretation if combined or rubric == "2" else None,
        )
        record(
            "rca_analysis_draft",
            {
                **draft,
                "input_view": view,
                "reason": "review_claims_withheld",
                "previous_review_evidence_id": review_id,
            },
        )
        feedback_review = review
        if global_issue:
            review = None
            review_diag = {
                "execution_status": "skipped",
                "reason": "draft_changed_after_review",
                "attempts": 0,
            }
        else:
            # The retained draft is the reviewed draft minus every challenged
            # claim; no unreviewed text was added, so the review still covers it.
            review = {
                **review,
                "verdict": WITHHELD_VERDICT,
                "analysis_id": draft["analysis_id"],
            }
            review_diag = {"execution_status": "complete", "attempts": 0}
        review_ids.append(
            record(
                "analysis_review",
                {
                    **review_diag,
                    "analysis_id": draft["analysis_id"],
                    "review": review,
                    "previous_review_evidence_id": review_id,
                },
                "ok" if review else "unavailable",
            )
        )
        break
    return dict(
        draft=draft,
        generation_mode="combined" if combined else "separate",
        interpretation=draft.get("interpretation"),
        stop_reason=stop_override,
        synthesis_status=status,
        synthesis=synthesis_diag,
        evidence=dict(
            execution_status=interpretation_diag["execution_status"],
            reason=interpretation_diag.get("reason"),
            evidence_refs=[validation_id, interpretation_id],
            **(
                {"interpretation": draft.get("interpretation")}
                if combined or rubric == "2"
                else {}
            ),
        ),
        review=dict(
            execution_status=review_diag["execution_status"],
            verdict=review["verdict"] if review else None,
            reason=review_diag.get("reason"),
            analysis_id=draft["analysis_id"],
            evidence_refs=[review_ids[-1]] if review_ids else [],
            rubric_version=rubric,
            criteria=review["criteria"] if review else {},
            unattributed_issues=unattributed,
            **(
                {"failure_reason": review_diag["failure_reason"]}
                if review_diag.get("failure_reason")
                else {}
            ),
        ),
        review_output=feedback_review or review,
    )
