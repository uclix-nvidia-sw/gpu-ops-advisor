import copy
import json
from pathlib import Path

import pytest

from rcca_agent.incident_findings import ACTIONS, APPLIES, catalog_terms
from rcca_agent.report import write_report

BOOK = json.loads(
    (Path(__file__).parents[2] / "rcca-agent/runbooks/xid/RB-XID-79.json").read_text(
        encoding="utf-8"
    )
)["content"]
GPU = "GPU-00000000-0000-0000-0000-000000000000"
PEER = "GPU-11111111-1111-1111-1111-111111111111"
T0 = 1792040964  # 2026-10-15T05:09:24Z


def series(uuid, bus, index, values, **labels):
    return {
        "metric": {"node": "node-a", "pci_bus_id": bus, "gpu": index, **labels}
        | {"UUID": uuid},
        "values": [[T0 + 60 * i, str(v)] for i, v in enumerate(values)],
    }


def metric(qid, producer, sample_type, data, **quality):
    return dict(
        id=qid,
        query_id=qid,
        tool_status="ok",
        quality=dict(
            complete=True,
            producer=producer,
            sample_type=sample_type,
            target_labels={"gpu_uuid": "UUID", "node": "node"},
            **quality,
        ),
        snapshot={"data": data},
    )


def status(minute, healthy):
    reason = (
        "XIDComponent is healthy"
        if healthy
        else f"XID 79 GPU has fallen off the bus detected on GPU PCI:0000:07:00 UUID:{GPU}"
    )
    return dict(
        component="accelerator-nvidia-error-xid",
        target={"node": "node-a"},
        raw_health="Healthy" if healthy else "Unhealthy",
        error_code=None if healthy else "xid:79",
        observed_at=f"2026-10-15T05:{minute:02d}:24Z",
        reason=reason,
        reported_pci_addresses=[] if healthy else ["PCI:0000:07:00"],
        time_basis="loki_recorded_at",
        fact_eligible=False,
        evidence_refs=["log"],
    )


def fixture(model="NVIDIA A100-SXM4-80GB", peer_bus="0000:0f:00.0", book=BOOK):
    busy = [100] * 13 + [0] * 18
    evidence = [
        dict(id="alert", query_id="incident_snapshot"),
        dict(
            id="book",
            query_id="runbook",
            query_version=7,
            quality={"origin": "published"},
            snapshot=book,
        ),
        metric(
            "D02",
            "nvidia_dcgm_exporter",
            "gauge",
            [
                series(
                    GPU,
                    "00000000:07:00.0",
                    "0",
                    busy,
                    modelName=model,
                    DCGM_FI_DRIVER_VERSION="580.173.02",
                    namespace="team-a",
                    pod="trainer-0",
                ),
                series(
                    PEER,
                    peer_bus,
                    "1",
                    busy,
                    modelName=model,
                    namespace="team-a",
                    pod="trainer-0",
                ),
            ],
            unit="percent",
            allocation_semantics="observed_pod_labels",
        ),
        metric(
            "D44",
            "fleet_intelligence",
            "counter",
            [series(GPU, "0000:07:00.0", "0", [0] * 30, model_name=model)],
            unit="count",
        ),
    ]
    event = dict(
        event_time="2026-10-15T05:37:51+00:00",
        cluster_id="cluster-a",
        component="accelerator-nvidia-error-xid",
        target={"node": "node-a"},
        reported_device="PCI:0000:07:00",
        error_code="xid:79",
        device_mapping="inventory_match",
        inventory_gpu_candidate=GPU,
        evidence_refs=["log"],
        fact_eligible=False,
    )
    result = dict(
        result_status="partial",
        termination_reason="missing_data",
        cause_candidates=[
            dict(
                id="observed_device_symptom",
                claim="수집 로그에 이상 상태가 보고됐으나 추가 확인이 필요합니다.",
                causal_status="candidate",
                supporting_refs=["log"],
            )
        ],
        recommendations=[],
        missing_inputs=["causal_confirmation_evidence", "unknown_value"],
        limitations=[],
        pod_relations=[],
        device_observations=[status(m, m < 38) for m in range(30, 40)],
        quality=dict(
            analysis=dict(
                error_events=[event],
                synthesis={
                    "error_code": "llm_context_budget_exhausted",
                    "budget_allocation": {"remaining_tokens": 8428},
                },
            ),
            collection_checks=[
                dict(
                    key="workload_identity",
                    title="GPU–작업 연결",
                    query_ids=["D02", "D06"],
                    status="plan_required",
                    evidence_refs=["D02"],
                    reasons=[],
                    connection_required="동일 서버·GPU UUID의 작업 라벨과 Pod UID 이력 원천을 연결하세요.",
                )
            ],
        ),
    )
    data = dict(
        incident_time="2026-10-15T05:39:10Z",
        scope={"clusters": [{"cluster_id": "cluster-a"}]},
        target={"cluster_id": "cluster-a", "node": "node-a"},
    )
    clues = {"provider_actions": {"value": {"repair_actions": ["REBOOT_SYSTEM"]}}}
    return result, data, clues, evidence


