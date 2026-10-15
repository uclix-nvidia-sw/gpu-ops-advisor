"""Report sentences follow the catalog action kind for every XID and for SXID."""

import copy
import json
import re
from pathlib import Path

import pytest

from rcca_agent.incident_findings import ACTION_KINDS, catalog_terms
from rcca_agent.report_findings import RESTART_GROUP
from test_rca_incident_findings import DEFERRALS, PRIMARY, fixture, report

ROOT = Path(__file__).parents[2] / "rcca-agent/runbooks"
XID_BOOKS = {
    p.name: json.loads(p.read_text(encoding="utf-8"))["content"]
    for p in sorted((ROOT / "xid").glob("RB-XID-*.json"))
}
SWITCH = "PCI:0000:c4:00.0"


def xid_case(book, model="NVIDIA A100-SXM4-80GB"):
    """Reuse the XID 79 fixture with another published code."""
    result, data, clues, evidence = fixture(model=model, book=copy.deepcopy(book))
    code = book["search"]["codes"][0]
    result["quality"]["analysis"]["error_events"][0]["error_code"] = code
    for row in result["device_observations"]:
        if row["error_code"]:
            row["error_code"] = code
    return result, data, clues, evidence


def first_book(immediate, applies):
    """The first single-code runbook with this NVIDIA action, plus a fitting GPU model.

    With applies=True the model is the first listed product; otherwise an A100 that
    the runbook excludes.
    """
    for name, book in XID_BOOKS.items():
        terms = catalog_terms(
            [
                dict(
                    id="b",
                    query_id="runbook",
                    quality={"origin": "published"},
                    snapshot=book,
                )
            ]
        )
        if not terms or len(book["search"]["codes"]) != 1:
            continue
        if terms.get("immediate") != immediate:
            continue
        if applies and terms.get("applies"):
            return name, book, f"NVIDIA {terms['applies'][0]}"
        if not applies and "A100" in terms.get("excludes", []) and terms.get("applies"):
            return name, book, "NVIDIA A100-SXM4-80GB"
    raise AssertionError(f"no catalog runbook for {immediate} applies={applies}")


def sxid_case(model="NVIDIA A100-SXM4-80GB"):
    book = json.loads((ROOT / "sxid/RB-SXID-11001.json").read_text(encoding="utf-8"))
    result, data, clues, evidence = fixture(model=model, book=book["content"])
    event = result["quality"]["analysis"]["error_events"][0]
    event.update(
        error_code="sxid:11001",
        component="accelerator-nvidia-error-sxid",
        reported_device=SWITCH,
        device_mapping="unresolved",
        inventory_gpu_candidate=None,
    )
    for row in result["device_observations"]:
        row["component"] = "accelerator-nvidia-error-sxid"
        row["gpu_candidates"] = [{"gpu_uuid": "GPU-x", "bus_id": "0000:07:00.0"}]
        if row["error_code"]:
            row.update(
                error_code="sxid:11001",
                reported_pci_addresses=[SWITCH],
                reason=f"SXID 11001(ingress invalid command) detected on {SWITCH}",
            )
    return result, data, clues, evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(XID_BOOKS), ids=lambda n: n.removesuffix(".json"))
