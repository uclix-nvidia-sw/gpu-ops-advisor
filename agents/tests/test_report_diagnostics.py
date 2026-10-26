"""Diagnostic explanations must preserve calculations and the writer's inputs."""

import asyncio
from copy import deepcopy
import time
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from agent_common.artifacts import render
from agent_common.contracts import validate_result
from agent_common.runtime import attempt_context
from ops_agent import aggregate_report
from ops_agent.aggregate_report import build_result
from ops_agent.identity_transitions import sample_bounds, verified_transitions
from ops_agent.report_contract import VERSION, previous_period
from ops_agent.report_interpretation import payload_for
from ops_agent.report_queries import ReportQueries
from test_aggregate_report import DATA, fixture
from test_identity_transitions import transition_fixture, proof
from test_report_interpretation import reply_for


def result_for(evidence, data=DATA):
    context = dict(
        data_cutoff_at=data["time_range"]["end"], incidents=[], previous_incidents=[]
    )
    claim = dict(
        job_id=str(uuid4()), kind="report", input=data, versions={"criteria": VERSION}
    )
    result = build_result(claim, context, evidence)
    validate_result(result, evidence)
    return result


def diagnostic(result):
    return result["topics"][0]["quality"]["observation_diagnostics"]


def changed_hours(period, cluster, count):
    evidence = fixture(period, cluster=cluster)
    for point in evidence[2]["snapshot"]["series"][0]["values"][:count]:
        point[1] = "2"
    return evidence


def test_shared_budget_prefers_current_period_and_alternates_clusters():
    data = deepcopy(DATA)
    data["scope"]["clusters"].append(dict(cluster_id="cpc-2", namespaces=None))
    previous = previous_period(data)
    groups = [
        changed_hours(data["time_range"], "cpc-1", 7),
        changed_hours(previous, "cpc-1", 9),
        changed_hours(data["time_range"], "cpc-2", 7),
        changed_hours(previous, "cpc-2", 7),
    ]
    evidence = [e for group in groups for e in group]
    baseline = result_for(deepcopy(evidence), data)
    calls = []

    async def query(args):
        calls.append(args)
        return {"data": {"result": []}}

    collector = ReportQueries({"query_prometheus": query}, data, time.monotonic() + 900)
    evidence.extend(
        asyncio.run(
            collector.check_transitions(
                [
                    (
                        group[0]["scope"]["clusters"][0],
                        group[0]["time_range"],
                        "mimir",
                        group,
                    )
                    for group in groups
                ]
            )
        )
    )
    assert len(calls) == collector.transition_calls == 32
    assert ['cluster_id="cpc-1"' in call["expr"] for call in calls[::2]] == [
        True,
        False,
    ] * 8
    checked = [e for e in evidence if e["query_id"] == "gpu_identity_transitions"]
    assert [e["time_range"] for e in checked] == [data["time_range"]] * 14 + [
        previous
    ] * 2
    assert [call["endTime"] for call in calls[::2]] == [
        e["input"]["queries"][0]["endTime"]
        for e in evidence
        if e["query_id"] == "gpu_identity_transitions"
    ]
    result = result_for(evidence, data)
    without_audit = deepcopy(evidence)
    for e in without_audit:
        e["quality"].pop("transition_verification", None)
    unannotated = result_for(without_audit, data)
    assert payload_for(result) == payload_for(unannotated)
    assert render(result)["csv"] == render(unannotated)["csv"]
    calculated_topics = deepcopy(result["topics"])
    old_topics = deepcopy(unannotated["topics"])
    for topic in calculated_topics + old_topics:
        topic["quality"].pop("observation_diagnostics", None)
    assert calculated_topics == old_topics
    assert result["result_status"] == baseline["result_status"] == "partial"
    for before, after in zip(baseline["topics"], result["topics"]):
        # Added evidence IDs are expected; calculations and interpretation are unchanged.
        for key in ("status", "missing_inputs"):
            assert before[key] == after[key]
    cpc2 = next(
        r
        for r in diagnostic(result)["rows"]
        if r["cluster_id"] == "cpc-2" and r["period_role"] == "previous"
    )
    assert (cpc2["valid_hours"], cpc2["excluded_hours"]) == (17, 7)
    assert (
        next(
            r
            for r in cpc2["reasons"]
            if r["code"] == "transition_query_budget_exhausted"
        )["hours"]
        == 6
    )
    audit = next(
        r
        for r in diagnostic(result)["collection"]
        if r["cluster_id"] == "cpc-2" and r["period_role"] == "previous"
    )
    assert (
        audit["checked_batches"],
        audit["skipped_hours"],
        audit["skipped_gpu_hours"],
    ) == (1, 6, 6)
    # Skips leave audits, not invented query evidence.
    assert len(checked) == 16
    assert len({e["cluster_id"] for e in checked}) == 2
    assert all(
        row["skipped_hours"] == 0
        for row in diagnostic(result)["collection"]
        if row["period_role"] == "current"
    )


