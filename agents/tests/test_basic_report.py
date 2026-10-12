"""Criteria 1.3 uses observations, not exclusive allocation or idle claims."""

import copy
import csv
import io
from datetime import datetime

import pytest

from agent_common.artifacts import render
from agent_common.contracts import go_json
from ops_agent.activity_trends import activity_trends
from ops_agent.workflow import calculate, query_ids
from test_binding_contract import profile
from test_namespace_usage import observations
from test_report_observation import DATA, START, END, evidence, row


def test_default_selection_omits_unrequested_queries():
    config = profile(active_defaults=True)
    queries = {
        q for t in ("O01", "O08", "O11") for q in query_ids(t, "1.3", profile=config)
    }
    assert queries == {
        "D02",
        "D03",
        "D04",
        "D06",
        "D10",
        "D16",
        "D20",
        "D22",
    }
    assert not queries & {"D07", "D09", "D11", "D12", "D13", "D21"}


def test_hourly_peak_is_concurrent_not_distinct_and_low_spans_cross_hours():
    rows = [
        dict(start=1800, end=3600, gpu_uuid="one"),
        dict(start=3600, end=5400, gpu_uuid="two"),
    ]
    out = activity_trends(
        rows, [(1800, 3600, "one", "A", 0), (3600, 5400, "two", "A", 100)], 1800, 5400
    )
    assert [h["peak_gpu_count"] for h in out["hourly"]] == [1, 1]
    assert out["model_means"][0]["mean"] == 50
    replacements = [
        dict(start=0, end=900, gpu_uuid="one"),
        dict(start=900, end=1800, gpu_uuid="two"),
    ]
    assert (
        activity_trends(replacements, [], 0, 3600)["hourly"][0]["peak_gpu_count"] == 1
    )
    same_hour = activity_trends(rows, [], 0, 7200)
    assert len(same_hour["hourly"]) == 2
    continuous = activity_trends(
        [dict(start=2700, end=4500, gpu_uuid="one")],
        [(2700, 3600, "one", "A", 0), (3600, 4500, "one", "A", 4)],
        0,
        7200,
    )
    assert continuous["low_windows"][0]["seconds"] == 1800
    assert len(continuous["low_windows"]) == 1
    gaps = activity_trends(
        [], [(0, 900, "one", "A", 0), (901, 1801, "one", "A", 0)], 0, 3600
    )
    assert gaps["low_windows"] == []
    assert gaps["hourly"][0]["peak_gpu_count"] is None
    mixed = activity_trends(
        rows, [(1800, 3600, "one", "A", 0), (3600, 5400, "two", "B", 100)], 1800, 5400
    )
    assert [m["mean"] for m in mixed["model_means"]] == [0, 100]


def test_namespace_new_version_preserves_legacy_and_missing_is_not_zero():
    source = observations(("a", "gpu-1", START, END, 0))
    data = dict(DATA, group_by=["namespace"])
    old = calculate("O08", data, source, {}, {}, criteria_version="1.2")
    new = calculate("O08", data, source, {}, {}, criteria_version="1.3")
    assert not any("hourly_" in m["id"] for m in old["metrics"])
    lows = [m for m in new["metrics"] if "observed_low_activity_seconds" in m["id"]]
    assert len(lows) == 1 and lows[0]["value"] == 3600
    assert lows[0]["period"] == data["time_range"]
    broken = copy.deepcopy(source)
    broken["D02"][0]["tool_status"] = "unavailable"
    missing = calculate("O08", data, broken, {}, {}, criteria_version="1.3")
    assert not any(
        "observed_low_activity_seconds" in m["id"] for m in missing["metrics"]
    )
    hourly = [m for m in missing["metrics"] if "hourly_gpu_activity" in m["id"]]
    assert hourly and all(m["value"] is None for m in hourly)
    go_json(new)
    assert len({m["id"] for m in new["metrics"]}) == len(new["metrics"])


def test_hourly_activity_keeps_missing_hours_for_each_observed_model():
    data = dict(DATA, group_by=["namespace"])
    data["time_range"] = {
        "start": "2026-09-18T00:00:00Z",
        "end": "2026-09-18T04:00:00Z",
    }
    start = datetime.fromisoformat(
        data["time_range"]["start"].replace("Z", "+00:00")
    ).timestamp()
    source = observations(
        ("a", "gpu-1", start, start + 3600, 0),
        ("a", "gpu-1", start + 3 * 3600, start + 4 * 3600, 50),
    )
    topic = calculate("O08", data, source, {}, {}, criteria_version="1.3")
    hourly = [m for m in topic["metrics"] if "hourly_gpu_activity" in m["id"]]
    assert [m["value"] for m in hourly] == [0, None, None, 50]
    assert len({m["target"]["model"] for m in hourly}) == 1
    assert hourly[0]["target"]["model"] is not None


def test_snapshot_is_recorded_point_and_monitoring_distinguishes_down_unknown():
    snapshot = evidence("D04", [row({"gpu_uuid": "gpu-1"}, "43", START, START)])
    snapshot["quality"].update(
        unit="celsius", sample_type="gauge", max_hold_seconds=0, complete=True
    )
    topic = calculate("O01", DATA, {"D04": [snapshot]}, {}, {}, criteria_version="1.3")
    point = next(m for m in topic["metrics"] if "recorded_temperature" in m["id"])
    assert point["value"] == 43 and point["period"] == {
        "at": DATA["time_range"]["start"]
    }
    assert point["quality"]["measurement_time_verified"] is False
    up = evidence(
        "D10",
        [
            dict(
                metric={"job": "scrape", "instance": "one"},
                values=[[START, "1"], [START + 15, "0"]],
            )
        ],
    )
    up["quality"].update(unit="state", sample_type="gauge", max_hold_seconds=15)
    topic = calculate("O11", DATA, {"D10": [up]}, {}, {}, criteria_version="1.3")
    values = {m["id"].split(".")[1]: m["value"] for m in topic["metrics"]}
    assert values["target_up_seconds"] == 15
    assert values["target_down_seconds"] == 15
    assert values["target_unknown_seconds"] == pytest.approx(END - START - 30)
    assert values["total_coverage"] is None


def test_new_csv_contains_target_and_time_without_changing_legacy():
    topic = calculate(
        "O08",
        dict(DATA, group_by=["namespace"]),
        observations(("a", "gpu-1", START, END, 0)),
        {},
        {},
        criteria_version="1.3",
    )
    result = dict(
        versions={"criteria": "1.3"},
        measurements=[],
        topics=[topic],
        quality={},
        result_status="partial",
        limitations=[],
    )
    output = render(result)
    reader = csv.DictReader(io.StringIO(output["csv"].decode("utf-8-sig")))
    assert "period" in reader.fieldnames and "target" in reader.fieldnames
    assert len(list(reader)) == len(topic["metrics"])
    result["versions"]["criteria"] = "1.2"
    assert "period" not in next(
        csv.reader(io.StringIO(render(result)["csv"].decode("utf-8-sig")))
    )
