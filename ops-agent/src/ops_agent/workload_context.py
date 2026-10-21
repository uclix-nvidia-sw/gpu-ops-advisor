"""Optional, time-aligned Pod labels and regular-container requests, not allocation."""

from collections import defaultdict
import math

from agent_common.contracts import timestamp
from .report_contract import iso
from .report_queries import selector

QUERY_ID = "hourly_gpu_workload_context"
VERSION = "pod-workload-context-v1"
POD_KEY = "cluster_id, namespace, pod, uid"
LABEL_FIELDS = tuple(
    "label_gpu_report_test_" + field
    for field in ("purpose", "profile", "execution", "queue_design", "run")
)
PROFILE_NAMES = {
    "service-wave": "서비스 부하 모의 테스트",
    "research-wave": "연구 부하 모의 테스트",
    "batch-wave": "배치 부하 모의 테스트",
}
LIMITS = (
    "작업 유형은 제출자가 붙인 테스트 라벨이며 실제 training·serving 목적이 아닙니다.",
    "GPU 요청은 일반 컨테이너의 요청 합계입니다. 초기화 컨테이너·실제 장치 할당·여유 GPU 수는 확인하지 않았습니다.",
    "노드 배정과 실행 상태는 대기 원인을 증명하지 않습니다. 대기 설계 라벨도 스케줄러 이벤트가 아닙니다.",
    "시간대 안에서 연결 정보가 바뀌거나 부족한 표본은 제외합니다. 기존 대기·완료 집계의 전체 작업을 대표하지 않습니다.",
)


def context_queries(cluster):
    def selected(name, extra=""):
        return selector(name, cluster)[:-1] + ',uid!=""' + extra + "}"

    def unique(expr, fields):
        return f"(max by ({fields}) ({expr}) == min by ({fields}) ({expr}))"

    raw = selected(
        "kube_pod_container_resource_requests",
        ',resource="nvidia_com_gpu",container!=""',
    )
    key = POD_KEY + ", container"
    valid = unique(raw, key)
    # A contradictory container must not silently disappear from the Pod sum.
    requests = (
        f"(sum by ({POD_KEY}) ({valid}) and on ({POD_KEY}) "
        f"(count by ({POD_KEY}) ({valid}) == count by ({POD_KEY}) "
        f"(count by ({key}) ({raw})))) > 0"
    )

    presence = f"max by ({POD_KEY}) ({raw} > bool 0)"

    def join(left, raw, fields, optional=False):
        key = POD_KEY + ", " + fields
        right = unique(raw, key)
        right = f"(({right} == 1) and on ({POD_KEY}) (count by ({POD_KEY}) ({right} == 1) == 1))"
        if optional:
            right = f"({right}) or on ({POD_KEY}) ({presence})"
        return f"(({left}) * on ({POD_KEY}) group_left ({fields}) ({right}))"

    expr = join(requests, selected("kube_pod_info"), "node")
    expr = join(expr, selected("kube_pod_status_phase"), "phase")
    expr = join(expr, selected("kube_pod_labels"), ", ".join(LABEL_FIELDS), True)
    expr = join(
        expr,
        selected("kube_pod_owner", ',owner_kind="Job",owner_is_controller="true"'),
        "owner_name",
        True,
    )
    return {
        QUERY_ID: " or ".join(
            f'label_replace({fn}(({expr})[1h:15s] offset 1ms), "measure", "{measure}", "", "")'
            for measure, fn in (
                ("min", "min_over_time"),
                ("max", "max_over_time"),
                ("samples", "count_over_time"),
            )
        )
    }


