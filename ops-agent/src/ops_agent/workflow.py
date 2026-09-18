from collections import defaultdict
from uuid import uuid4

from agent_common.calculations import (
    allocation_hours,
    energy,
    weighted_mean,
    low_activity_windows,
    seconds,
)
from agent_common.contracts import base_result, result_status, metric, timestamp, now
from agent_common.llm import explain
from agent_common.normalize import allocations, gpu_intervals, intervals
from agent_common.observation import Observation
from agent_common.runtime import attempt_context
from .prompts import EXPLANATION


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


def calculate(topic_id, data, collected, context, db_evidence):
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
    mapping = allocations(collected.get("D08", []), period, collected.get("D06", []))
    activity = gpu_intervals(collected.get("D02", []), period)
    all_refs = [e for q in PLAN[topic_id] for e in collected.get(q, [])]
    topic["evidence_refs"] = refs(all_refs)
    topic["quality"]["observations"] = [
        dict(
            query_id=e["query_id"],
            cluster_id=e.get("cluster_id"),
            tool_status=e["tool_status"],
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

    if topic_id == "O01":
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
    obs = Observation(tools, ctx["profile"], data, ctx["deadline"])
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
        collected_at=now(),
    )
    obs.evidence.append(db_evidence)
    collected = {}
    for query in sorted({q for topic in data["topic_ids"] for q in PLAN[topic]}):
        collected[query] = await obs.collect(query)
    if "O10" in data["topic_ids"] and data.get("comparison_range"):
        collected["comparison.D11"] = await obs.collect("D11", data["comparison_range"])
    topics = [
        calculate(t, data, collected, ctx["context"], db_evidence)
        for t in data["topic_ids"]
    ]
    result.update(
        topics=topics,
        result_status=result_status(topics),
        evidence_refs=refs(obs.evidence),
        limitations=[
            "기간 원본·신원·분모가 확인되지 않은 계산은 보류합니다.",
            "관측 변화는 조치의 인과적 효과를 확정하지 않습니다.",
        ],
    )
    await explain(result, ctx["llm"], EXPLANATION)
    result["llm_usage"] = ctx["llm"].usage
    return {"result": result, "evidence": obs.evidence}
