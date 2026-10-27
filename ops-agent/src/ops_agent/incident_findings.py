"""Node/alert editorial facts from the existing report snapshot, not RCA."""

from collections import Counter, defaultdict


INCIDENT_RULES = """incident_summary 작성:
- observation은 코드가 작성합니다. 빈 문자열 ""을 반환하세요. fact_ids도 코드가 정하므로 응답 값은 쓰이지 않습니다.
- meaning: findings의 최다 종류 비율과 노드별 비율(최다 노드, 두 번째 노드)을 비교하세요. 알림 종류가 한 종류에 집중됐는지, 노드가 한 노드에 집중됐는지를 각각 결론으로 쓰세요. 최다 종류의 이전 기간 건수가 0이면 새로 나타난 종류라고 쓰세요. 마지막에 저장 알림 기록이며 시험 알림이 섞일 수 있고 원인·같은 GPU 반복 장애·복구는 확정하지 않는다는 한계를 한 문장으로 쓰세요. "~했는지", "~를 설명" 같은 작성 지시 표현은 쓰지 마세요.
- next_check: 코드가 확인 대상 노드·알림, 기간, 건수, 발생 중 건수를 앞에 붙입니다. 대상·기간 토큰을 다시 쓰지 마세요. 그 알림의 발생 시각을 어떤 기록과 대조할지(기존 RCA 결과, 점검 기록, 같은 알림이 있는 다른 노드의 발생 시각)와 발생 중 건의 해제 여부 확인을 짧게 쓰세요.
- 건수 감소를 복구로, 알림 해제를 복구 확인으로 쓰지 마세요. 점검 불필요·현재 정상이라고 쓰지 마세요. 건수를 평균이나 GPU 활동률로 설명하지 마세요.
- 이 주제의 숫자·노드·알림 이름은 {{target:fact_id}}, {{value:metric_id}} 토큰으로만 쓰거나 생략하세요. 필드마다 짧은 두세 문장, 450자 이내입니다.
"""


def add_concentration_findings(topic, put, refs):
    summary = topic["summary"]
    incidents = {r["id"]: r for r in summary.get("incidents", [])}
    previous = next(
        m["period"]
        for m in topic["metrics"]
        if m["id"].startswith("incident_summary.previous_count.")
    )
    clusters = defaultdict(list)
    for category in summary.get("categories", []):
        clusters[category["cluster_id"]].append(category)
    for cluster_id, categories in sorted(
        clusters.items(), key=lambda item: (-sum(c["count"] for c in item[1]), item[0])
    ):
        total = sum(c["count"] for c in categories)
        if total < 2:
            continue
        category = min(categories, key=lambda c: (-c["count"], c["name"]))
        target = {"cluster_id": cluster_id, "alert_type": category["name"]}
        count, share = category["count"], round(category["count"] / total * 100, 1)
        cluster_target = {"cluster_id": cluster_id}
        previous_total = sum(c["previous_count"] for c in categories)
        ids = [
            put("top_type_count", count, "events", target),
            put("top_type_share", share, "percent", target),
            put(
                "top_type_previous_count",
                category["previous_count"],
                "events",
                target,
                period=previous,
            ),
            put("top_type_cluster_count", total, "events", cluster_target),
            put(
                "top_type_cluster_previous_count",
                previous_total,
                "events",
                cluster_target,
                period=previous,
            ),
        ]
        node_names = ", ".join(category["nodes"]) or "노드 미확인"
        topic["findings"].append(
            {
                "id": f"incident-top-type-{cluster_id}",
                "target": target,
                "value_refs": ids,
                "evidence_refs": refs,
                "text": f"{cluster_id} / {category['name']}: 이 클러스터 저장 사건 {total}건(이전 기간 {previous_total}건) 중 {count}건으로 {share:.1f}%입니다(이 종류의 이전 기간 {category['previous_count']}건, 발생 노드 {node_names}). 동일 원인이나 같은 GPU의 반복 장애를 뜻하지 않으며 시험 알림이 포함될 수 있습니다.",
            }
        )
        nodes = defaultdict(list)
        for category in categories:
            for key in category["incident_ids"]:
                event = incidents[key]
                node = (event.get("target") or {}).get("node")
                if node:
                    nodes[node].append((category["name"], event))
        if not nodes:
            continue
        for rank, (node, events) in enumerate(
            sorted(nodes.items(), key=lambda item: (-len(item[1]), item[0]))[:2]
        ):
            name = "top_node" if rank == 0 else "second_node"
            target = {"cluster_id": cluster_id, "node": node}
            count, share = len(events), round(len(events) / total * 100, 1)
            firing = sum(e.get("alarm_status") == "firing" for _, e in events)
            types = Counter(name for name, _ in events)
            breakdown = ", ".join(
                f"{name} {n}건"
                for name, n in sorted(
                    types.items(), key=lambda item: (-item[1], item[0])
                )
            )
            ids = [
                put(name + "_count", count, "events", target),
                put(name + "_share", share, "percent", target),
            ]
            status = ""
            if rank == 0:
                ids.append(put("top_node_firing", firing, "events", target))
                status = f" 보고서 작성 당시 발생 중 {firing}건."
            topic["findings"].append(
                {
                    "id": f"incident-{'top' if rank == 0 else 'second'}-node-{cluster_id}",
                    "target": target,
                    "value_refs": ids,
                    "evidence_refs": refs,
                    "text": f"{cluster_id} / {node}: 이번 기간 {count}건으로 이 클러스터 저장 사건의 {share:.1f}%입니다({breakdown}).{status} 동일 원인을 뜻하지 않습니다.",
                }
            )


