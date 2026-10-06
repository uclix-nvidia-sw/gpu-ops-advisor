"""Registered JSON health parser; unknown producer semantics remain unknown."""

import json
import re
from datetime import datetime, timedelta, timezone
from .calculations import normalize_health
from .contracts import timestamp


ERROR_CODE = re.compile(
    r"\b(s?xid)(?:\s*\([^\r\n)]{1,200}\))?\s*[:#]?\s*(\d+)\b", re.IGNORECASE
)


def log_entries(snapshot):
    if isinstance(snapshot, dict):
        if isinstance(snapshot.get("line"), str):
            yield snapshot.get("timestamp"), snapshot["line"]
        elif isinstance(snapshot.get("text"), str):
            yield None, snapshot["text"]
        elif isinstance(snapshot.get("values"), list) and "stream" in snapshot:
            for value in snapshot["values"]:
                if (
                    isinstance(value, list)
                    and len(value) > 1
                    and isinstance(value[1], str)
                ):
                    yield value[0], value[1]
        else:
            for key in ("data", "result", "logs", "entries"):
                if key in snapshot:
                    yield from log_entries(snapshot[key])
    elif isinstance(snapshot, list):
        for value in snapshot:
            yield from log_entries(value)


def log_lines(snapshot):
    for _, line in log_entries(snapshot):
        yield line


