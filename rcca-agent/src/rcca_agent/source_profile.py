"""Prepare an explicit RCA-only profile; never mutate a running/shared profile."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from agent_common.contracts import content_hash
from agent_common.query_contract import query_definition, validate_profile


BINDING = "fleet_intelligence.rca_gpu_util"
EVIDENCE = "docs/evidence/rca-source-contracts.md"


def fleet_util_profile(base, clusters, revision):
    validate_profile(base)
    if not clusters or any(not isinstance(c, str) or not c.strip() for c in clusters):
        raise ValueError("explicit reviewed cluster IDs required")
    if (
        not isinstance(revision, str)
        or not revision.strip()
        or revision == base["revision"]
    ):
        raise ValueError("a new profile revision is required")
    if BINDING in base.get("bindings", {}):
        raise ValueError("Fleet RCA binding already exists")
    donor = base.get("bindings", {}).get("fleet_intelligence.D04", {})
    if (
        donor.get("producer") != "fleet_intelligence"
        or donor.get("metric") != "dcgm_fi_dev_gpu_temp"
    ):
        raise ValueError("reviewed Fleet source contract required")
    original = query_definition(base, "D02", next(iter(clusters)))
    if original.get("availability") != "verified":
        raise ValueError("resolve the existing GPU utilization binding first")
    result = deepcopy(base)
    result["revision"] = revision
    binding = deepcopy(donor)
    binding.update(
        query_id="D02",
        revision="rca-fleet-gpu-util-20261102-r1",
        producer_version="reviewed Fleet source 84f99beef3e633071ad0998b10629b01fb294eaf",
        metric="dcgm_fi_dev_gpu_util",
        unit="percent",
        target_labels={"gpu_uuid": "uuid", "node": "node"},
        sample_interval={"seconds": 60},
        max_hold={
            "seconds": 0,
            "policy": "Recorded Fleet samples only; no forward fill.",
        },
        invalid_values={"minimum": 0, "maximum": 100, "sentinels": []},
        equivalence_evidence_refs=[EVIDENCE],
        verification={
            "status": "verified",
            "observed_window": {
                "start": "2026-10-30T05:59:47Z",
                "end": "2026-10-30T06:29:47Z",
            },
            "retention_evidence": EVIDENCE,
            "evidence_refs": [EVIDENCE],
            "applicability": "Reviewed Fleet DCGM percent gauge, lowercase UUID label. RCA observations only.",
            "limitation": "Producer sample freshness, workload allocation and health are not asserted; live Worker publication pending.",
        },
    )
    binding.pop("reference", None)
    binding["environment"] = {
        "datasource_uid": None,
        "datasource_mode": "discover",
        "scope_labels": {"cluster_id": "cluster_id"},
        "selector": {"job": "fleet-intelligence-agent"},
    }
    result["bindings"][BINDING] = binding
    query = result["queries"]["D02"]
    # Appending a verified alternative would make automatic selection ambiguous.
    # Preserve the original global selection and every existing cluster override.
    if not query.get("selected_binding"):
        global_binding = query_definition(base, "D02", "__unconfigured_cluster__")
        if global_binding.get("availability") != "verified":
            raise ValueError("explicit global GPU utilization binding required")
        query["selected_binding"] = global_binding["binding_id"]
    query["binding_candidates"].append(BINDING)
    for cluster in clusters:
        result.setdefault("clusters", {}).setdefault(cluster, {}).setdefault(
            "bindings", {}
        )["D02"] = BINDING
    result["delivery"] = {
        "stage": "rca-only-prepared-profile",
        "runtime_ready": True,
        "intended_path": "RCA Worker AGENT_CONFIG_FILE only; never the shared/Ops configuration",
        "note": "Prepared configuration, not deployment or successful publication.",
    }
    result.setdefault("provenance", {})["rca_source_profile"] = {
        "base_revision": base["revision"],
        "base_content_hash": content_hash(base),
        "clusters": sorted(set(clusters)),
        "evidence": EVIDENCE,
    }
    validate_profile(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--cluster-id", action="append", required=True)
    args = parser.parse_args()
    result = fleet_util_profile(
        json.loads(args.base.read_text(encoding="utf-8-sig")),
        args.cluster_id,
        args.revision,
    )
    with args.output.open("x", encoding="utf-8", newline="\r\n") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Prepared RCA-only profile: {args.output}")


if __name__ == "__main__":
    main()
