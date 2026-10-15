"""Deterministic incident findings for the report.

Everything here is a reported association or a recorded sample. Nothing is promoted
to a verified health fact, an allocation contract or an executed action.
"""

import re
from datetime import datetime, timezone

from agent_common.contracts import timestamp
from agent_common.observation import usable_observation

from .fleet_events import pci

MODEL_LABELS = ("modelName", "model_name")
DRIVER_LABELS = ("DCGM_FI_DRIVER_VERSION", "driver_version")
UUID_LABELS = ("UUID", "uuid", "gpu_uuid")
NODE_LABELS = ("node", "Hostname", "host_name")
STATUS_UUID = re.compile(r"UUID:(GPU-[0-9a-f-]{36})", re.I)
FAMILY = re.compile(r"\b(GB\d{3}|[ABHLV]\d{2,3})\b")
APPLIES = re.compile(r"^NVIDIA 적용: (.+?)(?:; 제외: (.+?))?\.$")
ACTIONS = re.compile(
    r"^NVIDIA 조치 분류: immediate=([^;]+); investigatory=([^;]+); Xid154 linkage=(.+)\.$"
)
FLEET = re.compile(
    r"^Fleet 고정 카탈로그: (.+?); event_type=(\w+); 기본 action=(.+)\.$"
)
UNSTATED = {"미기재", "해당 제품 없음", ""}


def _series(evidence):
    """Yield (evidence, labels, [(seconds, value)]) for complete metric snapshots."""
    for e in evidence:
        if not str(e.get("query_id", "")).startswith("D"):
            continue
        if not isinstance(e.get("quality"), dict) or not usable_observation(e):
            continue
        data = e.get("snapshot", {})
        data = data.get("data", []) if isinstance(data, dict) else data
        if not isinstance(data, list):
            continue
        for s in data:
            if not isinstance(s, dict) or not isinstance(s.get("metric"), dict):
                continue
            values = []
            for point in s.get("values") or []:
                try:
                    values.append((float(point[0]), float(point[1])))
                except (TypeError, ValueError, IndexError):
                    continue
            if values:
                yield e, s["metric"], sorted(values)


def _label(labels, e, role, fallbacks):
    key = (e.get("quality", {}).get("target_labels") or {}).get(role)
    for name in ([key] if key else []) + list(fallbacks):
        value = labels.get(name)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def device_identity(event, observations, evidence):
    """Compare every collected PCI↔UUID report for the event address on its node."""
    address = pci(event.get("reported_device"))
    node = event.get("target", {}).get("node")
    if address is None or not node:
        return None
    sources = []
    if event.get("inventory_gpu_candidate"):
        sources.append(
            dict(
                source="fleet_inventory",
                producer="fleet_intelligence",
                gpu_uuid=event["inventory_gpu_candidate"],
                evidence_refs=list(event.get("evidence_refs", [])),
            )
        )
    for row in observations:
        if (
            row.get("target", {}).get("node") != node
            or row.get("error_code") != event.get("error_code")
            or address not in {pci(a) for a in row.get("reported_pci_addresses", [])}
        ):
            continue
        for uuid in sorted(set(STATUS_UUID.findall(row.get("reason") or ""))):
            sources.append(
                dict(
                    source="fleet_status_message",
                    producer="fleet_intelligence",
                    gpu_uuid=uuid,
                    evidence_refs=list(row.get("evidence_refs", [])),
                )
            )
    by_uuid = {}
    for e, labels, _ in _series(evidence):
        if _label(labels, e, "node", NODE_LABELS) != node:
            continue
        uuid = _label(labels, e, "gpu_uuid", UUID_LABELS)
        bus = labels.get("pci_bus_id")
        if not uuid or pci(bus) is None:
            continue
        by_uuid.setdefault(uuid, set()).add(pci(bus))
        if pci(bus) != address:
            continue
        sources.append(
            dict(
                source="metric_labels",
                query_id=e["query_id"],
                producer=e["quality"].get("producer") or e["query_id"],
                gpu_uuid=uuid,
                model=_label(labels, e, "model", MODEL_LABELS),
                driver=_label(labels, e, "driver", DRIVER_LABELS),
                gpu_index=labels.get("gpu"),
                evidence_refs=[e["id"]],
            )
        )
    if not sources:
        return None
    uuids = {s["gpu_uuid"] for s in sources}
    # A UUID reported at another bus is a conflict even if the event address agrees.
    moved = any(len(by_uuid.get(u, set()) | {address}) > 1 for u in uuids)
    producers = {s["producer"] for s in sources}
    merged = {}
    for s in sources:
        key = (s["source"], s.get("query_id"), s["gpu_uuid"])
        if key in merged:
            merged[key]["evidence_refs"] = list(
                dict.fromkeys(merged[key]["evidence_refs"] + s["evidence_refs"])
            )
        else:
            merged[key] = s
    sources = list(merged.values())
    pick = lambda key: sorted({s[key] for s in sources if s.get(key)})  # noqa: E731
    return dict(
        reported_device=event["reported_device"],
        gpu_uuid=next(iter(uuids)) if len(uuids) == 1 else None,
        status="conflicting"
        if len(uuids) > 1 or moved
        else "corroborated"
        if len(producers) > 1
        else "single_source",
        producers=sorted(producers),
        sources=sources,
        models=pick("model"),
        drivers=pick("driver"),
        gpu_indexes=pick("gpu_index"),
        basis="reported_identifiers_agree",
    )


