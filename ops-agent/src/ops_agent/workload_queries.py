"""Ops-only regular-container GPU Pod and batch Job observations."""

from .report_queries import selector

QUERY_IDS = {"hourly_gpu_workload", "hourly_gpu_jobs"}


def workload_queries(cluster):
    pod_key = "cluster_id, namespace, pod, uid"
    job_key = "cluster_id, namespace, job_name"
    ns_key = "cluster_id, namespace"

    def selected(metric, extra=""):
        value = selector(metric, cluster)
        return value[:-1] + ("," + extra if extra else "") + "}"

    def unique(expr, key):
        # Ignore contradictory replica values; never add duplicate exporters together.
        return f"(max by ({key}) ({expr}) == min by ({key}) ({expr}))"

    requests = selected(
        "kube_pod_container_resource_requests", 'resource="nvidia_com_gpu",uid!=""'
    )
    gpu = f"(max by ({pod_key}) ({requests}) > bool 0)"
    gpu = f"({gpu} == 1)"
    phase = selected("kube_pod_status_phase", 'phase="Pending",uid!=""')
    scheduled = selected("kube_pod_status_scheduled", 'condition="false",uid!=""')
    running = selected("kube_pod_status_phase", 'phase="Running",uid!=""')
    states = {
        "pending": f"{unique(phase, pod_key)} * on ({pod_key}) {gpu}",
        "unscheduled": f"({unique(phase, pod_key)} * on ({pod_key}) {unique(scheduled, pod_key)}) * on ({pod_key}) {gpu}",
        "running": f"{unique(running, pod_key)} * on ({pod_key}) {gpu}",
    }
    parts = []
    for state, expr in states.items():
        # A namespace sample is usable only when every eligible Pod has this state metric.
        complete = f"(sum by ({ns_key}) ({expr}) and on ({ns_key}) (count by ({ns_key}) ({expr}) == count by ({ns_key}) ({gpu})))"
        for measure, fn in (("peak", "max_over_time"), ("samples", "count_over_time")):
            parts.append(
                f'label_replace({fn}(({complete})[1h:15s] offset 1ms), "measure", "{state}_{measure}", "", "")'
            )

    owner = selected(
        "kube_pod_owner", 'owner_kind="Job",owner_is_controller="true",uid!=""'
    )
    owned = f"({owner} == 1) and on ({pod_key}) {gpu}"
    jobs = f'max by ({job_key}) (label_replace({owned}, "job_name", "$1", "owner_name", "(.+)"))'
    job_parts = []
    for field, metric in (
        ("created", "kube_job_created"),
        ("started", "kube_job_status_start_time"),
        ("completed", "kube_job_status_completion_time"),
    ):
        # Keep the source labels: duplicate/conflicting job sources are rejected in Python.
        expr = f"({selected(metric)} > 0) and on ({job_key}) ({jobs})"
        for measure, fn in (("min", "min_over_time"), ("max", "max_over_time")):
            job_parts.append(
                f'label_replace({fn}(({expr})[1h:15s] offset 1ms), "measure", "{field}_{measure}", "", "")'
            )
    return {
        "hourly_gpu_workload": " or ".join(parts),
        "hourly_gpu_jobs": " or ".join(job_parts),
    }
