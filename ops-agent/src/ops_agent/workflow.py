import asyncio
from collections import defaultdict
import contextlib
import logging
import time
from uuid import uuid4

from agent_common.calculations import (
    allocation_hours,
    energy,
    weighted_mean,
    low_activity_windows,
    seconds,
)
from agent_common.contracts import base_result, result_status, metric, timestamp
from agent_common.normalize import allocations, gpu_intervals, intervals
from agent_common.runtime import attempt_context
from agent_common.observation import evidence_stamp
from .report import write_report
from .namespace_usage import namespace_usage
from .collection import collect_report


log = logging.getLogger(__name__)


PLAN = {
    "O01": ("D01", "D03", "D04", "D06"),
    "O02": ("D08", "D01", "D06", "D10"),
    "O03": ("D08", "D06", "D02", "D10"),
    "O04": ("D08", "D06", "D02"),
    "O05": ("D10",),
    "O06": ("D08", "D06", "D13"),
    "O07": ("D07", "D12"),
    "O08": ("D08", "D01", "D06", "D12"),
    "O09": ("D11", "D10"),
    "O10": ("D11", "D02", "D13", "D09"),
    "O11": ("D10",),
}


def refs(es):
    return [e["id"] for e in es]


def add(
    topic,
    name,
    value,
    unit,
    data,
    evidence,
    method,
    reason="required_data_missing",
    target=None,
):
    m = metric(
        topic["topic_id"] + "." + name,
        value,
        unit,
        data,
        refs(evidence),
        method,
        reason,
    )
    if target is not None:
        m["target"] = target
    topic["metrics"].append(m)
    if value is not None:
        topic["facts"].append(
            dict(
                id=m["id"] + ".fact",
                text=name,
                value_refs=[m["id"]],
                evidence_refs=m["evidence_refs"],
            )
        )
    else:
        topic["missing_inputs"].append(reason)


def query_ids(topic_id, criteria_version=None):
    return (
        ("D01", "D02", "D06", "D08")
        if topic_id == "O08" and criteria_version == "1.2"
        else PLAN[topic_id]
    )


