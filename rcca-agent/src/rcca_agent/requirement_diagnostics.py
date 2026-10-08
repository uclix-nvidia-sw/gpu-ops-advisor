"""Explain unmet requirements without creating facts or changing assessments."""


def _scoped_reports(health, events, data):
    target = data.get("target", {})
    cluster = target.get("cluster_id")
    clusters = data.get("scope", {}).get("clusters", [])
    if not cluster and len(clusters) == 1:
        cluster = clusters[0].get("cluster_id")
    identity = {
        k: target[k]
        for k in ("machine_id", "node", "gpu_uuid", "pod_uid")
        if target.get(k)
    }
    if target.get("k8s_node_name"):
        if identity.get("node", target["k8s_node_name"]) != target["k8s_node_name"]:
            return [], []
        identity["node"] = target["k8s_node_name"]

    def matches(row):
        return (
            not data.get("identity_conflicts")
            and bool(identity)
            and bool(cluster)
            and row.get("cluster_id") == cluster
            and (
                not target.get("component")
                or row.get("component") == target["component"]
            )
            and all(row.get("target", {}).get(k) == v for k, v in identity.items())
        )

    reports = [h for h in health if matches(h) and h.get("check_status") == "valid"]
    reported_events = [
        e for e in events if matches(e) and e.get("status") == "reported_event"
    ]
    return reports, reported_events


def unmet_requirements(missing, health, events, data):
    reports, reported_events = _scoped_reports(health, events, data)
    result = []
    for requirement in sorted(set(missing)):
        observed = []
        if requirement in {"error_code", "producer_contract", "normalized_health"}:
            observed = [
                h for h in reports if h.get(requirement) not in (None, "unknown", "")
            ]
            if requirement == "error_code":
                observed += [e for e in reported_events if e.get("error_code")]
            reason = (
                "reported_but_required_semantics_unverified"
                if observed
                else "required_fact_not_established"
            )
        elif requirement == "causal_confirmation_evidence":
            reason = "cause_not_confirmed"
        else:
            continue
        result.append(
            {
                "requirement": requirement,
                "status": "unmet",
                "reason": reason,
                "evidence_refs": sorted(
                    {r for row in observed for r in row.get("evidence_refs", [])}
                ),
            }
        )
    return result


def reported_facts(health, events, data):
    """Scoped source reports; never current-health or action-condition facts."""
    reports, reported_events = _scoped_reports(health, events, data)
    result = {}
    for field in ("error_code", "producer_contract"):
        rows = reports + (reported_events if field == "error_code" else [])
        values = {
            r.get(field)
            for r in rows
            if r.get("evidence_refs") and r.get(field) not in (None, "unknown", "")
        }
        if len(values) == 1:
            result["reported_" + field] = values.pop()
    return result


def requirement_groups(content):
    """Expose existing validation gates without weakening their requirements."""
    groups = {
        "reported_facts": [],
        "device_state": [],
        "cause": [],
        "action_conditions": [],
    }
    for fact in content.get("required_evidence", []):
        group = "reported_facts" if fact.startswith("reported_") else "device_state"
        groups[group].append(fact)
    groups["cause"] = ["causal_confirmation_evidence"]
    groups["action_conditions"] = sorted(
        {
            condition["field"]
            for recommendation in content.get("recommendations", [])
            for condition in recommendation.get("preconditions", [])
        }
    )
    return groups
