"""Versioned runbook authoring contract; no retrieval, IO or fact inference."""

from copy import deepcopy
from datetime import date
import json
import re
from urllib.parse import urlsplit

SCHEMA = "gpu-rca-runbook/1.0"
UNEXPECTED_EVENTS = {
    "unknown_value",
    "missing_evidence",
    "conflicting_evidence",
    "query_failed",
}


def unexpected_policy(content):
    """Old published revisions keep conservative defaults; never infer success."""
    return content.get(
        "unexpected_evidence",
        {
            "on": sorted(UNEXPECTED_EVENTS),
            "additional_queries": [],
            "fallback": "general_runbook",
        },
    )


CODE = re.compile(r"(?:xid|sxid):(0|[1-9][0-9]*)")
FACT_NAMES = {
    "producer_contract",
    "error_code",
    "incident_mapping",
    "observations",
    "incident_history",
    "topology",
    "current_mapping",
    "action_policy",
    "action_records",
    "device_recovery_evidence",
    "workload_evidence",
    "normalized_health",
    "component",
    "severity",
}
SCALAR_FACTS = {
    "producer_contract",
    "error_code",
    "normalized_health",
    "component",
    "severity",
}
COMPATIBILITY_TYPES = {
    "cluster_id": str,
    "producer_contract": str,
    "gpu_model": str,
    "driver_version": str,
    "dcgm_version": str,
    "fleet_version": str,
    "fabric_manager_version": str,
    "mig_enabled": bool,
    "nvswitch_present": bool,
}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _text(value, path):
    _require(isinstance(value, str) and bool(value.strip()), path + ": expected text")


def _strings(value, path, *, nonempty=False):
    _require(isinstance(value, list), path + ": expected list")
    for item in value:
        _text(item, path)
    _require(len(value) == len(set(value)), path + ": duplicate values")
    _require(not nonempty or bool(value), path + ": empty list")
    return value


def schema_kind(content):
    """Missing schema is legacy; an explicit unsupported schema fails closed."""
    _require(isinstance(content, dict), "content: expected object")
    if "schema" not in content:
        return "legacy"
    _require(content["schema"] == SCHEMA, "content.schema: unsupported schema")
    return "v1"


def _compatibility(requirements, *, allow_empty=False):
    _require(isinstance(requirements, dict), "compatibility: expected object")
    _require(allow_empty or bool(requirements), "compatibility: unbound draft")
    for key, expected in requirements.items():
        _require(key in COMPATIBILITY_TYPES, "compatibility: unsupported attribute")
        values = expected if isinstance(expected, list) else [expected]
        _require(bool(values), "compatibility: empty alternatives")
        for value in values:
            _require(
                type(value) is COMPATIBILITY_TYPES[key], "compatibility: wrong type"
            )
            if isinstance(value, str):
                _text(value, "compatibility." + key)
                _require(
                    not any(char in value for char in "*?<>~=^"),
                    "compatibility: exact values only",
                )


def compatibility_status(requirements, attributes):
    """Evaluate already scope/time/quality-validated attribute facts.

    The caller supplies {name: {status: 'known', value: scalar}}. Unknown facts
    keep the candidate pending; a known mismatch excludes it even if others
    are unknown. This function cannot establish provenance or freshness.
    """
    _compatibility(requirements)
    _require(isinstance(attributes, dict), "attributes: expected object")
    pending = False
    for key, expected in requirements.items():
        fact = attributes.get(key)
        if (
            not isinstance(fact, dict)
            or fact.get("status") != "known"
            or type(fact.get("value")) is not COMPATIBILITY_TYPES[key]
        ):
            pending = True
            continue
        values = expected if isinstance(expected, list) else [expected]
        if fact["value"] not in values:
            return "incompatible"
    return "pending" if pending else "compatible"


def _conditions(conditions, path, *, nonempty=False):
    _require(isinstance(conditions, list), path + ": expected list")
    _require(not nonempty or bool(conditions), path + ": empty conditions")
    for condition in conditions:
        _require(
            isinstance(condition, dict) and set(condition) == {"field", "equals"},
            path + ": only field/equals conditions are supported",
        )
        field = condition["field"]
        _require(
            isinstance(field, str) and field in SCALAR_FACTS,
            path + ": unsupported fact",
        )
        _text(condition["equals"], path + ".equals")
        if field == "error_code":
            _require(
                CODE.fullmatch(condition["equals"]), path + ": expected xid:N or sxid:N"
            )


