"""Prune only unused or conditionally unnecessary Ops observations."""

import copy
import time
from types import SimpleNamespace

import pytest

from agent_common.runtime import attempt_context
from ops_agent import workflow
from ops_agent.collection import collection_plan, report_profile
from test_report_collection import setup, source
from test_report_observation import DATA, collected, evidence, row
from test_worker import claim


def values(topic):
    return [
        (m["id"], m["target"], m["value"], m["unit"], m["method"])
        for m in topic["metrics"]
    ]


def test_inventory_does_not_depend_on_pod_history_but_other_topics_still_do(
    monkeypatch,
):
    observed = collected()
    observed["D01"][0]["snapshot"]["data"][0]["metric"]["gpu_uuid"] = "GPU-1"
    observed["D03"] = [evidence("D03", [row({"uuid": "GPU-1"}, "1024")])]
    observed["D03"][0]["quality"]["unit"] = "MiB"
    observed["D04"] = [evidence("D04", [row({"uuid": "GPU-1"}, "45")])]
    observed["D04"][0]["quality"]["unit"] = "celsius"
    current = workflow.calculate("O01", DATA, observed, {}, {})
    with monkeypatch.context() as previous:
        previous.setitem(workflow.PLAN, "O01", ("D01", "D03", "D04", "D06"))
        original = workflow.calculate("O01", DATA, observed, {}, {})
    assert values(current) == values(original)
    assert [m["value"] for m in current["metrics"]] == [1, 1024 * 1048576, 45]
    observed["D06"][0]["tool_status"] = "unavailable"
    assert workflow.calculate("O01", DATA, observed, {}, {}) == current
    assert "D06cpc-1" not in current["evidence_refs"]
    for topic in ("O02", "O03", "O04", "O06", "O08"):
        assert "D06" in workflow.query_ids(topic, "1.2", context={"incidents": []})


@pytest.mark.parametrize("days", [1, 7, 31])
def test_health_plan_removes_twelve_pod_windows_per_cluster_day(days):
    profile, data = setup(days)
    data["topic_ids"] = ["O01", "O09", "O05"]
    queries = {q for t in data["topic_ids"] for q in workflow.query_ids(t)}
    current, reason = collection_plan(report_profile(profile), data, sorted(queries))
    original, _ = collection_plan(
        report_profile(profile), data, sorted(queries | {"D06"})
    )
    assert reason is None
    assert sum(t["planned_calls"] for t in current) == 10 * days
    assert sum(t["planned_calls"] for t in original) == 34 * days
    assert queries == {"D01", "D03", "D04", "D10", "D11"}


@pytest.mark.parametrize(
    "context", [None, {}, {"incidents": None}, {"incidents": [{}]}]
)
def test_unknown_or_nonempty_incident_snapshot_never_skips_logs(context):
    assert "D13" in workflow.query_ids("O06", context=context)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "topics,has_incident,expect_logs",
    [
        (["O06"], False, False),
        (["O06"], True, True),
        (["O06", "O10"], False, True),
        (["O01", "O09", "O05"], False, False),
        (["O01", "O02"], False, False),
    ],
)
async def test_workflow_prunes_actual_calls_and_records_why(
    topics, has_incident, expect_logs
):
    profile, data = setup(1)
    profile["clusters"] = {
        c: {**definition, "loki_uid": "logs", "loki_selector": {"cluster_id": c}}
        for c, definition in profile["clusters"].items()
    }
    data.update(topic_ids=topics, group_by=["cluster"])
    c = claim()
    c["input"] = data
    context = dict(
        data_cutoff_at=c["deadline_at"], incidents=[], rca_results=[], actions=[]
    )
    if has_incident:
        context["incidents"] = [
            dict(
                id="incident",
                cluster_id="cpc-1",
                occurred_at=data["time_range"]["start"],
                target={"gpu_uuid": "gpu"},
            )
        ]
    calls, log_calls = [], []

    async def logs(args):
        log_calls.append(args)
        return {"data": {"result": []}}

    before = copy.deepcopy((profile, data, context))
    token = attempt_context.set(
        dict(
            claim=c,
            context=context,
            profile=profile,
            deadline=time.monotonic() + 60,
            llm=SimpleNamespace(configured=False, usage={}),
        )
    )
    try:
        output = await workflow.run(
            {"query_prometheus": source(data, calls), "query_loki_logs": logs}
        )
    finally:
        attempt_context.reset(token)
    assert (profile, data, context) == before
    result = output["result"]
    collection = result["quality"]["collection"]
    actual = {t["query_id"] for t in collection["tasks"]}
    assert ("D13" in actual) == expect_logs
    assert bool(log_calls) == expect_logs
    assert collection["query_calls"] == len(calls) + len(log_calls)
    if topics == ["O01", "O09", "O05"]:
        assert "D06" not in actual
        assert len(calls) == collection["planned_calls"] == 10
    else:
        assert "D06" in actual
    if topics == ["O06"] and not has_incident:
        assert len(calls) == collection["planned_calls"] == 26
    if "O06" in topics:
        topic = next(t for t in result["topics"] if t["topic_id"] == "O06")
        assert topic["status"] == "blocked" and topic["metrics"][0]["value"] is None
        assert "verified_workload_disruption_evidence" in topic["missing_inputs"]
        if not has_incident:
            omission = topic["quality"]["omitted_queries"][0]
            db = output["evidence"][0]
            assert omission["evidence_refs"] == [db["id"]]
            assert db["snapshot"]["incidents"] == []
            text = " ".join(n["text"] for n in result["narrative"])
            assert (
                "저장된 사건이 0건" in text
                and "다른 주제에 필요하면 조회를 유지" in text
            )
            assert "등록되지 않은 장애가 없었다는 뜻은 아닙니다" in text
            assert "D13" not in {
                o["query_id"] for o in topic["quality"]["observations"]
            }
        else:
            assert "omitted_queries" not in topic["quality"]
