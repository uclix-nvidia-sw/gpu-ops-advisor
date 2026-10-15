"""Separate acquisition, interpretation and review within the existing attempt."""

from copy import deepcopy
import time
import json

from agent_common.parsers import parse_health
from agent_common.contracts import now, incident_source

from .analysis_review import analysis_draft, review_analysis, review_reserve
from .evidence_interpretation import inspection_context, interpret_evidence, SENSITIVE
from .synthesis import synthesize
from .synthesis_context import bounded_context, encoded_size


BASE_LIMIT = "관측·권고는 원인 확정, 조치 수행 또는 업무 복구를 의미하지 않습니다."
REVIEW_LIMIT = "LLM 검토는 정답을 보장하지 않으며 원본 증거와 남은 불확실성을 함께 확인해야 합니다."


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
    obs, data, profile, health, payload, assemble, llm, state, round_no, allowed
):
    """Keep model judgments out of verified facts and review the final assembled draft."""

    def record(kind, body, status="ok"):
        metadata = {"round": round_no, "stage": kind}
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
            body["rubric_version"] = "1"
        return obs._evidence(
            kind,
            None,
            data["time_range"],
            deepcopy({"round": round_no, **body}),
            status,
            metadata,
        )["id"]

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
            {"interpretation_" + key: rows for key, rows in interpretation.items()}
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
    synthesis_diag = {}
    review, review_diag, draft = None, {}, None
    review_ids = []
    stop_override = None
    while True:
        old_reserve = getattr(llm, "reserved_tokens", 0)
        llm.reserved_tokens = max(old_reserve, review_reserve(view, llm))
        started_at, started = now(), time.monotonic()
        before = dict(getattr(llm, "usage", {}))
        try:
            status, model_candidates, limits = await synthesize(
                llm, payload, synthesis_diag
            )
        finally:
            llm.reserved_tokens = old_reserve
        record(
            "rca_synthesis",
            {
                "status": status,
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
        candidates, recommendations = assemble(model_candidates)
        limits = list(dict.fromkeys([BASE_LIMIT, REVIEW_LIMIT, *limits]))
        if interpretation is None:
            limits.append(
                "증거 의미 해석을 완료하지 못해 해석 결과는 미검토 상태입니다."
            )
        draft = analysis_draft(candidates, recommendations, limits, view)
        record("rca_analysis_draft", {**draft, "input_view": view})
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
        if not state.get("revisions") and status == "complete":
            state["revisions"] = 1
            record(
                "investigation_decision",
                {
                    "action": "revise",
                    "reason": "review_revision_required",
                    "analysis_id": draft["analysis_id"],
                    "evidence_refs": [review_id],
                },
            )
            payload["review_feedback"] = review
            continue
        # Known-invalid assertions cannot survive exhaustion or an unrepairable rule claim.
        affected = {issue["claim_id"] for issue in review["issues"]}
        global_issue = None in affected
        candidates = [
            c
            for c in candidates
            if not global_issue and "cause:" + c["id"] not in affected
        ]
        recommendations = [
            dict(r, eligibility="withheld", reason="analysis_review_unresolved")
            if affected
            else r
            for r in recommendations
        ]
        limits = [BASE_LIMIT, REVIEW_LIMIT]
        limits.append(
            "검토에서 해결하지 못한 주장은 제외하고 관련 권고는 보류했습니다. 원인 판단은 추가 확인이 필요합니다."
        )
        draft = analysis_draft(candidates, recommendations, limits, view)
        record("rca_analysis_draft", {**draft, "input_view": view})
        review, review_diag = await review_analysis(llm, draft, view, [])
        if not review:
            stop_override = (
                "llm_budget_exhausted"
                if review_diag.get("reason") == "llm_token_budget_exhausted"
                else "analysis_unresolved"
            )
            review_diag["failure_reason"] = review_diag.get("reason")
            review_diag.update(
                execution_status="skipped", reason="draft_changed_after_review"
            )
        review_ids.append(
            record(
                "analysis_review",
                {**review_diag, "analysis_id": draft["analysis_id"], "review": review},
                "ok" if review else "unavailable",
            )
        )
        if review and review["verdict"] == "revision_required":
            stop_override = "revision_limit_reached"
            # Dependencies of a rejected fallback are not safe to infer from text.
            draft = analysis_draft(
                [],
                [],
                [
                    BASE_LIMIT,
                    REVIEW_LIMIT,
                    "검토 문제를 해결하지 못해 원인 주장과 권고를 보류했습니다.",
                ],
                view,
            )
            record("rca_analysis_draft", {**draft, "input_view": view})
            review = None
            review_diag = {
                "execution_status": "skipped",
                "reason": "draft_changed_after_review",
                "attempts": 0,
            }
            review_ids.append(
                record(
                    "analysis_review",
                    {
                        **review_diag,
                        "analysis_id": draft["analysis_id"],
                        "review": None,
                    },
                    "unavailable",
                )
            )
        break
    return dict(
        draft=draft,
        stop_reason=stop_override,
        synthesis_status=status,
        synthesis=synthesis_diag,
        evidence=dict(
            execution_status=interpretation_diag["execution_status"],
            reason=interpretation_diag.get("reason"),
            evidence_refs=[validation_id, interpretation_id],
        ),
        review=dict(
            execution_status=review_diag["execution_status"],
            verdict=review["verdict"] if review else None,
            reason=review_diag.get("reason"),
            analysis_id=draft["analysis_id"],
            evidence_refs=[review_ids[-1]],
            rubric_version="1",
            criteria=review["criteria"] if review else {},
            **(
                {"failure_reason": review_diag["failure_reason"]}
                if review_diag.get("failure_reason")
                else {}
            ),
        ),
        review_output=review,
    )