async def test_every_xid_report_avoids_access_loss_and_restart_assumptions(name):
    book = XID_BOOKS[name]
    result, text = await report(*xid_case(book))
    findings = result["quality"]["incident_findings"]
    plan = findings.get("plan") or {}
    joined = "\n".join(text.values())
    primary = "\n".join(text.get(k, "") for k in PRIMARY)
    assert not [p for p in DEFERRALS if p in primary]
    # The appendix keeps the immutable Runbook text verbatim, including "nil".
    assert not re.search(r"\bnil\b", primary)
    assert (
        "IGNORE)을 권고" not in joined and "IGNORE_NO_ACTION_REQUIRED)을" not in joined
    )
    assert not re.search(r"(XID|SXID) \d+[를가](?: |$)", joined.replace("XID 79가", ""))
    if book.get("classification", {}).get("category") != "gpu_access_loss":
        assert "사용할 수 없는 상태" not in joined
    if plan.get("kind") != "restart":
        assert "재시작하면 사라지는" not in text.get("action", "")
        assert "하드웨어 결함 쪽으로" not in text["cause"]
    if plan.get("kind") not in ("restart", "application", "inspection"):
        assert "시험 주입 여부" not in text.get("next", "")
    if "같은 조치입니다" in joined:
        assert plan["action"] == "REBOOT_SYSTEM" or plan["action"] in RESTART_GROUP
    if findings.get("model_applicability") == "excluded":
        assert "작업 배출" not in joined and "조치 후 확인" not in joined
    assert result["recommendations"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "immediate,expected,absent",
    [
        (
            "RESET_GPU",
            ["GPU 리셋(RESET_GPU)을 권고합니다", "작업 배출", "조치 후 확인"],
            [],
        ),
        (
            "RESTART_APP",
            [
                "애플리케이션(프로세스)을 재시작하십시오(RESTART_APP)",
                "호스트 재시작은 필요하지 않습니다",
            ],
            ["작업 배출", "VM(패스스루)"],
        ),
        (
            "CONTACT_SUPPORT",
            ["공급사 기술 지원을 요청하십시오(CONTACT_SUPPORT)"],
            ["작업 배출", "조치 후 확인", "재발 대응"],
        ),
        (
            "IGNORE",
            ["즉시 조치는 필요하지 않습니다(IGNORE)"],
            ["작업 배출", "권고합니다"],
        ),
        (
            "CHECK_UVM",
            ["UVM 드라이버 점검(CHECK_UVM) 절차를 따르십시오"],
            ["작업 배출"],
        ),
    ],
)
async def test_action_kind_sentences_for_applicable_model(immediate, expected, absent):
    _, book, model = first_book(immediate, applies=True)
    result, text = await report(*xid_case(book, model))
    assert result["quality"]["incident_findings"]["plan"]["kind"] == ACTION_KINDS.get(
        immediate, "procedure"
    )
    for phrase in expected:
        assert phrase in text["action"]
    for phrase in absent:
        assert phrase not in text["action"]


@pytest.mark.asyncio
async def test_fleet_suggestion_is_not_called_same_when_actions_differ():
    _, book, model = first_book("RESET_GPU", applies=True)
    _, text = await report(*xid_case(book, model))
    assert "Fleet 원천 권고(REBOOT_SYSTEM)는 이 조치와 다르며" in text["action"]
    assert "같은 조치입니다" not in text["action"]


@pytest.mark.asyncio
async def test_excluded_model_gets_no_drain_or_post_check():
    _, book, model = first_book("RESTART_VM", applies=False)
    result, text = await report(*xid_case(book, model))
    assert result["quality"]["incident_findings"]["model_applicability"] == "excluded"
    assert "적용 대상이 아닙니다" in text["action"]
    assert "작업 배출" not in text["action"] and "조치 후 확인" not in text["action"]
    assert "시험 주입 여부" not in text["next"]


@pytest.mark.asyncio
async def test_product_without_nvidia_listing_falls_back_to_fleet_catalog():
    # NVIDIA lists no action for A100-class products; Fleet's default action leads.
    name, book = next(
        (n, b)
        for n, b in XID_BOOKS.items()
        if "NVIDIA 적용: 해당 제품 없음; 제외: A100, H100, B100, GB200."
        in b["analysis_guidance"]
        and len(b["search"]["codes"]) == 1
    )
    result, text = await report(*xid_case(book))
    findings = result["quality"]["incident_findings"]
    assert findings["model_applicability"] == "not_listed"
    assert findings["plan"]["source"] in ("fleet", "gpud", "none")
    assert "NVIDIA 카탈로그에 이 제품군 조치 없음" in text["guidance"]
    assert "적용 대상이 아닙니다(적용: 기재 없음)" not in text["action"]


@pytest.mark.asyncio
async def test_sxid_names_switch_and_recommends_fleet_reboot_with_inspection():
    result, text = await report(*sxid_case())
    findings = result["quality"]["incident_findings"]
    assert findings["identity"]["kind"] == "switch"
    assert findings["identity"]["status"] == "reported"
    assert findings["plan"] == dict(
        source="fleet",
        action="REBOOT_SYSTEM",
        kind="restart",
        followup="HARDWARE_INSPECTION",
    )
    assert (
        "NVSwitch PCI 0000:c4:00.0에서 SXID 11001 오류가 보고됐습니다"
        in text["problem"]
    )
    assert "GPU가 아닌 NVSwitch 장치입니다" in text["problem"]
    assert "스위치 포트와 연결된 GPU·파티션은 수집 원천에 없습니다" in text["problem"]
    assert "GPUd는 잠재적 Fatal" in text["impact"]
    assert "사용할 수 없는 상태" not in text["impact"]
    assert "node-a 시스템 재부팅(REBOOT_SYSTEM)을 권고합니다" in text["action"]
    assert "제외 대상(B200, B300)이 아닙니다" in text["action"]
    assert "Fabric Manager 로그" in text["action"]
    assert "하드웨어 점검·수리(HARDWARE_INSPECTION)" in text["action"]
    assert "같은 NVSwitch(PCI 0000:c4:00.0)에서 SXID가 재발하지 않고" in text["action"]
    assert any(
        p.startswith("스위치 포트·연결 대상:") for p in text["next"].split("\n\n")
    )
    assert "적용 제외 플랫폼: B200, B300" in text["guidance"]
    primary = "\n".join(text.get(k, "") for k in PRIMARY)
    assert not [p for p in DEFERRALS + ("단정할 수는 없습니다",) if p in primary]
    assert "Pod" not in primary and "GPU–작업" not in primary


