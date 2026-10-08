"""Audit saved Runbooks without network access, DB access, or content mutation."""

import argparse
from collections import Counter
import json
from pathlib import Path

from agent_common.query_contract import query_facts

from .runbook_contract import (
    contract_reason,
    validate_published_runbook,
    validate_runbook,
)


def review_inventory(row, profile, entries):
    """Identify review work, never approve semantics from a static checklist."""
    content = row.get("content", {})
    entry = entries.get(row.get("knowledge_key"), {})
    findings = []
    supplied = set()
    planned = []
    unsupported = []
    for step in content.get("observation_plan", []):
        query_id = step.get("query_id")
        if isinstance(query_id, str):
            planned.append(query_id)
        facts = set(step.get("fact_names", []))
        if query_id not in profile["queries"]:
            findings.append("query_not_registered")
            if isinstance(query_id, str):
                unsupported.append(query_id)
            continue
        supported = query_facts(query_id)
        if facts - supported:
            findings.append("facts_outside_query_capability")
        if step.get("required"):
            supplied.update(facts & supported)
    if set(content.get("required_evidence", [])) - supplied:
        findings.append("required_facts_not_in_required_plan")
    fleet_time_gated_facts = []
    health_facts = {
        "normalized_health",
        "component",
        "severity",
        "producer_contract",
        "error_code",
    }
    required_health = set(content.get("required_evidence", [])) & health_facts
    if required_health and {"D05", "D09"} & set(planned):
        # This is the configured Fleet adapter's time gate, not a live assessment.
        fleet = profile.get("health_contracts", {}).get("fleet-component-log-v1", {})
        if fleet.get("loki_timestamp_is_observed_at") is not True:
            findings.append("fleet_observation_time_unverified")
            fleet_time_gated_facts = sorted(required_health)
    if not row.get("compatibility"):
        findings.append("compatibility_unbound")
    source_status = entry.get("source_status", "not_in_manifest")
    if source_status != "documented":
        findings.append("source_applicability_review_required")
    # Even documented sources do not prove error-specific query sufficiency.
    findings.append("error_specific_evidence_review_required")
    return {
        "source_status": source_status,
        "evidence_group": entry.get("evidence_group"),
        "planned_queries": sorted(set(planned)),
        "unregistered_queries": sorted(set(unsupported)),
        "fleet_time_gated_facts": fleet_time_gated_facts,
        "findings": sorted(set(findings)),
        "operational_approval": "not_assessed",
    }


def audit(rows, profile, *, authoring=False, manifest=None):
    entries = {
        entry["knowledge_key"]: entry for entry in (manifest or {}).get("entries", [])
    }
    results = []
    for index, row in enumerate(rows):
        item = {"index": index}
        if isinstance(row, dict):
            item.update(
                {key: row.get(key) for key in ("knowledge_key", "revision", "id")}
            )
        try:
            if authoring:
                validate_runbook(
                    row, profile["queries"], list(profile["queries"]), authoring=True
                )
            else:
                validate_published_runbook(row, profile)
            item["status"] = "contract_valid"
        except ValueError as exc:
            item.update(status="invalid_contract", reason=contract_reason(exc))
        except (TypeError, KeyError, AttributeError):
            item.update(status="invalid_contract", reason="malformed_contract_value")
        if manifest is not None:
            # Review remains useful for old revisions rejected by the runtime.
            # A malformed review input must not change the contract verdict.
            try:
                item["review"] = review_inventory(row, profile, entries)
            except (ValueError, TypeError, KeyError, AttributeError):
                item["review"] = {
                    "findings": ["review_input_malformed"],
                    "operational_approval": "not_assessed",
                }
        results.append(item)
    return {
        "mode": "authoring" if authoring else "published_snapshot",
        "total": len(results),
        "counts": dict(Counter(item["status"] for item in results)),
        "failure_reasons": dict(
            Counter(item["reason"] for item in results if "reason" in item)
        ),
        "scope": "Content contract only; not applicability, source validity, or operational approval. First failure per revision; no live state checked.",
        "writes": 0,
        "results": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", type=Path, help="Saved JSON row/list or RB-*.json directory"
    )
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument(
        "--review-manifest",
        type=Path,
        help="Add static review findings from the saved catalog; never approves publication",
    )
    parser.add_argument(
        "--authoring",
        action="store_true",
        help="Allow unbound drafts; do not check publication hashes",
    )
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        if args.input.is_dir():
            rows = [
                json.loads(p.read_text(encoding="utf-8-sig"))
                for p in sorted(args.input.rglob("RB-*.json"))
            ]
        else:
            rows = json.loads(args.input.read_text(encoding="utf-8-sig"))
            if isinstance(rows, dict):
                rows = [rows]
        if not isinstance(rows, list) or not rows:
            raise ValueError("expected nonempty row list")
        manifest = (
            json.loads(args.review_manifest.read_text(encoding="utf-8-sig"))
            if args.review_manifest
            else None
        )
        result = audit(rows, profile, authoring=args.authoring, manifest=manifest)
    except (OSError, ValueError, TypeError, KeyError):
        parser.exit(
            2, "Cannot read audit inputs; expected a profile and saved Runbook rows.\n"
        )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if result["counts"].get("invalid_contract") else 0


if __name__ == "__main__":
    raise SystemExit(main())
