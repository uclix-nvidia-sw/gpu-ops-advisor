import json
import time
from uuid import uuid4

from agent_common.contracts import (
    base_result,
    result_status,
    content_hash,
    timestamp,
    incident_source,
)
from agent_common.normalize import allocations
from agent_common.query_contract import consolidated, mapping_query
from agent_common.observation import Observation, usable_observation, evidence_stamp
from agent_common.runtime import attempt_context
from agent_common.parsers import parse_health, health_facts
from importlib.resources import files
from .synthesis import synthesis_input
from .evaluation import evaluate_analysis, collection_status, BASE_LIMIT
from .decision_trace import check, record_decision
from .fleet_events import (
    MISMATCH_CODES,
    enrich_report_inventory,
    match_alert,
    parse_events,
    incident_selector,
    matches_target,
)
from .report import write_report
from .report_observations import summarize_reports
from .investigation_summary import investigation_summary
from .switch_inventory import collect_switch_pci
from .host_history import host_history, history_summary
from .incident_dossier import (
    METRICS,
    enabled as dossier_enabled,
    current_data,
    comparison_targets,
    dossier_summary,
    error_tools,
    operator_view,
    component_report,
    component_view,
    incident_brief,
)
from .operator_guidance import project_guidance
from .collection_checks import collection_checks, reported_gpu_identity
from .requirement_diagnostics import (
    unmet_requirements,
    reported_facts,
)
from .report_labels import LABELS, query_label
from .observation_agents import collect_round
from .incident import alert_clues
from .retrieval import retrieve_runbooks
from .runbook_contract import (
    schema_kind,
    validate_published_runbook,
    contract_reason,
    validate_runbook,
    compatibility_status,
)


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
        and type(facts[c["field"]]) is type(c["equals"])
        and facts[c["field"]] == c["equals"]
        for c in conditions
    )


def select_runbooks(rows, source, profile, obs):
    legacy, current, plans, diagnostics = [], [], {}, []
    general_key = profile.get("rca", {}).get("general_runbook_key")
    for row in rows:
        try:
            kind, plan = validate_published_runbook(row, profile)
            if kind == "legacy":
                legacy.append(row)
            else:
                plans[row["id"]] = plan
                current.append(row)
        except ValueError as exc:
            diagnostics.append(
                {
                    "revision_id": row["id"],
                    "status": "invalid_contract",
                    "reason": contract_reason(exc),
                }
            )

    # Store already restricts visibility/state and pins revisions at the JC claim.
    # The claim pins every published revision. Keep the newest one per
    # compatibility contract before ranking, so a lexical score cannot pick an
    # older revision of the same knowledge.
    def contract(row):
        return row["knowledge_key"], json.dumps(row["compatibility"], sort_keys=True)

    newest = {}
    for row in current:
        if row["revision"] > newest.get(contract(row), {"revision": -1})["revision"]:
            newest[contract(row)] = row
    current = list(newest.values())
    general = [r for r in current if r["knowledge_key"] == general_key]
    ranked = retrieve_runbooks([r for r in current if r not in general], source)
    selected = compatible_runbooks(legacy, source)
    keys = set()
    for entry in ranked:
        row = entry["runbook"]
        if contract(row) in keys:
            continue
        keys.add(contract(row))
        selected.append(row)
        diagnostics.append(
            {
                "revision_id": row["id"],
                "status": "retrieved",
                "score": entry["total_score"],
                "tokenizer_revision": entry["tokenizer_revision"],
            }
        )
    if general:
        selected.append(
            {**max(general, key=lambda r: r["revision"]), "general_investigation": True}
        )
    # Packaged fallback is an investigation template, never published knowledge.
    content = json.loads(
        files("rcca_agent").joinpath("general_runbook.json").read_text(encoding="utf-8")
    )
    row = dict(
        id="builtin-general",
        knowledge_key="BUILTIN-GENERAL-GPU-NODE",
        revision=1,
        content=content,
        compatibility={},
        origin="builtin",
    )
    plans[row["id"]] = validate_runbook(
        row, profile["queries"], list(profile["queries"]), authoring=True
    )
    selected.append({**row, "general_investigation": True})
    for book in selected:
        if book.get("general_investigation"):
            diagnostics.append(
                {
                    "revision_id": book["id"],
                    "status": "general_available",
                    "origin": book.get("origin", "published"),
                }
            )
    obs._evidence(
        "runbook_selection",
        None,
        obs.data["time_range"],
        diagnostics,
        "ok",
        {"deterministic": True},
    )
    return selected, plans


