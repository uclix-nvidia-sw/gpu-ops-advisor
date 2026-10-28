"""Bound the model view without changing stored evidence or claiming full coverage."""

import json
from collections import defaultdict
from itertools import zip_longest

from agent_common.contracts import timestamp
from .fleet_events import matches_target
from .report_observations import event_devices_by_scope, report_scope

SECTIONS = (
    "incident_brief",
    "incident_comparison",
    "error_events",
    "device_observations",
    "pod_relations",
    "metric_observations",
    "raw_excerpts",
    "evidence_checks",
    "interpretation_findings",
    "interpretation_unknowns",
    "interpretation_conflicts",
    "interpretation_limitations",
    "query_quality",
    "runbook_plans",
)


OBSERVATION_SECTIONS = frozenset(
    {
        "incident_brief",
        "incident_comparison",
        "error_events",
        "device_observations",
        "pod_relations",
        "metric_observations",
        "raw_excerpts",
    }
)


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode())


def bounded_context(payload, max_bytes):
    sections = tuple(
        k
        for k in SECTIONS
        if k not in {"incident_comparison", "incident_brief"} or k in payload
    )
    # The limit applies to the serialized model view, not the source snapshots.
    view = {
        k: v
        for k, v in payload.items()
        if k not in (*sections, "observation_refs", "input_evidence_refs")
    }
    view.update({k: [] for k in sections})
    view["observation_refs"] = []
    view["input_evidence_refs"] = sorted(
        {
            ref
            for row in payload.get("investigation_summary", [])
            for ref in row.get("evidence_refs", [])
        }
    )
    coverage = {
        "method": "bounded_original_observations",
        "complete": False,
        "omitted_observations": {k: len(payload.get(k, [])) for k in sections},
        "omitted_metric_samples": sum(
            len(row.get("samples", []))
            for row in payload.get("metric_observations", [])
        ),
    }
    view["context_selection"] = coverage
    selector = payload.get("event_target", {})
    target_events = [
        e for e in payload.get("error_events", []) if matches_target(e, selector)
    ]

    def distance(row):
        try:
            return abs(
                timestamp(row["event_time"]) - timestamp(payload["incident_time"])
            )
        except (KeyError, TypeError, ValueError):
            return float("inf")

    primary = min(target_events, key=distance) if target_events else None
    if selector:
        coverage["target_event"] = (
            "retained" if primary is not None else "not_collected"
        )
    inventories = {}
    # Reserve room for the coverage counters and evidence IDs before admitting rows.
    # Admit one row per evidence source before more rows from that source.
    groups = defaultdict(list)
    for section in sections:
        for original in payload.get(section, []):
            groups[(section, tuple(original.get("evidence_refs", [])))].append(original)
    # Prefer the reported incident device over earlier sibling-device reports.
    # Keep all original rows in evidence; only order the bounded model view.
    devices = event_devices_by_scope(payload.get("error_events", []))
    for (section, _), rows in groups.items():
        if section == "device_observations" and devices:
            rows.sort(
                key=lambda row: not devices.get(report_scope(row), set()).intersection(
                    row.get("reported_pci_addresses", [])
                )
            )
    scheduled = [
        item
        for batch in zip_longest(
            *[[(section, row) for row in rows] for (section, _), rows in groups.items()]
        )
        for item in batch
        if item is not None
    ]
    # Passed format checks carry no incident meaning; admit them only after observations.
    scheduled.sort(
        key=lambda item: (
            item[1] is not primary,
            not matches_target(item[1], selector, same_code=False),
            item[0] != "incident_brief",
            item[0] == "evidence_checks" and item[1].get("outcome") == "pass",
        )
    )
    for section, original in scheduled:
        row = dict(original)
        inventory_key = None
        if section == "device_observations" and row.get("gpu_candidates"):
            inventory = row.pop("gpu_candidates")
            signature = json.dumps(
                sorted(
                    json.dumps(item, sort_keys=True, ensure_ascii=False)
                    for item in inventory
                ),
                ensure_ascii=False,
            )
            inventory_key = inventories.get(signature)
            if inventory_key is None:
                inventory_key = f"inventory-{len(inventories) + 1}"
                inventories[signature] = inventory_key
            row["gpu_inventory_ref"] = inventory_key
            tables = view.setdefault("gpu_inventories", {})
            new_inventory = inventory_key not in tables
            tables.setdefault(inventory_key, inventory)
        if section == "metric_observations":
            samples = original.get("samples", [])
            # Sparse original samples are not aggregates or proof of continuity.
            indices = (
                sorted({i * (len(samples) - 1) // 7 for i in range(8)})
                if samples
                else []
            )
            row["samples"] = [samples[i] for i in indices]
            row["sample_selection"] = {
                "method": "evenly_spaced_original_indices",
                "original_count": len(samples),
                "complete": len(indices) == len(samples),
            }
        previous_refs = view["observation_refs"]
        previous_inputs = view["input_evidence_refs"]
        view[section].append(row)
        view["input_evidence_refs"] = sorted(
            set(previous_inputs) | set(row.get("evidence_refs", []))
        )
        if section in OBSERVATION_SECTIONS:
            view["observation_refs"] = sorted(
                set(previous_refs) | set(row.get("evidence_refs", []))
            )
        # Leave room for event identities and published checks, not only aggregates.
        brief_overflow = (
            section == "incident_brief"
            and bool(payload.get("error_events") or payload.get("runbook_plans"))
            and encoded_size(view["incident_brief"]) > max_bytes // 2
        )
        if encoded_size(view) > max_bytes or brief_overflow:
            if original is primary:
                # Fail the existing size gate rather than send a view without its target.
                coverage["target_event"] = "budget_exceeded"
                coverage["omitted_observations"][section] -= 1
                continue
            view[section].pop()
            view["observation_refs"] = previous_refs
            view["input_evidence_refs"] = previous_inputs
            if inventory_key and new_inventory:
                del view["gpu_inventories"][inventory_key]
                if not view["gpu_inventories"]:
                    del view["gpu_inventories"]
            continue
        coverage["omitted_observations"][section] -= 1
        if section == "metric_observations":
            coverage["omitted_metric_samples"] -= len(row["samples"])
    coverage["complete"] = not (
        any(coverage["omitted_observations"].values())
        or coverage["omitted_metric_samples"]
    )
    return view
