"""O08 draft: activity of observed connected GPUs, never tenant consumption."""

from collections import defaultdict

from agent_common.calculations import allocation_hours, seconds, union
from agent_common.contracts import timestamp
from agent_common.normalize import allocations, intervals
from agent_common.observation import series


def namespace_usage(data, collected):
    period = data["time_range"]
    scope = {c["cluster_id"]: c["namespaces"] for c in data["scope"]["clusters"]}
    usable = {
        q: [
            e for e in collected.get(q, []) if e["quality"].get("complete") is not False
        ]
        for q in ("D01", "D02", "D06", "D08")
    }
    observed = allocations(usable["D01"], period, usable["D06"], observed=True)
    # An instance UUID cannot be counted as a physical GPU without its parent history.
    observed = [r for r in observed if not r["gpu_uuid"].startswith("MIG-")]
    allocated = allocations(usable["D08"], period, usable["D06"])
    mapped_windows = defaultdict(list)
    for r in observed:
        mapped_windows[
            (r["cluster_id"], r["gpu_uuid"], r["namespace"], r["pod"], r["node"])
        ].append((r["start"], r["end"]))
    mapped_windows = {key: union(spans) for key, spans in mapped_windows.items()}
    inventory = {
        cluster: dict(
            gpus=set(), unlabeled=set(), unattributed=set(), issues=False, invalid=False
        )
        for cluster in scope
    }
    groups = {}
    events = defaultdict(lambda: defaultdict(list))
    unattributed = 0

    def group(cluster, namespace):
        return groups.setdefault(
            (cluster, namespace),
            dict(
                rows=[],
                seconds=0.0,
                weighted=0.0,
                reasons=set(),
                models=set(),
                gpus=set(),
            ),
        )

    def allowed(cluster, namespace):
        return cluster in scope and (
            scope[cluster] is None or namespace in scope[cluster]
        )

    def register(key, kind, row, spans):
        for start, end in spans:
            token = (kind, id(row), start, end)
            events[key][start].append((token, row))
            events[key][end].append((token, None))

    for cluster, namespaces in scope.items():
        for namespace in namespaces or []:
            group(cluster, namespace)
    for row in observed:
        if row["namespace"] and allowed(row["cluster_id"], row["namespace"]):
            group(row["cluster_id"], row["namespace"])["rows"].append(row)
            register(
                (row["cluster_id"], row["gpu_uuid"]),
                "mapping",
                row,
                [(row["start"], row["end"])],
            )
    for row in allocated:
        register(
            (row["cluster_id"], row["gpu_uuid"]),
            "allocation",
            row,
            [(row["start"], row["end"])],
        )

    for query in ("D01", "D02"):
        units = {e["id"]: e["quality"].get("unit") for e in usable[query]}
        for row in intervals(usable[query], period):
            labels, cluster = row["labels"], row["cluster_id"]
            gpu = labels.get("gpu_uuid") or labels.get("UUID") or labels.get("uuid")
            namespace = labels.get("namespace")
            if cluster not in scope:
                continue
            if query == "D01" and allowed(cluster, namespace):
                spans = [(a, b) for a, b, value in row["intervals"] if value >= 0]
                if not spans:
                    inventory[cluster]["invalid"] = True
                    continue
                state = inventory[cluster]
                physical = (
                    bool(gpu)
                    and not gpu.startswith("MIG-")
                    and not any(
                        labels.get(k) is not None
                        for k in ("instance_id", "GPU_I_ID", "GPU_CI_ID")
                    )
                )
                if physical:
                    state["gpus"].add(gpu)
                mapped = mapped_windows.get(
                    (cluster, gpu, namespace, labels.get("pod"), labels.get("node")), []
                )
                blank = not any(
                    labels.get(k) for k in ("namespace", "pod", "pod_uid", "uid")
                )
                if blank and physical and scope[cluster] is None:
                    state["unlabeled"].add(gpu)
                elif (
                    not physical
                    or not namespace
                    or not labels.get("pod")
                    or seconds(spans + mapped) > seconds(mapped) + 1e-6
                ):
                    unattributed += 1
                    state["issues"] = True
                    if physical:
                        state["unattributed"].add(gpu)
                if namespace and allowed(cluster, namespace):
                    group(cluster, namespace)
            if not gpu:
                continue
            row["unit_valid"] = all(units[r] == "percent" for r in row["evidence_refs"])
            for start, end, value in row["intervals"]:
                item = dict(row, value=value)
                register((cluster, gpu), query, item, [(start, end)])

    for (cluster, gpu), changes in sorted(events.items()):
        active = {}
        times = sorted(changes)
        for start, end in zip(times, times[1:]):
            for token, row in changes[start]:
                if row is None:
                    active.pop(token, None)
                else:
                    active[token] = row
            mappings = [r for t, r in active.items() if t[0] == "mapping"]
            if not mappings:
                continue
            sources = [r for t, r in active.items() if t[0] in {"D01", "D02"}]
            activity = [r for t, r in active.items() if t[0] == "D02"]
            allocation = [r for t, r in active.items() if t[0] == "allocation"]
            identities = {(r["namespace"], r["pod_uid"]) for r in mappings}
            names = {(r["namespace"], r["pod"], r["node"]) for r in mappings}
            reason = None
            if (
                len(identities) != 1
                or any(r["mode"] in {"shared", "mig"} for r in allocation)
                or len({(r["namespace"], r["pod_uid"]) for r in allocation}) > 1
            ):
                reason = "shared_gpu_attribution_unverified"
            elif any(
                (
                    r["labels"].get("namespace"),
                    r["labels"].get("pod"),
                    r["labels"].get("node"),
                )
                not in names
                or (
                    (r["labels"].get("pod_uid") or r["labels"].get("uid"))
                    and (
                        r["labels"].get("namespace"),
                        r["labels"].get("pod_uid") or r["labels"].get("uid"),
                    )
                    not in identities
                )
                or any(
                    r["labels"].get(k) is not None
                    for k in ("instance_id", "GPU_I_ID", "GPU_CI_ID")
                )
                for r in sources
            ):
                reason = "gpu_activity_identity_unverified"
            elif not activity:
                reason = "gpu_activity_missing"
            elif not all(r["unit_valid"] for r in activity):
                reason = "source_unit_unverified"
            elif any(not 0 <= r["value"] <= 100 for r in activity):
                reason = "invalid_gpu_activity"
            elif len({r["value"] for r in activity}) != 1:
                reason = "conflicting_gpu_activity"
            models = {
                r["labels"].get("modelName") or r["labels"].get("model")
                for r in activity
            }
            for namespace in {r["namespace"] for r in mappings}:
                summary = group(cluster, namespace)
                if reason:
                    summary["reasons"].add(reason)
                else:
                    summary["seconds"] += end - start
                    summary["weighted"] += activity[0]["value"] * (end - start)
                    summary["models"].update(models)
                    summary["gpus"].add(gpu)

    output = []
    for (cluster, namespace), summary in sorted(groups.items()):
        connected = (
            allocation_hours(summary["rows"], "unknown") * 3600
            if summary["rows"]
            else None
        )
        valid = summary["seconds"]
        reasons = summary["reasons"]
        if connected is None:
            reasons.add("gpu_pod_identity_missing")
        models = summary["models"]
        if len(models - {None}) > 1 or (len(summary["gpus"]) > 1 and None in models):
            reasons.add("gpu_model_comparison_unverified")
            valid = 0.0
        if connected is not None and valid < connected and not reasons:
            reasons.add("gpu_activity_missing")
        output.append(
            dict(
                target={"cluster_id": cluster, "namespace": namespace},
                connected_gpu_count=len({r["gpu_uuid"] for r in summary["rows"]})
                if summary["rows"]
                else None,
                connected_hours=connected / 3600 if connected is not None else None,
                valid_hours=valid / 3600 if connected is not None else None,
                mean=summary["weighted"] / valid if valid else None,
                reasons=sorted(reasons),
            )
        )
    cluster_output = []
    for cluster in sorted(scope):
        state = inventory[cluster]
        es = [e for e in collected.get("D01", []) if e["cluster_id"] == cluster]
        # Successful empty collection can establish zero observed devices; a missing
        # query or incomplete requested range cannot. This is not fleet coverage.
        complete = (
            bool(es)
            and all(
                e["tool_status"] in {"ok", "empty"}
                and e["quality"].get("complete") is True
                for e in es
            )
            and seconds(
                [
                    (
                        max(
                            timestamp(e["time_range"]["start"]),
                            timestamp(period["start"]),
                        ),
                        min(
                            timestamp(e["time_range"]["end"]), timestamp(period["end"])
                        ),
                    )
                    for e in es
                    if e.get("time_range")
                ]
            )
            >= timestamp(period["end"]) - timestamp(period["start"])
        )
        connections = [
            r
            for r in observed
            if r["cluster_id"] == cluster
            and allowed(cluster, r["namespace"])
            and r["gpu_uuid"] in state["gpus"]
        ]
        known = bool(state["gpus"]) or (
            complete and not state["issues"] and not state["invalid"]
        )
        zero_connections = complete and not state["issues"] and not state["invalid"]
        cluster_output.append(
            dict(
                target={"cluster_id": cluster},
                observed_gpu_count=len(state["gpus"]) if known else None,
                connected_gpu_count=len({r["gpu_uuid"] for r in connections})
                if connections or zero_connections
                else None,
                connected_gpu_hours=allocation_hours(connections, "unknown")
                if connections or zero_connections
                else None,
                unlabeled_gpu_count=len(state["unlabeled"]) if known else None,
                unattributed_gpu_count=len(state["unattributed"]) if known else None,
                reason="unattributed_gpu_observation"
                if state["issues"]
                else "gpu_inventory_missing",
                complete=complete,
            )
        )
    return output, unattributed, cluster_output


def pod_namespace_scope(collected):
    """Narrow only complete namespace-report inputs; missing clues retain the full scope."""
    out = {}
    clusters = {e["cluster_id"] for e in collected.get("D01", [])}
    for cluster in clusters:
        sources = {
            q: [e for e in collected.get(q, []) if e["cluster_id"] == cluster]
            for q in ("D01", "D08")
        }
        if any(
            not es
            or any(
                e["tool_status"] not in {"ok", "empty"}
                or e["quality"].get("complete") is not True
                for e in es
            )
            for es in sources.values()
        ):
            continue
        labels = [
            r["labels"]
            for es in sources.values()
            for r in series(es)
            if r["labels"].get("pod")
        ]
        if labels and all(r.get("namespace") for r in labels):
            out[cluster] = sorted({r["namespace"] for r in labels})
    return out
