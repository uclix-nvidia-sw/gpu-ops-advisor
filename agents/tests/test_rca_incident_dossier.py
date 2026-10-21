"""Synthetic RCA comparisons and complete workflow; no live service calls."""

from copy import deepcopy
import json

import pytest

from agent_common.contracts import content_hash, timestamp
from agent_common.observation import series
from rcca_agent.incident_dossier import (
    ERROR_FILTER,
    current_data,
    dossier_summary,
    log_records,
    operator_view,
    same_device,
)
from rcca_agent.synthesis_context import bounded_context, encoded_size
from rca_replay import replay
from rca_replay_cases import ROOT
from test_fleet_rca import match_case


def dossier_case(kind):
    case = match_case(kind=kind)
    book = case["attempt"]["context"]["runbooks"][0]
    book["content"] = json.loads(
        (ROOT / f"rcca-agent/runbooks/{kind}/{book['knowledge_key']}.json").read_text(
            "utf-8"
        )
    )["content"]
    book["content_hash"] = book["reviewed_content_hash"] = content_hash(book["content"])
    profile = case["attempt"]["profile"]
    for query in book["content"]["required_queries"]:
        if query not in profile["queries"]:
            profile["queries"][query] = deepcopy(profile["queries"]["D44"])
            profile["queries"][query]["metric"] = "fixture_" + query
    data = case["attempt"]["claim"]["input"]
    data["log_query_target"] = {"node": "node-1", "machine_id": "machine-1"}
    period = current_data(data, case["attempt"]["context"]["data_cutoff_at"])[
        "time_range"
    ]
    query = case["queries"][0]
    query["arguments"].update(
        logql='{} | drop dsx_json_0, dsx_json_0_extracted | json dsx_json_0="resources[\\"k8s.node.name\\"]" | __error__="" | (dsx_json_0="node-1" or dsx_json_0_extracted="node-1")'
        + ERROR_FILTER,
        startRfc3339=period["start"],
        endRfc3339=period["end"],
    )
    return case


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_workflow_collects_metrics_despite_matching_alert_and_no_model_budget(
    kind,
):
    case = dossier_case(kind)
    case["token_budget"] = 0
    result = await replay(case)
    assert not result["missing_inputs"]
    assert "decision_policy" not in case["attempt"]["context"]["runbooks"][0]["content"]
    calls = result["query_calls"]
    logs = [c for c in calls if c["tool"] == "query_loki_logs"]
    assert len(logs) == 1
    assert any(c["matched"] for c in logs), logs
    expected = case["attempt"]["context"]["runbooks"][0]["content"]["required_queries"]
    evidence = result["output"]["evidence"]
    assert set(expected) <= {e["query_id"] for e in evidence}
    source = result["output"]["result"]["quality"]["report"]["source_items"]
    assert any("이번 조회 범위" in s["text"] for s in source)
    assert any("원문 발췌" in s["text"] for s in source)
    assert len(calls) <= case["attempt"]["profile"]["limits"]["max_queries"]
    assert not series([e for e in evidence if e["quality"].get("comparison_role")])


def records_fixture(kind="xid"):
    case = dossier_case(kind)
    query = case["queries"][0]
    data = deepcopy(case["attempt"]["claim"]["input"])
    data["time_range"] = {
        "start": query["arguments"]["startRfc3339"],
        "end": query["arguments"]["endRfc3339"],
    }
    e = dict(
        id="logs",
        query_id="D09",
        cluster_id="c",
        time_range=data["time_range"],
        quality={"complete": True},
        tool_status="ok",
        snapshot=query["response"],
    )
    return data, e


def test_repeated_reports_preserve_raw_and_do_not_count_failures_or_reboots():
    data, e = records_fixture()
    values = e["snapshot"]["data"]["result"][0]["values"]
    repeated = deepcopy(values[-1])
    repeated[0] = str(int(repeated[0]) + 10**9)
    values.append(repeated)
    before = deepcopy(e)
    rows = log_records([e], data)
    assert len(rows) == 3
    text = str(dossier_summary(data, [e], {}))
    assert "보고 2건 수신" in text and "별개 신규 장애 횟수로 세지 않습니다" in text
    assert e == before
    other = deepcopy(rows[0])
    other["gpu"] = "replacement-gpu"
    assert not same_device(rows[0], other)
    other = deepcopy(rows[0])
    other["machine"] = "other-machine"
    assert not same_device(rows[0], other)


@pytest.mark.parametrize("change", ["node", "time", "component", "incomplete"])
def test_invalid_scope_and_incomplete_sources_cannot_support_history(change):
    data, e = records_fixture()
    if change == "node":
        data["target"]["node"] = "other"
    elif change == "time":
        e["time_range"] = {
            "start": "2020-01-01T00:00:00Z",
            "end": "2020-01-01T00:30:00Z",
        }
    elif change == "component":
        e["snapshot"] = json.loads(
            json.dumps(e["snapshot"]).replace(
                "accelerator-nvidia-error-xid", "unknown-producer"
            )
        )
    else:
        e["quality"]["complete"] = False
        e["tool_status"] = "partial"
    assert log_records([e], data) == []


def test_sxid_identity_preserves_switch_function_without_gpu_mapping():
    data, e = records_fixture("sxid")
    row = log_records([e], data)[0]
    assert row["gpu"] is None
    other = {**row, "device": row["device"][:-1] + "1"}
    assert not same_device(row, other)


def test_large_comparison_is_bounded_only_in_model_view():
    payload = {
        "incident_comparison": [
            {"text": "보고 내용 " * 300, "evidence_refs": [f"e{i}"]} for i in range(100)
        ]
    }
    view = bounded_context(payload, 8000)
    assert encoded_size(view) <= 8000
    assert view["context_selection"]["omitted_observations"]["incident_comparison"] > 0
    assert len(payload["incident_comparison"]) == 100


def test_metric_comparison_keeps_scope_gaps_and_counter_semantics():
    data, logs = records_fixture()
    target = log_records([logs], data)[0]
    at = timestamp(data["time_range"]["end"]) - 100
    metric = dict(
        id="replay",
        query_id="D44",
        cluster_id="c",
        time_range=data["time_range"],
        tool_status="ok",
        quality={"complete": True, "original_samples": True, "unit": "count"},
        snapshot={
            "data": {
                "result": [
                    {
                        "metric": {"node": "node-1", "uuid": target["gpu"]},
                        "values": [[at, "2"], [at + 60, "4"], [at + 65, "NaN"]],
                    }
                ]
            }
        },
    )
    data["target"]["machine_id"] = target["machine"]
    comparison = {"targets": [target]}
    view = operator_view(data, [logs, metric], comparison)
    assert view["metrics"][0]["max"] == 4
    text = str(dossier_summary(data, [logs, metric], comparison))
    assert "최소 2, 최대 4 count" in text
    assert "최대 간격 60초" in text
    assert "사건 증가량이나 AER로 해석하지 않습니다" in text
    metric["snapshot"]["data"]["result"][0]["metric"]["node"] = "other-node"
    text = str(dossier_summary(data, [logs, metric], comparison))
    assert "최소 2" not in text
    assert "측정 기록을 확보하지 못했습니다" in text
