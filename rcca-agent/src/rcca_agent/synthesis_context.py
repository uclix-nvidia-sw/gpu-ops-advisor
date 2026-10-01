"""Bound the model view without changing stored evidence or claiming full coverage."""

import json


SECTIONS = ("device_observations", "pod_relations", "metric_observations")


def encoded_size(value):
    return len(json.dumps(value, ensure_ascii=False).encode())


def bounded_context(payload, max_bytes):
    # The limit applies to the serialized model view, not the source snapshots.
    view = {
        k: v for k, v in payload.items() if k not in (*SECTIONS, "observation_refs")
    }
    view.update({k: [] for k in SECTIONS})
    view["observation_refs"] = []
    coverage = {
        "method": "bounded_original_observations",
        "complete": False,
        "omitted_observations": {k: len(payload.get(k, [])) for k in SECTIONS},
        "omitted_metric_samples": sum(
            len(row.get("samples", []))
            for row in payload.get("metric_observations", [])
        ),
    }
    view["context_selection"] = coverage
    # Reserve room for the coverage counters and evidence IDs before admitting rows.
    for section in SECTIONS:
        for original in payload.get(section, []):
            row = dict(original)
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
            view[section].append(row)
            view["observation_refs"] = sorted(
                set(previous_refs) | set(row["evidence_refs"])
            )
            if encoded_size(view) > max_bytes:
                view[section].pop()
                view["observation_refs"] = previous_refs
                continue
            coverage["omitted_observations"][section] -= 1
            if section == "metric_observations":
                coverage["omitted_metric_samples"] -= len(row["samples"])
    coverage["complete"] = not (
        any(coverage["omitted_observations"].values())
        or coverage["omitted_metric_samples"]
    )
    return view
