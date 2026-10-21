"""Explain scoped comparisons from full collected evidence, before model truncation."""

from datetime import datetime
import math

from agent_common.observation import series, usable_observation

from .fleet_events import pci
from .requirement_diagnostics import _scoped_reports

QUERY_NAMES = {
    "D09": "오류·상태 로그",
    "D02": "GPU 목록과 사용률",
    "D11": "GPU 전력",
    "D44": "PCIe 재전송 횟수",
    "D47": "GPU별 Fabric Manager 상태 코드",
    "D33": "NVLink 수신량",
    "D34": "NVLink 송신량",
    "D13": "보조 원본 로그",
}


def at(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def investigation_summary(data, evidence, health, events):
    """Describe recorded evidence only; never infer current health or physical absence."""
    reports, events = _scoped_reports(health, events, data)
    collected = [
        e
        for e in evidence
        if e.get("query_id", "").startswith("D") and usable_observation(e)
    ]
    if not collected:
        return []
    rows = []

    def add(section, text, refs):
        rows.append(dict(section=section, text=text, evidence_refs=sorted(set(refs))))

    query_ids = list(dict.fromkeys(e["query_id"] for e in collected))
    add(
        "investigation",
        "알림이 어떤 장치의 어떤 오류를 가리키는지 확인하기 위해, "
        "알림 내용과 같은 서버·조사 시간대에 수집된 기록을 비교했습니다. "
        "이번에 조회한 자료는 "
        + ", ".join(QUERY_NAMES.get(q, "추가 관측 자료") for q in query_ids)
        + "입니다.",
        [e["id"] for e in collected],
    )
    node = data.get("target", {}).get("node") or data.get("target", {}).get(
        "k8s_node_name"
    )
    clusters = {c["cluster_id"] for c in data.get("scope", {}).get("clusters", [])}
    metrics = [
        row
        for row in series(collected)
        if node
        and row["labels"].get("node", row["labels"].get("Hostname")) == node
        and row.get("cluster_id") in clusters
    ]
    # A GPU inventory cannot establish whether an NVSwitch exists.
    for address in sorted(
        {
            e["reported_device"]
            for e in events
            if e.get("error_code", "").startswith("xid:")
            and pci(e.get("reported_device"))
        }
    ):
        event_rows = [e for e in events if e.get("reported_device") == address]
        component = event_rows[0].get("component")
        inventories = [
            r
            for r in reports
            if r.get("component") == component and r.get("gpu_candidates")
        ]
        inventory_pci = {
            pci(g.get("bus_id"))[:3]
            for r in inventories
            for g in r["gpu_candidates"]
            if pci(g.get("bus_id"))
        }
        metric_pci = {
            pci(r["labels"].get("pci_bus_id"))[:3]
            for r in metrics
            if pci(r["labels"].get("pci_bus_id"))
        }
        target = pci(address)[:3]
        refs = [
            ref
            for e in event_rows + inventories + metrics
            for ref in e["evidence_refs"]
        ]
        if inventory_pci and target not in inventory_pci:
            text = (
                f"오류 로그가 가리키는 GPU를 찾기 위해 로그의 주소 {address}를 "
                f"이 서버에서 수집한 GPU 목록({len(inventory_pci)}개 주소)과 비교했습니다. "
                "그 목록에는 해당 주소가 없습니다."
            )
            if metric_pci and target not in metric_pci:
                text += (
                    f" 추가로 조회한 GPU 지표의 장치 주소 {len(metric_pci)}개에도 없습니다. "
                    "지표에 값이 있더라도 다른 GPU의 기록이므로, 오류 로그에 나온 GPU가 "
                    "정상인지 고장인지 판단하는 데 연결할 수 없습니다."
                )
            text += " 먼저 알림·로그에 장치 주소가 올바르게 기록됐는지 확인해야 합니다."
            add("cause", text, refs)
        elif inventory_pci and target in inventory_pci:
            add(
                "cause",
                f"오류 로그의 GPU 주소 {address}는 같은 서버에서 수집한 GPU 목록에 있습니다. "
                "어느 GPU에 관한 보고인지는 연결됐습니다. 이 대조는 오류의 물리적 원인이나 "
                "현재 복구 여부를 확인하는 검사는 아닙니다.",
                refs,
            )
    event_times = [at(e.get("event_time")) for e in events]
    if event_times and all(t is not None for t in event_times):
        # Keep this a recorded-value comparison, never an access/health assertion.
        util_refs = {e["id"] for e in collected if e["query_id"] == "D02"}
        values, addresses, refs = [], set(), set()
        for row in metrics:
            address = pci(row["labels"].get("pci_bus_id"))
            if (
                not address
                or not util_refs.intersection(row["evidence_refs"])
                or row["labels"].get("__name__") != "DCGM_FI_DEV_GPU_UTIL"
            ):
                continue
            for timestamp, value in row["samples"]:
                try:
                    timestamp, value = float(timestamp), float(value)
                except (ValueError, TypeError):
                    continue
                if (
                    math.isfinite(timestamp)
                    and math.isfinite(value)
                    and timestamp > max(event_times)
                    and 0 <= value <= 100
                ):
                    values.append(value)
                    addresses.add(address[:3])
                    refs.update(row["evidence_refs"])
        if values:
            value_range = (
                f"{min(values):g}"
                if min(values) == max(values)
                else f"{min(values):g}~{max(values):g}"
            )
            add(
                "comparison",
                f"오류가 보고된 뒤에도 GPU 사용률 기록이 있는지 조회했습니다. "
                f"수집된 GPU {len(addresses)}개 주소에서 이후 측정 기록 {len(values)}개가 있으며, "
                f"기록된 사용률은 {value_range}%입니다. "
                "이는 지표에 기록된 값의 범위입니다. 위의 장치 주소 대조 결과와 함께 읽어야 하며, "
                "값이 기록됐다는 사실만으로 알림 대상 장치의 정상 동작이나 복구를 뜻하지는 않습니다.",
                list(refs) + [ref for e in events for ref in e["evidence_refs"]],
            )
    for component in sorted({e.get("component", "") for e in events}):
        component_events = [e for e in events if e.get("component") == component]
        baseline = [
            r
            for r in reports
            if r.get("component") == component and r.get("raw_health") == "Healthy"
        ]
        if baseline:
            event_times = [at(e.get("event_time")) for e in component_events]
            report_times = [at(r.get("observed_at")) for r in baseline]
            earlier = all(t is not None for t in event_times + report_times) and max(
                report_times
            ) < min(event_times)
            add(
                "comparison",
                "오류 기록뿐 아니라 같은 점검 항목이 정상(Healthy)으로 보고된 로그도 함께 확인했습니다. "
                + (
                    f"정상 보고 {len(baseline)}건은 모두 오류 이벤트 시각보다 앞서 기록됐습니다. "
                    "오류가 나기 전의 보고이므로, 오류가 난 뒤 다시 정상으로 돌아왔는지를 "
                    "알려주는 자료는 아닙니다."
                    if earlier
                    else "정상 보고가 오류 대상 장치의 복구 확인인지까지는 확인되지 않았습니다. "
                    "다른 장치의 보고이거나 이전 상태를 다시 기록한 것일 수 있으므로, "
                    "정상이라는 문구만으로 알림 대상이 복구됐다고 판단하지 않습니다."
                )
                + " 비교에는 정상 보고가 로그에 기록된 시각과 오류 이벤트에 적힌 발생 시각을 사용했습니다.",
                [
                    ref
                    for r in baseline + component_events
                    for ref in r["evidence_refs"]
                ],
            )
    return rows
