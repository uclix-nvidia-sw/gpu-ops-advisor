"""Hourly observed connections and sustained low activity; never allocation advice."""

from collections import defaultdict
from datetime import datetime, timezone

from agent_common.calculations import union


def iso(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat().replace("+00:00", "Z")


def activity_trends(rows, valid, start, end):
    # The caller has already rejected ambiguous GPU/Pod identities and values.
    buckets = {}
    at = start
    while at < end:
        stop = min(end, (int(at) // 3600 + 1) * 3600)
        buckets[int(at) // 3600] = dict(start=at, end=stop, connections=[], models={})
        at = stop
    for row in rows:
        at, stop = max(start, row["start"]), min(end, row["end"])
        while at < stop:
            key = int(at) // 3600
            until = min(stop, buckets[key]["end"])
            buckets[key]["connections"].append((at, until, row["gpu_uuid"]))
            at = until
    lows = defaultdict(list)
    models = defaultdict(lambda: [0.0, 0.0])
    for a, b, gpu, model, value in valid:
        models[model][0] += value * (b - a)
        models[model][1] += b - a
        if value < 5:
            lows[(gpu, model)].append((a, b))
        at = a
        while at < b:
            key = int(at) // 3600
            until = min(b, buckets[key]["end"])
            item = buckets[key]["models"].setdefault(model, [0.0, 0.0])
            item[0] += value * (until - at)
            item[1] += until - at
            at = until
    hourly = []
    for bucket in buckets.values():
        devices = defaultdict(list)
        for a, b, gpu in bucket["connections"]:
            devices[gpu].append((a, b))
        changes = defaultdict(int)
        for spans in devices.values():
            for a, b in union(spans):
                changes[a] += 1
                changes[b] -= 1
        current = peak = 0
        for at in sorted(changes):
            current += changes[at]
            peak = max(peak, current)
        hourly.append(
            dict(
                period={"start": iso(bucket["start"]), "end": iso(bucket["end"])},
                peak_gpu_count=peak if devices else None,
                activity=[
                    dict(model=model, mean=total / duration, valid_seconds=duration)
                    for model, (total, duration) in sorted(bucket["models"].items())
                ],
            )
        )
    low_windows = [
        dict(
            gpu_uuid=gpu,
            model=model,
            period={"start": iso(a), "end": iso(b)},
            seconds=b - a,
        )
        for (gpu, model), spans in sorted(lows.items())
        for a, b in union(spans)
        if b - a >= 1800
    ]
    return dict(
        hourly=hourly,
        low_windows=low_windows,
        model_means=[
            dict(model=model, mean=total / duration, valid_seconds=duration)
            for model, (total, duration) in sorted(models.items())
        ],
    )
