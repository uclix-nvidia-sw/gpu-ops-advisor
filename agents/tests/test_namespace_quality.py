"""Attribution quality changes neither observed calculations nor selected evidence."""

from copy import deepcopy

import pytest

from test_aggregate_report import DATA, fixture
from test_report_diagnostics import diagnostic, result_for
from ops_agent.report_contract import previous_period


def scenario(case, namespaces=None):
    data = deepcopy(DATA)
    data["scope"]["clusters"].append(dict(cluster_id="cpc-2", namespaces=namespaces))
    evidence = []
    for period in (data["time_range"], previous_period(data)):
        evidence.extend(fixture(period))
        second = fixture(period, cluster="cpc-2", namespace="selected")
        if case == "labels_missing":
            for item in second[:2]:
                for series in item["snapshot"]["series"]:
                    series["metric"].pop("namespace", None)
                    series["metric"].pop("pod", None)
        elif case == "empty" or (
            case == "previous_only" and period == data["time_range"]
        ):
            for item in second:
                item["snapshot"]["series"] = []
        elif case == "query_failed":
            second[0]["tool_status"] = "unavailable"
            second[0]["quality"]["reason"] = "report_query_failed"
        elif case == "partial":
            for series in second[0]["snapshot"]["series"]:
                series["values"].pop()
        elif case == "unattributed":
            extra = fixture(period, cluster="cpc-2", namespace="")
            for item in extra:
                for series in item["snapshot"]["series"]:
                    if "UUID" in series["metric"]:
                        series["metric"]["UUID"] = "unattributed-gpu"
            second.extend(extra)
        for item in second:
            item["scope"]["clusters"][0]["namespaces"] = namespaces
        evidence.extend(second)
    return data, evidence


@pytest.mark.parametrize(
    "case", ["labels_missing", "empty", "previous_only", "query_failed", "partial"]
)
def test_missing_or_invalid_cluster_cannot_be_hidden_by_another_cluster(case):
    data, evidence = scenario(case)
    result = result_for(evidence, data)
    topic = result["topics"][0]
    assert topic["status"] == "partial"
    if case in {"labels_missing", "empty", "previous_only"}:
        assert diagnostic(result)["clusters_without_current_attribution"] == ["cpc-2"]
        assert "namespace_current_attribution_missing" in topic["missing_inputs"]
        assert any(
            "cpc-2: 현재 기간에 선택 범위" in m for m in diagnostic(result)["messages"]
        )
    if case == "query_failed":
        assert "report_query_failed" in topic["missing_inputs"]
        messages = diagnostic(result)["messages"]
        assert any("현재 기간 기본 조회가 완료되지 않아" in m for m in messages)
        assert not any("유휴 상태인지 수집 누락인지" in m for m in messages)


@pytest.mark.parametrize("namespaces", [None, ["selected"]])
def test_selected_idle_cluster_is_unknown_even_with_successful_queries(namespaces):
    data, evidence = scenario("empty", namespaces)
    result = result_for(evidence, data)
    assert result["topics"][0]["status"] == "partial"
    assert diagnostic(result)["clusters_without_current_attribution"] == ["cpc-2"]


@pytest.mark.parametrize("case", ["empty", "labels_missing"])
def test_no_attributed_activity_is_blocked(case):
    data, evidence = scenario(case)
    data["scope"]["clusters"] = data["scope"]["clusters"][1:]
    result = result_for([e for e in evidence if e["cluster_id"] == "cpc-2"], data)
    assert result["topics"][0]["status"] == "blocked"
    assert (
        "namespace_current_attribution_missing" in result["topics"][0]["missing_inputs"]
    )


def test_unattributed_observations_are_retained_without_downgrading_named_rows():
    data, evidence = scenario("unattributed")
    saved = deepcopy(evidence)
    result = result_for(evidence, data)
    topic = result["topics"][0]
    assert topic["status"] == "ready"
    assert result["result_status"] == "ready"
    assert evidence == saved
    assert (
        topic["quality"]["namespace_status_basis"]
        == "attributed_rows_with_current_cluster_coverage_v1"
    )
    unnamed = [r for r in topic["rows"] if not r["namespace"]]
    assert len(unnamed) == 1 and unnamed[0]["quality_status"] == "blocked"
    assert len(unnamed[0]["hours"]) == 24 and unnamed[0]["evidence_refs"]
    assert all(r["activity_percent"] == 60 for r in topic["rows"] if r["namespace"])
    details = diagnostic(result)
    assert details["messages"] == details["summary"] == []
    assert details["unattributed_messages"]
    assert all(
        "미할당 여부와 전체 GPU 귀속의 완전성은 미확인" in m
        for m in details["unattributed_messages"]
    )
    assert len([r for r in details["rows"] if not r["namespace"]]) == 2
