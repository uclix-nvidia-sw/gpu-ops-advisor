"""Structured Fleet event observations; never current-health or Runbook facts."""

import json
import re
import hashlib
from datetime import datetime, timezone

from agent_common.contracts import timestamp
from agent_common.observation import usable_observation
from agent_common.parsers import ERROR_CODE, log_entries
from .decision_trace import check

PCI_TEXT = re.compile(r"PCI:[0-9a-f]{4,8}:[0-9a-f]{2}:[0-9a-f]{2}(?:\.[0-7])?", re.I)
STATUS_UUID = re.compile(r"UUID:(GPU-[0-9a-f-]{36})", re.I)
# Alerts built from Fleet event logs carry the log body: "[Fatal] <component>: " and,
# for SXID, "[Potential Fatal]" precede the reason a state report carries.
EVENT_TAGS = re.compile(r"^(?:\s*\[[^\]]+\]\s*(?:[\w.-]+:)?)+\s*")


def report_reason(text):
    """Reason text without event-log severity and component tags."""
    return EVENT_TAGS.sub("", str(text or "")).strip()


# Keep historical comparison codes readable; current events are matched by target.
# Codes describe evidence gaps, never device-health facts or extra collection.
MISMATCH_CODES = (
    "alert_report_not_found",
    "report_reason_changed",
    "event_not_found",
    "pci_mismatch",
    "multiple_devices",
    "uuid_unresolved",
    "uuid_mismatch",
)


def object_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def pci(value):
    match = re.fullmatch(
        r"(?:PCI:)?([0-9a-f]{4,8}):([0-9a-f]{2}):([0-9a-f]{2})(?:\.([0-7]))?",
        value or "",
        re.I,
    )
    return tuple(int(v, 16) for v in match.groups(default="0")) if match else None


def event_selector(clues):
    """Alert identity is a search selector, never a verified device fact."""
    component = clues.get("component", "")
    kind = component.rsplit("-", 1)[-1]
    codes = clues.get("error_codes", [])
    if (
        kind not in ("xid", "sxid")
        or len(codes) != 1
        or not codes[0].startswith(kind + ":")
    ):
        return {}
    addresses = sorted(set(PCI_TEXT.findall(clues.get("reason", ""))))
    uuids = sorted(set(STATUS_UUID.findall(clues.get("reason", ""))))
    return {
        "component": component,
        "error_code": codes[0],
        "pci": addresses[0] if len(addresses) == 1 else None,
        "gpu_uuid": uuids[0] if kind == "xid" and len(uuids) == 1 else None,
        **{
            k: clues[k]
            for k in ("cluster_id", "machine_id", "k8s_node_name")
            if clues.get(k)
        },
    }


def incident_selector(data):
    from agent_common.contracts import incident_source
    from .incident import alert_clues

    if "incident_snapshot" not in data:
        return {}
    selector = event_selector(alert_clues(incident_source(data["incident_snapshot"])))
    clusters = data.get("scope", {}).get("clusters", [])
    if selector and len(clusters) == 1:
        selector["cluster_id"] = clusters[0]["cluster_id"]
    return selector


def matches_target(row, selector, *, same_code=True):
    """Match producer-reported host/PCI, without treating siblings as conflicts."""
    address = pci(selector.get("pci"))
    if not address or not any(selector.get(k) for k in ("machine_id", "k8s_node_name")):
        return False
    if row.get("component") != selector.get("component"):
        return False
    if selector.get("cluster_id") and row.get("cluster_id") != selector["cluster_id"]:
        return False
    for clue, key in (("machine_id", "machine_id"), ("k8s_node_name", "node")):
        if selector.get(clue) and row.get("target", {}).get(key) != selector[clue]:
            return False
    if same_code and row.get("error_code") != selector.get("error_code"):
        return False
    addresses = (
        [row["reported_device"]]
        if row.get("reported_device")
        else row.get("reported_pci_addresses")
        or PCI_TEXT.findall(row.get("reason") or "")
    )
    width = 3 if selector["component"].endswith("-xid") else 4
    devices = {parsed[:width] for value in addresses if (parsed := pci(value))}
    return devices == {address[:width]}


