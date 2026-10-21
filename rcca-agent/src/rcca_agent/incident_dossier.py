"""RCA-only bounded collection and deterministic comparisons of recorded reports."""

from collections import defaultdict
from copy import copy, deepcopy
from datetime import datetime, timezone
import json
import math
import re

from agent_common.contracts import timestamp
from agent_common.observation import series, usable_observation
from agent_common.parsers import ERROR_CODE, log_entries

from .fleet_events import object_value, pci


METRICS = {
    "D02": "GPU 사용률",
    "D11": "GPU 전력",
    "D44": "PCIe replay 누적값",
    "D47": "GPU별 Fabric Manager 상태 코드",
    "D33": "NVLink 수신량",
    "D34": "NVLink 송신량",
}
ADDRESSES = re.compile(r"PCI:[0-9a-f]{4,8}:[0-9a-f]{2}:[0-9a-f]{2}(?:\.[0-7])?", re.I)
ERROR_FILTER = (
    ' | json rca_component="attributes[\\"component\\"]"'
    ' | rca_component=~"accelerator-nvidia-error-(xid|sxid)"'
)


def error_tools(tools):
    result = copy(tools)
    original = result["query_loki_logs"]

    async def logs(args):
        args["logql"] += ERROR_FILTER
        return await original(args)

    result["query_loki_logs"] = logs
    return result


def enabled(books):
    """New authoring revisions opt in through their explicit required observation plan."""
    return any(
        (book.get("knowledge_key"), marker)
        in {("RB-XID-79", "D44"), ("RB-SXID-11001", "D47")}
        for book in books
        for marker in book["content"].get("required_queries", [])
    )


def iso(value):
    return (
        datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    )


def current_data(data, cutoff):
    result = deepcopy(data)
    end = min(timestamp(data["time_range"]["end"]), timestamp(cutoff))
    result["time_range"] = {"start": iso(end - 1800), "end": iso(end)}
    # Preserve the authorized machine/node/cluster, collect both error families
    # and adjacent Fleet context instead of filtering to the alert component.
    result["log_query_target"].pop("component", None)
    for key in ("node", "machine_id"):
        if result.get("target", {}).get(key):
            result["log_query_target"][key] = result["target"][key]
    return result


def log_records(evidence, data):
    """Keep source positions; repeated receptions never become failure counts."""
    target = data.get("target", {})
    clusters = {c["cluster_id"] for c in data["scope"]["clusters"]}
    records, seen = [], set()
    for e in evidence:
        if e.get("query_id") != "D09" or not usable_observation(e):
            continue
        if e.get("cluster_id") not in clusters:
            continue
        period = e["quality"].get("request_time_range", e["time_range"])
        for index, (ns, line) in enumerate(log_entries(e["snapshot"])):
            raw = object_value(line)
            attrs, resources = (
                object_value(raw.get("attributes")),
                object_value(raw.get("resources")),
            )
            node, machine = resources.get("k8s.node.name"), resources.get("machine.id")
            if (
                not node
                or not machine
                or not (target.get("node") or target.get("machine_id"))
            ):
                continue
            if any(
                target.get(k) and target[k] != v
                for k, v in (("node", node), ("machine_id", machine))
            ):
                continue
            try:
                recorded = int(ns) / 1e9
                if (
                    not timestamp(period["start"])
                    <= recorded
                    <= timestamp(period["end"])
                ):
                    continue
            except (TypeError, ValueError, OverflowError):
                continue
            extra = object_value(attrs.get("extra_info"))
            detail = object_value(extra.get("data"))
            message = (
                detail.get("raw_kmsg") or attrs.get("reason") or raw.get("body", "")
            )
            if not isinstance(message, str):
                continue
            codes = {(k.lower(), int(n)) for k, n in ERROR_CODE.findall(message)}
            for kind in ("xid", "sxid"):
                if type(detail.get(kind)) is int and detail[kind] > 0:
                    codes.add((kind, detail[kind]))
            if len(codes) != 1:
                continue
            kind, code = next(iter(codes))
            if attrs.get("component") != "accelerator-nvidia-error-" + kind:
                continue
            device = detail.get("device_uuid") or extra.get("device_uuid")
            addresses = set(ADDRESSES.findall(message))
            if not device and len(addresses) == 1:
                device = next(iter(addresses))
            if not isinstance(device, str):
                continue
            gpu = None
            inventory = resources.get("gpuInfo.gpus", [])
            if isinstance(inventory, str):
                try:
                    inventory = json.loads(inventory)
                except ValueError:
                    inventory = []
            if kind == "xid" and isinstance(inventory, list):
                matches = {
                    g.get("uuid")
                    for g in inventory
                    if isinstance(g, dict)
                    and isinstance(g.get("uuid"), str)
                    and pci(device)
                    and pci(g.get("busID"))
                    and pci(device)[:3] == pci(g["busID"])[:3]
                }
                if len(matches) == 1:
                    gpu = next(iter(matches))
            event_time = detail.get("time")
            try:
                event_time = (
                    iso(timestamp(event_time)) if timestamp(event_time) > 0 else None
                )
            except (ValueError, TypeError, AttributeError):
                event_time = None
            identity = (e["cluster_id"], ns, line)
            if identity in seen:
                continue
            seen.add(identity)
            records.append(
                dict(
                    cluster=e["cluster_id"],
                    node=node,
                    machine=machine,
                    code=f"{kind}:{code}",
                    device=device,
                    gpu=gpu,
                    message=message,
                    recorded_at=iso(recorded),
                    event_time=event_time,
                    event_id=attrs.get("event_id"),
                    kind=attrs.get("log_type"),
                    refs=[e["id"]],
                    position=index,
                )
            )
    return sorted(records, key=lambda r: (r["recorded_at"], r["code"], r["device"]))