@pytest.mark.parametrize(
    "case", ["deadline", "base", "query", "overlap", "pod", "proof"]
)
def test_failure_stages_are_distinct_and_do_not_promote_hours(case):
    evidence, gpu, pods, at = transition_fixture()
    if case == "base":
        evidence[1]["tool_status"] = "unavailable"
    if case == "overlap":
        gpu[1]["values"][0][0] = gpu[0]["values"][-1][0]
    if case == "pod":
        pods[0]["metric"]["uid"] = ""
    calls = []

    async def query(args):
        calls.append(args)
        if case == "query":
            raise RuntimeError("secret-upstream-detail")
        return {"data": {"result": pods if "kube_pod_info" in args["expr"] else gpu}}

    collector = ReportQueries(
        {"query_prometheus": query},
        DATA,
        time.monotonic() + (20 if case == "deadline" else 900),
    )
    checks = asyncio.run(
        collector.check_transitions(
            [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
        )
    )
    if case == "proof":
        checks[0]["snapshot"]["checks"][0]["values"]["activity_sum"] += 1
    result = result_for(evidence + checks + fixture(previous_period(DATA)))
    row = next(r for r in result["topics"][0]["rows"] if r["namespace"])
    assert row["valid_hours"] == (0 if case == "base" else 23)
    code = dict(
        deadline="transition_deadline_exhausted",
        base="base_query_unavailable",
        query="transition_verification_unavailable",
        overlap="gpu_interval_unverified",
        pod="pod_uid_unverified",
        proof="transition_aggregate_mismatch",
    )[case]
    assert code in str(diagnostic(result))
    if case == "base":
        collection = diagnostic(result)["collection"][0]
        assert collection["skipped_hours"] is None
        assert collection["skipped_gpu_hours"] is None
    assert "secret-upstream-detail" not in str(evidence + checks)
    assert len(calls) == (
        0 if case in {"deadline", "base"} else 1 if case == "query" else 2
    )


@pytest.mark.parametrize("case", ["budget", "deadline", "gpu"])
@pytest.mark.parametrize("conflicting_labels", [False, True])
def test_transition_audits_only_explain_repairable_named_rows(case, conflicting_labels):
    evidence, gpu, pods, _ = transition_fixture()
    if conflicting_labels:
        for series in evidence[0]["snapshot"]["series"]:
            if series["metric"].get("namespace"):
                series["metric"]["node"] = "other-node"
    if case == "gpu":
        gpu[1]["values"][0][0] = gpu[0]["values"][-1][0]

    async def query(args):
        return {"data": {"result": pods if "kube_pod_info" in args["expr"] else gpu}}

    collector = ReportQueries(
        {"query_prometheus": query},
        DATA,
        time.monotonic() + (20 if case == "deadline" else 900),
    )
    if case == "budget":
        collector.transition_calls = 32
    checks = asyncio.run(
        collector.check_transitions(
            [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
        )
    )
    result = result_for(evidence + checks + fixture(previous_period(DATA)))
    details = diagnostic(result)
    code = dict(
        budget="transition_query_budget_exhausted",
        deadline="transition_deadline_exhausted",
        gpu="gpu_interval_unverified",
    )[case]
    unnamed = next(r for r in details["rows"] if not r["namespace"])
    named = next(r for r in details["rows"] if r["namespace"])
    assert code not in {r["code"] for r in unnamed["reasons"]}
    assert "identity_labels_missing" in {r["code"] for r in unnamed["reasons"]}
    assert (code in {r["code"] for r in named["reasons"]}) is not conflicting_labels
    audit = evidence[0]["quality"]["transition_verification"][0]
    assert code == (audit["reason"] or audit["rejected"][0]["reason"])
    assert details["collection"][0]["skipped_hours"] == (0 if case == "gpu" else 1)
    unannotated = deepcopy(evidence + checks + fixture(previous_period(DATA)))
    unannotated[0]["quality"].pop("transition_verification")
    baseline = result_for(unannotated)
    assert result["topics"][0]["rows"] == baseline["topics"][0]["rows"]
    assert result["result_status"] == baseline["result_status"]
    assert payload_for(result) == payload_for(baseline)
    assert render(result)["csv"] == render(baseline)["csv"]


def test_diagnostics_are_output_only_and_old_evidence_does_not_invent_skip_cause():
    evidence, _, _, _ = transition_fixture()
    result = result_for(evidence + fixture(previous_period(DATA)))
    assert "transition_query_budget_exhausted" not in str(diagnostic(result))
    payload = payload_for(result)
    baseline = deepcopy(result)
    del baseline["topics"][0]["quality"]["observation_diagnostics"]
    assert payload == payload_for(baseline)
    assert render(result)["csv"] == render(baseline)["csv"]
    result["limitations"].extend(diagnostic(result)["messages"])
    html = render(result)["html"].decode()
    assert "Namespace 미표기" in html and "미할당 여부는 미확인" in html
    assert render(result)["csv"] == render(baseline)["csv"]


@pytest.mark.parametrize(
    "count,status", [(0, "ready"), (7, "partial"), (24, "blocked")]
)
def test_quality_boundaries_and_previous_period_explanations(count, status):
    result = result_for(
        changed_hours(DATA["time_range"], "cpc-1", count)
        + fixture(previous_period(DATA))
    )
    assert result["topics"][0]["status"] == status
    assert result["result_status"] == ("ready" if status == "ready" else "partial")
    if not count:
        assert diagnostic(result)["messages"] == []
    else:
        assert diagnostic(result)["rows"][0]["excluded_hours"] == count
    previous = result_for(fixture() + changed_hours(previous_period(DATA), "cpc-1", 7))
    assert diagnostic(previous)["rows"][0]["period_role"] == "previous"
    assert "이전 기간" in diagnostic(previous)["messages"][0]


def test_verified_flag_does_not_hide_another_rejected_identity_in_same_row_hour():
    evidence, gpu, pods, at = transition_fixture()
    evidence.append(proof(evidence, gpu, pods, at))
    extra = deepcopy(evidence[0]["snapshot"]["series"][:4])
    for series in extra:
        series["metric"]["UUID"] = "gpu-2"
        series["metric"].pop("pod")
        series["values"] = series["values"][:1]
    evidence[0]["snapshot"]["series"].extend(extra)
    result = result_for(evidence + fixture(previous_period(DATA)))
    row = next(r for r in result["topics"][0]["rows"] if r["namespace"])
    assert row["hours"][0]["verified_connection_change"] is True
    assert row["hours"][0]["activity_percent"] is None
    assert row["valid_hours"] == 23
    assert row["sample_count"] == 23 * 240
    assert (
        next(r for r in diagnostic(result)["rows"] if r["namespace"])["excluded_hours"]
        == 1
    )


def test_multiple_gpus_in_one_skipped_hour_do_not_double_count_row_hours():
    evidence = changed_hours(DATA["time_range"], "cpc-1", 1)
    for index in (0, 2):
        copies = deepcopy(evidence[index]["snapshot"]["series"])
        for series in copies:
            series["metric"]["UUID"] = "gpu-2"
        evidence[index]["snapshot"]["series"].extend(copies)

    async def unexpected(args):
        raise AssertionError("exhausted budget must not call upstream")

    collector = ReportQueries(
        {"query_prometheus": unexpected}, DATA, time.monotonic() + 900
    )
    collector.transition_calls = 32
    assert (
        asyncio.run(
            collector.check_transitions(
                [(DATA["scope"]["clusters"][0], DATA["time_range"], "mimir", evidence)]
            )
        )
        == []
    )
    result = result_for(evidence + fixture(previous_period(DATA)))
    audit = diagnostic(result)["collection"][0]
    assert (audit["skipped_hours"], audit["skipped_gpu_hours"]) == (1, 2)
    assert audit["skipped_by_reason"] == [
        dict(code="transition_query_budget_exhausted", hours=1, gpu_hours=2)
    ]
    row = diagnostic(result)["rows"][0]
    assert row["excluded_hours"] == 1
    assert (
        next(
            r
            for r in row["reasons"]
            if r["code"] == "transition_query_budget_exhausted"
        )["hours"]
        == 1
    )


def test_absent_periods_and_all_blocked_keep_existing_status_rules():
    for evidence, missing in [
        (fixture(), "이전"),
        (fixture(previous_period(DATA)), "현재"),
    ]:
        result = result_for(evidence)
        assert any(
            f"{missing} 기간의 대응 관측이 없어" in m
            for m in diagnostic(result)["messages"]
        )
    data = {**DATA, "topic_ids": ["namespace_usage"]}
    result = result_for(changed_hours(DATA["time_range"], "cpc-1", 24), data)
    assert result["result_status"] == "blocked"


async def test_run_appends_diagnostics_only_after_llm_interpretation(monkeypatch):
    async def collect(self, cluster, period, *, queries=None, uid=None):
        if queries is not None:
            return []
        evidence = changed_hours(period, cluster["cluster_id"], 7)
        for item in evidence:
            item["input"]["datasourceUid"] = "fixture"
        return evidence

    async def query(args):
        return {"data": {"result": []}}

    requests = []

    async def complete(system, payload, *, json_object):
        assert json_object is True
        requests.append(deepcopy(payload))
        return reply_for(payload)

    monkeypatch.setattr(ReportQueries, "collect", collect)
    llm = AsyncMock(configured=True, usage={})
    llm.complete.side_effect = complete
    token = attempt_context.set(
        dict(
            claim=dict(
                job_id=str(uuid4()),
                kind="report",
                input=DATA,
                versions={"criteria": VERSION},
            ),
            context=dict(
                data_cutoff_at=DATA["time_range"]["end"],
                incidents=[],
                previous_incidents=[],
            ),
            deadline=time.monotonic() + 900,
            llm=llm,
        )
    )
    try:
        output = await aggregate_report.run({"query_prometheus": query})
    finally:
        attempt_context.reset(token)
    result = output["result"]
    validate_result(result, output["evidence"])
    messages = diagnostic(result)["messages"]
    assert messages and requests
    assert result["quality"]["report"]["method"] == "llm_interpreted"
    assert all(message in result["limitations"] for message in messages)
    for request in requests:
        # The ordinary interpretation path sends limitations to the model.
        assert not any(t.get("advice_mode") for t in request["topics"])
        assert "limitations" in request
        assert not set(messages).intersection(request["limitations"])


@pytest.mark.parametrize("namespaces", [None, ["test-dept-service"], ["other"]])
def test_transition_rejections_preserve_selected_namespace_scope(namespaces):
    _, gpu, pods, at = transition_fixture()
    gpu[0]["metric"].update(namespace="other", pod="other-pod")
    pods[0]["metric"]["uid"] = ""
    rejected = []
    assert not verified_transitions(
        sample_bounds(gpu, at, "cpc-1"),
        sample_bounds(pods, at, "cpc-1"),
        at,
        {"gpu-1": 2},
        namespaces,
        rejected=rejected,
    )
    expected = [
        dict(
            gpu_id="gpu-1",
            reason="pod_identity_missing",
            namespace="other",
            pod="other-pod",
        ),
        dict(
            gpu_id="gpu-1",
            reason="pod_uid_unverified",
            namespace="test-dept-service",
            pod="test-pod",
        ),
    ]
    assert rejected == [
        item
        for item in expected
        if namespaces is None or item["namespace"] in namespaces
    ]