def incident_focus(findings):
    """Compose incident observations and a check target from verified payload facts."""
    ids = []
    metrics = {
        f["fact_id"]: {v["metric_id"].split(".")[1]: v for v in f["values"]}
        for f in findings
    }

    def token(kind, fact, name=None):
        fid = fact["fact_id"]
        if fid not in ids:
            ids.append(fid)
        key = fid if kind == "target" else metrics[fid][name]["metric_id"]
        return "{{" + kind + ":" + key + "}}"

    top_types = [f for f in findings if f["fact_id"].startswith("incident-top-type-")]
    node_facts = [f for f in findings if f["fact_id"].startswith("incident-node-")]
    nodes = {
        (f["target"].get("cluster_id"), prefix): f
        for f in findings
        for prefix in ("incident-top-node-", "incident-second-node-")
        if f["fact_id"].startswith(prefix)
    }
    observations = []
    for fact in top_types:
        text = (
            f"{token('target', fact)} · {token('period', fact, 'top_type_count')}: "
            f"클러스터 저장 사건 {token('value', fact, 'top_type_cluster_count')}"
            f"(이전 {token('value', fact, 'top_type_cluster_previous_count')}) 중 "
            f"{token('value', fact, 'top_type_count')}, {token('value', fact, 'top_type_share')}"
            f"(이 종류의 이전 기간 {token('value', fact, 'top_type_previous_count')})."
        )
        cluster = fact["target"]["cluster_id"]
        top_node = nodes.get((cluster, "incident-top-node-"))
        if top_node:
            text += (
                f" 노드별: {token('target', top_node)} {token('value', top_node, 'top_node_count')}, "
                f"{token('value', top_node, 'top_node_share')}, "
                f"작성 당시 발생 중 {token('value', top_node, 'top_node_firing')}"
            )
            second = nodes.get((cluster, "incident-second-node-"))
            if second:
                text += (
                    f" · {token('target', second)} {token('value', second, 'second_node_count')}, "
                    f"{token('value', second, 'second_node_share')}"
                )
            text += "."
        observations.append(text)
    if not top_types:
        if node_facts:
            fact = node_facts[0]
            observations.append(
                f"{token('target', fact)} · {token('period', fact, 'node_alert_count')}: "
                f"저장 사건 {token('value', fact, 'node_alert_count')}, "
                f"작성 당시 발생 중 {token('value', fact, 'node_alert_firing')}."
            )
        else:
            fact = next(
                (f for f in findings if f["fact_id"] == "incident-period-summary"), None
            )
            if fact:
                observations.append(
                    f"{token('target', fact)} · {token('period', fact, 'count')}: "
                    f"저장 사건 {token('value', fact, 'count')}"
                    f"(이전 {token('value', fact, 'previous_count')})."
                )
    check = next(
        (
            f
            for f in node_facts
            if metrics[f["fact_id"]]["node_alert_firing"]["value"] > 0
        ),
        node_facts[0] if node_facts else None,
    )
    prefix = ""
    if check:
        prefix = (
            f"{token('target', check)} · {token('period', check, 'node_alert_count')}: "
            f"저장 사건 {token('value', check, 'node_alert_count')}"
        )
        if metrics[check["fact_id"]]["node_alert_firing"]["value"] > 0:
            prefix += (
                f", 작성 당시 발생 중 {token('value', check, 'node_alert_firing')}"
            )
        prefix += ". "
    return {"ids": ids, "observation": " ".join(observations), "check_prefix": prefix}


def add_node_findings(topic, put, refs):
    summary = topic["summary"]
    incidents = {r["id"]: r for r in summary.get("incidents", [])}
    candidates = []
    for category in summary.get("categories", []):
        nodes = defaultdict(list)
        for key in category["incident_ids"]:
            event = incidents[key]
            node = (event.get("target") or {}).get("node")
            if node and event.get("occurred_at"):
                nodes[node].append(event)
        for node, events in nodes.items():
            candidates.append((category, node, events))
    for i, (category, node, events) in enumerate(
        sorted(
            candidates,
            key=lambda x: (-len(x[2]), x[0]["cluster_id"], x[1], x[0]["name"]),
        )[:6]
    ):
        target = {
            "cluster_id": category["cluster_id"],
            "node": node,
            "alert_type": category["name"],
        }
        count = put("node_alert_count", len(events), "events", target)
        firing = put(
            "node_alert_firing",
            sum(e.get("alarm_status") == "firing" for e in events),
            "events",
            target,
        )
        topic["findings"].append(
            {
                "id": f"incident-node-{i}",
                "target": target,
                "value_refs": [count, firing],
                "evidence_refs": refs,
                "text": f"{category['cluster_id']} / {node} / {category['name']}: 저장 사건입니다. {len(events)}건 중 보고서 작성 당시 발생 중 {sum(e.get('alarm_status') == 'firing' for e in events)}건. 같은 GPU의 반복 장애나 원인 확정이 아닙니다. 이 노드의 해당 알림 시각과 기존 조사·점검 기록을 대조하세요. 시험 알림이 포함될 수 있습니다.",
            }
        )
