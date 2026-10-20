"""Reader explanations retain whole-collection device comparisons and scope."""

from copy import deepcopy

import pytest

from rcca_agent.investigation_summary import investigation_summary
from rcca_agent.synthesis_context import bounded_context
from rcca_agent.report_writer import report_sources
from test_rca_llm_roles import material


def comparison_case(code="xid:79", address="PCI:0000:01:00"):
    target = {"node": "node-1"}
    data = {"target": target, "scope": {"clusters": [{"cluster_id": "c"}]}}
    event = {
        "target": target,
        "cluster_id": "c",
        "status": "reported_event",
        "error_code": code,
        "component": "accelerator-nvidia-error-" + code.split(":")[0],
        "reported_device": address,
        "event_time": "2026-10-20T06:29:57Z",
        "evidence_refs": ["log"],
    }
    report = {
        **event,
        "check_status": "valid",
        "raw_health": "Healthy",
        "observed_at": "2026-10-20T06:29:24Z",
        "gpu_candidates": [{"bus_id": "0000:07:00.0", "gpu_uuid": "gpu-a"}],
    }
    evidence = [
        {
            "id": "log",
            "query_id": "D09",
            "tool_status": "ok",
            "cluster_id": "c",
            "quality": {"complete": True},
            "snapshot": {},
        },
        {
            "id": "util",
            "query_id": "D02",
            "tool_status": "ok",
            "cluster_id": "c",
            "quality": {"complete": True, "original_samples": True},
            "snapshot": {
                "data": [
                    {
                        "metric": {"node": "node-1", "pci_bus_id": "00000000:07:00.0"},
                        "values": [[1792477903, "0"]],
                    }
                ]
            },
        },
    ]
    return data, evidence, [report], [event]


@pytest.mark.parametrize("code", ["xid:13", "xid:48", "xid:79", "xid:119"])
def test_other_xid_codes_explain_address_absence_without_claiming_hardware_absence(
    code,
):
    args = comparison_case(code)
    before = deepcopy(args)
    rows = investigation_summary(*args)
    text = " ".join(r["text"] for r in rows)
    assert "그 목록에는 해당 주소가 없습니다" in text
    assert "추가로 조회한 GPU 지표의 장치 주소 1개에도 없습니다" in text
    assert "다른 GPU의 기록" in text
    assert "오류가 나기 전의 보고" in text
    assert "실제 존재하지 않는" not in text
    assert args == before


@pytest.mark.parametrize("code", ["sxid:11001", "sxid:11012"])
def test_switch_address_is_never_compared_with_gpu_inventory(code):
    rows = investigation_summary(*comparison_case(code, "PCI:0000:c9:00.0"))
    assert not any("그 목록에는 해당 주소가 없습니다" in r["text"] for r in rows)


def test_matching_pci_normalizes_domain_case_and_function():
    rows = investigation_summary(*comparison_case(address="PCI:00000000:07:00"))
    assert any("같은 서버에서 수집한 GPU 목록에 있습니다" in r["text"] for r in rows)


def test_other_node_and_failed_metrics_do_not_support_comparison():
    args = comparison_case()
    args[1][1]["snapshot"]["data"][0]["metric"]["node"] = "other-node"
    text = str(investigation_summary(*args))
    assert "추가로 조회한 GPU 지표의 장치 주소" not in text
    args[1][1]["tool_status"] = "unavailable"
    assert "GPU 목록과 사용률" not in str(investigation_summary(*args))


def test_later_healthy_report_is_not_recovery_proof():
    args = comparison_case()
    args[2][0]["observed_at"] = "2026-10-20T06:30:24Z"
    text = str(investigation_summary(*args))
    assert "오류가 나기 전의 보고" not in text
    assert "복구 확인인지까지는 확인되지 않았습니다" in text


def test_compact_comparison_and_refs_survive_source_sample_truncation():
    summaries = investigation_summary(*comparison_case())
    view = bounded_context(
        {
            "investigation_summary": summaries,
            "metric_observations": [
                {
                    "labels": {"large": "x" * 10000},
                    "samples": [[1, 0]],
                    "evidence_refs": ["util"],
                }
            ],
        },
        4000,
    )
    assert not view["metric_observations"]
    assert view["investigation_summary"] == summaries
    assert set(view["input_evidence_refs"]) == {"log", "util"}


def test_missing_address_is_in_visible_report_even_without_model_findings():
    source = material()
    source["investigation_summary"] = investigation_summary(*comparison_case())
    rows = report_sources(source)
    assert any(
        r["section"] == "cause"
        and r["fixed"]
        and "그 목록에는 해당 주소가 없습니다" in r["text"]
        for r in rows
    )
    assert any(r["section"] == "investigation" for r in rows)
    assert not any("D09" in r["text"] or "D02" in r["text"] for r in rows)


async def test_mismatch_collects_all_four_optional_queries_within_existing_budget():
    from agent_common.contracts import content_hash
    from rca_replay import replay
    from test_fleet_rca import match_case

    case = match_case("pci")
    book = case["attempt"]["context"]["runbooks"][0]
    step = deepcopy(book["content"]["observation_plan"][-1])
    step["query_id"] = "D03"
    book["content"]["observation_plan"].append(step)
    link = deepcopy(book["content"]["decision_policy"]["followup_links"][-1])
    link["query_id"] = "D03"
    book["content"]["decision_policy"]["followup_links"].append(link)
    book["content_hash"] = book["reviewed_content_hash"] = content_hash(book["content"])
    case["attempt"]["profile"]["queries"]["D03"] = deepcopy(
        case["attempt"]["profile"]["queries"]["D02"]
    )
    outcome = await replay(case)
    decision = next(
        e["snapshot"]
        for e in outcome["output"]["evidence"]
        if e["query_id"] == "investigation_decision"
    )
    assert set(decision["selected_queries"]) == {"D02", "D03", "D11", "D44"}
    collected = {e["query_id"] for e in outcome["output"]["evidence"]}
    assert set(decision["selected_queries"]) <= collected


def test_full_post_event_utilization_summary_is_not_current_health():
    args = comparison_case()
    row = args[1][1]["snapshot"]["data"][0]
    row["metric"]["__name__"] = "DCGM_FI_DEV_GPU_UTIL"
    row["values"] = [[1792477903, "0"], [1792477904, "7"], [1792477905, "NaN"]]
    text = str(investigation_summary(*args))
    assert "이후 측정 기록 2개" in text
    assert "0~7%" in text
    assert "정상 동작이나 복구를 뜻하지는 않습니다" in text
    row["metric"]["node"] = "other-node"
    assert "이후 측정 기록" not in str(investigation_summary(*args))