def health_transition(event, observations):
    """Bracket the producer event time by the component's recorded status reports."""
    node = event.get("target", {}).get("node")
    at = timestamp(event["event_time"])
    rows = sorted(
        (
            r
            for r in observations
            if r.get("component") == event.get("component")
            and r.get("target", {}).get("node") == node
            and isinstance(r.get("raw_health"), str)
            and r.get("observed_at")
        ),
        key=lambda r: timestamp(r["observed_at"]),
    )
    before = [
        r
        for r in rows
        if timestamp(r["observed_at"]) < at and r["raw_health"].lower() == "healthy"
    ]
    after = [
        r
        for r in rows
        if timestamp(r["observed_at"]) >= at
        and r.get("error_code") == event.get("error_code")
        and r["raw_health"].lower() != "healthy"
    ]
    if not after:
        return None
    later = [r for r in rows if timestamp(r["observed_at"]) >= at]
    return dict(
        time_basis="loki_recorded_at",
        last_healthy_at=before[-1]["observed_at"] if before else None,
        first_unhealthy_at=after[0]["observed_at"],
        first_unhealthy_state=after[0]["raw_health"],
        last_report_at=later[-1]["observed_at"],
        persisted=all(r["raw_health"].lower() != "healthy" for r in later),
        unhealthy_reports=len(after),
        brackets_event=bool(before),
        evidence_refs=list(
            dict.fromkeys(
                ref
                for r in (before[-1:] + after[:1] + later[-1:])
                for ref in r.get("evidence_refs", [])
            )
        ),
    )


def metric_context(gpu, node, at, evidence):
    """Summarize the identified GPU's samples around the event without causal claims."""
    output = []
    peers = {}
    for e, labels, values in _series(evidence):
        if _label(labels, e, "node", NODE_LABELS) != node:
            continue
        quality = e["quality"]
        metric = quality.get("metric") or labels.get("__name__")
        uuid = _label(labels, e, "gpu_uuid", UUID_LABELS)
        prior = [(t, v) for t, v in values if t <= at]
        if not prior:
            continue
        common = dict(
            query_id=e["query_id"],
            metric=metric,
            unit=quality.get("unit"),
            start=_iso(values[0][0]),
            end=_iso(values[-1][0]),
            samples=len(values),
            evidence_refs=[e["id"]],
        )
        if quality.get("sample_type") == "counter":
            entry = dict(
                kind="counter",
                first=values[0][1],
                last=values[-1][1],
                reset=any(b < a for (_, a), (_, b) in zip(values, values[1:])),
                **common,
            )
        else:
            active = [t for t, v in prior if v > 0]
            entry = dict(
                kind="gauge",
                before_event=prior[-1][1],
                before_event_at=_iso(prior[-1][0]),
                window_max=max(v for _, v in values),
                window_min=min(v for _, v in values),
                last_nonzero_at=_iso(active[-1]) if active else None,
                **common,
            )
        peers.setdefault(e["query_id"], []).append((uuid, entry))
        if uuid == gpu:
            output.append(entry)
    for entry in output:
        same = [p for _, p in peers.get(entry["query_id"], [])]
        entry["node_series"] = len(same)
        if entry["kind"] == "counter":
            entry["node_series_unchanged"] = sum(
                1 for p in same if p["first"] == p["last"] and not p["reset"]
            )
            continue
        entry["node_series_zero"] = sum(1 for p in same if p["window_max"] == 0)
        if entry["last_nonzero_at"]:
            mine = timestamp(entry["last_nonzero_at"])
            entry["node_series_stopped_together"] = sum(
                1
                for p in same
                if p["before_event"] == 0
                and p["last_nonzero_at"]
                and abs(timestamp(p["last_nonzero_at"]) - mine) <= 60
            )
    return output


