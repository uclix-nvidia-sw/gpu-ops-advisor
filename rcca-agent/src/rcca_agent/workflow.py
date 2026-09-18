import json
from uuid import uuid4

from agent_common.contracts import (
    base_result,
    result_status,
    content_hash,
    timestamp,
    now,
    incident_source,
)
from agent_common.llm import explain
from agent_common.normalize import allocations
from agent_common.observation import Observation
from agent_common.runtime import attempt_context
from agent_common.parsers import parse_health, health_facts
from .procedures import select_procedure
from .prompts import EXPLANATION


REQUIRED = {
    "R01": ["producer_contract", "error_code"],
    "R02": ["incident_mapping"],
    "R03": ["incident_mapping"],
    "R04": ["incident_mapping", "workload_evidence"],
    "R05": ["observations"],
    "R06": ["incident_history"],
    "R07": ["incident_history", "topology"],
    "R08": ["current_mapping", "action_policy"],
    "R09": ["action_records", "device_recovery_evidence", "workload_evidence"],
}


def compatible_runbooks(rows, source):
    found = {}
    for row in rows:
        compatibility = row["compatibility"]
        if (
            not compatibility
            or row["content_hash"] != row.get("reviewed_content_hash")
            or content_hash(row["content"]) != row["content_hash"]
        ):
            continue
        if not all(
            source.get(k) in (v if isinstance(v, list) else [v])
            for k, v in compatibility.items()
        ):
            continue
        if (
            row["knowledge_key"] not in found
            or row["revision"] > found[row["knowledge_key"]]["revision"]
        ):
            found[row["knowledge_key"]] = row
    return list(found.values())


def check_conditions(conditions, facts):
    # Explicit equality predicates only. No eval, scripts, SQL, YAML execution.
    return bool(conditions) and all(
        isinstance(c, dict)
        and set(c) == {"field", "equals"}
        and c["field"] in facts
        and facts[c["field"]] == c["equals"]
        for c in conditions
    )


