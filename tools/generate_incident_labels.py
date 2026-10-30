"""Generate the incident list/dashboard labels from the authored Runbooks.

Per XID/SXID code or Fleet component: a short Korean name, the catalog name, the
NVIDIA-classified next action and the Runbook response step titles.
Run `npm run format` in frontend/ afterwards, as for rcaLabels.json.
"""

import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
runbooks = root / "rcca-agent/runbooks"
destination = root / "frontend/src/lib/incidentLabels.json"

# NVIDIA Xid catalog resolution buckets (Analyzing Xid Catalog, Table 3).
ACTIONS = {
    "RESTART_BM": "호스트 재시작 (RESTART_BM)",
    "RESTART_VM": "VM 재시작 (RESTART_VM)",
    "RESET_GPU": "GPU 리셋 (RESET_GPU)",
    "RESTART_APP": "애플리케이션 재시작 (RESTART_APP)",
    "CONTACT_SUPPORT": "공급사 문의 (CONTACT_SUPPORT)",
    "IGNORE": "조치 불필요 (IGNORE)",
    "CHECK_MECHANICALS": "기계적 연결 점검 (CHECK_MECHANICALS)",
    "UPDATE_SWFW": "소프트웨어·펌웨어 업데이트 (UPDATE_SWFW)",
    "CHECK_UVM": "UVM 점검 (CHECK_UVM)",
    "XID_154": "XID 154 복구 수준 따름",
}
# Fabric Manager User Guide SXID tables.
FM_TABLES = {
    "22": "비치명 SXID (FM 표 22)",
    "23": "치명 가능 SXID (FM 표 23)",
    "24": "항상 치명 SXID (FM 표 24)",
    "25": "기타 주의 SXID (FM 표 25)",
}

# Investigation summaries, not unconditional recovery commands. The Xid catalog
# leaves the immediate bucket blank for 162–172; use its trigger context and
# GPU Node Triage evidence steps instead. 173/20009 retain source-specific plans.
CHECKS = {
    "xid:162": "전력 평활 기능 재활성화와 전력 변동 확인",
    "xid:163": "전력 평활 중단 원인: 온도·시간 초과 확인",
    "xid:164": "전력 변동과 전력 평활 회로 수명 점검",
    "xid:165": "전력 평활 종료에 따른 전력 변동·설비 수용량 점검",
    "xid:166": "기밀 컴퓨팅 모드와 NVLink 암호화 설정 확인",
    "xid:167": "PCIe 연결·GPU 응답과 커널 오류 확인",
    "xid:168": "ECC 설정과 쓰기 보호 메모리 영역 오류 확인",
    "xid:169": "GPU 내부 제어기 중단 로그·드라이버 확인",
    "xid:170": "기밀 컴퓨팅 모드와 같은 시각 NVLink 오류 확인",
    "xid:171": "XID 48 동반 여부와 DRAM 정정 불가 오류 확인",
    "xid:172": "XID 48 동반 여부와 SRAM 정정 불가 오류 확인",
    "xid:173": "C2C 연결 상태·오류 증가와 양 끝 장치 로그 확인",
    "sxid:20009": "NVSwitch 수신 오류 반복·증가와 링크 상태 확인",
}
WORKFLOWS = {
    "WORKFLOW_XID_45": "동반 XID 확인 · 단독 발생이면 Fabric Manager 점검",
    "WORKFLOW_XID_48": "ECC 오류·메모리 재매핑·XID 154 복구 지시 확인",
    "WORKFLOW_NVLINK_ERR": "NVLink 연결 상태·상대 장치 오류 확인",
    "WORKFLOW_NVLINK5_ERR": "세부 오류값·드라이버 버전별 NVLink 조치 확인",
}


def action(entry, steps):
    immediate = (entry or {}).get("immediate_action") or ""
    if immediate.startswith("WORKFLOW_"):
        return WORKFLOWS.get(immediate, "동반 오류와 복구 조건 확인")
    if immediate in ACTIONS:
        return ACTIONS[immediate]
    if (entry or {}).get("fm_sxid_table") in FM_TABLES:
        return FM_TABLES[entry["fm_sxid_table"]] + " · 런북 판단"
    judged = next((s for s in steps if s.startswith("판단")), "")
    return (
        CHECKS.get((entry or {}).get("code"))
        or judged
        or "원문·발생 장치와 작업 영향 확인"
    )


def names(title):
    title = re.sub(r"\s*\(Fleet [^)]+\)$", "", title)
    title = re.sub(r"^(?:S?XID|S?Xid|SXid) \d+\s*", "", title)
    if " · " in title:
        detail, name = title.rsplit(" · ", 1)
    else:
        detail, name = "", title
    name = re.sub(r"\s*조사$", "", name)
    return ("NVSwitch 오류" if name == "NVSwitch" else name), detail


def build():
    manifest = json.loads((runbooks / "catalog-manifest.json").read_text("utf-8"))
    entries = {e["knowledge_key"]: e for e in manifest["entries"]}
    labels = {}
    for path in sorted(runbooks.rglob("RB-*.json")):
        row = json.loads(path.read_text("utf-8"))
        content, key = row["content"], row["knowledge_key"]
        search = content.get("search", {})
        keys = search.get("codes") or (
            [f"component:{c}" for c in search.get("producer_events", [])]
            if path.parent.name == "component"
            else []
        )
        if not keys:
            continue
        steps = [
            s["title"]
            for s in content["operator_guidance"]["next_checks"]
            if not s["title"].startswith("알림이 가리키는")
        ]
        name, detail = names(content["title"])
        aliases = search.get("aliases") or [""]
        detail = detail or (aliases[0] if re.fullmatch(r"[ -~]+", aliases[0]) else "")
        for code in keys:
            labels[code] = {
                "name": name,
                "detail": detail,
                "action": action(entries.get(key), steps),
                "steps": steps,
            }
            # Reviewed exceptions to the received Reserved label. Keep source
            # aliases and stored alert text untouched; expose catalog guidance.
            if code.startswith("xid:") and (
                code == "xid:173"
                or entries.get(key, {}).get("source_status") == "unused_or_legacy"
                or any(
                    any(
                        f"Fleet 고정 카탈로그: {value};" in line
                        for value in ("Reserved", "Unused")
                    )
                    for line in content.get("analysis_guidance", [])
                )
            ):
                labels[code]["official"] = {
                    "name": name,
                    "meaning": content["operator_guidance"]["meaning"],
                    "source": (
                        next(
                            s["url"]
                            for s in content["sources"]
                            if "/NVIDIA/open-gpu-kernel-modules/" in s["url"]
                            and "/nverror.h" in s["url"]
                        )
                        if code == "xid:173"
                        else "https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html"
                    ),
                }
    return dict(sorted(labels.items()))


if __name__ == "__main__":
    destination.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(destination)