def enrich_context(topic, evidence, data):
    sources = [
        e
        for e in evidence
        if e["query_id"] == QUERY_ID and e["time_range"] == data["time_range"]
    ]
    if not sources:
        return
    start, end = (timestamp(data["time_range"][k]) for k in ("start", "end"))
    grouped = defaultdict(lambda: defaultdict(list))
    refs = defaultdict(set)
    identity_fields = (
        "cluster_id",
        "namespace",
        "pod",
        "uid",
        "node",
        "phase",
        "owner_name",
    ) + LABEL_FIELDS
    allowed_clusters = {
        c["cluster_id"]: c.get("namespaces") for c in data["scope"]["clusters"]
    }
    for e in sources:
        if e["tool_status"] != "ok" or e["cluster_id"] not in allowed_clusters:
            continue
        allowed = allowed_clusters[e["cluster_id"]]
        source_allowed = e["scope"]["clusters"][0].get("namespaces")
        for series in e["snapshot"]["series"]:
            labels = series["metric"]
            if (
                labels.get("cluster_id") != e["cluster_id"]
                or not all(labels.get(k) for k in ("namespace", "pod", "uid"))
                or (allowed is not None and labels["namespace"] not in allowed)
                or (
                    source_allowed is not None
                    and labels["namespace"] not in source_allowed
                )
            ):
                continue
            identity = tuple(labels.get(k, "") for k in identity_fields)
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
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = math.nan
                grouped[(identity, at)][labels.get("measure")].append(value)
                refs[(identity, at)].add(e["id"])
    # Do not choose one variant when labels/state/node change within the same hour.
    variants = defaultdict(set)
    for identity, at in grouped:
        variants[(identity[:4], at)].add(identity)
    records, excluded = [], 0
    for (identity, at), values in sorted(grouped.items()):
        if len(variants[(identity[:4], at)]) != 1 or any(
            len(values.get(k, [])) != 1 for k in ("min", "max", "samples")
        ):
            excluded += 1
            continue
        low, high, samples = (values[k][0] for k in ("min", "max", "samples"))
        if not (math.isfinite(low) and low == high and low > 0 and samples == 240):
            excluded += 1
            continue
        labels = dict(zip(identity_fields, identity))
        phase, node = labels["phase"], labels["node"]
        if phase not in {"Pending", "Running", "Succeeded", "Failed"} or (
            phase == "Running" and not node
        ):
            excluded += 1
            continue
        purpose, profile, execution, queue, run = (labels[k] for k in LABEL_FIELDS)
        known = (
            purpose == "synthetic-observation"
            and profile in PROFILE_NAMES
            and execution == ("batch" if profile == "batch-wave" else "continuous")
        )
        records.append(
            {
                **{k: labels[k] for k in ("cluster_id", "namespace", "pod", "uid")},
                "period": {"start": iso(at - 3600), "end": iso(at)},
                "node": node or None,
                "phase": phase,
                "job_name": labels["owner_name"] or None,
                "regular_gpu_request": low,
                "workload_type": PROFILE_NAMES[profile]
                if known
                else "작업 유형 미확인",
                "type_status": "declared_test" if known else "unknown",
                "profile": profile if known else None,
                "execution": execution if known else None,
                "queue_design": queue
                if known and queue in {"none", "pod-antiaffinity"}
                else None,
                "evidence_refs": sorted(refs[(identity, at)]),
            }
        )
    completed = []
    for workload in topic.get("workloads", []):
        for job in workload.get("completed_jobs", []):
            linked = [
                r
                for r in records
                if all(r[k] == workload[k] for k in ("cluster_id", "namespace"))
                and r["job_name"] == job["job_name"]
                and job["created_at"]
                <= r["period"]["start"]
                < r["period"]["end"]
                <= job["completed_at"]
            ]
            types = {(r["workload_type"], r["type_status"]) for r in linked}
            known = len(types) == 1 and next(iter(types))[1] == "declared_test"
            completed.append(
                {
                    "cluster_id": workload["cluster_id"],
                    "namespace": workload["namespace"],
                    "job_name": job["job_name"],
                    "created_at": job["created_at"],
                    "workload_type": next(iter(types))[0]
                    if known
                    else "작업 유형 미확인",
                    "type_status": "declared_test" if known else "unknown",
                    "pod_uids": sorted({r["uid"] for r in linked}),
                    "evidence_refs": sorted(
                        set(workload.get("evidence_refs", []))
                        | {ref for r in linked for ref in r["evidence_refs"]}
                    ),
                }
            )
    topic["workload_context"] = {
        "completed_jobs": completed,
        "version": VERSION,
        "records": records,
        "excluded_records": excluded,
        "status": "partial" if records else "unavailable",
        "limitations": list(LIMITS),
        "evidence_refs": sorted({e["id"] for e in sources}),
    }
    # Existing metrics/findings/candidates are deliberately not changed.


def context_for(fact, topic):
    """Bound LLM context to the candidate's exact hours; never send raw label text."""
    hours = {(h["start"], h["end"]) for h in fact.get("source_hours", [])}
    records = [
        r
        for r in topic.get("workload_context", {}).get("records", [])
        if all(r[k] == fact["target"].get(k) for k in ("cluster_id", "namespace"))
        and (r["period"]["start"], r["period"]["end"]) in hours
    ]
    if not records:
        return {
            "status": "unavailable",
            "meaning": "이 후보의 같은 시간대 작업 라벨·요청량을 연결하지 못했습니다.",
        }
    groups = defaultdict(list)
    for r in records:
        groups[
            (r["workload_type"], r["type_status"], r["phase"], bool(r["node"]))
        ].append(r)
    completed = [
        r
        for r in topic.get("workload_context", {}).get("completed_jobs", [])
        if r["cluster_id"] == fact["target"].get("cluster_id")
        and r["namespace"] == fact["target"].get("namespace")
        and any(
            r["job_name"] == j["job_name"] and r["created_at"] == j["created_at"]
            for j in fact.get("completed_jobs", [])
        )
    ]
    return {
        "completed_type_status": "declared_test"
        if completed and all(r["type_status"] == "declared_test" for r in completed)
        else "unknown",
        "status": "partial",
        "scope": "matched_pod_hour_samples_not_namespace_totals",
        "groups": [
            {
                "workload_type": key[0],
                "type_status": key[1],
                "phase": key[2],
                "node_assigned": key[3],
                "observed_pods": len({r["uid"] for r in rows}),
                "regular_gpu_request_per_pod": [
                    min(r["regular_gpu_request"] for r in rows),
                    max(r["regular_gpu_request"] for r in rows),
                ],
                "evidence_refs": sorted(
                    {ref for r in rows for ref in r["evidence_refs"]}
                ),
            }
            for key, rows in sorted(groups.items())
        ],
        "limitations": list(LIMITS[:3]),
    }