@pytest.mark.asyncio
async def test_sxid_on_excluded_platform_withholds_reboot():
    _, text = await report(*sxid_case(model="NVIDIA B200"))
    assert "적용 대상이 아닙니다(제외: B200, B300)" in text["action"]
    assert "을 권고합니다" not in text["action"]
    assert "작업 배출" not in text["action"]


@pytest.mark.asyncio
async def test_sxid_published_hedged_guidance_is_stated_directly():
    review = json.loads(
        (ROOT / "incident-report-review-20261015.json").read_text(encoding="utf-8")
    )
    previous = next(
        e["previous_values"] for e in review["entries"] if e["file"].startswith("sxid/")
    )
    result, data, clues, evidence = sxid_case()
    book = next(e for e in evidence if e["query_id"] == "runbook")
    book["snapshot"] = book["snapshot"] | copy.deepcopy(previous)
    _, text = await report(result, data, clues, evidence)
    assert text["impact"].startswith(
        "의미: SXID11001은 NVSwitch의 수신 측에서 잘못된 명령을 감지했다는 오류(ingress invalid command)입니다."
    )
    primary = "\n".join(text.get(k, "") for k in PRIMARY)
    assert "단정할 수는 없습니다" not in primary
    assert "확정할 수 없습니다" not in primary


@pytest.mark.asyncio
async def test_sxid_switch_address_on_gpu_bus_is_conflicting():
    result, data, clues, evidence = sxid_case()
    for row in result["device_observations"]:
        row["gpu_candidates"] = [{"gpu_uuid": "GPU-x", "bus_id": "0000:c4:00.0"}]
    result, text = await report(result, data, clues, evidence)
    assert result["quality"]["incident_findings"]["identity"]["status"] == "conflicting"
    assert "오류 장치를 특정하지 못했습니다" in text["problem"]
    assert "권고합니다" not in text.get("action", "")


SXID_BOOKS = {
    p.name: json.loads(p.read_text(encoding="utf-8"))["content"]
    for p in sorted((ROOT / "sxid").glob("RB-SXID-*.json"))
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name", list(SXID_BOOKS), ids=lambda n: n.removesuffix(".json")
)
async def test_every_sxid_report_names_the_switch_without_deferring(name):
    book = SXID_BOOKS[name]
    result, data, clues, evidence = sxid_case()
    code = book["search"]["codes"][0]
    result["quality"]["analysis"]["error_events"][0]["error_code"] = code
    for row in result["device_observations"]:
        if row["error_code"]:
            row["error_code"] = code
    next(e for e in evidence if e["query_id"] == "runbook")["snapshot"] = copy.deepcopy(
        book
    )
    result, text = await report(result, data, clues, evidence)
    findings = result["quality"]["incident_findings"]
    assert findings["identity"]["kind"] == "switch"
    assert findings["plan"]["source"] in ("fleet", "gpud", "none")
    primary = "\n".join(text.get(k, "") for k in PRIMARY)
    assert (
        f"NVSwitch PCI 0000:c4:00.0에서 {code.upper().replace(':', ' ')} 오류가"
        in primary
    )
    assert not [p for p in DEFERRALS if p in primary]
    assert not re.search(r"\bnil\b", primary)
    assert "사용할 수 없는 상태" not in primary
    assert "Pod" not in primary
    if findings["plan"]["kind"] == "restart":
        assert "Fabric Manager 로그" in text["action"]
        assert (
            "같은 NVSwitch(PCI 0000:c4:00.0)에서 SXID가 재발하지 않고" in text["action"]
        )
