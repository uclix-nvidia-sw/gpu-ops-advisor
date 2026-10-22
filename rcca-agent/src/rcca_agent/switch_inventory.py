"""Bounded SXID PCI lookup through the same scoped Grafana MCP datasource."""

import asyncio
import json
import re
import time

from agent_common.contracts import timestamp
from agent_common.grafana_time import mcp_time
from agent_common.observation import unwrap
from .fleet_events import pci
from .incident_dossier import ADDRESSES


async def collect_switch_pci(obs, budget, clues, targets):
    alert_addresses = {pci(a) for a in ADDRESSES.findall(clues.get("reason", ""))} - {
        None
    }
    event_addresses = {
        pci(t["device"]) for t in targets if t["code"].startswith("sxid:")
    } - {None}
    addresses = alert_addresses | event_addresses
    addresses.discard(None)
    if not any(c.startswith("sxid:") for c in clues.get("error_codes", [])):
        return []
    rows = []
    node = obs.data["target"].get("node") or obs.data["target"].get("k8s_node_name")
    period = obs.data["time_range"]
    seen = set()
    clusters = {c["cluster_id"] for c in obs.data["scope"]["clusters"]}
    sources = sorted(obs.evidence, key=lambda e: e["query_id"] != "D47")
    for source in sources:
        quality = source["quality"]
        uid = quality.get("datasource_uid")
        cluster = source.get("cluster_id")
        selectors = quality.get("resolved_cluster_selector")
        node_label = (quality.get("target_labels") or {}).get("node")
        if (
            source["query_id"] not in {"D47", "D33", "D34"}
            or cluster not in clusters
            or not uid
            or not selectors
            or not node_label
            or not node
        ):
            continue
        if (cluster, uid) in seen:
            continue
        seen.add((cluster, uid))
        status, snapshot = "unavailable", {}
        detail = {
            "complete": False,
            "source": "grafana_mcp",
            "purpose": "nvswitch_pci_identity",
            "datasource_uid": uid,
        }
        args = {}
        if not addresses or len(addresses) > 4:
            detail["reason"] = "ambiguous_pci_addresses"
        elif time.monotonic() >= obs.deadline:
            detail["reason"] = "deadline_exhausted"
        elif budget["queries"] <= 0:
            detail["reason"] = "budget_exhausted"
        else:
            # Match full domain/bus/device/function; GPU index is never a switch ID.
            pattern = (
                "(?i)("
                + "|".join(
                    f"0*{d:x}:{b:02x}:{v:02x}[.]{f}" for d, b, v, f in sorted(addresses)
                )
                + ")"
            )
            filters = {**selectors, node_label: node}
            if any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", k) for k in filters):
                continue
            selector = ",".join(
                k + "=" + json.dumps(v) for k, v in sorted(filters.items())
            )
            duration = int(timestamp(period["end"]) - timestamp(period["start"])) + 1
            args = dict(
                datasourceUid=uid,
                expr="{"
                + selector
                + ",pci_bus_id=~"
                + json.dumps(pattern)
                + "}"
                + f"[{duration}s]",
                queryType="instant",
                endTime=mcp_time(period["end"]),
            )
            budget["queries"] -= 1
            obs.calls += 1
            try:
                async with asyncio.timeout(
                    min(
                        obs.profile["limits"].get("query_timeout_seconds", 30),
                        max(0.01, obs.deadline - time.monotonic()),
                    )
                ):
                    response = unwrap(await obs.tools["query_prometheus"](args))
                payload = (
                    response.get("data", response) if isinstance(response, dict) else {}
                )
                values = (
                    payload.get("result", []) if isinstance(payload, dict) else payload
                )
                count = (
                    sum(len(r.get("values", [])) for r in values if isinstance(r, dict))
                    if isinstance(values, list)
                    else 0
                )
                if (
                    len(json.dumps(response).encode())
                    > obs.profile["limits"]["max_bytes"]
                    or count > obs.profile["limits"]["max_rows"]
                ):
                    detail["reason"] = "response_limit"
                elif (
                    not isinstance(response, dict)
                    or not isinstance(values, list)
                    or response.get("status") == "error"
                    or not isinstance(payload, (dict, list))
                ):
                    detail["reason"] = "invalid_response"
                elif isinstance(payload, dict) and "result" not in payload:
                    detail["reason"] = "invalid_response"
                else:
                    snapshot = response
                    status = "ok" if values else "empty"
                    detail.update(complete=True, reason=None)
            except Exception as exc:
                detail["reason"] = "pci_lookup_failed"
                detail["error_type"] = type(exc).__name__
        evidence = obs._evidence(
            "nvswitch_pci_inventory", cluster, period, snapshot, status, detail, args
        )
        found = set()
        payload = snapshot.get("data", snapshot)
        values = payload.get("result", []) if isinstance(payload, dict) else payload
        for series in values if isinstance(values, list) else []:
            if not isinstance(series, dict) or not isinstance(
                series.get("metric"), dict
            ):
                continue
            labels = series["metric"]
            address = (
                pci(labels["pci_bus_id"])
                if isinstance(labels.get("pci_bus_id"), str)
                else None
            )
            # Response-side identity check protects against broad/misconfigured sources.
            if address not in addresses or any(
                labels.get(k) != v
                for k, v in {**(selectors or {}), node_label: node}.items()
            ):
                continue
            machine = obs.data["target"].get("machine_id")
            if machine and labels.get("machine_id") and labels["machine_id"] != machine:
                continue
            samples = series.get("values", [])
            if not any(
                in_period(v, period)
                for v in (samples if isinstance(samples, list) else [])
            ):
                continue
            found.add(labels["pci_bus_id"])
        rows.append(
            {
                "type": "switch_pci_lookup",
                "node": node,
                "reported_pci": [
                    f"{d:04x}:{b:02x}:{v:02x}.{f}" for d, b, v, f in sorted(addresses)
                ],
                "alert_pci": [
                    f"{d:04x}:{b:02x}:{v:02x}.{f}"
                    for d, b, v, f in sorted(alert_addresses)
                ],
                "event_pci": [
                    f"{d:04x}:{b:02x}:{v:02x}.{f}"
                    for d, b, v, f in sorted(event_addresses)
                ],
                "observed_pci": sorted(found),
                "status": status,
                "period": period,
                "evidence_refs": [evidence["id"]],
                "interpretation_limits": "PCI label observation only; no GPU index mapping, switch health or recovery inference.",
            }
        )
    return rows


def in_period(value, period):
    try:
        return (
            isinstance(value, list)
            and len(value) == 2
            and timestamp(period["start"])
            <= float(value[0])
            <= timestamp(period["end"])
        )
    except (TypeError, ValueError, OverflowError):
        return False