def catalog_terms(evidence):
    """Read the reviewed catalog lines of the selected published Runbook only."""
    for e in evidence:
        if (
            e.get("query_id") != "runbook"
            or e.get("quality", {}).get("origin") != "published"
        ):
            continue
        content = e.get("snapshot", {})
        terms = dict(evidence_refs=[e["id"]])
        for line in content.get("analysis_guidance", []):
            if not isinstance(line, str):
                continue
            if m := APPLIES.match(line):
                terms["applies"] = [
                    v for v in m.group(1).split(", ") if v not in UNSTATED
                ]
                terms["excludes"] = m.group(2).split(", ") if m.group(2) else []
            elif m := ACTIONS.match(line):
                terms["immediate"] = m.group(1).strip()
                terms["investigatory"] = m.group(2).strip()
                terms["xid154_linkage"] = m.group(3).strip()
                driver = re.search(r"GPU driver R(\d+)", m.group(3))
                terms["xid154_driver"] = int(driver.group(1)) if driver else None
            elif m := FLEET.match(line):
                terms["fleet_name"] = m.group(1)
                terms["fleet_event_type"] = m.group(2)
                terms["fleet_actions"] = m.group(3).split(", ")
        if len(terms) > 1:
            terms["sources"] = [
                {k: s.get(k) for k in ("url", "section", "revision")}
                for s in content.get("sources", [])
                if isinstance(s, dict) and str(s.get("url", "")).startswith("https://")
            ]
            terms["title"] = content.get("title")
            terms["revision"] = e.get("query_version")
            return terms
    return None


def model_applicability(models, terms):
    if not terms or "applies" not in terms or len(models) != 1:
        return None
    family = FAMILY.search(models[0])
    if not family:
        return "unlisted"
    name = family.group(1)
    if name in terms["applies"]:
        return "applies"
    return "excluded" if name in terms.get("excludes", []) else "unlisted"


def driver_supports_linkage(drivers, terms):
    if not terms or not terms.get("xid154_driver") or len(drivers) != 1:
        return None
    major = re.match(r"(\d+)\.", drivers[0])
    return int(major.group(1)) >= terms["xid154_driver"] if major else None


def incident_findings(result, evidence, data):
    analysis = result.get("quality", {}).get("analysis", {})
    events = [e for e in analysis.get("error_events", []) if e.get("event_time")]
    if len(events) != 1 or len(data.get("scope", {}).get("clusters", [None])) != 1:
        # Several events or clusters need a per-event report; keep existing prose.
        return None
    event = events[0]
    observations = result.get("device_observations", [])
    identity = device_identity(event, observations, evidence)
    terms = catalog_terms(evidence)
    findings = dict(
        schema="incident-findings/2",
        event_time=event["event_time"],
        error_code=event["error_code"],
        node=event.get("target", {}).get("node"),
        identity=identity,
        health=health_transition(event, observations),
        catalog=terms,
        companion_codes=sorted(
            {
                e["error_code"]
                for e in analysis.get("error_events", [])
                if e is not event
                and e.get("target", {}).get("node")
                == event.get("target", {}).get("node")
            }
        ),
    )
    gpu = identity and identity["status"] != "conflicting" and identity["gpu_uuid"]
    if gpu:
        at = timestamp(event["event_time"])
        findings["metrics"] = metric_context(gpu, findings["node"], at, evidence)
        findings["model_applicability"] = model_applicability(identity["models"], terms)
        findings["xid154_supported"] = driver_supports_linkage(
            identity["drivers"], terms
        )
    # Host-only facts stay explicit; none is inferred from absence. RCA scope is the
    # GPU node; Kubernetes workload identity is outside it.
    findings["unknowns"] = ["operating_mode", "current_access", "synthetic_origin"]
    return findings