def matching_runbooks(books, legacy_facts, verified, data):
    attributes = {k: {"status": "known", "value": v} for k, v in verified.items()}
    clusters = data["scope"]["clusters"]
    if len(clusters) == 1:
        attributes["cluster_id"] = {
            "status": "known",
            "value": clusters[0]["cluster_id"],
        }
    applicable, pending = [], []
    for book in books:
        content = book["content"]
        facts = legacy_facts if schema_kind(content) == "legacy" else verified
        compatibility_attributes = dict(attributes)
        if (
            content.get("investigation_only")
            and "reported_producer_contract" in content.get("required_evidence", [])
            and verified.get("reported_producer_contract")
            and "producer_contract" not in compatibility_attributes
        ):
            # Adapter compatibility is independent of current device health.
            # Do not add the stronger scalar to applicability/action facts.
            compatibility_attributes["producer_contract"] = {
                "status": "known",
                "value": verified["reported_producer_contract"],
            }
        status = (
            "compatible"
            if schema_kind(content) == "legacy" or book.get("origin") == "builtin"
            else compatibility_status(book["compatibility"], compatibility_attributes)
        )
        if status == "incompatible" or check_conditions(
            content.get("exclusion_conditions", []), facts
        ):
            continue
        if (
            status == "compatible"
            and set(content.get("required_evidence", [])) <= facts.keys()
            and all(
                c["field"] in facts for c in content.get("exclusion_conditions", [])
            )
            and (
                content.get("investigation_only")
                or check_conditions(content.get("applicability_conditions", []), facts)
            )
        ):
            applicable.append(book)
        else:
            pending.append(book)
    specific = [b for b in applicable + pending if not b.get("general_investigation")]
    if specific:
        applicable = [b for b in applicable if not b.get("general_investigation")]
        pending = [b for b in pending if not b.get("general_investigation")]
    elif any(b.get("origin") != "builtin" for b in applicable + pending):
        applicable = [b for b in applicable if b.get("origin") != "builtin"]
        pending = [b for b in pending if b.get("origin") != "builtin"]
    return applicable, pending


def normalized_state(obs, collected, data, profile, initial_facts):
    health = parse_health(
        obs.evidence, profile.get("health_contracts", {}), profile["queries"]
    )
    health = enrich_report_inventory(health, obs.evidence)
    complete = {e["id"]: e for e in obs.evidence if usable_observation(e)}
    valid = [h for h in health if set(h["evidence_refs"]) <= complete.keys()]
    # Scope-local health is usable only for the same target. A missing freshness
    # contract cannot authorize a v1 runbook, even if the transport succeeded.
    fresh = [
        h
        for h in valid
        if h["check_status"] == "valid"
        and all(
            0
            <= timestamp(data["incident_time"]) - timestamp(h["observed_at"])
            <= (
                complete[r]["quality"].get("max_hold_seconds")
                if consolidated(profile)
                else profile["queries"]
                .get(complete[r]["query_id"], {})
                .get("max_hold_seconds", -1)
            )
            for r in h["evidence_refs"]
        )
    ]
    verified = (
        health_facts(fresh, data.get("target", {}))
        if len(data["scope"]["clusters"]) == 1 and not data.get("identity_conflicts")
        else {}
    )
    # Report-only facts cannot satisfy the existing current-health scalar fields.
    if len(data["scope"]["clusters"]) == 1 and not data.get("identity_conflicts"):
        verified.update(
            reported_facts(
                valid, parse_events(obs.evidence, profile, data.get("target", {})), data
            )
        )
    facts = {**initial_facts, **verified}
    mapping_id = mapping_query(profile)
    mapping = allocations(
        [
            e
            for e in collected.get(mapping_id, [])
            if e["tool_status"] == "ok" and e["quality"].get("complete")
        ],
        data["time_range"],
        [
            e
            for e in collected.get("D06", [])
            if e["tool_status"] == "ok" and e["quality"].get("complete")
        ],
        require_pod_join=(
            consolidated(profile)
            or profile["queries"].get(mapping_id, {}).get("allocation_semantics")
            == "observed_pod_labels"
        ),
        observed=(
            consolidated(profile)
            or profile["queries"].get(mapping_id, {}).get("allocation_semantics")
            == "observed_pod_labels"
        ),
    )
    incident_at = timestamp(data["incident_time"])
    mapping_identity, identity_refs = reported_gpu_identity(data, valid)
    relations = [
        dict(
            cluster_id=m["cluster_id"],
            gpu_uuid=m["gpu_uuid"],
            pod_uid=m["pod_uid"],
            namespace=m["namespace"],
            relation_scope="incident_time_mapping",
            impact_status="not_assessed",
            evidence_refs=list(dict.fromkeys(m["evidence_refs"] + identity_refs)),
        )
        for m in mapping
        if m["start"] <= incident_at < m["end"]
        and not data.get("identity_conflicts")
        and mapping_identity
        and all(m.get(k) == v for k, v in mapping_identity.items())
        and all(
            m.get(k) == v
            for k, v in data.get("target", {}).items()
            if k in {"node", "namespace"}
        )
    ]
    available = set(facts)
    if relations:
        available.add("incident_mapping")
    payload = synthesis_input(data, obs.evidence, health, relations, [])
    if payload["observation_refs"]:
        available.add("observations")
    return health, facts, verified, relations, available