async def run(tools):
    ctx = attempt_context.get()
    claim, profile = ctx["claim"], ctx["profile"]
    data = claim["input"]
    result = base_result(claim, ctx["context"]["data_cutoff_at"])
    source = incident_source(data["incident_snapshot"])
    obs = Observation(tools, profile, data, ctx["deadline"])
    eid = str(uuid4())
    obs.evidence.append(
        dict(
            id=eid,
            query_id="incident_snapshot",
            query_version=str(data["evidence_version"]),
            cluster_id=None,
            scope=data["scope"],
            time_range=data["time_range"],
            input={"incident_id": data["incident_id"]},
            tool_status="ok",
            quality={"immutable": True},
            snapshot=data["incident_snapshot"],
            collected_at=now(),
        )
    )
    facts = dict(source.get("verified_facts", {}))
    procedure = select_procedure(data, source)
    runbooks = compatible_runbooks(ctx["context"]["runbooks"], source)
    applicable = []
    queries = set()
    for book in runbooks:
        content = book["content"]
        required = content.get("required_evidence", [])
        excluded = check_conditions(content.get("exclusion_conditions", []), facts)
        if (
            set(required) <= facts.keys()
            and check_conditions(content.get("applicability_conditions", []), facts)
            and not excluded
        ):
            applicable.append(book)
        else:
            queries.update(
                q
                for q in content.get("required_queries", [])
                if q in procedure.allowed_next_steps
            )
    if not applicable:
        queries.update(procedure.required_queries)
    # A known error runbook does not satisfy an independent mapping/impact purpose.
    purpose_queries = {
        "R02": ("D08", "D06"),
        "R03": ("D08", "D06", "D02"),
        "R04": ("D08", "D06", "D13"),
        "R07": ("D01", "D08", "D06"),
        "R09": ("D05", "D09", "D13"),
    }
    for purpose in data["purpose_ids"]:
        if any(k not in facts for k in REQUIRED[purpose]):
            queries.update(purpose_queries.get(purpose, ()))
    collected = {}
    for query in sorted(queries):
        collected[query] = await obs.collect(query)
    health = parse_health(obs.evidence, profile.get("health_contracts", {}))
    facts.update(health_facts(health, data.get("target", {})))
    # Required observations may establish or refute applicability; always re-check.
    applicable = [
        book
        for book in runbooks
        if set(book["content"].get("required_evidence", [])) <= facts.keys()
        and check_conditions(book["content"].get("applicability_conditions", []), facts)
        and not check_conditions(book["content"].get("exclusion_conditions", []), facts)
    ]
    # Optional tool calling selects query IDs only, with no arbitrary query or side effects.
    remaining = [q for q in procedure.optional_queries if q not in collected]
    for _ in range(profile["limits"]["max_followups"]):
        if applicable or not remaining or not ctx["llm"].configured:
            break
        calls = await ctx["llm"].complete(
            "Choose one registered investigation step or stop. Return a tool call only.",
            {
                "procedure": procedure.procedure_id,
                "available": remaining,
                "observed_status": {
                    q: [e["tool_status"] for e in es] for q, es in collected.items()
                },
            },
            stage="investigation",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "investigate",
                        "description": "Select a permitted read-only observation.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query_id": {
                                    "type": "string",
                                    "enum": remaining + ["stop"],
                                }
                            },
                            "required": ["query_id"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
        )
        try:
            if (
                not calls
                or len(calls) != 1
                or calls[0]["function"]["name"] != "investigate"
            ):
                break
            args = json.loads(calls[0]["function"]["arguments"])
            if set(args) != {"query_id"} or args["query_id"] not in remaining:
                break
            query = args["query_id"]
        except (ValueError, KeyError, TypeError):
            break
        remaining.remove(query)
        collected[query] = await obs.collect(query)
    # Re-check after optional observations as well as the required collection.
    health = parse_health(obs.evidence, profile.get("health_contracts", {}))
    facts.update(health_facts(health, data.get("target", {})))
    applicable = [
        book
        for book in runbooks
        if set(book["content"].get("required_evidence", [])) <= facts.keys()
        and check_conditions(book["content"].get("applicability_conditions", []), facts)
        and not check_conditions(book["content"].get("exclusion_conditions", []), facts)
    ]
    # Observations do not acquire semantic truth merely because a query succeeded.
    mapping = allocations(
        collected.get("D08", []), data["time_range"], collected.get("D06", [])
    )
    incident_at = timestamp(data["incident_time"])
    relations = [
        dict(
            cluster_id=m["cluster_id"],
            gpu_uuid=m["gpu_uuid"],
            pod_uid=m["pod_uid"],
            namespace=m["namespace"],
            relation_scope="incident_time_mapping",
            impact_status="not_assessed",
            evidence_refs=m["evidence_refs"],
        )
        for m in mapping
        if m["start"] <= incident_at < m["end"]
    ]
    available = set(facts)
    if relations:
        available.add("incident_mapping")
    if any(e["tool_status"] == "ok" for q, es in collected.items() for e in es):
        available.add("observations")
    if ctx["context"]["incidents"]:
        available.add("incident_history")
    candidates = []
    recommendations = []
    for book in applicable:
        bid = str(uuid4())
        obs.evidence.append(
            dict(
                id=bid,
                query_id="runbook",
                query_version=str(book["revision"]),
                cluster_id=None,
                scope=data["scope"],
                time_range=data["time_range"],
                input={"revision_id": book["id"]},
                tool_status="ok",
                quality={"reviewed": True},
                snapshot=book["content"],
                collected_at=now(),
            )
        )
        observation_refs = [
            e["id"]
            for e in obs.evidence
            if e["tool_status"] == "ok" and e["query_id"] in collected
        ]
        candidates.append(
            dict(
                id=book["id"],
                claim=book["content"].get("claim", book["knowledge_key"]),
                causal_status="supported",
                supporting_refs=[eid, bid] + observation_refs,
                contradicting_refs=[],
                value_refs=[],
                missing_inputs=[],
            )
        )
        for rec in book["content"].get("recommendations", []):
            eligible = check_conditions(rec.get("preconditions", []), facts)
            recommendations.append(
                dict(
                    text=rec["text"],
                    preconditions=rec.get("preconditions", []),
                    eligibility="eligible" if eligible else "withheld",
                    reason=None if eligible else "preconditions_not_verified",
                    evidence_refs=[eid, bid],
                    value_refs=[],
                    execution="not_performed",
                )
            )
    assessments = []
    for purpose in data["purpose_ids"]:
        missing = [k for k in REQUIRED[purpose] if k not in available]
        assessments.append(
            dict(
                purpose_id=purpose,
                status="ready"
                if not missing
                else (
                    "partial"
                    if "observations" in available or applicable or relations
                    else "blocked"
                ),
                missing_inputs=missing,
                evidence_refs=[eid]
                + [
                    e["id"]
                    for e in obs.evidence
                    if e["tool_status"] == "ok" and e["id"] != eid
                ],
            )
        )
    missing = sorted({m for a in assessments for m in a["missing_inputs"]})
    failures = [e for e in obs.evidence if e["tool_status"] == "unavailable"]
    state_groups = {}
    for h in health:
        if h["check_status"] == "valid":
            key = (
                h["cluster_id"],
                json.dumps(h["target"], sort_keys=True),
                h["component"],
                h["observed_at"],
            )
            state_groups.setdefault(key, set()).add(h["normalized_health"])
    conflicting = any(
        "healthy" in states and bool(states & {"degraded", "unhealthy"})
        for states in state_groups.values()
    )
    if not candidates and health:
        supporting = list(
            dict.fromkeys(
                r
                for h in health
                if h["normalized_health"] in ("degraded", "unhealthy")
                for r in h["evidence_refs"]
            )
        )
        contradicting = list(
            dict.fromkeys(
                r
                for h in health
                if h["normalized_health"] == "healthy"
                for r in h["evidence_refs"]
            )
        )
        if supporting:
            candidates.append(
                dict(
                    id="observed_device_symptom",
                    claim="장비 검사에서 이상 상태가 관측됐으나 근본 원인은 추가 확인이 필요합니다.",
                    causal_status="candidate",
                    supporting_refs=supporting,
                    contradicting_refs=contradicting,
                    value_refs=[],
                    missing_inputs=["causal_confirmation_evidence"],
                )
            )
    reason = "evidence_sufficient" if not missing else "missing_data"
    if conflicting:
        reason = "conflicting_evidence"
    if any(e["quality"].get("reason") == "budget_exhausted" for e in failures):
        reason = "budget_exhausted"
    elif any(e["quality"].get("reason") == "query_failed" for e in failures):
        reason = "query_failed"
    elif failures and all(
        e["quality"].get("reason") == "unsupported_source" for e in failures
    ):
        reason = "unsupported_source"
    result.update(
        incident_id=data["incident_id"],
        incident_time=data["incident_time"],
        current_checked_at=None,
        pod_relations=relations,
        assessments=assessments,
        cause_candidates=candidates,
        recommendations=recommendations,
        missing_inputs=missing,
        termination_reason=reason,
        procedure={
            "procedure_id": procedure.procedure_id,
            "version": procedure.version,
        },
        runbook_revisions=[
            {"id": b["id"], "revision": b["revision"]} for b in applicable
        ],
        device_observations=health,
        result_status=result_status(assessments),
        evidence_refs=[e["id"] for e in obs.evidence],
        limitations=[
            "관측·권고는 원인 확정, 조치 수행 또는 업무 복구를 의미하지 않습니다."
        ],
    )
    result["facts"] = [
        dict(
            id="incident-observed",
            text="고정된 사건 증거를 기준으로 조사했습니다.",
            evidence_refs=[eid],
            value_refs=[],
        )
    ]
    await explain(result, ctx["llm"], EXPLANATION)
    result["llm_usage"] = ctx["llm"].usage
    return {"result": result, "evidence": obs.evidence}