def event_item(raw, ns, contract, period, target, cluster):
    attributes = object_value(raw.get("attributes"))
    resources = object_value(raw.get("resources"))
    component = attributes.get("component")
    if not isinstance(component, str):
        return None
    kind = contract.get("components", {}).get(component)
    if (
        kind not in ("xid", "sxid")
        or attributes.get("log_type") != "event"
        or attributes.get("event_name") != f"error_{kind}"
        or target.get("component", component) != component
        or raw.get("producer_contract") not in (None, contract["producer_contract"])
    ):
        return None
    identity = {
        "machine_id": resources.get("machine.id"),
        "node": resources.get("k8s.node.name"),
    }
    if not all(isinstance(v, str) and v.strip() for v in identity.values()):
        return None
    requested = {k: target[k] for k in identity if target.get(k)}
    if target.get("k8s_node_name"):
        if requested.get("node", target["k8s_node_name"]) != target["k8s_node_name"]:
            return None
        requested["node"] = target["k8s_node_name"]
    if (
        not requested
        or any(identity[k] != v for k, v in requested.items())
        or not cluster
        or target.get("cluster_id", cluster) != cluster
    ):
        return None
    extra = object_value(attributes.get("extra_info"))
    data = object_value(extra.get("data"))
    if data.get("data_source") != "kmsg":
        return None
    code, at = data.get(kind), data.get("time")
    if type(code) is not int or code <= 0 or code > 2147483647:
        return None
    if any(data.get(other) is not None for other in ("xid", "sxid") if other != kind):
        return None
    try:
        start, end = timestamp(period["start"]), timestamp(period["end"])
        if not start <= timestamp(at) <= end:
            return None
        if not isinstance(ns, str) or not ns.isdecimal() or len(ns) > 20:
            return None
        if not start <= int(ns) / 1_000_000_000 <= end:
            return None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None
    message = data.get("raw_kmsg", "")
    if not isinstance(message, str):
        return None
    codes = {(k.lower(), int(n)) for k, n in ERROR_CODE.findall(message)}
    if codes and codes != {(kind, code)}:
        return None
    devices = [v for v in (data.get("device_uuid"), extra.get("device_uuid")) if v]
    if not all(isinstance(v, str) for v in devices):
        return None
    device = devices[0] if devices else None
    conflict = any(
        v != device and (not pci(v) or pci(v) != pci(device)) for v in devices
    )
    inventory = resources.get("gpuInfo.gpus", [])
    if isinstance(inventory, str):
        try:
            inventory = json.loads(inventory)
        except ValueError:
            inventory = []
    matches = (
        {
            gpu["uuid"]
            for gpu in inventory
            if isinstance(gpu, dict)
            and isinstance(gpu.get("uuid"), str)
            and device
            and not conflict
            and (
                device == gpu["uuid"]
                or (
                    isinstance(gpu.get("busID"), str)
                    and pci(device)
                    and pci(device) == pci(gpu["busID"])
                )
            )
        }
        if isinstance(inventory, list)
        else set()
    )
    # Inventory agreement is a reported association, not independent GPU identity proof.
    # SXID names an NVSwitch; a GPU inventory cannot establish switch identity.
    mapped = next(iter(matches)) if kind == "xid" and len(matches) == 1 else None
    if target.get("gpu_uuid") and target["gpu_uuid"] != mapped:
        return None
    return {
        "component": component,
        "producer_contract": contract["producer_contract"],
        "cluster_id": cluster,
        "target": identity,
        "error_code": f"{kind}:{code}",
        "event_time": datetime.fromtimestamp(timestamp(at), timezone.utc).isoformat(),
        "time_basis": "producer_event_time",
        "loki_timestamp_ns": ns,
        "reported_device": device,
        "inventory_gpu_candidate": mapped,
        "device_mapping": "conflicting"
        if conflict
        else "inventory_match"
        if mapped
        else "unresolved",
        "event_id": attributes.get("event_id")
        if isinstance(attributes.get("event_id"), str)
        else None,
        "status": "reported_event",
        "source_payload_sha256": hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest(),
        "fact_eligible": False,
        "limitations": [
            "current_health_unverified",
            "physical_or_synthetic_origin_unverified",
            "device_identity_not_independently_verified",
        ],
    }


