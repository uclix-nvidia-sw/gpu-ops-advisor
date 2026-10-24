"""RCA-only bounded collection and deterministic comparisons of recorded reports."""

from collections import Counter, defaultdict
from copy import copy, deepcopy
from datetime import datetime, timezone
import json
import math
import re

from agent_common.contracts import timestamp
from agent_common.observation import series, usable_observation
from agent_common.parsers import ERROR_CODE, log_entries

from .fleet_events import object_value, pci
from .analysis_values import compact_brief, register_values


METRICS = {
    "D02": "GPU 사용률",
    "D03": "GPU 메모리 사용량",
    "D04": "GPU 온도",
    "D11": "GPU 전력",
    "D23": "GPU 메모리 온도",
    "D36": "정정 가능 ECC(SBE) 휘발성 누적값",
    "D38": "정정 가능 ECC(SBE) 영구 누적값",
    "D40": "정정 불가 ECC(DBE) 휘발성 누적값",
    "D42": "정정 불가 ECC(DBE) 영구 누적값",
    "D44": "PCIe replay 누적값",
    "D45": "클록 제한 사유 비트마스크",
    "D47": "GPU별 Fabric Manager 상태 코드",
    "D48": "적용 전력 한도",
    "D33": "NVLink 수신량",
    "D34": "NVLink 송신량",
    "D50": "행 재매핑 대기",
    "D51": "행 재매핑 실패",
    "D52": "정정 불가 재매핑 행 수",
    "D53": "정정 가능 재매핑 행 수",
    "D54": "예비 행 없는 메모리 뱅크 수",
    "D55": "NVLink CRC 오류 누적값",
    "D56": "NVLink 복구 오류 누적값",
    "D57": "NVLink 재전송 오류 누적값",
    "D58": "InfoROM 설정 유효",
    "D59": "디스크 사용량",
    "D60": "디스크 여유 공간",
    "D61": "열 제한 누적 시간",
    "D62": "전력 제한 누적 시간",
}
COUNTERS = {
    "D36",
    "D38",
    "D40",
    "D42",
    "D44",
    "D52",
    "D53",
    "D55",
    "D56",
    "D57",
    "D61",
    "D62",
}
# Coded values: compare equality only, never magnitude or health.
ENUMS = {"D45", "D47", "D50", "D51", "D58"}
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
    """XID/SXID revisions opt in by requiring a report metric; legacy D09-only stays."""
    return any(
        any(
            c.startswith(("xid:", "sxid:"))
            for c in content.get("search", {}).get("codes", [])
        )
        and any(q in METRICS for q in content.get("required_queries", []))
        for content in (book["content"] for book in books)
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


def state_onset(health, target, codes):
    """Bracket the first Unhealthy report by the last Healthy one (Loki record time)."""
    node = target.get("node") or target.get("k8s_node_name")
    for code in codes:
        component = "accelerator-nvidia-error-" + code.split(":")[0]
        rows = sorted(
            (
                h
                for h in health
                if h.get("component") == component
                and h.get("observed_at")
                and isinstance(h.get("raw_health"), str)
                and (not node or h.get("target", {}).get("node") == node)
            ),
            key=lambda h: timestamp(h["observed_at"]),
        )
        bad = [
            h
            for h in rows
            if h["raw_health"].lower() != "healthy" and h.get("error_code") == code
        ]
        if not bad:
            continue
        first = timestamp(bad[0]["observed_at"])
        good = [
            h
            for h in rows
            if h["raw_health"].lower() == "healthy"
            and timestamp(h["observed_at"]) < first
        ]
        return {
            "code": code,
            "time_basis": "loki_recorded_at",
            "last_healthy_at": good[-1]["observed_at"] if good else None,
            "first_unhealthy_at": bad[0]["observed_at"],
            "evidence_refs": sorted(
                {r for h in good[-1:] + bad[:1] for r in h.get("evidence_refs", [])}
            ),
        }
    return None


# DCGM exporter labels; recorded as observed, never as allocation or ownership.
WORKLOAD_LABELS = ("namespace", "pod", "container")
# DCGM exporter and Fleet exporters name the same facts differently.
GPU_LABELS = {
    "model": ("modelName", "model_name"),
    "driver": ("DCGM_FI_DRIVER_VERSION",),
    "pci_bus_id": ("pci_bus_id",),
    "gpu_index": ("gpu",),
}
# Only DCGM exporter series carry the Kubernetes pod mapping.
POD_LABEL_SOURCE = "DCGM_FI_DRIVER_VERSION"


def metric_rows(data, evidence, boundary, keep):
    """Per (query, GPU or mount) before/after rows, node GPU labels and observed pods.

    `keep(gpu)` limits rows to the devices the report covers; labels and pods always
    cover the whole node.
    """
    start, end = (
        timestamp(data["time_range"]["start"]),
        timestamp(data["time_range"]["end"]),
    )
    # One row per (query, GPU): exporters split a GPU's series by workload labels.
    merged, workloads, gpus = {}, {}, {}
    pod_labels = False
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
            values = set()
            for at, value in metric["samples"]:
                try:
                    at, value = float(at), float(value)
                    if math.isfinite(value) and start <= at <= end:
                        values.add((at, value))
                except (ValueError, TypeError):
                    pass
            if not values:
                continue
            # GPU and pod labels cover the whole node: a pod may span the alert GPU
            # and others, and neighbours give context. Metrics stay per alert GPU.
            if gpu:
                info = gpus.setdefault(gpu, {})
                for key, names in GPU_LABELS.items():
                    for label in names:
                        if isinstance(labels.get(label), str) and labels[label]:
                            info.setdefault(key, labels[label])
            work = tuple(labels.get(k) for k in WORKLOAD_LABELS)
            pod_labels = pod_labels or POD_LABEL_SOURCE in labels or bool(work[1])
            if gpu and work[1]:
                times = [t for t, _ in values]
                seen = workloads.setdefault((gpu, work), [min(times), max(times)])
                seen[0], seen[1] = min(seen[0], *times), max(seen[1], *times)
            if not keep(gpu):
                continue
            # Node-level series (disk) are told apart by mount, not by GPU.
            mount = None if gpu else labels.get("mount_point")
            row = merged.setdefault(
                (entry["query_id"], gpu, mount),
                {"values": set(), "unit": metric.get("unit"), "refs": set()},
            )
            row["values"] |= values
            row["refs"].add(entry["id"])
    metrics = []
    for (query_id, gpu, mount), row in merged.items():
        values = sorted(row["values"])
        windows = {}
        for label, selected in (
            ("before", [(t, v) for t, v in values if t < boundary]),
            ("at_or_after", [(t, v) for t, v in values if t >= boundary]),
        ):
            windows[label] = (
                {
                    "samples": len(selected),
                    "min": min(v for _, v in selected),
                    "max": max(v for _, v in selected),
                    "first_value": selected[0][1],
                    "last_value": selected[-1][1],
                    "first": iso(selected[0][0]),
                    "last": iso(selected[-1][0]),
                }
                if selected
                else None
            )
        metrics.append(
            {
                "query_id": query_id,
                "name": METRICS[query_id] + (f" ({mount})" if mount else ""),
                "gpu_uuid": gpu,
                **({"mount_point": mount} if mount else {}),
                "unit": row["unit"],
                "min": min(v for _, v in values),
                "max": max(v for _, v in values),
                "last_value": values[-1][1],
                "incident_windows": windows,
                "max_sample_gap_seconds": max(
                    (b[0] - a[0] for a, b in zip(values, values[1:])),
                    default=None,
                ),
                "kind": "enum"
                if query_id in ENUMS
                else "counter"
                if query_id in COUNTERS
                else "gauge",
                "enum_mapping": None if query_id in ENUMS else {},
                "samples": len(values),
                "first": iso(values[0][0]),
                "last": iso(values[-1][0]),
                "evidence_refs": sorted(row["refs"]),
            }
        )
    observed = {
        "gpus": [{"gpu_uuid": g, **info} for g, info in sorted(gpus.items())],
        "workloads": [
            {
                "gpu_uuid": gpu,
                **dict(zip(WORKLOAD_LABELS, work)),
                "first": iso(seen[0]),
                "last": iso(seen[1]),
                "label_basis": "dcgm_exporter_labels",
            }
            for (gpu, work), seen in sorted(workloads.items(), key=lambda x: x[1][0])
        ],
        # None: no series could show pods, so an empty list does not mean "no pods".
        "workload_label_source": "dcgm_exporter_labels" if pod_labels else None,
    }
    return metrics, observed


def operator_view(data, evidence, comparison, health=()):
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
            "event_times": sorted({r["event_time"] for r in group if r["event_time"]}),
            "evidence_refs": sorted({ref for row in group for ref in row["refs"]}),
        }
        for (code, device, message), group in groups.items()
    ]
    targets = comparison.get("targets", [])
    switch = any(t["code"].startswith("sxid:") for t in targets)
    boundary = timestamp(event_boundary(data, targets)[0])
    metrics, observed = metric_rows(
        data,
        evidence,
        boundary,
        lambda gpu: switch or any(t["gpu"] and t["gpu"] == gpu for t in targets),
    )
    return {
        "schema": "rca-triage-observations/1",
        "target": data["target"],
        "period": data["time_range"],
        "event_boundary": event_boundary(data, targets)[0],
        "boundary_basis": event_boundary(data, targets)[1],
        "alert_time": data["incident_time"],
        "logs": logs,
        "switch_pci": comparison.get("switch_pci", []),
        "metrics": metrics,
        "metric_scope": "node_gpu_context" if switch else "reported_gpu",
        "onset": state_onset(
            health, data["target"], sorted({row["code"] for row in logs})
        ),
        **observed,
    }


