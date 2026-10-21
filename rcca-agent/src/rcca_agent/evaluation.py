"""Assemble one validated RCA author result; no critic, goal grading or token reserve."""

from copy import deepcopy
import time
import json

from agent_common.parsers import parse_health
from agent_common.contracts import now, incident_source
from .analysis_material import analysis_draft
from .evidence_interpretation import inspection_context, SENSITIVE
from .combined_synthesis import generate
from .synthesis_context import bounded_context, encoded_size

BASE_LIMIT = "관측·권고는 원인 확정, 조치 수행 또는 업무 복구를 의미하지 않습니다."
# Historical fixed text is recognized when reading saved report material.
REVIEW_LIMIT = "LLM 검토는 정답을 보장하지 않으며 원본 증거와 남은 불확실성을 함께 확인해야 합니다."
INTERPRETATION_LIMIT = "증거 의미 해석을 완료하지 못해 해석 결과는 미검토 상태입니다."
UNRESOLVED_LIMIT = "검토에서 해결하지 못한 주장은 제외하고 관련 권고는 보류했습니다."
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
    obs, data, profile, health, payload, assemble, llm, state, round_no, allowed
):
    """Keep model judgments separate from recorded observations and publishable guidance."""
    combined = True

    def record(kind, body, status="ok"):
        metadata = {"round": round_no, "stage": kind}
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
    interpretation = None
    interpretation_diag = {}
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
    if combined:
        for key in tuple(view):
            if key.startswith("interpretation_"):
                view[key] = []
    synthesis_diag = {}
    started_at, started = now(), time.monotonic()
    before = dict(getattr(llm, "usage", {}))
    request_limit = getattr(llm, "request_attempt_limit", 3)
    llm.request_attempt_limit = 1
    try:
        authored = await generate(llm, payload, synthesis_diag)
        status, model_candidates, limits = (
            authored["status"],
            authored["candidates"],
            authored["limitations"],
        )
        interpretation = authored["interpretation"]
        interpretation_diag = {
            "execution_status": "complete" if interpretation is not None else "failed",
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
    finally:
        llm.request_attempt_limit = request_limit
    synthesis_id = record(
        "rca_synthesis",
        {
            "status": status,
            **(
                {
                    "generation_mode": "combined",
                    "interpretation": interpretation,
                    "interpretation_status": interpretation_diag["execution_status"],
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
                k: v - before.get(k, 0) for k, v in getattr(llm, "usage", {}).items()
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
    limits = list(dict.fromkeys([BASE_LIMIT, *limits]))
    draft = analysis_draft(
        candidates,
        recommendations,
        limits,
        view,
        interpretation,
    )
    record("rca_analysis_draft", {**draft, "input_view": view})
    return dict(
        draft=draft,
        generation_mode="combined",
        interpretation=draft.get("interpretation"),
        stop_reason=None,
        synthesis_status=status,
        synthesis=synthesis_diag,
        evidence=dict(
            execution_status=interpretation_diag["execution_status"],
            reason=interpretation_diag.get("reason"),
            evidence_refs=[validation_id, synthesis_id],
            interpretation=draft.get("interpretation"),
        ),
        # Existing JC/result readers require this envelope. It is not an evaluation.
        review=dict(
            execution_status="skipped",
            verdict=None,
            reason="not_requested",
            analysis_id=draft["analysis_id"],
            evidence_refs=[],
            rubric_version="1",
            criteria={},
            unattributed_issues=False,
        ),
        review_output=None,
    )
