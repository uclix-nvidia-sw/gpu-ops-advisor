"""Shared logical-query/binding contract for RCA and Report.

Legacy profiles remain literal, pinned profiles. New profiles never resolve retired
IDs, infer producer equivalence, or execute reference.legacy_definition values.
"""

from copy import deepcopy
import math
import re

from .contracts import timestamp

CONTRACT = "single-query-v3-draft"
LABEL = r"[a-zA-Z_][a-zA-Z0-9_]*"
METRIC = r"[a-zA-Z_:][a-zA-Z0-9_:]*"
BASE_UNITS = {
    "D02": "percent",
    "D03": "MiB",
    "D04": "celsius",
    "D06": "info",
    "D07": "resource_units",
    "D10": "boolean",
    "D11": "W",
    "D12": "resource_units",
}


def consolidated(profile):
    return (profile or {}).get("query_contract") == CONTRACT


def inventory_query(profile):
    return "D02" if consolidated(profile) else "D01"


def mapping_query(profile):
    return "D02" if consolidated(profile) else "D08"


def _require(condition, message):
    if not condition:
        raise ValueError("query binding: " + message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def scope_label_names(environment):
    value = environment["scope_labels"]["cluster_id"]
    return [value] if isinstance(value, str) else value


def _labels(value, *, nonempty=False):
    return (
        isinstance(value, dict)
        and (bool(value) or not nonempty)
        and all(
            isinstance(k, str) and re.fullmatch(LABEL, k) and _text(v)
            for k, v in value.items()
        )
    )


def _verified(binding, query):
    for key in ("producer_version", "revision", "unit", "timestamp_basis"):
        _require(_text(binding.get(key)) and binding[key] != "unknown", key)
    environment = binding.get("environment", {})
    _require(isinstance(environment, dict), "environment")
    parameterized = "scope_labels" in environment
    if not parameterized:
        _require(_text(environment.get("cluster_id")), "cluster_id")
    if environment.get("datasource_mode", "pinned") == "pinned":
        _require(_text(environment.get("datasource_uid")), "datasource_uid")
    _require(
        _labels(environment.get("selector"), nonempty=not parameterized), "selector"
    )
    labels = binding.get("target_labels")
    raw_context = (
        binding.get("observation_semantics", {}).get("evidence_role")
        == "raw_log_context"
    )
    if raw_context:
        _require(
            binding["query_id"] == "D13"
            and binding["source"] == "loki"
            and binding.get("health_contract") is None
            and binding["observation_semantics"].get("workload_fact_eligible") is False
            and binding["observation_semantics"].get("health_fact_eligible") is False,
            "raw log context cannot promote facts",
        )
    _require(_labels(labels, nonempty=not raw_context), "target_labels")
    _require(all(re.fullmatch(LABEL, v) for v in labels.values()), "target label name")
    verification = binding["verification"]
    if parameterized:
        _require(
            _text(verification.get("applicability")),
            "shared source contract applicability",
        )
        _require(
            not set(scope_label_names(environment)) & set(labels.values()),
            "scope label cannot be a target label",
        )
    refs = verification.get("evidence_refs")
    _require(
        isinstance(refs, list) and bool(refs) and all(_text(r) for r in refs),
        "evidence_refs",
    )
    _require(_text(verification.get("retention_evidence")), "retention_evidence")
    window = verification.get("observed_window") or {}
    try:
        valid_window = timestamp(window["start"]) < timestamp(window["end"])
    except (KeyError, ValueError, TypeError, AttributeError):
        valid_window = False
    _require(valid_window, "observed_window")
    hold = binding.get("max_hold") or {}
    _require(isinstance(hold, dict), "max_hold")
    _require(_number(hold.get("seconds")) and hold["seconds"] >= 0, "max_hold.seconds")
    interval = binding.get("sample_interval") or {}
    invalid = binding.get("invalid_values") or {}
    reset = binding.get("counter_reset") or {}
    _require(
        all(isinstance(rule, dict) for rule in (interval, invalid, reset)),
        "sample rules",
    )
    if binding["source"] == "mimir":
        _require(
            binding["timestamp_basis"] == "prometheus_sample",
            "unsupported metric timestamp_basis",
        )
        _require(
            _number(interval.get("seconds")) and interval["seconds"] > 0,
            "sample_interval.seconds",
        )
        _require(
            binding.get("sample_type")
            in {"gauge", "counter", "info", "enum", "bitmask"},
            "sample_type",
        )
        _require(
            isinstance(invalid.get("sentinels"), list)
            and all(_number(v) for v in invalid["sentinels"]),
            "invalid_values.sentinels",
        )
        for key in ("minimum", "maximum"):
            _require(
                key in invalid and (invalid[key] is None or _number(invalid[key])),
                "invalid_values." + key,
            )
        _require(
            invalid["minimum"] is None
            or invalid["maximum"] is None
            or invalid["minimum"] <= invalid["maximum"],
            "invalid value range",
        )
        if binding["sample_type"] == "counter":
            _require(
                reset.get("mode") == "reject_decrease", "unsupported counter reset rule"
            )
        else:
            _require(
                reset.get("mode") == "not_applicable" and _text(reset.get("reason")),
                "counter_reset applicability",
            )
    else:
        _require(
            binding.get("sample_type") == "log" and binding["unit"] == "log",
            "log type/unit",
        )
        _require(
            binding["timestamp_basis"] == "loki_recorded_at"
            and binding.get("event_timestamp_rule") == "loki_recorded_at",
            "unsupported log timestamp rule",
        )
        _require(_labels(binding.get("json_target_fields")), "json_target_fields")
        for rule in (interval, invalid, reset):
            _require(
                rule.get("mode") == "not_applicable" and _text(rule.get("reason")),
                "log rule applicability",
            )
    scope = query["scope_kind"]
    required_labels = {
        "G": {"gpu_uuid", "node"},
        "N": {"node"},
        "P": {"namespace", "pod", "node", "uid"},
        "T": {"scrape_target"},
        "L": {"node"},
    }[scope]
    if raw_context:
        required_labels = set()
    _require(required_labels <= labels.keys(), "scope entity labels")
    # These dimensions are consumed by O01 and must survive producer mapping.
    # Fleet calls the load window load_duration; KSM splits condition/status.
    dimensions = {
        "D19": {"window"},
        "D20": {"condition", "status"},
    }.get(binding["query_id"], set())
    _require(dimensions <= labels.keys(), "consumer dimension labels")
    _require(
        len({labels[key] for key in required_labels | dimensions})
        == len(required_labels | dimensions),
        "distinct entity and dimension labels",
    )
    expected = BASE_UNITS.get(binding["query_id"])
    _require(not expected or binding["unit"] == expected, "base consumer unit mismatch")
    if binding["query_id"] in BASE_UNITS:
        _require(
            binding["sample_type"] in {"gauge", "info"},
            "base consumer sample type mismatch",
        )


def validate_profile(profile):
    _require(isinstance(profile, dict), "profile object")
    contract = profile.get("query_contract")
    if contract is None:
        _require(
            "bindings" not in profile, "binding profile must declare query_contract"
        )
        return profile
    _require(contract == CONTRACT, "unsupported query contract")
    _require(
        type(profile.get("auto_select_verified_bindings", False)) is bool,
        "auto_select_verified_bindings must be boolean",
    )
    _require(
        profile.get("schema_version") == "d-query-profile/3-draft", "schema_version"
    )
    queries, bindings = profile.get("queries"), profile.get("bindings")
    _require(
        isinstance(queries, dict) and isinstance(bindings, dict), "registries required"
    )
    _require(
        not {"D01", "D05", "D08", "D14"} & queries.keys(),
        "retired or DB query in new default registry",
    )
    _require(all(isinstance(b, dict) for b in bindings.values()), "binding objects")
    producers = profile.get("producers")
    clusters = profile.get("clusters", {})
    _require(
        isinstance(producers, dict)
        and all(isinstance(p, dict) for p in producers.values()),
        "producer registry",
    )
    _require(isinstance(clusters, dict), "cluster registry")
    for cluster in clusters.values():
        _require(
            isinstance(cluster, dict) and isinstance(cluster.get("bindings", {}), dict),
            "cluster binding map",
        )
    for query_id, query in queries.items():
        _require(isinstance(query_id, str) and isinstance(query, dict), "query object")
        _require(
            re.fullmatch(r"D\d{2,}", query_id) and _text(query.get("revision")),
            "query identity/revision",
        )
        _require(query.get("scope_kind") in {"G", "N", "P", "T", "L"}, "scope_kind")
        _require(query.get("kind") in {"metric", "log"}, "query kind")
        _require(
            not {"metric", "source", "derived_from"} & query.keys(),
            "logical query must use binding",
        )
        candidates = query.get("binding_candidates")
        _require(
            isinstance(candidates, list)
            and bool(candidates)
            and all(isinstance(b, str) for b in candidates),
            "binding_candidates",
        )
        _require(len(candidates) == len(set(candidates)), "duplicate binding candidate")
        for binding_id in candidates:
            _require(
                binding_id in bindings
                and bindings[binding_id].get("query_id") == query_id,
                "binding reference",
            )
        selections = [query.get("selected_binding")]
        for cluster in profile.get("clusters", {}).values():
            _require(
                isinstance(cluster, dict)
                and set(cluster.get("bindings", {})) <= queries.keys(),
                "cluster binding map",
            )
            selections.append(cluster.get("bindings", {}).get(query_id))
        for selected in selections:
            _require(
                selected is None
                or isinstance(selected, str)
                and selected in candidates,
                "selected_binding",
            )
            if selected:
                _require(
                    (bindings[selected].get("verification") or {}).get("status")
                    == "verified",
                    "selected binding must be verified",
                )
                if selected != candidates[0]:
                    refs = bindings[selected].get("equivalence_evidence_refs")
                    _require(
                        isinstance(refs, list)
                        and bool(refs)
                        and all(_text(r) for r in refs),
                        "alternative binding requires equivalence evidence",
                    )
    for binding_id, binding in bindings.items():
        environment = binding.get("environment") or {}
        _require(isinstance(environment, dict), "environment")
        mode = environment.get("datasource_mode", "pinned")
        _require(mode in ("pinned", "discover"), "datasource_mode")
        if mode == "discover":
            _require(
                "scope_labels" in environment, "discovery requires parameter scope"
            )
            _require(
                environment.get("datasource_uid") is None,
                "discovery cannot also pin datasource_uid",
            )
        if "scope_labels" in environment:
            scope_labels = environment["scope_labels"]
            _require(
                isinstance(scope_labels, dict) and set(scope_labels) == {"cluster_id"},
                "scope_labels must map cluster_id",
            )
            labels = scope_label_names(environment)
            _require(
                isinstance(labels, list)
                and 1 <= len(labels) <= 8
                and all(isinstance(v, str) and re.fullmatch(LABEL, v) for v in labels)
                and len(set(labels)) == len(labels),
                "scope label candidates must be distinct valid labels",
            )
            _require(
                isinstance(scope_labels["cluster_id"], str) or mode == "discover",
                "label candidates require datasource discovery",
            )
            _require(
                "cluster_id" not in environment, "mixed literal and parameter scope"
            )
            _require(_labels(environment.get("selector")), "selector")
            _require(
                not set(labels) & set(environment["selector"]),
                "static selector conflicts with scope label",
            )
        query_id = binding.get("query_id")
        _require(
            query_id in queries
            and binding_id in queries[query_id]["binding_candidates"],
            "orphan binding",
        )
        producer = profile.get("producers", {}).get(binding.get("producer"), {})
        _require(
            binding.get("source") in producer.get("sources", []), "producer source"
        )
        _require(_text(binding.get("revision")), "binding revision")
        _require(
            isinstance(binding.get("verification"), dict)
            and binding["verification"].get("status") in {"candidate", "verified"},
            "verification status",
        )
        _require("derived_from" not in binding, "derived bindings unsupported")
        if queries[query_id]["kind"] == "metric":
            _require(
                binding["source"] == "mimir"
                and isinstance(binding.get("metric"), str)
                and re.fullmatch(METRIC, binding["metric"]),
                "single metric required",
            )
        else:
            _require(
                binding["source"] == "loki" and binding.get("metric") is None,
                "log source",
            )
        if binding["verification"]["status"] == "verified":
            _verified(binding, queries[query_id])
    return profile


def query_definition(profile, query_id, cluster_id=None):
    """Resolve one environment binding, without mutating or flattening the profile."""
    query = profile["queries"].get(query_id, {})
    if not consolidated(profile):
        return query
    cluster_selections = (
        profile.get("clusters", {})
        .get(cluster_id if isinstance(cluster_id, str) else None, {})
        .get("bindings", {})
    )
    selected = cluster_selections.get(query_id, query.get("selected_binding"))
    definition = {
        "revision": query.get("revision", "unconfigured"),
        "scope_kind": query.get("scope_kind"),
        "availability": "unavailable",
        "reason": "binding_unselected",
    }
    if (
        not selected
        and query_id not in cluster_selections
        and profile.get("auto_select_verified_bindings", False)
    ):
        candidates = query.get("binding_candidates", [])
        eligible = [
            bid
            for bid in candidates
            if profile["bindings"][bid]["verification"]["status"] == "verified"
            and "scope_labels" in profile["bindings"][bid]["environment"]
            and (
                bid == candidates[0]
                or (
                    isinstance(
                        profile["bindings"][bid].get("equivalence_evidence_refs"), list
                    )
                    and bool(profile["bindings"][bid]["equivalence_evidence_refs"])
                    and all(
                        _text(ref)
                        for ref in profile["bindings"][bid]["equivalence_evidence_refs"]
                    )
                )
            )
        ]
        if len(eligible) == 1:
            selected = eligible[0]
            definition["selection_method"] = "automatic_verified"
        elif len(eligible) > 1:
            return {**definition, "selection_reason": "multiple_verified_candidates"}
    if not selected:
        return definition
    definition.setdefault("selection_method", "explicit")
    binding = profile["bindings"][selected]
    definition.update(
        binding_id=selected,
        binding_revision=binding["revision"],
        producer=binding["producer"],
        producer_version=binding["producer_version"],
    )
    if binding["verification"]["status"] != "verified":
        return {**definition, "reason": "binding_unverified"}
    environment = binding["environment"]
    if "scope_labels" in environment and not _text(cluster_id):
        return {**definition, "reason": "binding_scope_unavailable"}
    if (
        "scope_labels" not in environment
        and cluster_id is not None
        and environment["cluster_id"] != cluster_id
    ):
        return {**definition, "reason": "binding_environment_mismatch"}
    resolved = deepcopy(binding)
    if "scope_labels" in environment:
        label = environment["scope_labels"]["cluster_id"]
        if isinstance(label, str):
            resolved["environment"]["selector"][label] = cluster_id
        resolved["environment"]["cluster_id"] = cluster_id
    resolved.update(definition)
    resolved.update(
        availability="verified",
        reason=None,
        max_hold_seconds=binding["max_hold"]["seconds"],
        allocation_semantics="observed_pod_labels" if query_id == "D02" else None,
    )
    return resolved


def query_facts(query_id):
    if query_id == "D09":
        return {
            "observations",
            "reported_error_code",
            "reported_producer_contract",
            "producer_contract",
            "error_code",
            "normalized_health",
            "component",
            "severity",
        }
    return {"observations"}