def component_metrics(books):
    """Component Runbooks whose plan names a report metric get stored metric rows."""
    return any(
        book.get("knowledge_key", "").startswith("RB-COMPONENT-")
        and any(
            s.get("query_id") in METRICS
            for s in book["content"].get("observation_plan", [])
        )
        for book in books
    )


def component_view(data, evidence, health, component):
    """Metric rows for a component alert, split at its first Unhealthy report.

    Component reports name a component and node, not a device, so rows cover every
    GPU (or mount) on the node; the Fleet reports themselves stay in the result.
    """
    node = data["target"].get("node") or data["target"].get("k8s_node_name")
    bad = sorted(
        (
            h
            for h in health
            if h.get("component") == component
            and h.get("observed_at")
            and str(h.get("raw_health")).lower() == "unhealthy"
            and (not node or h.get("target", {}).get("node") == node)
        ),
        key=lambda h: timestamp(h["observed_at"]),
    )
    boundary, basis = (
        (bad[0]["observed_at"], "loki_recorded_at")
        if bad
        else (data["incident_time"], "alert_time")
    )
    metrics, observed = metric_rows(
        data, evidence, timestamp(boundary), lambda gpu: True
    )
    return {
        "schema": "rca-component-observations/1",
        "component": component,
        "event_boundary": boundary,
        "boundary_basis": basis,
        "metrics": metrics,
        "metric_scope": "node_gpu_context",
        **observed,
    }