def same_device(left, right):
    if (left["cluster"], left["machine"], left["node"]) != (
        right["cluster"],
        right["machine"],
        right["node"],
    ):
        return False
    if left["code"].startswith("xid:"):
        # Historical GPU identity must survive PCI reuse/replacement.
        return bool(left["gpu"] and right["gpu"] and left["gpu"] == right["gpu"])
    return bool(pci(left["device"]) and pci(left["device"]) == pci(right["device"]))


def comparison_targets(data, clues, current):
    records = log_records(current, data)
    targets = [r for r in records if r["code"] in clues.get("error_codes", [])]
    # Do not guess one of several devices from a node-wide log batch.
    addresses = set(ADDRESSES.findall(clues.get("reason", "")))
    if len(addresses) == 1:
        address = pci(next(iter(addresses)))
        targets = [
            r
            for r in targets
            if pci(r["device"])
            and pci(r["device"])[: 3 if r["code"].startswith("xid:") else 4]
            == address[: 3 if r["code"].startswith("xid:") else 4]
        ]
    if len({(r["code"], r["gpu"] or pci(r["device"])) for r in targets}) > 1:
        targets = []
    return {"targets": targets}


def metric_host_matches(target, labels):
    node = target.get("node") or target.get("k8s_node_name")
    machine = target.get("machine_id")
    if node and labels.get("node") != node:
        return False
    if machine and labels.get("machine_id") and labels["machine_id"] != machine:
        return False
    return bool(node or (machine and labels.get("machine_id") == machine))


def operator_view(data, evidence, comparison):
    groups = defaultdict(list)
    for row in log_records(evidence, data):
        groups[(row["code"], row["device"], row["message"])].append(row)
    logs = [
        {
            "code": code,
            "device": device,
            "message": message,
            "first": group[0]["recorded_at"],
            "last": group[-1]["recorded_at"],
            "reports": len(group),
            "evidence_refs": sorted({ref for row in group for ref in row["refs"]}),
        }
        for (code, device, message), group in groups.items()
    ]
    metrics = []
    targets = comparison.get("targets", [])
    switch = any(t["code"].startswith("sxid:") for t in targets)
    for entry in evidence:
        if entry["query_id"] not in METRICS or not usable_observation(entry):
            continue
        for metric in series([entry]):
            labels = metric["labels"]
            gpu = labels.get("gpu_uuid", labels.get("uuid", labels.get("UUID")))
            if metric["cluster_id"] not in {
                c["cluster_id"] for c in data["scope"]["clusters"]
            }:
                continue
            if not metric_host_matches(data["target"], labels):
                continue
            if not switch and not any(t["gpu"] and t["gpu"] == gpu for t in targets):
                continue
            values = []
            for at, value in metric["samples"]:
                try:
                    at, value = float(at), float(value)
                    if math.isfinite(value) and timestamp(
                        data["time_range"]["start"]
                    ) <= at <= timestamp(data["time_range"]["end"]):
                        values.append((at, value))
                except (ValueError, TypeError):
                    pass
            values = sorted(set(values))
            if values:
                metrics.append(
                    {
                        "query_id": entry["query_id"],
                        "name": METRICS[entry["query_id"]],
                        "gpu_uuid": gpu,
                        "unit": metric.get("unit"),
                        "min": min(v for _, v in values),
                        "max": max(v for _, v in values),
                        "last_value": values[-1][1],
                        "samples": len(values),
                        "first": iso(values[0][0]),
                        "last": iso(values[-1][0]),
                        "evidence_refs": [entry["id"]],
                    }
                )
    return {
        "schema": "rca-triage-observations/1",
        "target": data["target"],
        "period": data["time_range"],
        "logs": logs,
        "metrics": metrics,
        "metric_scope": "node_gpu_context" if switch else "reported_gpu",
    }


