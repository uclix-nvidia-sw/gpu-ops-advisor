"""Collector rollover must not erase identity or hide overlapping sources."""

import asyncio
from copy import deepcopy
import time

import pytest

from test_aggregate_report import DATA, fixture
from test_workload_summary import jobs, build
from ops_agent.collector_identity import groups, series_for, verified
from ops_agent.identity_transitions import sample_bounds
from ops_agent.namespace_summary import summarize
from ops_agent.report_queries import ReportQueries


def rollover(job=False):
    evidence = jobs() if job else fixture()[1]
    at = evidence["snapshot"]["series"][0]["values"][0][0]
    originals = deepcopy(evidence["snapshot"]["series"])
    evidence["snapshot"]["series"] = []
    raw = []
    fields = {
        "created": "kube_job_created",
        "started": "kube_job_status_start_time",
        "completed": "kube_job_status_completion_time",
    }
    for source, first, last in (("old", 30 if job else 0, 120), ("new", 120, 240)):
        for series in originals:
            labels = {
                **series["metric"],
                "instance": source,
                "exporter_pod": "ksm-" + source,
            }
            if job:
                values = series["values"]
            else:
                values = [
                    [t, str(last - first) if t == at else v]
                    for t, v in series["values"]
                ]
                values = [v for v in values if source == "old" or v[0] == at]
            evidence["snapshot"]["series"].append({"metric": labels, "values": values})
            if not job or labels["measure"].endswith("_min"):
                metric = (
                    fields[labels["measure"].removesuffix("_min")]
                    if job
                    else "kube_pod_info"
                )
                value = float(values[0][1]) if job else 1
                raw.append(
                    {
                        "metric": {
                            **{k: v for k, v in labels.items() if k != "measure"},
                            "__name__": metric,
                        },
                        "values": [
                            [at - 3600 + i * 15 + 2, str(value)]
                            for i in range(first, last)
                        ],
                    }
                )
    return evidence, raw, at


def attach(evidence, raw, at):
    bounds = []
    for row in raw:
        b = sample_bounds([row], at, "cpc-1")[0]
        b["metric_name"] = row["metric"]["__name__"]
        bounds.append(b)
    evidence["quality"]["collector_handoffs"] = [
        dict(at=t, identity=key, bounds=bounds)
        for (t, key), rows in groups(evidence).items()
        if t == at and verified(t, rows, evidence["query_id"], bounds)
    ]


def test_same_uid_rollover_restores_hour_without_changing_other_hours_or_snapshot():
    e, raw, at = rollover()
    base = fixture()
    base[1] = e
    before = summarize(base, DATA["time_range"])[0][0]
    original = deepcopy(e["snapshot"])
    attach(e, raw, at)
    after = summarize(base, DATA["time_range"])[0][0]
    assert before["valid_hours"] == 23 and after["valid_hours"] == 24
    assert after["activity_percent"] == 60
    assert after["hours"][1:] == before["hours"][1:]
    assert e["snapshot"] == original


@pytest.mark.parametrize("job", [False, True])
@pytest.mark.parametrize(
    "problem",
    ["overlap", "gap", "uid_or_lifetime", "duplicate", "aggregate", "other_metadata"],
)
def test_unsafe_handoff_stays_excluded(job, problem):
    e, raw, at = rollover(job)
    half = len(raw) // 2
    if problem == "overlap":
        for row in raw[half:]:
            row["values"][0][0] = raw[0]["values"][-1][0]
    elif problem == "gap":
        for row in raw[half:]:
            del row["values"][:3]
    elif problem == "uid_or_lifetime":
        for row in raw[half:]:
            if job and row["metric"]["__name__"] == "kube_job_created":
                row["values"][0][1] = "1"
            elif not job:
                row["metric"]["uid"] = "different"
    elif problem == "duplicate":
        raw.append(deepcopy(raw[0]))
    elif problem == "aggregate":
        if job:
            raw[0]["values"][0][1] = "1"
        else:
            raw[0]["values"].pop()
    elif problem == "other_metadata":
        for row in raw[half:]:
            row["metric"]["unverified_source"] = "different"
    attach(e, raw, at)
    if job:
        assert build(e)[0]["topics"][0]["workloads"][0]["completed_observed"] is None
    else:
        base = fixture()
        base[1] = e
        assert summarize(base, DATA["time_range"])[0][0]["valid_hours"] == 23


def test_job_rollover_keeps_one_completion_and_unchanged_elapsed():
    e, raw, at = rollover(True)
    before = build(e)[0]["topics"][0]["workloads"][0]
    attach(e, raw, at)
    after = build(e)[0]["topics"][0]["workloads"][0]
    assert before["completed_observed"] is None
    assert after["completed_observed"] == 1 and after["mean_elapsed_seconds"] == 300


def test_recreated_job_stays_excluded_after_verified_collector_rollover():
    e, raw, at = rollover(True)
    attach(e, raw, at)
    for series in e["snapshot"]["series"]:
        if series["metric"]["instance"] == "new":
            series["values"].append(
                [at + 3600, str(float(series["values"][0][1]) + 3600)]
            )
    assert build(e)[0]["topics"][0]["workloads"][0]["completed_observed"] is None


@pytest.mark.parametrize("job", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_bounded_collector_verifies_raw_source_times_and_keeps_only_bounds(
    job, failure
):
    e, raw, at = rollover(job)
    calls = []

    async def query(args):
        calls.append(args)
        assert args["queryType"] == "instant" and "[1h] offset 1ms" in args["expr"]
        if failure:
            raise RuntimeError("private upstream details")
        return {"data": {"result": raw}}

    c = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 60)
    asyncio.run(
        c.check_collectors(
            DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", [e]
        )
    )
    assert len(calls) == 1
    assert bool(e["quality"].get("collector_handoffs")) is not failure
    assert "private" not in str(e["quality"])
    for check in e["quality"].get("collector_handoffs", []):
        assert all(
            isinstance(b["values"], dict) and "points" not in b for b in check["bounds"]
        )
    c.collector_calls = 4
    asyncio.run(
        c.check_collectors(
            DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", [e]
        )
    )
    assert len(calls) == 1


def test_original_duplicate_timestamp_rejection_is_preserved():
    base = fixture()
    row = base[1]["snapshot"]["series"][0]
    row["values"].append(deepcopy(row["values"][0]))
    with pytest.raises(ValueError, match="invalid_aggregate_time"):
        summarize(base, DATA["time_range"])


def test_collector_deadline_does_not_trigger_optional_raw_reads():
    e, _, _ = rollover()

    async def query(args):
        raise AssertionError("The expired optional budget must not query")

    collector = ReportQueries({"query_prometheus": query}, DATA, time.monotonic() + 10)
    asyncio.run(
        collector.check_collectors(
            DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", [e]
        )
    )
    assert collector.calls == 0
    assert not e["quality"].get("collector_handoffs")


def test_unchanged_identity_keeps_hours_in_one_compact_series():
    e = fixture()[1]
    rows = series_for(e)
    assert len(rows) == len(e["snapshot"]["series"]) == 1
    assert len(rows[0]["values"]) == 24
