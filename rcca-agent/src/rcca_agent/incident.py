"""Normalize Grafana/Fleet search clues without promoting them to verified facts."""

import json

from .retrieval import XID


def alert_clues(source):
    alert = source.get("alert", {})
    result = {"status": "unverified", "conflicts": []}
    labels, annotations = {}, {}
    for key, destination in (("labels", labels), ("annotations", annotations)):
        value = alert.get(key, {})
        if isinstance(value, dict):
            destination.update(value)
        else:
            result["conflicts"].append(key)
    for key in (
        "component",
        "machine_id",
        "k8s_node_name",
        "reason",
        "suggested_actions",
    ):
        left, right = labels.get(key), annotations.get(key)
        if left and right and left != right:
            result["conflicts"].append(key)
            continue
        if isinstance(left or right, str):
            result[key] = left or right
    if result.get("component", "").endswith(("-xid", "-sxid")):
        result["symptom"] = "xid"
    result["error_codes"] = sorted(
        {
            f"{kind.lower()}:{int(code)}"
            for kind, code in XID.findall(result.get("reason", ""))
        }
    )
    raw = result.get("suggested_actions")
    if raw:
        try:
            parsed = json.loads(raw)
            if (
                not isinstance(parsed, dict)
                or not isinstance(parsed.get("description"), str)
                or not isinstance(parsed.get("repair_actions"), list)
                or not all(
                    isinstance(action, str) for action in parsed["repair_actions"]
                )
            ):
                raise ValueError("invalid actions")
            result["provider_actions"] = {
                "value": parsed,
                "execution": "not_performed",
                "eligibility": "withheld",
            }
        except (ValueError, TypeError):
            result["provider_actions_status"] = "invalid"
    return result
