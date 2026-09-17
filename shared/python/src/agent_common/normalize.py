from .calculations import sample_intervals, intersect
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


def allocations(evidence, period, pods=None):
    out = []
    pod_rows = intervals(pods or [], period)
    for s in intervals(evidence, period):
        labels = s["labels"]
        gpu = labels.get("gpu_uuid") or labels.get("UUID") or labels.get("uuid")
        if not gpu or not labels.get("pod"):
            continue
        uid = labels.get("pod_uid") or labels.get("uid")
        mode = labels.get("allocation_mode", "unknown")
        # Deployment must explicitly establish exclusive/shared/MIG meaning.
        if mode not in {"exclusive", "shared", "mig"}:
            mode = "unknown"
        for a, b, value in s["intervals"]:
            if value < 0:
                continue
            matches = []
            if uid:
                matches = [(a, b, uid)]
            else:
                for pod in pod_rows:
                    pl = pod["labels"]
                    if (
                        pod["cluster_id"] == s["cluster_id"]
                        and all(
                            pl.get(k) == labels.get(k)
                            for k in ("namespace", "pod", "node")
                        )
                        and pl.get("uid")
                    ):
                        matches += [
                            (x, y, pl["uid"])
                            for x, y in intersect(
                                [(a, b)],
                                [(x, y) for x, y, v in pod["intervals"] if v == 1],
                            )
                        ]
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
                        episode=labels.get("allocation_episode_key"),
                        start=x,
                        end=y,
                        evidence_refs=s["evidence_refs"],
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
