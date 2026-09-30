"""Bounded evidence interpretation; model output never establishes verified facts."""

import re

from agent_common.observation import series, usable_observation

from .prompts import SYNTHESIS


def synthesis_input(data, evidence, health, relations, applicable, planned=()):
    # Raw logs and unregistered producer semantics cannot establish device health.
    complete = [
        e for e in evidence if e["tool_status"] == "ok" and e["quality"].get("complete")
    ]
    valid_ids = {e["id"] for e in evidence if usable_observation(e)}
    observations = [
        h
        for h in health
        if h["check_status"] == "valid"
        and h["normalized_health"] != "unknown"
        and set(h["evidence_refs"]) <= valid_ids
    ]
    metrics = series(complete)
    refs = sorted(
        {r for h in observations + relations + metrics for r in h["evidence_refs"]}
    )
    return {
        "incident_time": data["incident_time"],
        "scope": data["scope"],
        "target": data.get("target", {}),
        "purpose_ids": data["purpose_ids"],
        "device_observations": observations,
        "pod_relations": relations,
        "metric_observations": metrics,
        "observation_refs": refs,
        "query_quality": [
            {k: e[k] for k in ("id", "query_id", "tool_status", "quality")}
            for e in evidence
            if e["query_id"].startswith("D")
        ],
        "runbook_matches": [
            {"id": b["id"], "claim": b["content"].get("claim", b["knowledge_key"])}
            for b in applicable
        ],
        "runbook_plans": [
            {
                "id": b["id"],
                "revision": b["revision"],
                "application_status": "applicable" if b in applicable else "pending",
                "investigation_only": b["content"].get("investigation_only", False),
                "analysis_guidance": b["content"].get("analysis_guidance", []),
                "limitations": b["content"].get("limitations", []),
            }
            for b in planned
        ],
    }


def validate_synthesis(response, refs):
    """Validate structure/references, not the truth of an LLM hypothesis."""
    if not isinstance(response, dict) or set(response) != {
        "hypotheses",
        "limitations",
    }:
        raise ValueError("invalid analysis shape")
    hypotheses = response["hypotheses"]
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise ValueError("invalid hypotheses")

    def strings(items):
        return (
            isinstance(items, list)
            and len(items) <= 32
            and all(isinstance(s, str) and s.strip() and len(s) <= 2000 for s in items)
        )

    if not strings(response["limitations"]) or any(
        re.search(r"\d", s) for s in response["limitations"]
    ):
        raise ValueError("invalid limitations")
    candidates = []
    for i, h in enumerate(hypotheses):
        if not isinstance(h, dict) or set(h) != {
            "claim",
            "supporting_refs",
            "contradicting_refs",
            "missing_inputs",
        }:
            raise ValueError("invalid hypothesis shape")
        if (
            not isinstance(h["claim"], str)
            or not h["claim"].strip()
            or len(h["claim"]) > 2000
            or re.search(r"\d", h["claim"])
        ):
            raise ValueError("invalid claim")
        if not all(
            strings(h[k])
            for k in ("supporting_refs", "contradicting_refs", "missing_inputs")
        ):
            raise ValueError("invalid hypothesis references")
        supporting, contradicting = (
            set(h["supporting_refs"]),
            set(h["contradicting_refs"]),
        )
        if (
            not supporting
            or not (supporting | contradicting) <= set(refs)
            or supporting & contradicting
        ):
            raise ValueError("ungrounded or contradictory references")
        candidates.append(
            dict(
                id=f"analysis-{i + 1}",
                claim=h["claim"],
                causal_status="candidate",
                supporting_refs=sorted(supporting),
                contradicting_refs=sorted(contradicting),
                value_refs=[],
                missing_inputs=list(
                    dict.fromkeys(
                        h["missing_inputs"] + ["causal_confirmation_evidence"]
                    )
                ),
            )
        )
    return candidates


async def synthesize(llm, payload):
    if not payload["observation_refs"]:
        return "no_usable_evidence", [], []
    if not llm.configured:
        return "unconfigured", [], []
    # RemoteUncertain and cancellation propagate to Worker fencing.
    try:
        response = await llm.complete(SYNTHESIS, payload, stage="synthesis")
        candidates = validate_synthesis(response, payload["observation_refs"])
    except (ValueError, TypeError, KeyError):
        return "failed", [], []
    return "complete", candidates, response["limitations"]