def dossier_summary(data, current, comparison):
    """Fixed report material remains useful even when every model call fails."""
    rows = []

    def add(section, text, refs, *, detail_only=False):
        rows.append(
            {
                "section": section,
                "text": text,
                "evidence_refs": sorted(set(refs)),
                "detail_only": detail_only,
            }
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
            detail_only=True,
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
        add(
            "problem", text, [ref for r in group for ref in r["refs"]], detail_only=True
        )
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
                if q in ENUMS:
                    text += " 열거형 상태 코드이며 의미 매핑 없이 정상·비정상 또는 심각도로 해석하지 않습니다."
                if q == "D44":
                    text += " 누적값이며 reset·공백 검증 없이 사건 증가량이나 AER로 해석하지 않습니다."
                elif q in COUNTERS:
                    text += " 누적값이며 reset·공백 검증 없이 사건 증가량으로 해석하지 않습니다."
                if sxid:
                    text += " 같은 노드 GPU의 참고값이며 스위치·포트 상태가 아닙니다."
                add("comparison", text, [e["id"]], detail_only=True)
            if not matched_series:
                add(
                    "comparison",
                    f"{label} {METRICS[q]}: 대상에 연결 가능한 측정 기록을 확보하지 못했습니다 (빈 결과·조회 상태·장치 대응은 연결 근거 참조).",
                    [e["id"]],
                )
    return rows


def incident_brief(data, current, comparison, history):
    """Compact comparisons from complete scoped series, before model sampling."""
    view = operator_view(data, current, comparison)
    result = []
    for metric in view["metrics"]:
        result.append(
            {
                **metric,
                "type": "metric_comparison",
                "scope": view["metric_scope"],
                "boundary": view["event_boundary"],
                "boundary_basis": view["boundary_basis"],
                "interpretation_limits": (
                    "Enum mapping unavailable; no health or severity inference."
                    if metric["kind"] == "enum"
                    else "Cumulative counter; resets and gaps prevent an incident increment claim."
                    if metric["kind"] == "counter"
                    else "Recorded values; no inference of continuous coverage, health or causation."
                ),
            }
        )
    for log in view["logs"]:
        result.append(
            {**log, "type": "log_report_group", "count_basis": "reports_not_incidents"}
        )
    if history:
        previous = [r for r in history["rows"] if not r["current"]]
        for code in sorted({c for r in history["rows"] for c in r["codes"]}):
            rows = [r for r in previous if code in r["codes"]]
            result.append(
                {
                    "type": "host_history",
                    "code": code,
                    "period": history["period"],
                    "complete": history["complete"],
                    "previous_incidents": len(rows),
                    "current_excluded": True,
                    "count_basis": "incident_id",
                    "device_counts": dict(
                        Counter(
                            r.get("device") or r["gpu_uuid"] or "node" for r in rows
                        )
                    ),
                    "latest_previous": rows[0]["occurred_at"] if rows else None,
                    "evidence_refs": history["evidence_refs"],
                }
            )
    if history:
        targets = comparison.get("targets", [])
        for row in history["rows"]:
            if row["current"] or not row.get("prior_rca"):
                continue
            matched = any(
                t["code"] in row["codes"]
                and (
                    (t["gpu"] and t["gpu"] == row["gpu_uuid"])
                    or (
                        t["code"].startswith("sxid:")
                        and pci(t["device"])
                        == pci((row.get("device") or "").removeprefix("NVSwitch "))
                    )
                )
                for t in targets
            )
            if matched:
                result.append(
                    {
                        "type": "prior_rca",
                        "occurred_at": row["occurred_at"],
                        "device": row.get("device"),
                        "codes": row["codes"],
                        "report": row["prior_rca"],
                        "evidence_refs": history["evidence_refs"],
                        "interpretation_limits": "Previous report claims are hypotheses, not new observations or performed actions.",
                    }
                )
    result.extend(comparison.get("switch_pci", []))
    return register_values(compact_brief(result))


def event_boundary(data, targets):
    """A unique producer event time takes precedence over alert receipt time."""
    times = {r["event_time"] for r in targets if r.get("event_time")}
    if len(times) == 1:
        return next(iter(times)), "producer_event_time"
    return data["incident_time"], "alert_time"
