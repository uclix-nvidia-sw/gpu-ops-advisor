"""Non-code Fleet goals share the existing collection/three-role pipeline."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from agent_common.contracts import content_hash
from rcca_agent.retrieval import retrieve_runbooks
from rcca_agent.runbook_contract import validate_runbook
from rcca_agent.report_writer import report_sources, write_material_report
from rca_replay import replay
from test_rca_combined_policy import policy_case
from test_rca_llm_roles import Writer, material

BOOKS = Path(__file__).resolve().parents[2] / "rcca-agent/runbooks"


def component_case():
    case = policy_case()
    case["id"] = "fleet_disk_report"
    profile = case["attempt"]["profile"]
    profile["health_contracts"]["fleet-component-log-v1"]["components"]["disk"] = (
        "component"
    )
    data = case["attempt"]["claim"]["input"]
    data["target"]["component"] = "disk"
    case["queries"][0]["arguments"]["logql"] = (
        '{node="node-1"} | drop dsx_json_0, dsx_json_0_extracted | json '
        'dsx_json_0="attributes[\\"component\\"]" | __error__="" | '
        '(dsx_json_0="disk" or dsx_json_0_extracted="disk")'
    )
    data["incident_snapshot"] = {
        "alert": {"labels": {"component": "disk", "reason": "filesystem is read-only"}}
    }
    values = case["queries"][0]["response"]["data"]["result"][0]["values"]
    raw = json.loads(values[0][1])
    raw["attributes"].update(component="disk", reason="filesystem is read-only")
    values[0][1] = json.dumps(raw)
    book = case["attempt"]["context"]["runbooks"][0]
    book["knowledge_key"] = "RB-FIXTURE-DISK"
    content = book["content"]
    content.update(
        schema="gpu-rca-runbook/1.2",
        title="Fleet disk 오류 보고",
        search={"aliases": ["disk", "filesystem is read-only"]},
        required_evidence=[
            "reported_component",
            "reported_normalized_health",
            "reported_producer_contract",
        ],
    )
    content["observation_plan"] = content["observation_plan"][:1]
    content["observation_plan"][0]["fact_names"] = content["required_evidence"]
    content["decision_policy"]["applies_when"] = {
        "reported_reason": "filesystem is read-only",
        "reported_component": "disk",
        "reported_normalized_health": "unhealthy",
        "reported_producer_contract": "fleet-component-log-v1",
    }
    content["decision_policy"]["followup_links"] = content["decision_policy"][
        "followup_links"
    ][:1]
    content["operator_guidance"] = {
        "schema": "gpu-rca-guidance/1.0",
        "meaning": "디스크 컴포넌트의 비정상 상태 보고입니다.",
        "cause_note": "보고 사유와 진단 자료로 조사 범위를 정합니다.",
        "next_checks": [
            {
                "title": "파일시스템 점검",
                "text": "읽기 전용 전환이면 마운트와 커널 기록을 보존하고, 쓰기 시험은 유지보수 승인 후 수행합니다.",
            }
        ],
        "references": [
            {
                "title": "검증용 지침",
                "text": "운영 지침이 아닌 테스트 fixture입니다.",
                "source_indices": [0],
            }
        ],
    }
    book.update(
        content_hash=content_hash(content), reviewed_content_hash=content_hash(content)
    )
    return case


async def test_noncode_component_uses_one_query_and_three_calls():
    case = component_case()
    book = case["attempt"]["context"]["runbooks"][0]
    profile = case["attempt"]["profile"]
    validate_runbook(book, profile["queries"], list(profile["queries"]))
    result = await replay(case)
    assert not result["missing_inputs"]
    assert len(result["query_calls"]) == 1
    assert [c["stage"] for c in result["model_calls"]] == [
        "synthesis",
        "report_writing",
    ]
    output = result["output"]["result"]
    assert (
        output["quality"]["rca_evaluation"]["investigation"]["stop_reason"]
        == "no_available_followup"
    )
    text = str(output["narrative"])
    assert "파일시스템 점검" in text and "유지보수 승인" in text
    assert "RESTART_BM" not in text
    assert all(not r.get("fact_eligible") for r in output["device_observations"])


async def test_shipped_component_guidance_survives_healthy_reports_before_failure():
    # Production disk windows hold periodic Healthy "ok" reports before the failure;
    # the unmapped Healthy state and mixed reasons must not hide component guidance.
    case = component_case()
    book = case["attempt"]["context"]["runbooks"][0]
    shipped = json.loads(
        (BOOKS / "component/RB-COMPONENT-DISK.json").read_text(encoding="utf-8")
    )
    book["knowledge_key"] = shipped["knowledge_key"]
    book["content"] = shipped["content"]
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
    # The shipped plan names optional disk queries newer than this legacy fixture
    # profile; unvalidated there, they are skipped like an unavailable binding.
    for query, metric in (("D59", "disk_used_bytes"), ("D60", "disk_free_bytes")):
        case["attempt"]["profile"]["queries"][query] = {
            "source": "mimir",
            "metric": metric,
            "unit": "bytes",
            "max_hold_seconds": 0,
            "revision": "fixture",
            "validated": False,
            "target_labels": {"node": "node", "mount_point": "mount_point"},
        }
    values = case["queries"][0]["response"]["data"]["result"][0]["values"]
    start, line = int(values[0][0]), values[0][1]
    values[0][0] = str(start + 40 * 10**9)
    for seconds in (10, 20, 30):
        healthy = json.loads(line)
        healthy["attributes"].update(health="Healthy", reason="ok")
        values.append([str(start + seconds * 10**9), json.dumps(healthy)])
    result = await replay(case)
    output = result["output"]["result"]
    assert len(output["device_observations"]) == 4
    # Healthy baseline reports stay context; the Unhealthy ones carry the values.
    assert "unknown_value" not in output["missing_inputs"]
    guidance = output["quality"]["runbook_guidance"]
    assert [g["report_applicability"] for g in guidance] == ["matched"]
    assert "findmnt -O ro" in str(output["narrative"])


@pytest.mark.parametrize("component", [None, "cpu", ["disk"]])
def test_noncode_retrieval_requires_exact_component_not_prose(component):
    book = component_case()["attempt"]["context"]["runbooks"][0]
    assert (
        retrieve_runbooks(
            [book],
            {"component": component, "description": "disk filesystem is read-only"},
        )
        == []
    )
    assert retrieve_runbooks(
        [book],
        {
            "alert": {
                "labels": {"component": "disk", "reason": "filesystem is read-only"}
            }
        },
    )


@pytest.mark.parametrize("failure", [None, "refs", "truncated"])
async def test_guidance_is_frozen_conditional_and_not_rewritten(failure):
    from rcca_agent.operator_guidance import project_guidance

    book = component_case()["attempt"]["context"]["runbooks"][0]
    source = material()
    source["runbook_guidance"] = project_guidance(
        [
            {
                "id": "published",
                "query_id": "runbook",
                "query_version": "revision-2",
                "snapshot": book["content"],
                "quality": {"origin": "published"},
            }
        ]
    )
    before = deepcopy(source)
    model, result = Writer(failure), {"quality": {}}
    await write_material_report(result, source, model)
    assert len(model.inputs) == 1
    assert source == before
    assert "유지보수 승인" not in str(model.inputs[0]["source_items"])
    action = next(r for r in result["narrative"] if r["id"] == "action")
    assert "쓰기 시험은 유지보수 승인 후 수행합니다." in action["text"]
    assert "published" in action["evidence_refs"]


def test_missing_input_is_not_promoted_to_action_and_time_fallback_is_bounded():
    source = material()
    source["missing_inputs"] = ["근거 없는 재시작 요청"]
    source["device_observations"] = [
        {
            "time_basis": "loki_recorded_at",
            "producer_time_status": "missing_or_zero",
            "evidence_refs": ["log"],
        }
    ]
    rows = report_sources(source)
    assert all(
        r["section"] == "limits" for r in rows if "근거 없는 재시작" in r["text"]
    )
    time = next(r for r in rows if "로그 기록 시각을 기준" in r["text"])
    assert time["fixed"] and time["evidence_refs"] == ["log"]
    assert "장애 발생·회복 시각 판정에는 사용하지" in time["text"]


@pytest.mark.parametrize("health", ["Healthy", "Unknown"])
async def test_component_state_mixture_does_not_claim_goal_or_recovery(health):
    case = component_case()
    values = case["queries"][0]["response"]["data"]["result"][0]["values"]
    other = json.loads(values[0][1])
    other["attributes"]["health"] = health
    values.append([values[0][0], json.dumps(other)])
    result = await replay(case)
    investigation = result["output"]["result"]["quality"]["rca_evaluation"][
        "investigation"
    ]
    assert "objective" not in investigation
    assert (
        result["output"]["result"]["quality"]["rca_evaluation"]["review"]["verdict"]
        is None
    )
    assert not any(
        r.get("fact_eligible")
        for r in result["output"]["result"]["device_observations"]
    )


def test_mismatched_published_guidance_stays_reference_only():
    from rcca_agent.operator_guidance import project_guidance

    book = component_case()["attempt"]["context"]["runbooks"][0]
    entry = {
        "id": "published",
        "query_id": "runbook",
        "quality": {"origin": "published"},
        "snapshot": book["content"],
    }
    guidance = project_guidance([entry], {"reported_component": "cpu"})
    assert guidance[0]["report_applicability"] == "reference_only"
    source = material()
    source["runbook_guidance"] = guidance
    assert "파일시스템 점검" not in str(report_sources(source))


def test_general_guidance_is_shown_only_as_the_fallback():
    from rcca_agent.operator_guidance import project_guidance

    root = Path(__file__).resolve().parents[2] / "rcca-agent/runbooks"
    content = json.loads((root / "RB-GENERAL-GPU-NODE.json").read_text("utf-8"))[
        "content"
    ]
    entry = {
        "id": "published",
        "query_id": "runbook",
        "quality": {"origin": "published"},
        "snapshot": content,
    }
    # Selection keeps it only when no dedicated Runbook applies, so no code matches.
    guidance = project_guidance([entry], {"reported_error_code": "xid:9999"})
    assert guidance[0]["report_applicability"] == "general_fallback"
    source = material()
    source["runbook_guidance"] = guidance
    assert content["operator_guidance"]["meaning"] in str(report_sources(source))


def test_same_component_different_reason_cannot_select_specific_procedure():
    book = component_case()["attempt"]["context"]["runbooks"][0]
    assert (
        retrieve_runbooks(
            [book], {"component": "disk", "reason": "failed to read disk events"}
        )
        == []
    )


def test_time_diagnostic_is_localized_without_mutating_analysis():
    source = material()
    source["evaluation"]["evidence"]["interpretation"]["findings"][0]["statement"] = (
        "producer_time_status=missing_or_zero"
    )
    before = deepcopy(source)
    rows = report_sources(source)
    assert "상태 보고의 발생 시각이 비어 있거나 초기값입니다" in str(rows)
    assert "producer_time_status" not in str(rows)
    assert source == before