def parse_events(evidence, profile, target):
    results = {}
    for e in evidence:
        if e["query_id"] != "D09" or not usable_observation(e):
            continue
        name = e["quality"].get("health_contract") or profile.get("queries", {}).get(
            "D09", {}
        ).get("health_contract")
        contract = profile.get("health_contracts", {}).get(name, {})
        if contract.get("adapter") != "fleet_component_v1":
            continue
        period = e["quality"].get("request_time_range", e["time_range"])
        for ns, line in log_entries(e["snapshot"]):
            raw = object_value(line)
            item = event_item(raw, ns, contract, period, target, e.get("cluster_id"))
            if item is None:
                continue
            # Re-exported events may acquire new IDs. Keep conflicting payloads separate.
            identity = json.dumps(
                {
                    k: v
                    for k, v in item.items()
                    if k not in ("event_id", "loki_timestamp_ns")
                },
                sort_keys=True,
            )
            if identity not in results:
                results[identity] = {**item, "evidence_refs": []}
            if e["id"] not in results[identity]["evidence_refs"]:
                results[identity]["evidence_refs"].append(e["id"])
    return list(results.values())


def match_alert(clues, health, events, diagnostics=None):
    """Confirm a target event; surrounding reports remain investigation context."""
    selector = event_selector(clues)
    alert = {k: selector.get(k) for k in ("error_code", "pci", "gpu_uuid")}

    def result(status, refs=(), **detail):
        return {
            "status": status,
            "alert": alert,
            "evidence_refs": list(dict.fromkeys(refs)),
            "detail": detail,
        }

    if check(
        diagnostics,
        "error_code_unparsed",
        "not event_selector(clues)",
        not selector,
        {"codes": clues.get("error_codes", [])},
    ):
        return result("error_code_unparsed")
    matched = [e for e in events if matches_target(e, selector)]
    same = [
        h
        for h in health
        if matches_target(h, selector, same_code=False)
        and report_reason(h.get("reason")) == report_reason(clues.get("reason"))
    ]
    refs = [r for h in same for r in h["evidence_refs"]]
    missing = check(
        diagnostics,
        "event_missing",
        "len(matched) == 0; matched = same-host, same-PCI, same-code events",
        not matched,
        {
            "event_count": len(events),
            "matched_event_count": len(matched),
            "error_code": selector["error_code"],
            "alert_pci": selector["pci"],
        },
    )
    if not missing:
        refs += [r for e in matched for r in e["evidence_refs"]]
        candidates = {e.get("inventory_gpu_candidate") for e in matched} - {None}
        if check(
            diagnostics,
            "uuid_mismatch",
            "bool(alert.gpu_uuid and candidates and candidates != {alert.gpu_uuid})",
            bool(
                alert["gpu_uuid"] and candidates and candidates != {alert["gpu_uuid"]}
            ),
            {"alert_gpu_uuid": alert["gpu_uuid"], "candidates": sorted(candidates)},
        ):
            return result(
                "uuid_mismatch", refs, inventory_gpu_candidates=sorted(candidates)
            )
        # Repeated occurrences and other devices never invalidate an observed event.
        return result(
            "match",
            refs,
            matched_event_count=len(matched),
            matching_basis="reported_host_pci_code_in_query_window",
        )

    # Preserve the legacy state-transition explanation when the event is absent.
    dated = sorted(
        (
            h
            for h in same
            if h.get("observed_at") and h.get("raw_health") == "Unhealthy"
        ),
        key=lambda h: timestamp(h["observed_at"]),
    )
    first = timestamp(dated[0]["observed_at"]) if dated else None
    scope = {
        k: selector[c]
        for c, k in (("machine_id", "machine_id"), ("k8s_node_name", "node"))
        if selector.get(c)
    }
    healthy = sorted(
        (
            h
            for h in health
            if h.get("component") == selector["component"]
            and str(h.get("raw_health")).lower() == "healthy"
            and h.get("observed_at")
            and first is not None
            and timestamp(h["observed_at"]) < first
            and all(h.get("target", {}).get(k) == v for k, v in scope.items())
            and (
                not selector.get("cluster_id")
                or h.get("cluster_id") == selector["cluster_id"]
            )
        ),
        key=lambda h: timestamp(h["observed_at"]),
    )
    if check(
        diagnostics,
        "preceding_healthy",
        "len(healthy) > 0",
        bool(healthy),
        {
            "first_unhealthy_at": dated[0]["observed_at"] if dated else None,
            "last_healthy_at": healthy[-1]["observed_at"] if healthy else None,
            "preceding_healthy_count": len(healthy),
            "time_basis": "loki_recorded_at",
            "selection": "earliest matching Unhealthy report; later transitions are not evaluated",
        },
    ):
        return result(
            "event_not_exported",
            refs + healthy[-1]["evidence_refs"],
            last_healthy_at=healthy[-1]["observed_at"],
            first_unhealthy_at=dated[0]["observed_at"],
        )
    return result(
        "event_not_found",
        refs,
        other_codes=sorted(
            {e["error_code"] for e in events} - {selector["error_code"]}
        ),
    )


