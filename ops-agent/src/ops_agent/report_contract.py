"""Versioned Ops-only report inputs; legacy reports keep their original path."""

from datetime import datetime, timezone

from agent_common.contracts import timestamp

VERSION = "report-aggregate-v1"
TOPICS = {"namespace_usage", "incident_summary"}
MAX_CLUSTERS = 4
MAX_NAMESPACES = 100
MAX_GPU_SERIES = 256
MAX_POINTS = 250_000
MAX_BYTES = 8 * 1024 * 1024
MAX_INCIDENTS = 2000


def aggregate_report(data):
    return bool(set(data.get("topic_ids", [])) & TOPICS)


def iso(value):
    return (
        datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    )


def previous_period(data):
    start, end = (timestamp(data["time_range"][key]) for key in ("start", "end"))
    return {"start": iso(start - (end - start)), "end": iso(start)}


def validate(data):
    topics = data["topic_ids"]
    if not topics or len(set(topics)) != len(topics) or not set(topics) <= TOPICS:
        raise ValueError("mixed_or_unknown_report_topics")
    start, end = (timestamp(data["time_range"][key]) for key in ("start", "end"))
    if (
        end - start not in (86400, 7 * 86400)
        or (start + 9 * 3600) % 86400
        or data.get("timezone") != "Asia/Seoul"
    ):
        raise ValueError("daily_or_weekly_kst_calendar_period_required")
    if any(
        key in data
        for key in ("comparison_range", "resource_selectors", "action_record_ids")
    ):
        raise ValueError("aggregate_report_uses_previous_equal_period")
    clusters = data["scope"]["clusters"]
    if len(clusters) > MAX_CLUSTERS or any(
        len(cluster.get("namespaces") or []) > MAX_NAMESPACES for cluster in clusters
    ):
        raise ValueError("report_scope_limit_exceeded")
    if set(data["group_by"]) != {"cluster", "namespace"}:
        raise ValueError("aggregate_report_group_by")
