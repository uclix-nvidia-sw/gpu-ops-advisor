"""Registered JSON health parser; unknown producer semantics remain unknown."""

import json
from .calculations import normalize_health
from .contracts import timestamp


def log_lines(snapshot):
    if isinstance(snapshot, dict):
        if isinstance(snapshot.get("line"), str):
            yield snapshot["line"]
        elif isinstance(snapshot.get("text"), str):
            yield snapshot["text"]
        elif isinstance(snapshot.get("values"), list) and "stream" in snapshot:
            for value in snapshot["values"]:
                if (
                    isinstance(value, list)
                    and len(value) > 1
                    and isinstance(value[1], str)
                ):
                    yield value[1]
        else:
            for key in ("data", "result", "logs", "entries"):
                if key in snapshot:
                    yield from log_lines(snapshot[key])
    elif isinstance(snapshot, list):
        for value in snapshot:
            yield from log_lines(value)


def parse_health(evidence, contracts):
    results = []
    for e in evidence:
        if e["query_id"] not in ("D05", "D09") or e["tool_status"] not in (
            "ok",
            "partial",
        ):
            continue
        for line_no, line in enumerate(log_lines(e["snapshot"])):
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    continue
            except ValueError:
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
                normalized["source_position"] = {"line": line_no, "child": child_no}
                normalized["cluster_id"] = e["cluster_id"]
                try:
                    at = timestamp(normalized["observed_at"])
                    if (
                        not timestamp(e["time_range"]["start"])
                        <= at
                        <= timestamp(e["time_range"]["end"])
                    ):
                        raise ValueError("outside period")
                except (ValueError, TypeError, AttributeError):
                    normalized.update(
                        check_status="unknown",
                        normalized_health="unknown",
                        severity="unknown",
                    )
                results.append(normalized)
    return results


def health_facts(health, target):
    selected = [
        r
        for r in health
        if r["check_status"] == "valid"
        and r["normalized_health"] != "unknown"
        and target
        and all(r["target"].get(k) == v for k, v in target.items())
    ]
    facts = {}
    # Do not promote a mixture of device states to a single fact for a whole scope.
    for field in ("normalized_health", "component", "severity", "producer_contract"):
        values = {r[field] for r in selected}
        if len(values) == 1:
            facts[field] = values.pop()
    return facts
