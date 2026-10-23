"""Supplemental workload facts. Missing sources are not zero workloads."""

from collections import defaultdict
import math

from agent_common.contracts import metric, timestamp
from .report_contract import MAX_NAMESPACES, iso
from .workload_queries import QUERY_IDS
from .collector_identity import series_for


def enrich_workloads(topic, evidence, data):
    current = [
        e
        for e in evidence
        if e["query_id"] in QUERY_IDS and e["time_range"] == data["time_range"]
    ]
    if not current:
        return
    start, end = (timestamp(data["time_range"][k]) for k in ("start", "end"))
    hours = defaultdict(lambda: defaultdict(list))
    jobs = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    job_sources = defaultdict(set)
    namespaces = {
        (r["cluster_id"], r["namespace"])
        for r in topic.get("rows", [])
        if r["namespace"]
    }
    for e in current:
        allowed = e["scope"]["clusters"][0].get("namespaces")
        if allowed is not None:
            namespaces.update((e["cluster_id"], n) for n in allowed)
        if e["tool_status"] != "ok":
            continue
        for series in series_for(e):
            labels = series["metric"]
            cluster, ns = labels.get("cluster_id"), labels.get("namespace")
            if (
                cluster != e["cluster_id"]
                or not ns
                or (allowed is not None and ns not in allowed)
            ):
                continue
            namespaces.add((cluster, ns))
            for at, value in series["values"]:
                try:
                    at = float(at)
                except (ValueError, TypeError):
                    continue
                if (
                    not math.isfinite(at)
                    or not start < at <= end
                    or (at - start) % 3600
                ):
                    continue
                # Keep invalid values so they cannot hide a contradictory duplicate.
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = math.nan
                if e["query_id"] == "hourly_gpu_workload":
                    hours[(cluster, ns, at)][labels.get("measure")].append(value)
                elif labels.get("job_name"):
                    key = (cluster, ns, labels["job_name"])
                    job_sources[key].add(
                        tuple(
                            sorted(
                                (k, v)
                                for k, v in labels.items()
                                if k not in {"measure", "__name__"}
                            )
                        )
                    )
                    jobs[key][at][labels.get("measure")].append(value)

    if len(namespaces) > MAX_NAMESPACES:
        topic["workloads"] = []
        topic["workload_unavailable_reason"] = "namespace_limit_exceeded"
        return

    def stable(values, field):
        low, high = values.get(field + "_min", []), values.get(field + "_max", [])
        if len(low) == len(high) == 1 and 0 < low[0] == high[0]:
            return low[0]
        return None

    completed = defaultdict(list)
    excluded = defaultdict(int)
    for (cluster, ns, job), observations in jobs.items():
        lifetimes, candidates = set(), []
        invalid = len(job_sources[(cluster, ns, job)]) != 1
        for at, values in observations.items():
            created = stable(values, "created")
            if created is None:
                invalid = True
                continue
            lifetimes.add(created)
            started, finished = stable(values, "started"), stable(values, "completed")
            if any(k.startswith("completed_") for k in values):
                if (
                    started is None
                    or finished is None
                    or not created <= started <= finished < at
                ):
                    invalid = True
                elif start <= finished < end:
                    candidates.append((created, started, finished))
        # KSM Job gauges have no UID. Reused names/changed timestamps cannot be attributed safely.
        if invalid or len(lifetimes) != 1 or len(set(candidates)) > 1:
            excluded[(cluster, ns)] += 1
        elif candidates:
            created, started, finished = candidates[0]
            completed[(cluster, ns)].append(
                {
                    "job_name": job,
                    "created_at": iso(created),
                    "started_at": iso(started),
                    "completed_at": iso(finished),
                    "elapsed_seconds": finished - started,
                }
            )

    output = []
    for cluster, ns in sorted(namespaces):
        refs = [e["id"] for e in current if e["cluster_id"] == cluster]
        observed_hours = []
        for (c, n, at), values in sorted(hours.items()):
            if (c, n) != (cluster, ns):
                continue
            hour = {"start": iso(at - 3600), "end": iso(at)}
            for state in ("pending", "unscheduled", "running"):
                peaks, samples = (
                    values.get(state + "_peak", []),
                    values.get(state + "_samples", []),
                )
                valid = (
                    len(peaks) == len(samples) == 1
                    and all(math.isfinite(v) and v >= 0 for v in peaks + samples)
                    and peaks[0].is_integer()
                    and samples[0].is_integer()
                    and 0 < samples[0] <= 240
                )
                hour[state + "_peak"] = int(peaks[0]) if valid else None
                hour[state + "_samples"] = int(samples[0]) if valid else 0
            if (
                all(
                    hour[s + "_peak"] is not None
                    for s in ("pending", "unscheduled", "running")
                )
                and hour["unscheduled_peak"] > hour["pending_peak"]
            ):
                for state in ("pending", "unscheduled", "running"):
                    hour[state + "_peak"], hour[state + "_samples"] = None, 0
            observed_hours.append(hour)
        observed_jobs = completed[(cluster, ns)]
        row = {
            "cluster_id": cluster,
            "namespace": ns,
            "hours": observed_hours,
            "completed_jobs": observed_jobs,
            "excluded_jobs": excluded[(cluster, ns)],
            "evidence_refs": refs,
            "completed_observed": len(observed_jobs) if observed_jobs else None,
            "mean_elapsed_seconds": sum(j["elapsed_seconds"] for j in observed_jobs)
            / len(observed_jobs)
            if observed_jobs
            else None,
        }
        for state in ("pending", "unscheduled", "running"):
            row[state + "_peak"] = max(
                (
                    h[state + "_peak"]
                    for h in observed_hours
                    if h[state + "_peak"] is not None
                ),
                default=None,
            )
        row["status"] = (
            "partial"
            if observed_jobs
            or any(
                row[s + "_peak"] is not None
                for s in ("pending", "unscheduled", "running")
            )
            else "unavailable"
        )
        output.append(row)
        target = {"cluster_id": cluster, "namespace": ns}
        ids = []
        for name, value, unit in (
            ("pending_peak", row["pending_peak"], "pods"),
            ("unscheduled_peak", row["unscheduled_peak"], "pods"),
            ("running_peak", row["running_peak"], "pods"),
            ("completed_observed", row["completed_observed"], "jobs"),
            ("mean_elapsed_seconds", row["mean_elapsed_seconds"], "seconds"),
        ):
            m = metric(
                f"namespace_usage.workload_{name}.{len(topic['metrics'])}",
                value,
                unit,
                data,
                refs,
                "observed_gpu_workload_v1",
                "workload_observation_missing" if value is None else None,
            )
            m["target"] = target
            topic["metrics"].append(m)
            if value is not None:
                ids.append(m["id"])
        if ids:
            topic["findings"].append(
                {
                    "id": f"namespace-workload-{len(output)}",
                    "target": target,
                    "value_refs": ids,
                    "evidence_refs": refs,
                    "text": f"{cluster} / {ns}: GPU를 요청한 일반 컨테이너가 있는 Pod의 관측 상태와 성공 완료가 확인된 Job 표본입니다. 대기는 GPU 부족의 증거가 아니며 Job 소요시간은 GPU 연산 시간이 아닙니다. 누락·짧은 작업·init 전용 GPU 요청·MIG·Run:ai 대기열은 포함을 보장하지 않습니다. 0건 완료 또는 전체 작업 수로 해석하지 마세요.",
                }
            )
        topic["evidence_refs"] = list(dict.fromkeys(topic["evidence_refs"] + refs))
    topic["workloads"] = output
