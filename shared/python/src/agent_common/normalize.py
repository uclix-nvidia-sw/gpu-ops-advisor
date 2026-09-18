from collections import defaultdict

from .calculations import sample_intervals, union
from .contracts import timestamp
from .observation import series


def intervals(evidence, period):
    start, end = timestamp(period["start"]), timestamp(period["end"])
    out = []
    for row in series(evidence):
        row["intervals"] = sample_intervals(
            row["samples"], start, end, row["max_hold_seconds"] or 0
        )
        out.append(row)
    return out


def allocations(evidence, period, pods=None, *, observed=False):
    out = []
    identities = defaultdict(lambda: defaultdict(list))
    identity_refs = defaultdict(set)
    for pod in intervals(pods or [], period):
        labels = pod["labels"]
        if not all(labels.get(k) for k in ("namespace", "pod", "node", "uid")):
            continue
        key = (pod["cluster_id"], labels["namespace"], labels["pod"], labels["node"])
        identities[key][labels["uid"]].extend(
            (a, b) for a, b, v in pod["intervals"] if v == 1
        )
        identity_refs[key].update(pod["evidence_refs"])
    # Resolve Pod names only where a single UID is observed. A restarted Pod
    # may have overlapping stale series; those intervals must stay unknown.
    pod_windows = {}
    for key, uids in identities.items():
        events = defaultdict(list)
        for uid, spans in uids.items():
            for a, b in union(spans):
                events[a].append((uid, 1))
                events[b].append((uid, -1))
        active = set()
        windows = []
        times = sorted(events)
        for i, at in enumerate(times[:-1]):
            for uid, change in events[at]:
                if change == 1:
                    active.add(uid)
                else:
                    active.discard(uid)
            if len(active) == 1:
                windows.append((at, times[i + 1], next(iter(active))))
        pod_windows[key] = windows
    for s in intervals(evidence, period):
        labels = s["labels"]
        gpu = labels.get("gpu_uuid") or labels.get("UUID") or labels.get("uuid")
        if not gpu or not labels.get("pod"):
            continue
        uid = labels.get("pod_uid") or labels.get("uid")
        mode = "unknown" if observed else labels.get("allocation_mode", "unknown")
        # Deployment must explicitly establish exclusive/shared/MIG meaning.
        if mode not in {"exclusive", "shared", "mig"}:
            mode = "unknown"
        for a, b, value in s["intervals"]:
            # Zero GPU utilization still proves an observed mapping. A zero
            # normalized allocation-info sample does not prove an allocation.
            if value < 0 or (not observed and value == 0):
                continue
            matches = []
            evidence_refs = list(s["evidence_refs"])
            if uid:
                matches = [(a, b, uid)]
            else:
                key = (
                    s["cluster_id"],
                    labels.get("namespace"),
                    labels.get("pod"),
                    labels.get("node"),
                )
                matches = [
                    (max(a, x), min(b, y), pod_uid)
                    for x, y, pod_uid in pod_windows.get(key, [])
                    if min(b, y) > max(a, x)
                ]
                evidence_refs += sorted(identity_refs.get(key, set()))
            for x, y, pod_uid in matches:
                out.append(
                    dict(
                        cluster_id=s["cluster_id"],
                        gpu_uuid=gpu,
                        pod_uid=pod_uid,
                        namespace=labels.get("namespace"),
                        pod=labels.get("pod"),
                        node=labels.get("node"),
                        project=labels.get("project"),
                        mode=mode,
                        instance_id=labels.get("instance_id"),
                        episode=None
                        if observed
                        else labels.get("allocation_episode_key"),
                        start=x,
                        end=y,
                        evidence_refs=evidence_refs,
                    )
                )
    return out


def gpu_intervals(evidence, period):
    out = {}
    for row in intervals(evidence, period):
        labels = row["labels"]
        gpu = labels.get("gpu_uuid") or labels.get("UUID") or labels.get("uuid")
        if not gpu:
            continue
        key = (row["cluster_id"], gpu)
        # Conflicting producers are withheld instead of averaged or double-counted.
        if key in out:
            out[key] = []
        else:
            out[key] = row["intervals"]
    return out