def dossier_summary(data, current, comparison):
    """Fixed report material remains useful even when every model call fails."""
    rows = []

    def add(section, text, refs):
        rows.append(
            {"section": section, "text": text, "evidence_refs": sorted(set(refs))}
        )

    refs = [e["id"] for e in current]
    period = data["time_range"]
    add(
        "investigation",
        f"이번 조회 범위: {period['start']} ~ {period['end']} (UTC), 알림 대상 노드. "
        "다른 노드의 집중도는 조회하지 않았습니다. 기록 순서는 원인 순서를 뜻하지 않습니다.",
        refs,
    )
    records = log_records(current, data)
    if records:
        add(
            "investigation",
            "로그 기록 순서: "
            + " → ".join(
                f"{r['recorded_at']} {r['code'].upper()} {r['device']}"
                for r in records[:24]
            )
            + (". 이후 기록은 연결된 전체 원문 참조." if len(records) > 24 else "."),
            [ref for r in records for ref in r["refs"]],
        )
    groups = defaultdict(list)
    for r in records:
        groups[(r["code"], r["device"], r["message"], r["kind"])].append(r)
    for (code, device, message, kind), group in groups.items():
        identifiers = {
            ("id", r["event_id"]) if r["event_id"] else ("time", r["event_time"])
            for r in group
            if r["event_id"] or r["event_time"]
        }
        text = (
            f"{code.upper()} · {group[0]['node']} · {group[0]['gpu'] or device}: "
            f"{group[0]['recorded_at']} ~ {group[-1]['recorded_at']}에 보고 {len(group)}건 수신. "
        )
        text += (
            f"이벤트 식별자 우선·발생 시각 보조로 구분한 보고 {len(identifiers)}개(장애 횟수 아님). "
            if identifiers
            else (
                "동일 내용의 반복 보고이며 별개 신규 장애 횟수로 세지 않습니다. "
                if len(group) > 1
                else "사건 식별 정보가 없는 상태 보고이며 별개 신규 장애로 세지 않습니다. "
            )
        )
        text += f"원문 발췌: {message[:700]}" + (
            " [발췌 생략; 전체 원문은 연결 근거에 보존]" if len(message) > 700 else ""
        )
        add("problem", text, [ref for r in group for ref in r["refs"]])
    history, previous = comparison.get("history", []), comparison.get("previous", [])
    matched = comparison.get("matched", [])
    hp = comparison.get("history_period")
    if hp:
        dates = sorted({r["recorded_at"][:10] for r in matched})
        text = f"과거 조회: {hp['start']} ~ {hp['end']} (UTC). "
        text += (
            f"동일 대상·동일 코드로 연결된 이벤트 보고 {len(matched)}건"
            if any(
                t["gpu"] or t["code"].startswith("sxid:")
                for t in comparison.get("targets", [])
            )
            else "이번 구간에서 대상을 대응하지 못해 동일 장치의 이력 비교를 보류했습니다"
        )
        text += " (" + ", ".join(dates) + ")" if dates else ""
        text += ". 이는 조회된 보고 건수이며 실제 장애 횟수·재부팅 횟수가 아닙니다."
        add("comparison", text, [e["id"] for e in history])
    for label, entries in (
        ("이번", current),
        ("과거", history),
        ("이전 비교", previous),
    ):
        failed = [
            e
            for e in entries
            if not usable_observation(e) and e["tool_status"] != "empty"
        ]
        if failed:
            add(
                "comparison",
                f"{label} 조회 일부가 실패하거나 제한에 도달했습니다. 표시된 보고 건수와 값은 전체 기간의 완전한 집계가 아닙니다.",
                [e["id"] for e in failed],
            )
    if previous:
        old = log_records(previous, data)
        old_codes, new_codes = {r["code"] for r in old}, {r["code"] for r in records}
        pp = previous[0]["time_range"]
        add(
            "comparison",
            f"이전 비교 구간: {pp['start']} ~ {pp['end']} (UTC). "
            f"같은 노드에서 조회된 오류 코드: 이전 {', '.join(sorted(old_codes)) or '없음'}, "
            f"이번 {', '.join(sorted(new_codes)) or '없음'}. "
            f"이번 결과에만 보이는 코드: {', '.join(sorted(new_codes - old_codes)) or '없음'}. "
            "수집 범위에서의 차이이며 원인이나 새 장애 판정이 아닙니다.",
            [e["id"] for e in previous + current if e["query_id"] == "D09"],
        )
        old_messages = {r["message"] for r in old}
        for r in records:
            if r["message"] not in old_messages:
                old_messages.add(r["message"])
                add(
                    "comparison",
                    f"이전 결과에 없던 보고 문구 ({r['code'].upper()}, {r['device']}): {r['message'][:700]}",
                    r["refs"],
                )
    for label, entries in (("이번", current), ("이전", previous)):
        for e in entries:
            q = e["query_id"]
            if q not in METRICS:
                continue
            metrics = series([e]) if usable_observation(e) else []
            matched_series = []
            for metric in metrics:
                labels = metric["labels"]
                target = data.get("target", {})
                if metric["cluster_id"] not in {
                    c["cluster_id"] for c in data["scope"]["clusters"]
                }:
                    continue
                if not metric_host_matches(target, labels):
                    continue
                gpu = labels.get("gpu_uuid", labels.get("uuid", labels.get("UUID")))
                # SXID: GPU metrics are node context, never switch/port measurements.
                targets = comparison.get("targets", [])
                sxid = any(t["code"].startswith("sxid:") for t in targets)
                if not sxid and not any(t["gpu"] and t["gpu"] == gpu for t in targets):
                    continue
                values = []
                for t, v in metric["samples"]:
                    try:
                        t, v = float(t), float(v)
                        if (
                            math.isfinite(v)
                            and math.isfinite(t)
                            and timestamp(e["time_range"]["start"])
                            <= t
                            <= timestamp(e["time_range"]["end"])
                        ):
                            values.append((t, v))
                    except (ValueError, TypeError):
                        pass
                values = sorted(set(values))
                if not values:
                    continue
                matched_series.append(metric)
                numbers = [v for _, v in values]
                gaps = [b[0] - a[0] for a, b in zip(values, values[1:])]
                text = (
                    f"{label} {METRICS[q]} · {gpu or '장치 식별자 없음'}: "
                    f"{iso(values[0][0])} ~ {iso(values[-1][0])}, {len(values)}개 기록, "
                    f"최소 {min(numbers):g}, 최대 {max(numbers):g} {metric.get('unit') or ''}."
                )
                if gaps:
                    text += f" 기록 사이 최대 간격 {max(gaps):g}초; 조회 구간 전체의 연속 관측을 보장하지 않습니다."
                if q == "D44":
                    text += " 누적값이며 reset·공백 검증 없이 사건 증가량이나 AER로 해석하지 않습니다."
                if sxid:
                    text += " 같은 노드 GPU의 참고값이며 스위치·포트 상태가 아닙니다."
                add("comparison", text, [e["id"]])
            if not matched_series:
                add(
                    "comparison",
                    f"{label} {METRICS[q]}: 대상에 연결 가능한 측정 기록을 확보하지 못했습니다 (빈 결과·조회 상태·장치 대응은 연결 근거 참조).",
                    [e["id"]],
                )
    return rows