def validate_runbook(row, queries, allowed_queries, *, authoring=False):
    """Validate v1 content and return an independent, ordered observation plan.

    authoring=True permits empty compatibility for unfinished drafts only.
    Publication/hash/scope validation and fact evaluation remain caller duties.
    """
    _require(isinstance(row, dict), "runbook: expected object")
    content = row.get("content")
    _require(schema_kind(content) == "v1", "content: v1 schema required")
    try:
        json.dumps(content, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("content: expected finite JSON values") from exc
    allowed_fields = {
        "schema",
        "title",
        "description",
        "claim",
        "classification",
        "search",
        "required_evidence",
        "applicability_conditions",
        "exclusion_conditions",
        "required_queries",
        "observation_plan",
        "recommendations",
        "sources",
        "analysis_guidance",
        "limitations",
        "investigation_only",
        "unexpected_evidence",
    }
    _require(set(content) <= allowed_fields, "content: unsupported fields")
    investigation_only = content.get("investigation_only", False)
    _require(type(investigation_only) is bool, "investigation_only: expected boolean")
    _compatibility(row.get("compatibility"), allow_empty=authoring)
    for field in ("title", "description", "claim"):
        _text(content.get(field), "content." + field)
    classification = content.get("classification")
    _require(
        isinstance(classification, dict)
        and set(classification) == {"domain", "category"},
        "classification: expected domain/category",
    )
    for value in classification.values():
        _text(value, "classification")
    search = content.get("search")
    _require(
        isinstance(search, dict)
        and set(search) <= {"codes", "producer_events", "aliases", "symptoms"},
        "search: unsupported fields",
    )
    for key, values in search.items():
        _strings(values, "search." + key)
    _require(any(search.values()), "search: at least one clue required")
    for code in search.get("codes", []):
        _require(CODE.fullmatch(code), "search.codes: expected xid:N or sxid:N")
    facts = _strings(
        content.get("required_evidence"), "required_evidence", nonempty=True
    )
    _require(set(facts) <= FACT_NAMES, "required_evidence: unsupported facts")
    _conditions(
        content.get("applicability_conditions"),
        "applicability_conditions",
        nonempty=not investigation_only,
    )
    _conditions(content.get("exclusion_conditions", []), "exclusion_conditions")
    recommendations = content.get("recommendations", [])
    _require(isinstance(recommendations, list), "recommendations: expected list")
    for recommendation in recommendations:
        _require(
            isinstance(recommendation, dict)
            and set(recommendation) <= {"text", "preconditions", "execution"},
            "recommendations: unsupported fields",
        )
        _text(recommendation.get("text"), "recommendations.text")
        _conditions(
            recommendation.get("preconditions"),
            "recommendations.preconditions",
            nonempty=True,
        )
        _require(
            recommendation.get("execution", "not_performed") == "not_performed",
            "recommendations: actions must remain not_performed",
        )
    for field in ("analysis_guidance", "limitations"):
        _strings(content.get(field, []), field)
    sources = content.get("sources")
    _require(
        isinstance(sources, list) and bool(sources), "sources: expected nonempty list"
    )
    for source in sources:
        _require(
            isinstance(source, dict)
            and set(source) == {"url", "revision", "section", "checked_at"},
            "sources: expected url/revision/section/checked_at",
        )
        for value in source.values():
            _text(value, "sources")
        url = urlsplit(source["url"])
        _require(
            url.scheme in ("https", "http")
            and bool(url.hostname)
            and url.username is None
            and url.password is None,
            "sources.url: expected public document URL",
        )
        _require(
            date.fromisoformat(source["checked_at"]).isoformat()
            == source["checked_at"],
            "sources.checked_at: expected ISO date",
        )
    _require(isinstance(queries, dict), "queries: expected registry object")
    _require(
        isinstance(allowed_queries, (list, tuple, set))
        and all(isinstance(item, str) for item in allowed_queries),
        "allowed_queries: expected query IDs",
    )
    allowed = set(allowed_queries)
    policy = unexpected_policy(content)
    _require(
        isinstance(policy, dict)
        and set(policy) == {"on", "additional_queries", "fallback"},
        "unexpected_evidence: invalid fields",
    )
    _require(
        set(_strings(policy["on"], "unexpected_evidence.on", nonempty=True))
        <= UNEXPECTED_EVENTS,
        "unexpected_evidence: unsupported event",
    )
    _require(
        set(
            _strings(
                policy["additional_queries"], "unexpected_evidence.additional_queries"
            )
        )
        <= set(queries) & allowed,
        "unexpected_evidence: unregistered query",
    )
    _require(
        policy["fallback"] in ("general_runbook", "stop"),
        "unexpected_evidence: unsupported fallback",
    )
    required = _strings(content.get("required_queries", []), "required_queries")
    plan = content.get("observation_plan")
    if plan is None:
        _require("observation_plan" not in content, "observation_plan: null is invalid")
        plan = [
            {
                "query_id": query,
                "priority": index + 1,
                "required": True,
                "fact_names": [],
                "purpose": "Runbook required observation",
                "binding": "execution_profile",
                "time_range": "incident",
                "freshness": "query_contract",
            }
            for index, query in enumerate(required)
        ]
    _require(isinstance(plan, list), "observation_plan: expected list")
    seen = set()
    for step in plan:
        _require(
            isinstance(step, dict)
            and set(step)
            == {
                "query_id",
                "priority",
                "required",
                "fact_names",
                "purpose",
                "binding",
                "time_range",
                "freshness",
            },
            "observation_plan: unsupported or missing fields",
        )
        query = step["query_id"]
        _text(query, "observation_plan.query_id")
        _require(
            query in queries and query in allowed,
            "observation_plan: unregistered or disallowed query",
        )
        _require(query not in seen, "observation_plan: duplicate query")
        seen.add(query)
        _require(
            type(step["priority"]) is int and step["priority"] > 0,
            "observation_plan: invalid priority",
        )
        _require(
            type(step["required"]) is bool, "observation_plan: required must be boolean"
        )
        _require(
            set(_strings(step["fact_names"], "fact_names")) <= FACT_NAMES,
            "fact_names: unsupported facts",
        )
        _text(step["purpose"], "observation_plan.purpose")
        for key, value in (
            ("binding", "execution_profile"),
            ("time_range", "incident"),
            ("freshness", "query_contract"),
        ):
            _require(
                step[key] == value, "observation_plan." + key + ": unsupported selector"
            )
    if "required_queries" in content:
        _require(
            set(required) == {step["query_id"] for step in plan if step["required"]},
            "required_queries: must match required observation_plan entries",
        )
    return deepcopy(sorted(plan, key=lambda step: (step["priority"], step["query_id"])))