def calculate(
    topic_id, data, collected, context, db_evidence, *, criteria_version=None
):
    topic = dict(
        topic_id=topic_id,
        status="blocked",
        metrics=[],
        facts=[],
        findings=[],
        missing_inputs=[],
        quality={},
        evidence_refs=[],
        recommendations=[],
    )
    period = data["time_range"]
    start, end = timestamp(period["start"]), timestamp(period["end"])
    namespace_draft = topic_id == "O08" and criteria_version == "1.2"
    mapping = (
        allocations(collected.get("D08", []), period, collected.get("D06", []))
        if topic_id in {"O02", "O03", "O04", "O06"}
        or (topic_id == "O08" and not namespace_draft)
        else []
    )
    activity = (
        gpu_intervals(collected.get("D02", []), period)
        if topic_id in {"O03", "O04"}
        else {}
    )
    all_refs = [
        e for q in query_ids(topic_id, criteria_version) for e in collected.get(q, [])
    ]
    topic["evidence_refs"] = refs(all_refs)
    topic["quality"]["observations"] = [
        dict(
            query_id=e["query_id"],
            cluster_id=e.get("cluster_id"),
            tool_status=e["tool_status"],
            time_range=e.get("time_range"),
            **e["quality"],
        )
        for e in all_refs
    ]

    def put(
        name,
        value,
        unit,
        method,
        reason="required_data_missing",
        evidence=None,
        target=None,
    ):
        add(
            topic,
            name,
            value,
            unit,
            data,
            all_refs if evidence is None else evidence,
            method,
            reason,
            target,
        )

    if namespace_draft:
        requested = data.get("group_by", [])
        topic["quality"].update(
            requested_group_by=requested,
            applied_group_by=[],
            aggregation_unit="physical_gpu_seconds",
            coverage_scope="observed_connections_only",
            interpretation="연결된 GPU의 관측 활동이며 namespace 실사용률·독점 할당량이 아닙니다.",
        )
        if set(requested) not in ({"namespace"}, {"cluster", "namespace"}):
            topic["missing_inputs"] = [
                "group_by_not_implemented"
                if set(requested) <= {"cluster", "namespace", "pod", "workload"}
                else "unsupported_group_by"
            ]
            return topic
        topic["quality"]["applied_group_by"] = requested
        summaries, unattributed, clusters = namespace_usage(data, collected)
        topic["quality"]["unattributed_series_count"] = unattributed
        if unattributed:
            topic["missing_inputs"].append("unattributed_gpu_observation")
        for i, cluster in enumerate(clusters):
            if not cluster["complete"]:
                topic["missing_inputs"].append("incomplete_observation")
            cluster_refs = [
                e
                for e in all_refs
                if e["cluster_id"] == cluster["target"]["cluster_id"]
            ]
            for field, unit, method in (
                ("observed_gpu_count", "physical_gpu", "unique_observed_inventory"),
                (
                    "connected_gpu_count",
                    "physical_gpu",
                    "observed_connected_gpu_distinct_count",
                ),
                ("connected_gpu_hours", "GPU-hours", "observed_gpu_pod_interval_union"),
                (
                    "unlabeled_gpu_count",
                    "physical_gpu",
                    "unique_gpu_without_pod_labels",
                ),
                (
                    "unattributed_gpu_count",
                    "physical_gpu",
                    "unique_gpu_with_unresolved_pod_identity",
                ),
            ):
                put(
                    f"cluster_{field}.{i}",
                    cluster[field],
                    unit,
                    method,
                    cluster["reason"],
                    evidence=cluster_refs,
                    target=cluster["target"],
                )
                m = topic["metrics"][-1]
                m["quality"].update(
                    coverage_scope="observed_scope_only", complete=cluster["complete"]
                )
                if field == "unlabeled_gpu_count" and cluster[field]:
                    m["quality"]["reason"] = "gpu_pod_labels_absent"
                if field == "unattributed_gpu_count" and cluster[field]:
                    m["quality"]["reason"] = "unattributed_gpu_observation"
        for i, summary in enumerate(summaries):
            reasons = summary["reasons"]
            for name, field, unit, method in (
                (
                    "namespace_connected_gpu_count",
                    "connected_gpu_count",
                    "physical_gpu",
                    "observed_connected_gpu_distinct_count",
                ),
                (
                    "observed_namespace_hours",
                    "connected_hours",
                    "GPU-hours",
                    "observed_gpu_pod_interval_union",
                ),
                (
                    "namespace_activity_valid_hours",
                    "valid_hours",
                    "GPU-hours",
                    "observed_mapping_activity_intersection",
                ),
                (
                    "namespace_connected_gpu_util",
                    "mean",
                    "percent",
                    "observed_connected_gpu_time_weighted_mean",
                ),
            ):
                put(
                    f"{name}.{i}",
                    summary[field],
                    unit,
                    method,
                    reasons[0] if reasons else "gpu_activity_missing",
                    target=summary["target"],
                )
                m = topic["metrics"][-1]
                m["quality"].update(
                    requested_group_by=requested,
                    applied_group_by=requested,
                    coverage_scope="observed_connections_only",
                    excluded_reasons=reasons,
                )
                if field == "mean":
                    m["denominator"] = {
                        "value": summary["valid_hours"] * 3600
                        if summary["valid_hours"] is not None
                        else None,
                        "unit": "GPU-seconds",
                    }
                if summary[field] is not None:
                    topic["facts"][-1]["text"] = {
                        "connected_gpu_count": "기간 중 연결이 확인된 고유 GPU 대수이며 동시 사용 대수가 아닙니다.",
                        "connected_hours": "Namespace별 GPU–Pod 연결 관측 시간",
                        "valid_hours": "연결 GPU 활동률 계산에 사용한 유효 관측 시간",
                        "mean": "Namespace에 연결돼 관측된 GPU의 평균 활동률이며 namespace 실사용률은 아닙니다.",
                    }[field]
            topic["missing_inputs"].extend(reasons)
        # The observed-connection interpretation is a limitation, not a failed input.
        # Actual missing allocation queries still retain incomplete_observation below.
    elif topic_id == "O01":
        rows = intervals(collected.get("D01", []), period)
        devices = {
            (r["cluster_id"], r["labels"].get("gpu_uuid", r["labels"].get("UUID")))
            for r in rows
            if r["intervals"]
        }
        devices = {k for k in devices if k[1]}
        put(
            "observed_devices",
            len(devices) if devices else None,
            "physical_gpu",
            "unique_observed_inventory",
        )
        for query, name, unit in [
            ("D03", "vram", "bytes"),
            ("D04", "temperature", "celsius"),
        ]:
            vals = gpu_intervals(collected.get(query, []), period)
            for i, (key, iv) in enumerate(sorted(vals.items())):
                source_units = {
                    e["quality"].get("unit")
                    for e in collected.get(query, [])
                    if e["tool_status"] == "ok"
                }
                value = weighted_mean(iv)
                if query == "D03" and source_units == {"MiB"}:
                    value = value * 1048576 if value is not None else None
                elif source_units != {unit}:
                    value = None
                put(
                    name + f".{i}",
                    value,
                    unit,
                    "time_weighted_mean",
                    "source_unit_unverified",
                    target={"cluster_id": key[0], "gpu_uuid": key[1]},
                )
        topic["missing_inputs"].append("inventory_completeness_and_change_events")
    elif topic_id in {"O02", "O08"}:
        observed = allocations(
            collected.get("D01", []), period, collected.get("D06", []), observed=True
        )
        observed_rows = intervals(collected.get("D01", []), period)
        devices = {
            (
                r["cluster_id"],
                r["labels"].get("gpu_uuid")
                or r["labels"].get("UUID")
                or r["labels"].get("uuid"),
            )
            for r in observed_rows
            if r["intervals"]
        }
        devices = {k for k in devices if k[1]}
        if devices:
            put(
                "observed_gpu_count",
                len(devices),
                "physical_gpu",
                "unique_observed_inventory",
                evidence=collected.get("D01", []),
            )
        if observed:
            observed_refs = collected.get("D01", []) + collected.get("D06", [])
            put(
                "mapped_gpu_count",
                len({(m["cluster_id"], m["gpu_uuid"]) for m in observed}),
                "physical_gpu",
                "observed_gpu_pod_identity_join",
                evidence=observed_refs,
            )
            put(
                "mapped_gpu_hours",
                allocation_hours(observed, "unknown"),
                "GPU-hours",
                "observed_gpu_pod_interval_union",
                evidence=observed_refs,
            )
            topic["quality"]["mapping_basis"] = "DCGM_Pod_UID_observation"
        elif devices:
            topic["missing_inputs"].append("gpu_pod_identity_missing")
        if not mapping:
            topic["missing_inputs"].append("allocation_contract_missing")
        elif any(m["mode"] == "unknown" for m in mapping):
            topic["missing_inputs"].append("allocation_mode_unverified")
        exclusive = [m for m in mapping if m["mode"] == "exclusive"]
        current = {
            (m["cluster_id"], m["gpu_uuid"]) for m in exclusive if m["end"] >= end
        }
        put(
            "current_allocated_gpu",
            len(current) if exclusive else None,
            "physical_gpu",
            "unique_exclusive_devices",
        )
        topic["metrics"][-1]["period"] = {"at": period["end"]}
        put(
            "allocated_gpu_hours",
            allocation_hours(mapping) if exclusive else None,
            "GPU-hours",
            "valid_interval_union",
        )
        mig = [m for m in mapping if m["mode"] == "mig" and m["instance_id"]]
        put(
            "allocated_instance_hours",
            allocation_hours(mig, "mig") if mig else None,
            "instance-hours",
            "MIG_instance_interval_union",
            "MIG_history_missing",
        )
        if topic_id == "O08":
            observed_groups = defaultdict(list)
            for m in observed:
                observed_groups[(m["cluster_id"], m["namespace"])].append(m)
            for i, (key, rows) in enumerate(sorted(observed_groups.items(), key=str)):
                put(
                    "observed_namespace_hours." + str(i),
                    allocation_hours(rows, "unknown"),
                    "GPU-hours",
                    "observed_gpu_pod_interval_union",
                    evidence=collected.get("D01", []) + collected.get("D06", []),
                    target={"cluster_id": key[0], "namespace": key[1]},
                )
            if observed:
                topic["missing_inputs"].append(
                    "observed_mapping_not_exclusive_allocation"
                )
                topic["missing_inputs"].append("project_owner_mapping")
            groups = defaultdict(list)
            for m in mapping:
                groups[(m["cluster_id"], m["namespace"], m["project"])].append(m)
            for i, (key, rows) in enumerate(sorted(groups.items(), key=str)):
                put(
                    "allocation_group." + str(i),
                    allocation_hours(rows)
                    if any(m["mode"] == "exclusive" for m in rows)
                    else None,
                    "GPU-hours",
                    "valid_interval_union",
                    target={
                        "cluster_id": key[0],
                        "namespace": key[1],
                        "project": key[2],
                    },
                )
            if any(m["project"] is None for m in mapping):
                topic["missing_inputs"].append("project_owner_mapping")
    elif topic_id == "O03":
        windows = low_activity_windows(mapping, activity)
        for i, w in enumerate(windows):
            put(
                "low_gpu_hours." + str(i),
                w["low_gpu_hours"],
                "GPU-hours",
                "allocation_activity_interval_intersection",
                target=dict(
                    zip(
                        ("cluster_id", "gpu_uuid", "pod_uid", "allocation_episode_key"),
                        w["target"],
                    )
                ),
            )
            topic["findings"].append(
                dict(
                    status=w["status"],
                    reason=w["reason"],
                    value_refs=[topic["metrics"][-1]["id"]],
                    evidence_refs=refs(all_refs),
                    active_observed=w["active_observed"],
                )
            )
            if w["reason"]:
                topic["missing_inputs"].append(w["reason"])
        if not windows:
            put(
                "low_gpu_hours",
                None,
                "GPU-hours",
                "allocation_activity_interval_intersection",
                "exclusive_episode_or_activity_missing",
            )
        topic["recommendations"].append(
            dict(
                text="초기화·체크포인트·추론 대기·예약 목적을 확인하세요.",
                preconditions=["workload_exception_review"],
                eligibility="withheld",
                reason="workload_purpose_unverified",
                execution="not_performed",
                value_refs=[],
                evidence_refs=refs(all_refs),
            )
        )
    elif topic_id == "O04":
        pods = defaultdict(set)
        for m in mapping:
            pods[(m["cluster_id"], m["pod_uid"])].add((m["cluster_id"], m["gpu_uuid"]))
        from agent_common.calculations import intersect

        for pi, (pod, devices) in enumerate(sorted(pods.items())):
            if len(devices) < 2:
                continue
            common = [(start, end)]
            for dev in devices:
                assigned = [
                    (m["start"], m["end"])
                    for m in mapping
                    if (m["cluster_id"], m["pod_uid"]) == pod
                    and (m["cluster_id"], m["gpu_uuid"]) == dev
                ]
                common = intersect(
                    common,
                    intersect(
                        assigned,
                        [(a, b) for a, b, v in activity.get(dev, []) if 0 <= v <= 100],
                    ),
                )
            means = []
            for di, dev in enumerate(sorted(devices)):
                iv = [
                    (x, y, v)
                    for a, b, v in activity.get(dev, [])
                    for x, y in intersect([(a, b)], common)
                ]
                avg = weighted_mean(iv)
                means.append(avg)
                put(
                    f"pod.{pi}.gpu.{di}.mean",
                    avg,
                    "percent",
                    "time_weighted_mean_common_interval",
                    target={
                        "cluster_id": dev[0],
                        "gpu_uuid": dev[1],
                        "pod_uid": pod[1],
                    },
                )
            valid = means and all(m is not None for m in means)
            for name, val in [
                ("min", min(means) if valid else None),
                ("max", max(means) if valid else None),
                ("difference", max(means) - min(means) if valid else None),
            ]:
                put(
                    f"pod.{pi}.{name}",
                    val,
                    "percentage_points" if name == "difference" else "percent",
                    "same_workload_common_interval",
                )
        if not topic["metrics"]:
            put(
                "difference",
                None,
                "percentage_points",
                "same_workload_common_interval",
                "multi_gpu_workload_history_missing",
            )
    elif topic_id == "O05":
        incidents = {i["id"]: i for i in context["incidents"]}
        put(
            "incident_count",
            len(incidents),
            "events",
            "deduplicated_incident_ids",
            evidence=[db_evidence],
        )
        put(
            "incident_rate",
            None,
            "events/1000 GPU-hours",
            "count_per_valid_incident_observation",
            "incident_observation_denominator_missing",
            evidence=[db_evidence],
        )
        times = sorted(
            timestamp(i["occurred_at"])
            for i in incidents.values()
            if i.get("occurred_at")
        )
        if len(times) > 1:
            put(
                "observed_recurrence_interval",
                (times[-1] - times[0]) / (len(times) - 1),
                "seconds",
                "mean_interarrival_observed_events",
                evidence=[db_evidence],
            )
        topic["rca_references"] = [
            {
                "result_id": r["result_id"],
                "content_hash": r["content_hash"],
                "cause_candidates": [
                    {
                        "claim": c["claim"],
                        "causal_status": c["causal_status"],
                        "source_supporting_refs": c["supporting_refs"],
                        "source_contradicting_refs": c["contradicting_refs"],
                        "confirmation_rule_ref": c.get("confirmation_rule_ref"),
                        "evidence_refs": [db_evidence["id"]],
                    }
                    for c in r["body"].get("cause_candidates", [])
                ],
            }
            for r in context["rca_results"]
        ]
    elif topic_id == "O06":
        relations = []
        for incident in context["incidents"]:
            at = timestamp(incident["occurred_at"])
            target = incident.get("target") or {}
            for m in mapping:
                if (
                    m["cluster_id"] == incident["cluster_id"]
                    and m["start"] <= at < m["end"]
                    and target.get("gpu_uuid") == m["gpu_uuid"]
                ):
                    relations.append(
                        dict(
                            incident_id=incident["id"],
                            pod_uid=m["pod_uid"],
                            relation_scope="incident_time_mapping",
                            impact_status="not_assessed",
                            causal_status="undetermined",
                            evidence_refs=m["evidence_refs"] + [db_evidence["id"]],
                        )
                    )
        topic["relations"] = relations
        put(
            "mapped_incident_relations",
            len(relations) if relations else None,
            "relations",
            "incident_timestamp_identity_join",
            "incident_time_mapping_missing",
            evidence=all_refs + [db_evidence],
        )
        topic["missing_inputs"].append("verified_workload_disruption_evidence")
    elif topic_id == "O07":
        rows = intervals(collected.get("D07", []), period)
        totals = defaultdict(float)
        seen = set()
        for row in rows:
            labels = row["labels"]
            if (
                not labels.get("uid")
                or labels.get("node")
                or labels.get("terminal") != "false"
                or labels.get("request_contract") != "effective-v1"
            ):
                continue
            key = (row["cluster_id"], labels["uid"], labels.get("resource"))
            if key in seen:
                continue
            seen.add(key)
            for a, b, v in row["intervals"]:
                if b >= end and v >= 0:
                    totals[labels["resource"]] += v
        for i, (resource, value) in enumerate(sorted(totals.items())):
            put(
                f"unbound_request.{i}",
                value,
                resource,
                "verified_effective_unbound_request",
            )
            topic["metrics"][-1]["resource"] = resource
        put(
            "gpu_shortage",
            None,
            "GPU",
            "scheduler_constraints",
            "scheduler_capacity_binding_evidence_missing",
        )
    elif topic_id == "O09":
        watts = gpu_intervals(
            [e for e in collected.get("D11", []) if e["quality"].get("unit") == "W"],
            period,
        )
        valid = [iv for iv in watts.values() if iv]
        value = sum(energy(iv) for iv in valid) if valid else None
        put(
            "gpu_energy",
            value,
            "kWh",
            "left_hold_actual_watts_integral",
            "actual_power_original_samples_missing",
        )
        if valid:
            topic["quality"]["observed_gpu_seconds"] = sum(
                sum(b - a for a, b, v in iv) for iv in valid
            )
            topic["quality"]["coverage_scope"] = "observed_devices_only"
    elif topic_id == "O10":
        actions = [
            a
            for a in context["actions"]
            if a["id"] in data.get("action_record_ids", [])
            and a["body"].get("execution") == "performed"
        ]
        topic["action_records"] = actions
        topic["comparison_range"] = data.get("comparison_range")
        if actions and data.get("comparison_range"):
            before = gpu_intervals(
                [
                    e
                    for e in collected.get("comparison.D11", [])
                    if e["quality"].get("unit") == "W"
                ],
                data["comparison_range"],
            )
            after = gpu_intervals(
                [
                    e
                    for e in collected.get("D11", [])
                    if e["quality"].get("unit") == "W"
                ],
                period,
            )
            common = sorted(set(before) & set(after))
            b = sum(energy(before[k]) for k in common if before[k]) if common else None
            a = sum(energy(after[k]) for k in common if after[k]) if common else None
            put(
                "energy_before",
                b,
                "kWh",
                "left_hold_actual_watts_integral",
                evidence=collected.get("comparison.D11", []),
            )
            topic["metrics"][-1]["period"] = data["comparison_range"]
            put("energy_after", a, "kWh", "left_hold_actual_watts_integral")
            put(
                "observed_energy_reduction",
                b - a if b is not None and a is not None else None,
                "kWh",
                "observed_difference",
            )
        else:
            put(
                "observed_change",
                None,
                "kWh",
                "observed_difference",
                "performed_action_and_comparison_required",
            )
        topic["missing_inputs"].append("comparable_workload_and_causal_evidence")
    elif topic_id == "O11":
        rows = intervals(collected.get("D10", []), period)
        valid_seconds = sum(
            seconds([(a, b) for a, b, v in r["intervals"] if v == 1]) for r in rows
        )
        put(
            "observed_healthy_collection_seconds",
            valid_seconds if rows else None,
            "target-seconds",
            "valid_up_intervals",
        )
        put(
            "total_coverage",
            None,
            "ratio",
            "expected_target_time_intersection",
            "expected_inventory_denominator_missing",
        )
        topic["quality"]["tool_statuses"] = {
            q: [e["tool_status"] for e in es] for q, es in collected.items()
        }
    useful = any(m["value"] is not None for m in topic["metrics"])
    topic["status"] = (
        "partial"
        if useful and topic["missing_inputs"]
        else ("ready" if useful else "blocked")
    )
    if any(
        e["tool_status"] in ("partial", "unavailable", "parse_error") for e in all_refs
    ):
        topic["missing_inputs"].append("incomplete_observation")
        if useful:
            topic["status"] = "partial"
    topic["missing_inputs"] = list(dict.fromkeys(topic["missing_inputs"]))
    return topic