def enrich_report_inventory(health, evidence):
    """Read inventory strings for RCA only; never promote device or health facts."""
    originals = {e["id"]: e for e in evidence}
    cached_lines = {}
    for report in health:
        if report.get("time_basis") != "loki_recorded_at":
            continue
        refs = report.get("evidence_refs", [])
        e = originals.get(refs[0]) if refs else None
        if not e:
            continue
        if e["id"] not in cached_lines:
            cached_lines[e["id"]] = list(log_entries(e["snapshot"]))
        lines = cached_lines[e["id"]]
        position = report.get("source_position", {}).get("line")
        if not isinstance(position, int) or not 0 <= position < len(lines):
            continue
        raw = object_value(lines[position][1])
        resources = object_value(raw.get("resources"))
        source_time = object_value(raw.get("attributes")).get("time")
        report["producer_time_status"] = (
            "missing_or_zero"
            if not source_time or str(source_time).startswith("0001-")
            else "unverified"
        )
        inventory = resources.get("gpuInfo.gpus")
        if isinstance(inventory, str):
            try:
                inventory = json.loads(inventory)
            except ValueError:
                inventory = None
        if not isinstance(inventory, list):
            continue
        report["gpu_candidates"] = [
            {
                "gpu_uuid": gpu["uuid"],
                "bus_id": gpu.get("busID"),
                "mapping_basis": "node_inventory_report",
                "verified": False,
            }
            for gpu in inventory
            if isinstance(gpu, dict)
            and isinstance(gpu.get("uuid"), str)
            and gpu["uuid"].strip()
        ]
        reason = object_value(raw.get("attributes")).get("reason", "")
        addresses = PCI_TEXT.findall(reason if isinstance(reason, str) else "")
        inventory_addresses = [
            gpu["bus_id"]
            for gpu in report["gpu_candidates"]
            if isinstance(gpu.get("bus_id"), str) and pci(gpu["bus_id"])
        ]
        if addresses:
            report["reported_pci_addresses"] = sorted(set(addresses))
        if addresses and report.get("component") == "accelerator-nvidia-error-sxid":
            # GPU inventory cannot validate a switch PCI address.
            report["pci_inventory_relation"] = "switch_inventory_required"
        elif addresses and inventory_addresses:
            report["pci_inventory_relation"] = (
                "not_in_reported_inventory"
                if any(
                    pci(address) not in {pci(v) for v in inventory_addresses}
                    for address in addresses
                )
                else "inventory_candidate_only"
            )
    return health
