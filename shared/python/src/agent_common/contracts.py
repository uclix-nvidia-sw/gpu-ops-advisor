from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.timestamp()


def go_json(value):
    """Go encoding/json map serialization, including its float64 number format."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        value = float(value)  # JC unmarshals body into map[string]any (float64).
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        if value == 0:
            return "0"
        s = repr(value).lower()
        if 1e-6 <= abs(value) < 1e21:
            from decimal import Decimal

            return (
                format(Decimal(s), "f").rstrip("0").rstrip(".")
                if "." in format(Decimal(s), "f")
                else format(Decimal(s), "f")
            )
        mantissa, exponent = s.split("e") if "e" in s else (s, "0")
        return (
            mantissa.removesuffix(".0")
            + "e"
            + ("+" if int(exponent) >= 0 else "-")
            + str(abs(int(exponent)))
        )
    if isinstance(value, str):
        return (
            json.dumps(value, ensure_ascii=False)
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )
    if isinstance(value, list):
        return "[" + ",".join(go_json(x) for x in value) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(go_json(k) + ":" + go_json(value[k]) for k in sorted(value))
            + "}"
        )
    raise ValueError("not JSON")


def content_hash(value):
    return hashlib.sha256(go_json(value).encode()).hexdigest()


def validate_input(kind, data):
    clusters = data["scope"]["clusters"]
    if not clusters or len({c["cluster_id"] for c in clusters}) != len(clusters):
        raise ValueError("invalid scope")
    for cluster in clusters:
        if not cluster["cluster_id"] or cluster.get("namespaces", []) == []:
            raise ValueError("invalid cluster/namespaces")
    start, end = (timestamp(data["time_range"][k]) for k in ("start", "end"))
    if start >= end:
        raise ValueError("invalid time range")
    if kind == "rca":
        UUID(data["incident_id"])
        if data["evidence_version"] < 1 or not data["analysis_profile_revision"]:
            raise ValueError("missing immutable revision")
        if not start <= timestamp(data["incident_time"]) <= end:
            raise ValueError("incident outside investigation period")
        ids, allowed = data["purpose_ids"], {f"R{i:02}" for i in range(1, 10)}
        snapshot = data["incident_snapshot"]
        if snapshot["input"] != {
            k: v for k, v in data.items() if k != "incident_snapshot"
        }:
            raise ValueError("incident snapshot mismatch")
    else:
        ZoneInfo(data["timezone"])
        ids, allowed = data["topic_ids"], {f"O{i:02}" for i in range(1, 12)}
        if not set(data["group_by"]) <= {
            "cluster",
            "namespace",
            "project",
            "node",
            "gpu",
            "pod",
            "model",
            "workload",
        }:
            raise ValueError("invalid group_by")
        if ("occurrence_id" in data) != ("schedule_revision" in data):
            raise ValueError("incomplete schedule snapshot")
        if "comparison_range" in data:
            if timestamp(data["comparison_range"]["start"]) >= timestamp(
                data["comparison_range"]["end"]
            ):
                raise ValueError("invalid comparison period")
    if not ids or len(set(ids)) != len(ids) or not set(ids) <= allowed:
        raise ValueError("invalid purpose/topic")


def result_status(items):
    statuses = [x["status"] for x in items if x["status"] != "not_applicable"]
    if not statuses:
        return "not_applicable"
    if all(x == "ready" for x in statuses):
        return "ready"
    return "partial" if any(x in ("ready", "partial") for x in statuses) else "blocked"


def base_result(claim, cutoff):
    data = claim["input"]
    return dict(
        job_id=claim["job_id"],
        kind=claim["kind"],
        scope=data["scope"],
        time_range=data["time_range"],
        timezone=data.get("timezone", "UTC"),
        data_cutoff_at=cutoff,
        result_schema_version="1.1",
        versions=claim["versions"],
        result_status="blocked",
        measurements=[],
        facts=[],
        evidence_refs=[],
        quality={},
        narrative_status="omitted",
        limitations=[],
    )


def metric(mid, value, unit, data, refs, method, reason=None, **extra):
    return dict(
        id=mid,
        value=value,
        value_type="number",
        unit=unit,
        target=data["scope"],
        period=data["time_range"],
        denominator=None,
        method=method,
        quality={"reason": reason} if value is None else {},
        evidence_refs=refs,
        **extra,
    )


def validate_result(result, evidence):
    content_hash(result)
    required = {
        "job_id",
        "kind",
        "scope",
        "time_range",
        "timezone",
        "data_cutoff_at",
        "result_schema_version",
        "versions",
        "result_status",
        "measurements",
        "facts",
        "evidence_refs",
        "quality",
        "narrative_status",
        "limitations",
    }
    if not required <= result.keys() or result["result_schema_version"] != "1.1":
        raise ValueError("invalid result schema")
    refs = {e["id"] for e in evidence}
    values = result["measurements"] + [
        m for t in result.get("topics", []) for m in t["metrics"]
    ]
    ids = {m["id"] for m in values}
    if len(ids) != len(values):
        raise ValueError("duplicate value id")
    for m in values:
        if m["value"] is None and not m["quality"].get("reason"):
            raise ValueError("null requires reason")
        if not {"unit", "period", "target", "method", "value_type"} <= m.keys():
            raise ValueError("invalid measurement")
        if m["value_type"] not in {"number", "integer", "ratio", "percentage"}:
            raise ValueError("invalid value type")
        if m["value"] is not None and (
            isinstance(m["value"], bool) or not isinstance(m["value"], (int, float))
        ):
            raise ValueError("measurement must be numeric or null")
        target = m["target"]
        allowed = {
            c["cluster_id"]: c["namespaces"] for c in result["scope"]["clusters"]
        }
        if isinstance(target, dict) and "cluster_id" in target:
            if target["cluster_id"] not in allowed:
                raise ValueError("measurement outside scope")
            namespaces = allowed[target["cluster_id"]]
            if (
                target.get("namespace") is not None
                and namespaces is not None
                and target["namespace"] not in namespaces
            ):
                raise ValueError("measurement outside namespace scope")

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if (
                    k in ("evidence_refs", "supporting_refs", "contradicting_refs")
                    and not set(v) <= refs
                ):
                    raise ValueError("unknown evidence")
                if k == "value_refs" and not set(v) <= ids:
                    raise ValueError("unknown value")
                walk(v)
            if obj.get("causal_status") == "confirmed" and not obj.get(
                "confirmation_rule_ref"
            ):
                raise ValueError("confirmation requires reviewed rule")
            if "eligibility" in obj and obj.get("execution") != "not_performed":
                raise ValueError("recommendation is not execution")
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(result)
    if result["kind"] == "rca":
        if (
            not {
                "incident_id",
                "incident_time",
                "current_checked_at",
                "pod_relations",
                "assessments",
                "cause_candidates",
                "recommendations",
                "missing_inputs",
                "termination_reason",
            }
            <= result.keys()
        ):
            raise ValueError("RCA fields required")
        if result["termination_reason"] not in {
            "evidence_sufficient",
            "missing_data",
            "conflicting_evidence",
            "unsupported_source",
            "budget_exhausted",
            "query_failed",
        }:
            raise ValueError("invalid termination reason")
    elif result["kind"] != "report" or "topics" not in result:
        raise ValueError("report topics required")
    items = result.get("topics", result.get("assessments", []))
    if any(
        i["status"] not in {"ready", "partial", "blocked", "not_applicable"}
        for i in items
    ):
        raise ValueError("invalid status")
    if result_status(items) != result["result_status"]:
        raise ValueError("aggregate status mismatch")
    if result["narrative_status"] not in {"complete", "failed", "omitted"}:
        raise ValueError("invalid narrative status")