async def run(tools):
    ctx = attempt_context.get()
    claim, data = ctx["claim"], ctx["claim"]["input"]
    result = base_result(claim, ctx["context"]["data_cutoff_at"])
    db_evidence = dict(
        id=str(uuid4()),
        query_id="report_db_snapshot",
        query_version="1.1",
        cluster_id=None,
        scope=data["scope"],
        time_range=data["time_range"],
        input={"data_cutoff_at": result["data_cutoff_at"]},
        tool_status="ok",
        quality={"repeatable_read": True},
        snapshot=ctx["context"],
        **evidence_stamp(),
    )
    criteria_version = claim["versions"].get("criteria")
    queries = {
        q for topic in data["topic_ids"] for q in query_ids(topic, criteria_version)
    }
    priority = (
        ("D01", "D02", "D06", "D08")
        if ("O08" in data["topic_ids"] and criteria_version == "1.2")
        else ()
    )
    namespace_only = (
        criteria_version == "1.2"
        and data["topic_ids"] == ["O08"]
        and set(data["group_by"]) in ({"namespace"}, {"cluster", "namespace"})
    )
    order = (
        ["D01", "D02", "D08", "D06"]
        if namespace_only
        else sorted(queries, key=lambda q: (q not in priority, int(q[1:])))
    )
    started = time.monotonic()
    log.info(
        "report collection started job=%s attempt=%s",
        claim["job_id"],
        claim.get("attempt_no"),
    )
    collected, evidence, collection = await collect_report(
        tools, ctx["profile"], data, ctx["deadline"], order, namespace_only
    )
    log.info(
        "report collection complete job=%s attempt=%s elapsed_seconds=%.3f evidence_count=%s",
        claim["job_id"],
        claim.get("attempt_no"),
        time.monotonic() - started,
        len(evidence),
    )
    evidence.insert(0, db_evidence)
    topics = []
    for topic_id in data["topic_ids"]:
        if time.monotonic() >= ctx["deadline"]:
            raise TimeoutError()
        started = time.monotonic()
        log.info(
            "report calculation started job=%s attempt=%s topic=%s",
            claim["job_id"],
            claim.get("attempt_no"),
            topic_id,
        )
        calculation = asyncio.create_task(
            asyncio.to_thread(
                calculate,
                topic_id,
                data,
                collected,
                ctx["context"],
                db_evidence,
                criteria_version=criteria_version,
            )
        )
        try:
            topics.append(await asyncio.shield(calculation))
        except asyncio.CancelledError:
            # Cancelling an await cannot stop CPU work in a thread. Drain this
            # topic before returning the attempt; never start the next topic.
            while not calculation.done():
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await asyncio.shield(calculation)
            if not calculation.cancelled():
                calculation.exception()
            raise
        log.info(
            "report calculation complete job=%s attempt=%s topic=%s elapsed_seconds=%.3f",
            claim["job_id"],
            claim.get("attempt_no"),
            topic_id,
            time.monotonic() - started,
        )
    result.update(
        topics=topics,
        result_status=result_status(topics),
        evidence_refs=refs(evidence),
        limitations=[
            "기간 원본·신원·분모가 확인되지 않은 계산은 보류합니다.",
            "관측 변화는 조치의 인과적 효과를 확정하지 않습니다.",
            "GPU–Pod 연결 관측은 독점 할당·실제 소비량이 아니며, Pod 라벨 부재는 유휴·회수 가능의 증명이 아닙니다.",
        ],
    )
    result["quality"].update(
        requested_group_by=data["group_by"],
        collection=collection,
    )
    if time.monotonic() >= ctx["deadline"]:
        raise TimeoutError()
    started = time.monotonic()
    log.info(
        "report narrative started job=%s attempt=%s",
        claim["job_id"],
        claim.get("attempt_no"),
    )
    await write_report(result, ctx["llm"])
    log.info(
        "report narrative complete job=%s attempt=%s elapsed_seconds=%.3f",
        claim["job_id"],
        claim.get("attempt_no"),
        time.monotonic() - started,
    )
    result["llm_usage"] = ctx["llm"].usage
    return {"result": result, "evidence": evidence}