class Model:
    configured = False


async def report(*args):
    result, data, clues, evidence = args
    before = copy.deepcopy(result)
    await write_report(result, data, clues, evidence, Model())
    for key in ("recommendations", "result_status", "missing_inputs", "pod_relations"):
        assert result[key] == before[key]
    known = {e["id"] for e in evidence} | {"log"}
    assert all(set(s["evidence_refs"]) <= known for s in result["narrative"]), (
        "narrative cites unknown evidence"
    )
    return result, {s["id"]: s["text"] for s in result["narrative"]}


PRIMARY = ("problem", "impact", "cause", "action", "next", "guidance")
# Deferring or hedging phrases the operator rejected; findings-led reports avoid them.
DEFERRALS = (
    "이 이름만으로 물리적인 분리나 부품 고장을 확정할 수는 없습니다",
    "Pod UID",
    "실제 장치에서 발생한 XID79라면",
    "적용 조건: 보고된 오류 코드가 xid:79인지 확인",
    "연결 근거가 필요",
    "현재 분석만으로 재시작이 필요하다고 확정한 것은 아닙니다",
)


@pytest.mark.asyncio
async def test_corroborated_device_leads_report_with_decisive_recovery():
    result, text = await report(*fixture())
    assert result["quality"]["report"]["presentation"] == "incident-first/2"
    findings = result["quality"]["incident_findings"]
    assert findings["identity"]["status"] == "corroborated"
    assert findings["identity"]["producers"] == [
        "fleet_intelligence",
        "nvidia_dcgm_exporter",
    ]
    assert "workload" not in findings
    problem = text["problem"].split("\n\n")
    assert problem[0] == (
        "2026-10-15 14:37:51 KST, cluster-a / node-a의 PCI 0000:07:00에서 XID 79가 보고됐습니다. "
        f"수집된 인벤토리와 지표 라벨상 해당 주소는 GPU {GPU}(GPU 0, NVIDIA A100-SXM4-80GB)와 일치합니다."
    )
    assert "독립 생산자 2개" in problem[1]
    assert "14:37:24 Healthy → 14:38:24 Unhealthy(XID 79)" in problem[2]
    assert "14:37:51은 그 사이" in problem[2]
    assert "접수까지 79초" in text["problem"]
    assert "회복 보고가 없습니다" in text["impact"]
    assert "사용할 수 없는 상태입니다" in text["impact"]
    assert "심각도: 높음" in text["impact"]
    assert "team-a" not in "\n".join(text.values())
    assert text["cause"].startswith("판단: node-a GPU 0 한 장치에서 XID 79가 발생했")
    assert "0→0, 증가 없음" in text["cause"]
    assert "마지막 0 초과 값은 14:21:24" in text["cause"]
    assert "XID 154 연계 조건(R565 이상)에 해당" in text["cause"]
    assert "PCIe 링크·슬롯·라이저 불량" in text["cause"]
    assert "근본 원인은 미확정" in text["cause"]
    assert "추가 확인이 필요합니다" not in text["cause"]
    action = text["action"].splitlines()
    assert action[0].startswith("1. 근거 보존(자동 완료):")
    assert "nvidia-bug-report.sh" in action[0]
    recovery = next(line for line in action if "복구:" in line)
    assert "node-a 호스트(bare-metal) 재시작(RESTART_BM)을 권고합니다" in recovery
    assert "적용 대상(A100, H100, B100, GB200)" in recovery
    assert "REBOOT_SYSTEM" in recovery
    assert "공급사 지원(CONTACT_SUPPORT)" in text["action"]
    assert "이 시스템은 조치를 실행하지 않습니다" in text["action"]
    nxt = text["next"].split("\n\n")
    assert nxt[0].startswith("운영 모드:")
    assert any(p.startswith("커널 PCIe 오류(AER)") for p in nxt)
    assert not any(p.startswith("현재 접근 상태") for p in nxt)
    section = next(s for s in result["narrative"] if s["id"] == "guidance")
    assert section["title"] == "이 오류에 대한 참고 안내"
    assert "Fleet 분류 Fatal" in text["guidance"]
    assert "이번 GPU NVIDIA A100-SXM4-80GB: 적용 대상." in text["guidance"]
    assert "https://docs.nvidia.com/" in text["guidance"]
    assert "해석하지 마세요" not in text["guidance"]
    assert "발행 조사 지침 원문" in text["limits"]
    assert "토큰 예산 부족" in text["limits"]
    assert "장치 연결 정보를 추가 확인" not in text["limits"]
    primary = "\n".join(text[k] for k in PRIMARY)
    assert not [p for p in DEFERRALS if p in primary]