def fleet_item(raw, ns, contract, period):
    """A registered Fleet log report is not proof of current device health."""
    attributes, resources = raw.get("attributes"), raw.get("resources")
    if not isinstance(attributes, dict) or not isinstance(resources, dict):
        return None
    component = attributes.get("component")
    if not isinstance(attributes.get("health"), str) or not isinstance(
        attributes.get("reason", ""), str
    ):
        return None
    if not isinstance(component, str) or component not in contract.get(
        "components", {}
    ):
        return None
    if attributes.get("log_type") != "component_data":
        return None
    if raw.get("producer_contract") not in (None, contract["producer_contract"]):
        return None
    machine, node = resources.get("machine.id"), resources.get("k8s.node.name")
    if not all(isinstance(v, str) and v.strip() for v in (machine, node)):
        return None
    if not isinstance(ns, str) or not ns.isdecimal() or len(ns) > 20:
        return None
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def bound(value):
        delta = datetime.fromisoformat(value.replace("Z", "+00:00")) - epoch
        return (
            delta.days * 86400 + delta.seconds
        ) * 1_000_000_000 + delta.microseconds * 1000

    value = int(ns)
    if not bound(period["start"]) <= value <= bound(period["end"]):
        return None
    at = epoch + timedelta(microseconds=value // 1000)
    reason = attributes.get("reason", "")
    codes = {
        f"{kind.lower()}:{int(code)}"
        for kind, code in ERROR_CODE.findall(reason if isinstance(reason, str) else "")
    }
    namespace = contract["components"][component]
    code = next(iter(codes)) if len(codes) == 1 else None
    if code and not code.startswith(namespace + ":"):
        code = None
    return dict(
        health=attributes.get("health"),
        check_status="reported",
        component=component,
        target={"machine_id": machine, "node": node},
        observed_at=at.isoformat().replace("+00:00", "Z"),
        producer_contract=contract["producer_contract"],
        error_code=code,
        reason=reason,
        gpu_candidates=[
            {
                "gpu_uuid": g["uuid"],
                "bus_id": g.get("busID"),
                "mapping_basis": "node_inventory_report",
                "verified": False,
            }
            for g in resources.get("gpuInfo.gpus", [])
            if isinstance(g, dict) and isinstance(g.get("uuid"), str)
        ]
        if isinstance(resources.get("gpuInfo.gpus"), list)
        else [],
        loki_timestamp_ns=ns,
        time_basis="loki_recorded_at",
        fact_eligible=contract.get("loki_timestamp_is_observed_at") is True,
    )


def parse_health(evidence, contracts, queries=None):
    results = []
    seen = {}
    for e in evidence:
        if e["query_id"] not in ("D05", "D09") or e["tool_status"] not in (
            "ok",
            "partial",
        ):
            continue
        period = e["quality"].get("request_time_range", e["time_range"])
        for line_no, (ns, line) in enumerate(log_entries(e["snapshot"])):
            # Same physical log across D05/D09/chunks is one observation.
            # Keep distinct cluster/contract/quality semantics; retain all provenance.
            identity = (
                e.get("cluster_id"),
                ns,
                line,
                e["quality"].get("health_contract")
                or (queries or {}).get(e["query_id"], {}).get("health_contract"),
                e["tool_status"],
                json.dumps(e["quality"].get("request_time_range", {}), sort_keys=True),
            )
            if ns is not None and identity in seen:
                for observation in seen[identity]:
                    if e["id"] not in observation["evidence_refs"]:
                        observation["evidence_refs"].append(e["id"])
                continue
            begin = len(results)
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    continue
            except ValueError:
                continue
            registered = contracts.get(
                e["quality"].get("health_contract")
                or (queries or {}).get(e["query_id"], {}).get("health_contract")
            )
            producer = raw.get("producer_contract")
            native = contracts.get(producer) if isinstance(producer, str) else None
            if native and not native.get("adapter"):
                registered = None
            if registered and registered.get("adapter") == "fleet_component_v1":
                raw = fleet_item(raw, ns, registered, period)
                if raw is None:
                    continue
            children = raw.get("incidents", [raw])
            if not isinstance(children, list):
                children = [children]
            for child_no, child in enumerate(children):
                if not isinstance(child, dict):
                    continue  # One invalid child does not erase valid siblings.
                inherited = {k: v for k, v in raw.items() if k != "incidents"}
                item = {**inherited, **child, "evidence_refs": [e["id"]]}
                contract = contracts.get(item.get("producer_contract"))
                normalized = normalize_health(item, contract)
                if registered and registered.get("adapter") == "fleet_component_v1":
                    for key in (
                        "error_code",
                        "reason",
                        "loki_timestamp_ns",
                        "time_basis",
                        "fact_eligible",
                        "gpu_candidates",
                    ):
                        normalized[key] = item[key]
                normalized["source_position"] = {"line": line_no, "child": child_no}
                normalized["cluster_id"] = e["cluster_id"]
                try:
                    at = timestamp(normalized["observed_at"])
                    if not timestamp(period["start"]) <= at <= timestamp(period["end"]):
                        raise ValueError("outside period")
                except (ValueError, TypeError, AttributeError):
                    normalized.update(
                        check_status="unknown",
                        normalized_health="unknown",
                        severity="unknown",
                    )
                results.append(normalized)
            if ns is not None:
                seen[identity] = results[begin:]
    return results


def health_facts(health, target):
    # Alarm metadata is not device identity; node aliases share one comparison.
    identity = {
        k: v
        for k, v in target.items()
        if k
        in {
            "machine_id",
            "node",
            "node_uid",
            "gpu_uuid",
            "namespace",
            "pod",
            "pod_uid",
            "container",
        }
    }
    if target.get("k8s_node_name"):
        if identity.get("node", target["k8s_node_name"]) != target["k8s_node_name"]:
            return {}
        identity["node"] = target["k8s_node_name"]
    selected = [
        r
        for r in health
        if r["check_status"] == "valid"
        and r["normalized_health"] != "unknown"
        and r.get("fact_eligible", True)
        and bool(set(identity) - {"namespace", "container"})
        and all(r["target"].get(k) == v for k, v in identity.items())
        and (not target.get("cluster_id") or r["cluster_id"] == target["cluster_id"])
    ]
    facts = {}
    # Do not promote a mixture of device states to a single fact for a whole scope.
    for field in (
        "normalized_health",
        "component",
        "severity",
        "producer_contract",
        "error_code",
    ):
        values = {r.get(field) for r in selected}
        if len(values) == 1 and None not in values and "unknown" not in values:
            facts[field] = values.pop()
    return facts
