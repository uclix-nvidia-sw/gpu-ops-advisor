"""De-identified production-shape regressions; no production services or data mutations."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

from agent_common.contracts import timestamp
from rcca_agent.incident_dossier import incident_brief, operator_view
from rcca_agent.analysis_values import resolve_values
from rcca_agent.combined_synthesis import validate_author
from rcca_agent.synthesis_context import bounded_context
from rcca_agent.switch_inventory import collect_switch_pci

CASES = json.loads(
    (Path(__file__).parent / "fixtures/rca-node-report-cases.json").read_text()
)["cases"]


def material(case):
    data = {
        "scope": {"clusters": [{"cluster_id": "test-cluster"}]},
        "target": {"node": "test-node", "machine_id": "test-machine"},
        "incident_time": case["alert"],
        "time_range": {"start": "2026-01-02T00:41:00Z", "end": "2026-01-02T01:12:00Z"},
    }
    target = {
        "code": "xid:79" if case["kind"] == "xid" else "sxid:11001",
        "gpu": "GPU-test-0" if case["kind"] == "xid" else None,
        "device": case["pci"],
        "event_time": case["event"],
    }
    evidence = []
    for metric in case["metrics"]:
        evidence.append(
            {
                "id": metric["query"],
                "query_id": metric["query"],
                "cluster_id": "test-cluster",
                "time_range": data["time_range"],
                "quality": {
                    "complete": True,
                    "original_samples": True,
                    "unit": metric["unit"],
                },
                "tool_status": "ok",
                "snapshot": {
                    "data": {
                        "result": [
                            {
                                "metric": {
                                    "node": "test-node",
                                    "uuid": f"GPU-test-{i}",
                                },
                                "values": metric["samples"],
                            }
                            for i in range(case["gpus"])
                        ]
                    }
                },
            }
        )
    return data, evidence, {"targets": [target]}


@pytest.mark.parametrize("case", CASES, ids=["xid-report", "sxid-report"])
def test_report_values_keep_device_unit_event_time_and_pre_event_coverage(case):
    data, evidence, comparison = material(case)
    before = deepcopy(evidence)
    view = operator_view(data, evidence, comparison)
    assert view["event_boundary"] == case["event"] != data["incident_time"]
    assert view["boundary_basis"] == "producer_event_time"
    assert len(view["metrics"]) == len(case["metrics"]) * case["gpus"]
    for metric in view["metrics"]:
        assert (metric["incident_windows"]["at_or_after"] is None) == (
            case["kind"] == "sxid"
        )
        expected = next(m for m in case["metrics"] if m["query"] == metric["query_id"])
        assert (
            metric["first"] == expected["first"] and metric["last"] == expected["last"]
        )
        assert metric["samples"] == len(expected["samples"])
    brief = incident_brief(data, evidence, comparison, None)
    assert len(brief) == 3
    if case["kind"] == "sxid":
        assert len(brief[0]["gpu_uuids"]) == 8
        assert brief[0]["kind"] == "enum" and brief[0]["enum_mapping"] is None
        assert "B/s" in brief[1]["value_text"]
    payload = {
        "incident_brief": brief,
        "device_observations": [],
        "error_events": [],
        "query_quality": [],
    }
    bounded = bounded_context(payload, 24000)
    assert bounded["context_selection"]["omitted_observations"]["incident_brief"] == 0
    response = {
        "interpretation": {
            "findings": [
                {
                    "id": "finding-1",
                    "statement": brief[0]["value_token"]
                    + (
                        "는 오류 발생 이전 구간의 측정값입니다. 사건 당시의 상태와 구분해 진단 로그를 대조할 필요가 있습니다."
                        if case["kind"] == "sxid"
                        else "에서 사용률 변화가 관측되지 않았습니다. 작업 부하와 장치 접근 가능성을 구분해 커널 로그를 대조할 필요가 있습니다."
                    ),
                    "kind": "observed",
                    "evidence_refs": brief[0]["evidence_refs"],
                }
            ],
            "unknowns": [],
            "conflicts": [],
            "limitations": [],
        },
        "hypotheses": [],
        "limitations": [],
    }
    dropped = []
    interpretation, _, _, errors = validate_author(
        response, bounded, None, dropped=dropped
    )
    assert not errors and not dropped
    assert brief[0]["value_text"] in interpretation["findings"][0]["statement"]
    assert evidence == before
    with pytest.raises(ValueError):
        resolve_values(brief[0]["value_token"], ["other-source"], bounded)
    with pytest.raises(ValueError):
        resolve_values("{{observation-999}}", brief[0]["evidence_refs"], bounded)


@pytest.mark.parametrize(
    "labels,expected",
    [
        (
            {
                "node": "test-node",
                "cluster_id": "test-cluster",
                "pci_bus_id": "00000000:CA:00.0",
            },
            ["00000000:CA:00.0"],
        ),
        (
            {
                "node": "other-node",
                "cluster_id": "test-cluster",
                "pci_bus_id": "0000:ca:00.0",
            },
            [],
        ),
        (
            {
                "node": "test-node",
                "cluster_id": "test-cluster",
                "pci_bus_id": "0000:07:00.0",
            },
            [],
        ),
    ],
)
async def test_sxid_queries_grafana_pci_with_fixed_scope_and_keeps_gpu_separate(
    labels, expected
):
    data, _, comparison = material(CASES[1])
    calls, saved = [], []

    async def query(args):
        calls.append(args)
        return {
            "data": {
                "result": [
                    {"metric": labels, "values": [[timestamp(CASES[1]["last"]), "0"]]}
                ]
            }
        }

    def evidence(query, cluster, period, snapshot, status, quality, args):
        item = {
            "id": "pci-source",
            "query_id": query,
            "cluster_id": cluster,
            "time_range": period,
            "snapshot": snapshot,
            "tool_status": status,
            "quality": quality,
            "input": args,
        }
        saved.append(item)
        return item

    obs = SimpleNamespace(
        data=data,
        profile={"limits": {"max_bytes": 10000, "max_rows": 100}},
        deadline=time.monotonic() + 30,
        calls=0,
        tools={"query_prometheus": query},
        _evidence=evidence,
        evidence=[
            {
                "query_id": "D47",
                "cluster_id": "test-cluster",
                "quality": {
                    "datasource_uid": "scoped-mimir",
                    "resolved_cluster_selector": {"cluster_id": "test-cluster"},
                    "target_labels": {"node": "node"},
                },
            }
        ],
    )
    budget = {"queries": 1}
    result = await collect_switch_pci(
        obs,
        budget,
        {"error_codes": ["sxid:11001"], "reason": "PCI:0000:ca:00.0"},
        comparison["targets"],
    )
    assert len(calls) == 1 and budget["queries"] == 0
    assert (
        'node="test-node"' in calls[0]["expr"]
        and 'cluster_id="test-cluster"' in calls[0]["expr"]
    )
    assert "pci_bus_id=~" in calls[0]["expr"] and "ca:00[.]0" in calls[0]["expr"]
    assert result[0]["observed_pci"] == expected
    assert result[0]["reported_pci"] == ["0000:ca:00.0"]
    assert saved[0]["query_id"] == "nvswitch_pci_inventory"
    await collect_switch_pci(
        obs, budget, {"error_codes": ["sxid:11001"]}, comparison["targets"]
    )
    assert len(calls) == 1 and saved[-1]["quality"]["reason"] == "budget_exhausted"


def test_value_registry_preserves_precision_and_korean_timezone():
    from rcca_agent.analysis_values import number, korean_time

    assert number(81.343123456789) == "81.343123456789"
    assert (
        korean_time("2026-01-02T01:10:12.123456Z") == "2026-01-02 10:10:12.123456 KST"
    )
    assert korean_time("2026-01-02T10:10:12+09:00") == "2026-01-02 10:10:12 KST"


def test_dropped_findings_cannot_be_reported_as_completed_analysis():
    data, evidence, comparison = material(CASES[0])
    view = bounded_context(
        {
            "incident_brief": incident_brief(data, evidence, comparison, None),
            "device_observations": [],
            "error_events": [],
            "query_quality": [],
        },
        24000,
    )
    response = {
        "interpretation": {
            "findings": [
                {
                    "id": "bad",
                    "statement": "GPU 전력은 99999 W입니다.",
                    "kind": "observed",
                    "evidence_refs": ["D11"],
                }
            ],
            "unknowns": [],
            "conflicts": [],
            "limitations": [],
        },
        "hypotheses": [],
        "limitations": [],
    }
    interpretation, _, _, errors = validate_author(response, view, None)
    assert interpretation["findings"] == []
    assert "empty_incident_analysis" in errors