@pytest.mark.asyncio
async def test_published_hedged_guidance_is_stated_directly():
    # Revisions published before this change carry conditional operator text.
    review = json.loads(
        (
            Path(__file__).parents[2]
            / "rcca-agent/runbooks/incident-report-review-20261015.json"
        ).read_text(encoding="utf-8")
    )
    book = copy.deepcopy(BOOK) | copy.deepcopy(review["entries"][0]["previous_values"])
    result, text = await report(*fixture(book=book))
    assert (
        "의미: XID79는 GPU가 PCIe 연결을 통해 접근되지 않는 상황을 나타내는 오류입니다."
        in (text["impact"])
    )
    assert "PCIe 연결 불량이나 전원 문제 등이 있습니다." in text["cause"]
    primary = "\n".join(text[k] for k in PRIMARY)
    assert not [p for p in DEFERRALS if p in primary]


@pytest.mark.asyncio
async def test_idle_node_is_stated_without_workload_identity():
    result, data, clues, evidence = fixture()
    for e in evidence:
        if e["query_id"] == "D02":
            for s in e["snapshot"]["data"]:
                s["values"] = [[t, "0"] for t, _ in s["values"]]
                for key in ("namespace", "pod"):
                    s["metric"].pop(key)
    _, text = await report(result, data, clues, evidence)
    assert (
        "수집 구간 동안 이 GPU 사용률은 0%였고 같은 노드 2개 중 2개가 0%"
        in text["impact"]
    )
    assert "0% 유지(같은 노드 2개 중 2개가 같은 상태)" in text["cause"]
    assert "2. 작업 확인: 수집 구간 동안 node-a의 GPU 2개가 사용률 0%" in text["action"]
    assert "위 작업" not in "\n".join(text.values())


@pytest.mark.asyncio
async def test_conflicting_metric_mapping_withholds_device_and_recovery():
    # The second GPU reports the event PCI address too: identity is not unique.
    result, text = await report(*fixture(peer_bus="0000:07:00.0"))
    assert result["quality"]["incident_findings"]["identity"]["status"] == "conflicting"
    assert "오류 GPU를 하나로 특정하지 못했습니다" in text["problem"]
    assert "장치 연결 충돌" in text["problem"]
    assert "재시작(RESTART_BM)을 권고합니다" not in text["action"]


@pytest.mark.asyncio
async def test_excluded_model_is_not_recommended_catalog_restart():
    book = copy.deepcopy(BOOK)
    book["analysis_guidance"] = [
        "NVIDIA 적용: B100, GB200; 제외: A100, H100."
        if line.startswith("NVIDIA 적용:")
        else line
        for line in book["analysis_guidance"]
    ]
    _, text = await report(*fixture(book=book))
    assert "적용 대상이 아닙니다" in text["action"]
    assert "그대로 적용하지 말고" in text["action"]
    assert "을 권고합니다" not in text["action"]
    assert "제외 모델." in text["guidance"]


@pytest.mark.asyncio
async def test_inventory_only_match_is_marked_single_source():
    result, data, clues, evidence = fixture()
    evidence = [e for e in evidence if not e["query_id"].startswith("D")]
    result, text = await report(result, data, clues, evidence)
    assert (
        result["quality"]["incident_findings"]["identity"]["status"] == "single_source"
    )
    assert f"수집된 인벤토리상 해당 주소는 GPU {GPU}와 일치합니다" in text["problem"]
    assert "1개 생산자의 매핑" in text["problem"]
    assert "적용 여부를 먼저 확인하십시오" in text["action"]
    assert any(p.startswith("장치 연결:") for p in text["next"].split("\n\n"))


@pytest.mark.asyncio
async def test_legacy_workload_check_is_not_reported():
    # Results from older workers may still carry a GPU–Pod connection request.
    _, text = await report(*fixture())
    assert "GPU–작업 연결" not in "\n".join(text.values())


def test_catalog_lines_of_every_xid_runbook_parse():
    root = Path(__file__).parents[2] / "rcca-agent/runbooks/xid"
    for path in root.glob("RB-XID-*.json"):
        content = json.loads(path.read_text(encoding="utf-8"))["content"]
        lines = content.get("analysis_guidance", [])
        for line in lines:
            if line.startswith("NVIDIA 적용:"):
                assert APPLIES.match(line), (path.name, line)
            if line.startswith("NVIDIA 조치 분류:"):
                assert ACTIONS.match(line), (path.name, line)
        terms = catalog_terms(
            [
                dict(
                    id="b",
                    query_id="runbook",
                    quality={"origin": "published"},
                    snapshot=content,
                )
            ]
        )
        if any(line.startswith("NVIDIA 조치 분류:") for line in lines):
            assert terms and terms.get("immediate"), path.name