def conflicting_health(health, selector=None):
    groups = {}
    for h in health:
        if selector and not matches_target(h, selector):
            continue
        if h["check_status"] == "valid":
            key = (
                h["cluster_id"],
                json.dumps(h["target"], sort_keys=True),
                h["component"],
                h["observed_at"],
            )
            groups.setdefault(key, set()).add(h["normalized_health"])
    return any(
        "healthy" in states and bool(states & {"degraded", "unhealthy"})
        for states in groups.values()
    )


async def run(tools):
    ctx = attempt_context.get()
    claim, profile = ctx["claim"], ctx["profile"]
    data = claim["input"]
    result = base_result(claim, ctx["context"]["data_cutoff_at"])
    source = incident_source(data["incident_snapshot"])
    clues = alert_clues(source)
    if len(data["scope"]["clusters"]) == 1:
        clues["cluster_id"] = data["scope"]["clusters"][0]["cluster_id"]
    # The raw snapshot stays immutable. Display names narrow collection only;
    # they do not prove a machine/GPU binding or become verified facts.
    target = dict(data.get("target", {}))
    conflicts = list(clues["conflicts"])
    for key in ("machine_id", "component", "k8s_node_name"):
        if clues.get(key):
            if target.get(key) and target[key] != clues[key]:
                conflicts.append(key)
            else:
                target[key] = clues[key]
    if (
        target.get("node")
        and target.get("k8s_node_name")
        and target["node"] != target["k8s_node_name"]
    ):
        conflicts.append("node")
    clues["conflicts"] = sorted(set(conflicts))
    if clues.get("k8s_node_name") and not target.get("node"):
        target["node"] = clues["k8s_node_name"]
    log_query_target = {}
    if clues.get("k8s_node_name"):
        log_query_target["node"] = target["node"]
    if clues.get("component"):
        log_query_target["component"] = clues["component"]
    if clues.get("machine_id"):
        log_query_target["machine_id"] = clues["machine_id"]
    data = {
        **data,
        "target": target,
        "log_query_target": log_query_target,
        "identity_conflicts": clues["conflicts"],
    }
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
            **evidence_stamp(),
        )
    )
    obs._evidence(
        "alert_clues", None, data["time_range"], clues, "ok", {"verified_facts": False}
    )
    initial_facts = {
        k: v
        for k, v in source.get("verified_facts", {}).items()
        if v is not None and v != "unknown"
    }
    runbooks, plans = select_runbooks(ctx["context"]["runbooks"], source, profile, obs)
    selection_id = obs.evidence[-1]["id"]
    applicable, pending = matching_runbooks(runbooks, initial_facts, {}, data)
    selected = applicable + pending
    rule_refs = {}

    def preserve_runbook(book):
        if book["id"] not in rule_refs:
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
                    quality={
                        "reviewed": book.get("origin") != "builtin",
                        "origin": book.get("origin", "published"),
                        "selection_evidence_id": selection_id,
                    },
                    snapshot=book["content"],
                    **evidence_stamp(),
                )
            )
            rule_refs[book["id"]] = bid
        return rule_refs[book["id"]]

    for book in selected:
        preserve_runbook(book)
    comparison_plan = dossier_enabled(selected)
    dossier = (
        comparison_plan
        and not data.get("identity_conflicts")
        and bool(target.get("node") or target.get("machine_id"))
    )
    comparison = {}
    if dossier:
        data = current_data(data, ctx["context"]["data_cutoff_at"])
        obs.data = data
        obs.tools = error_tools(obs.tools)
    if not data.get("identity_conflicts") and (
        target.get("node") or target.get("machine_id")
    ):
        history = host_history(ctx["context"], data)
        if history is not None:
            history_id = obs._evidence(
                "host_incident_history",
                None,
                history["period"],
                history,
                "ok",
                {"complete": history["complete"], "source": "incident_store"},
            )
            result["quality"]["host_incident_history"] = {
                **history,
                "evidence_refs": [history_id["id"]],
            }

    def steps(book):
        return plans.get(
            book["id"],
            [
                dict(
                    query_id=q,
                    required=True,
                    fact_names=[],
                    purpose="Runbook observation",
                )
                for q in book["content"].get("required_queries", [])
            ],
        )

    def plan_queries(books):
        return list(
            dict.fromkeys(step["query_id"] for book in books for step in steps(book))
        )

    approved = plan_queries(selected)
    queries = (
        list(approved)
        if not data.get("identity_conflicts") and (not comparison_plan or dossier)
        else []
    )
    plan_id = obs._evidence(
        "investigation_plan",
        None,
        data["time_range"],
        {
            "runbooks": [
                dict(
                    revision_id=b["id"],
                    revision=b["revision"],
                    content_hash=content_hash(b["content"]),
                    origin=b.get("origin", "published"),
                    required_evidence=b["content"].get("required_evidence", []),
                    steps=[
                        {k: step[k] for k in ("query_id", "purpose") if k in step}
                        for step in steps(b)
                    ],
                )
                for b in selected
            ],
            "planned_queries": queries,
            "allowed_queries": approved,
            "selection_evidence_id": selection_id,
            "evidence_refs": [rule_refs[book["id"]] for book in selected],
        },
        "ok",
        {"deterministic": True},
    )["id"]
    collected = {}
    budget = {
        "queries": profile["limits"]["max_queries"],
        "discovery": profile["limits"].get("max_discovery_calls", 64),
    }
    concurrency = profile["limits"].get("max_concurrency", 3)
    analysis_status = "skipped_runbook"
    followups, gaps, gate = 0, [], "sufficient"
    stop_reason = None
    max_rounds = 1  # One planned collection phase for new RCA reports.

    evaluation = None
    synthesis_diagnostics = {}
    error_events = []
    candidates, recommendations = [], []
    final_limits = [BASE_LIMIT]
    planned_queries = list(queries)

    def assemble_rca_draft(model_candidates, health, facts, verified, applicable):
        candidates = list(model_candidates)
        recommendations = []
        applicable_ids = {book["id"] for book in applicable}
        for book in selected:
            bid = rule_refs[book["id"]]
            if book["id"] not in applicable_ids:
                continue
            observation_refs = [
                e["id"]
                for e in obs.evidence
                if e["tool_status"] == "ok" and e["query_id"] in collected
            ]
            if book.get("general_investigation") or book["content"].get(
                "investigation_only"
            ):
                continue
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
                eligible = check_conditions(
                    rec.get("preconditions", []),
                    facts if schema_kind(book["content"]) == "legacy" else verified,
                )
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
        return candidates, recommendations

    def evaluate_requirements(round_no, approved):
        """Retain collection and Runbook requirement diagnostics independently of review."""
        decision_checks = []
        health, facts, verified, relations, available = normalized_state(
            obs, collected, data, profile, initial_facts
        )
        applicable, pending = matching_runbooks(runbooks, facts, verified, data)
        if ctx["context"]["incidents"]:
            available.add("incident_history")
        required_facts = {
            k for b in selected for k in b["content"].get("required_evidence", [])
        }
        gaps = sorted(required_facts - available)
        check(
            decision_checks,
            "required_evidence",
            "bool(required_facts - available)",
            bool(required_facts - available),
            {"required_facts": sorted(required_facts), "available": sorted(available)},
        )
        if check(
            decision_checks,
            "approved_runbook",
            "not selected",
            not selected,
            {"selected_count": len(selected)},
        ):
            gaps.append("approved_runbook")
        if check(
            decision_checks,
            "incident_mapping",
            "'incident_mapping' in required_facts and not relations",
            "incident_mapping" in required_facts and not relations,
            {
                "mapping_required": "incident_mapping" in required_facts,
                "relations_count": len(relations),
            },
        ):
            gaps.append(
                "mapping_target_unverified"
                if not (target.get("gpu_uuid") or target.get("pod_uid"))
                else "mapping_not_observed_at_incident"
            )
            mapping_id = mapping_query(profile)
            if not all(q in collected for q in (mapping_id, "D06")):
                gaps.append("mapping_queries_not_executed")
            elif not any(
                e["tool_status"] == "ok" and e["quality"].get("complete")
                for e in collected[mapping_id]
            ):
                gaps.append("mapping_source_unavailable")
        if check(
            decision_checks,
            "target_identity_conflict",
            "bool(identity_conflicts)",
            bool(data["identity_conflicts"]),
            {"identity_conflicts": data["identity_conflicts"]},
        ):
            gaps.append("target_identity_conflict")
        alert_checks = []
        alert_match = match_alert(
            clues,
            health,
            []
            if data.get("identity_conflicts")
            else parse_events(obs.evidence, profile, data.get("target", {})),
            diagnostics=alert_checks,
        )
        decision_checks.extend(
            {**c, "source": "rcca_agent.fleet_events.match_alert"} for c in alert_checks
        )
        d09 = collected.get("D09")
        if check(
            decision_checks,
            "collection_failed",
            "alert_match.status != 'error_code_unparsed' and not (d09 and all(usable_observation(e) for e in d09))",
            alert_match["status"] != "error_code_unparsed"
            and not (d09 and all(usable_observation(e) for e in d09)),
            {
                "alert_match.status": alert_match["status"],
                "d09_count": len(d09 or []),
                "d09_usable_count": sum(usable_observation(e) for e in d09 or []),
            },
        ):
            alert_match = {**alert_match, "status": "collection_failed"}
        if check(
            decision_checks,
            "alert_match_gap",
            "alert_match.status in MISMATCH_CODES",
            alert_match["status"] in MISMATCH_CODES,
            {
                "alert_match.status": alert_match["status"],
                "MISMATCH_CODES": list(MISMATCH_CODES),
            },
        ):
            gaps.append(alert_match["status"])
        # A failed optional (supporting) metric is reported by name; only failures of
        # the error source and the Runbooks' required metrics degrade the report.
        failed = {
            q
            for q, es in collected.items()
            if any(e["tool_status"] in ("unavailable", "partial") for e in es)
        }
        required = {
            s["query_id"] for b in selected for s in steps(b) if s.get("required")
        }
        optional = set(plan_queries(selected)) - required
        degraded = bool(failed - optional)
        conflicting = conflicting_health(health, incident_selector(data))
        check(
            decision_checks,
            "observation_degraded",
            "bool(failed - optional)",
            degraded,
            {"failed": sorted(failed), "optional": sorted(optional)},
        )
        check(
            decision_checks,
            "conflicting_evidence",
            "conflicting_health(health, incident_selector(data))",
            conflicting,
            {"health_count": len(health)},
        )
        events = []
        if gaps:
            events.append("missing_evidence")
        if conflicting:
            events.append("conflicting_evidence")
        if degraded:
            events.append("query_failed")
        # Fleet baseline reports ("Healthy" without an error code) are left unmapped
        # by the producer contract. When error-coded reports exist, only those carry
        # the values this investigation needs; baseline reports stay context. Component
        # alerts carry no code, so their mapped (Unhealthy) reports play that role.
        relevant = (
            [h for h in health if h.get("error_code")]
            or [h for h in health if h["normalized_health"] != "unknown"]
            or health
        )
        if check(
            decision_checks,
            "unknown_value",
            "any(h.check_status != 'valid' or h.normalized_health == 'unknown' for h in relevant) or (health_query_collected and not health)",
            any(
                h["check_status"] != "valid" or h["normalized_health"] == "unknown"
                for h in relevant
            )
            or (any(collected.get(q) for q in ("D05", "D09")) and not health),
            {
                "health_count": len(health),
                "relevant_count": len(relevant),
                "invalid_or_unknown_count": sum(
                    h["check_status"] != "valid" or h["normalized_health"] == "unknown"
                    for h in relevant
                ),
                "health_query_collected": any(collected.get(q) for q in ("D05", "D09")),
            },
        ):
            events.append("unknown_value")
            gaps.append("unknown_value")
        remaining = [q for q in approved if q not in collected]
        gate = "degraded" if degraded else "conflicted" if conflicting else "sufficient"
        return dict(
            health=health,
            facts=facts,
            verified=verified,
            relations=relations,
            available=available,
            applicable=applicable,
            pending=pending,
            gaps=gaps,
            gate=gate,
            remaining=remaining,
            approved=approved,
            events=events,
            optional_failed=sorted(failed & optional),
            alert_match=alert_match,
            decision_checks=decision_checks,
            # Skipping analysis needs the code's own published Runbook guidance.
            matched=False,
        )

    async def analyze_round(state, round_no):
        nonlocal evaluation, synthesis_diagnostics, analysis_status, error_events
        nonlocal candidates, recommendations, final_limits
        health = state["health"]
        facts = state["facts"]
        verified = state["verified"]
        relations = state["relations"]
        applicable = state["applicable"]
        error_events = (
            []
            if data.get("identity_conflicts")
            else parse_events(obs.evidence, profile, data.get("target", {}))
        )
        payload = synthesis_input(
            data,
            obs.evidence,
            health,
            relations,
            applicable,
            selected,
            error_events,
        )
        if dossier:
            payload["incident_brief"] = incident_brief(
                data,
                [e for values in collected.values() for e in values],
                comparison,
                result["quality"].get("host_incident_history"),
            )
            payload.setdefault("incident_comparison", []).extend(
                dossier_summary(
                    data,
                    [e for values in collected.values() for e in values],
                    comparison,
                )
            )
        history_findings = history_summary(
            result["quality"].get("host_incident_history")
        )
        if history_findings:
            payload.setdefault("incident_comparison", []).extend(history_findings)
        source_hashes = observation_hashes(collected)
        payload["source_version"] = content_hash(sorted(source_hashes))
        payload.update(generation_mode="combined")
        if (state["alert_match"] or {}).get("status") in MISMATCH_CODES:
            payload["alert_match"] = state["alert_match"]
        evaluation = await evaluate_analysis(
            obs,
            data,
            profile,
            health,
            payload,
            lambda model: assemble_rca_draft(
                model, health, facts, verified, applicable
            ),
            ctx["llm"],
            round_no,
        )
        synthesis_diagnostics = evaluation["synthesis"]
        analysis_status = evaluation["synthesis_status"]
        candidates = evaluation["draft"]["cause_candidates"]
        recommendations = evaluation["draft"]["recommendations"]
        final_limits = evaluation["draft"]["limitations"]
        if time.monotonic() >= ctx["deadline"]:
            raise TimeoutError("RCA evaluation deadline exhausted")

    round_no = 0
    if queries:
        collected.update(
            await collect_round(
                obs, queries, budget, round_no=round_no, concurrency=concurrency
            )
        )
    state = evaluate_requirements(round_no, approved)
    collection_decision_id = record_decision(
        obs,
        data["time_range"],
        "collection_assessment",
        "rcca_agent.workflow.evaluate_requirements",
        state["decision_checks"],
        {
            "phase": "after collection, before evidence_validation and rca_synthesis",
            "collected_queries": sorted(collected),
        },
        {
            "alert_match": state["alert_match"],
            "gaps": state["gaps"],
            "gate": state["gate"],
            "optional_failed": state["optional_failed"],
        },
        [e["id"] for es in collected.values() for e in es],
    )
    if dossier and round_no == 0:
        comparison = comparison_targets(
            data, clues, [e for values in collected.values() for e in values]
        )
        comparison["switch_pci"] = await collect_switch_pci(
            obs, budget, clues, comparison["targets"]
        )
        result["quality"]["triage_observations"] = operator_view(
            data,
            [e for values in collected.values() for e in values],
            comparison,
            state["health"],
        )
    elif round_no == 0 and component_report(selected):
        result["quality"]["component_observations"] = component_view(
            data,
            [e for values in collected.values() for e in values],
            state["health"],
            clues.get("component"),
        )
    await analyze_round(state, round_no)
    state.update(
        stop_reason="no_remaining_queries",
        next_queries=[],
        deferred_queries=[],
    )
    health = state["health"]
    relations, available = state["relations"], state["available"]
    applicable, pending = state["applicable"], state["pending"]
    gaps, gate, stop_reason = state["gaps"], state["gate"], state["stop_reason"]
    remaining, approved = state["remaining"], state["approved"]
    analysis_missing = []
    if analysis_status not in {"complete", "skipped_alert_match"}:
        analysis_missing.append("synthesis_" + analysis_status)
    if not selected:
        analysis_missing.append("approved_runbook")
    if gate in ("degraded", "conflicted"):
        analysis_missing.append("observation_" + gate)
    analysis_missing.extend(gaps)
    assessments = []
    for book in selected:
        missing = sorted(
            set(
                k
                for k in book["content"].get("required_evidence", [])
                if k not in available
            )
            | set(analysis_missing)
        )
        assessments.append(
            dict(
                assessment_id=book["id"],
                question=book["content"].get("title", book["knowledge_key"]),
                runbook_revision_id=book["id"],
                status="ready"
                if not missing
                else "partial"
                if "observations" in available or applicable or relations
                else "blocked",
                missing_inputs=missing,
                evidence_refs=[eid, plan_id]
                + [
                    e["id"]
                    for e in obs.evidence
                    if e["tool_status"] == "ok" and e["id"] not in (eid, plan_id)
                ],
            )
        )
    missing = sorted({m for a in assessments for m in a["missing_inputs"]})
    failures = [
        e
        for e in obs.evidence
        if e["tool_status"] == "unavailable"
        and e["query_id"] in collected
        and not e["quality"].get("superseded_by_retry")
    ]
    conflicting = conflicting_health(health, incident_selector(data))
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
        procedure={"procedure_id": "runbook_plan", "version": "1.0"},
        runbook_revisions=[
            {
                "id": b["id"],
                "revision": b["revision"],
                "knowledge_key": b["knowledge_key"],
                "title": b["content"].get("title") or b["knowledge_key"],
                "origin": b.get("origin", "published"),
            }
            for b in selected
        ],
        device_observations=health,
        result_status=result_status(assessments),
        evidence_refs=[e["id"] for e in obs.evidence],
        limitations=final_limits,
    )
    result["facts"] = [
        dict(
            id="incident-observed",
            text="고정된 사건 증거를 기준으로 조사했습니다.",
            evidence_refs=[eid],
            value_refs=[],
        )
    ]
    result["quality"]["analysis"] = {
        "status": analysis_status,
        "requirement_diagnostics": unmet_requirements(
            missing, health, error_events, data
        ),
        "fast_path": False,
        "alert_match": state["alert_match"],
        "resolved_scope_gaps": state.get("resolved_scope_gaps", []),
        "followups": followups,
        "plan_evidence_id": plan_id,
        "collection_stop_reason": stop_reason,
        "remaining_queries": remaining,
        "collection_max_rounds": max_rounds,
        "remaining_budget": budget,
        "synthesis": synthesis_diagnostics,
        "fleet_report_diagnostics": {
            "reports": sum(h.get("time_basis") == "loki_recorded_at" for h in health),
            "missing_or_zero_producer_time": sum(
                h.get("producer_time_status") == "missing_or_zero" for h in health
            ),
            "unverified_state_reports": sum(
                h.get("time_basis") == "loki_recorded_at" and not h.get("fact_eligible")
                for h in health
            ),
            "unknown_normalized_health": sum(
                h.get("normalized_health") == "unknown" for h in health
            ),
            "scope": "Collected reports; inventory candidates are not the error device and report time is not event time.",
        },
        "error_events": error_events,
        "reported_errors": [
            {
                "error_code": h["error_code"],
                "status": "reported",
                "verified": False,
                "fact_eligible": h.get("fact_eligible", False),
                "evidence_refs": h["evidence_refs"],
            }
            for h in health
            if h.get("error_code") and h["check_status"] == "valid"
        ],
        "gpu_identity_candidates": [
            {
                **candidate,
                "node": h["target"].get("node"),
                "observed_at": h["observed_at"],
                "evidence_refs": h["evidence_refs"],
                "limitation": "device_event_time_unverified",
            }
            for h in health
            for candidate in h.get("gpu_candidates", [])
        ],
    }
    analysis = result["quality"]["analysis"]
    analysis["workflow"] = "single_collection"
    result["quality"]["evidence_catalog"] = [
        {
            "id": e["id"],
            "label": query_label(e["query_id"]),
            "time_range": e["time_range"],
            "sample_count": e["quality"].get("sample_count"),
            "cluster_id": e["cluster_id"],
        }
        for e in obs.evidence
        if e["query_id"].startswith("D")
    ]
    result["quality"]["collection_checks"] = collection_checks(
        profile,
        approved,
        collected,
        relations,
        [h["error_code"] for h in health if h.get("error_code")]
        + [event["error_code"] for event in error_events]
        + clues.get("error_codes", []),
    )
    final_stop = {
        "sufficient": "analysis_unresolved",
        "no_remaining_queries": "no_available_followup",
    }.get(stop_reason, stop_reason)
    result["quality"]["rca_evaluation"] = {
        "schema_version": "2",
        "generation_mode": evaluation.get("generation_mode", "separate"),
        "collection": collection_status(planned_queries, collected),
        "evidence": evaluation["evidence"],
        "analysis_id": evaluation["draft"]["analysis_id"],
        "review": evaluation["review"],
        "investigation": {
            "status": "finished",
            "stop_reason": final_stop,
            "evidence_refs": [
                e["id"] for e in obs.evidence if e["query_id"] == "rca_analysis_draft"
            ],
        },
    }
    # Published guidance remains reference data, never a second RCA conclusion.
    selected_revisions = {b["id"] for b in selected}
    result["quality"]["runbook_guidance"] = project_guidance(
        [
            e
            for e in obs.evidence
            if e.get("input", {}).get("revision_id") in selected_revisions
        ],
        reported_facts(health, error_events, data),
    )
    if state["optional_failed"]:
        # Plain metric names for section 5; the report itself stays complete.
        result["quality"]["optional_unavailable"] = [
            {"query_id": q, "name": METRICS.get(q) or LABELS["queries"].get(q, q)}
            for q in state["optional_failed"]
        ]
    status_decision_id = record_decision(
        obs,
        data["time_range"],
        "rca_status_decision",
        "rcca_agent.workflow.run / agent_common.contracts.result_status",
        [],
        {
            "analysis_status": analysis_status,
            "gate": gate,
            "gaps": gaps,
            "analysis_missing": analysis_missing,
            "available": sorted(available),
            "applicable_count": len(applicable),
            "relations_count": len(relations),
            "assessment_rule": "ready if not missing else partial if 'observations' in available or applicable or relations else blocked",
            "missing_rule": "missing = (runbook.required_evidence - available) | analysis_missing",
            "analysis_rule": "analysis_missing = synthesis_<status> if analysis_status not in {complete, skipped_alert_match}; add approved_runbook if not selected; add observation_<gate> if gate in {degraded, conflicted}; extend gaps",
            "result_rule": "exclude not_applicable; none => not_applicable; all ready => ready; any ready/partial => partial; otherwise blocked",
        },
        {
            "assessments": [
                {k: a[k] for k in ("assessment_id", "status", "missing_inputs")}
                for a in assessments
            ],
            "missing_inputs": result["missing_inputs"],
            "result_status": result["result_status"],
            "termination_reason": result["termination_reason"],
        },
        [collection_decision_id]
        + [e["id"] for e in obs.evidence if e["query_id"] == "rca_analysis_draft"],
    )
    result["evidence_refs"].append(status_decision_id)
    material_fields = (
        "cause_candidates",
        "recommendations",
        "limitations",
        "missing_inputs",
        "device_observations",
        "error_events",
        "facts",
        "measurements",
    )
    material = {key: result.get(key, []) for key in material_fields}
    material["evaluation"] = result["quality"]["rca_evaluation"]
    material["analysis"] = result["quality"]["analysis"]
    material["runbook_guidance"] = result["quality"]["runbook_guidance"]
    material["reported_observations"] = summarize_reports(health, error_events, data)
    material["investigation_summary"] = investigation_summary(
        data, obs.evidence, health, error_events
    )
    dossier_rows = (
        dossier_summary(
            data, [e for values in collected.values() for e in values], comparison
        )
        if dossier
        else []
    )
    material["investigation_summary"].extend(dossier_rows)
    history_rows = history_summary(result["quality"].get("host_incident_history"))
    material["investigation_summary"].extend(history_rows)
    material_hash = content_hash(material)
    frozen_id = obs._evidence(
        "rca_result_frozen",
        None,
        data["time_range"],
        {
            "analysis_id": evaluation["draft"]["analysis_id"],
            "material": material,
            "material_hash": material_hash,
            "decision_evidence_refs": [collection_decision_id, status_decision_id],
            "execution_status": "complete",
            "evidence_refs": evaluation["review"]["evidence_refs"]
            + evaluation["evidence"]["evidence_refs"],
        },
        "ok",
        {"execution_status": "complete"},
    )["id"]
    await write_report(result, data, clues, obs.evidence, ctx["llm"], material)
    if (
        content_hash(
            {
                **{key: result.get(key, []) for key in material_fields},
                "evaluation": result["quality"]["rca_evaluation"],
                "analysis": result["quality"]["analysis"],
                "runbook_guidance": result["quality"]["runbook_guidance"],
                "reported_observations": summarize_reports(health, error_events, data),
                "investigation_summary": investigation_summary(
                    data, obs.evidence, health, error_events
                )
                + dossier_rows
                + history_rows,
            }
        )
        != material_hash
    ):
        raise ValueError("report changed frozen RCA material")
    obs._evidence(
        "report_assembly",
        None,
        data["time_range"],
        {
            **result["quality"]["report"].get("writer", {}),
            "assembly_status": "complete",
            "analysis_id": evaluation["draft"]["analysis_id"],
            "stop_reason": final_stop,
            "report": result["quality"]["report"],
            "material_hash": material_hash,
            "evidence_refs": [frozen_id],
        },
        "ok",
        {
            **{
                k: v
                for k, v in result["quality"]["report"].get("writer", {}).items()
                if k
                in {
                    "execution_status",
                    "reason",
                    "started_at",
                    "completed_at",
                    "elapsed_seconds",
                    "model",
                    "usage",
                    "attempts",
                }
            },
            "assembly_status": "complete",
            "stop_reason": final_stop,
        },
    )
    result["evidence_refs"] = list(
        dict.fromkeys(result["evidence_refs"] + [frozen_id, obs.evidence[-1]["id"]])
    )
    result["llm_usage"] = ctx["llm"].usage
    return {"result": result, "evidence": obs.evidence}


def observation_hashes(collected):
    """Original source content, not evidence UUIDs, feedback or model view sampling."""
    hashes = set()
    for entries in collected.values():
        for entry in entries:
            raw = entry["snapshot"]
            rows = raw.get("data", raw) if isinstance(raw, dict) else raw
            rows = rows.get("result", rows) if isinstance(rows, dict) else rows
            if entry["tool_status"] not in {"ok", "partial"} or not rows:
                continue
            # Ignore collection wrappers; timestamps and labels remain source facts.
            for row in rows if isinstance(rows, list) else [rows]:
                hashes.add(
                    content_hash(
                        {
                            "cluster": entry.get("cluster_id"),
                            "scope": entry["scope"],
                            "time_range": entry["time_range"],
                            "source": row,
                        }
                    )
                )
    return hashes
