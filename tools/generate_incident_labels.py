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


def action(entry, steps):
    immediate = (entry or {}).get("immediate_action") or ""
    if immediate.startswith("WORKFLOW_"):
        return f"조건별 절차 ({immediate})"
    if immediate in ACTIONS:
        return ACTIONS[immediate]
    if (entry or {}).get("fm_sxid_table") in FM_TABLES:
        return FM_TABLES[entry["fm_sxid_table"]] + " · 런북 판단"
    judged = next((s for s in steps if s.startswith("판단")), "")
    return judged or "런북 순서대로 확인"


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
    return dict(sorted(labels.items()))


if __name__ == "__main__":
    destination.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(destination)
