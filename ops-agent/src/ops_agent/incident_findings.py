"""Node/alert editorial facts from the existing report snapshot, not RCA."""

from collections import Counter, defaultdict


INCIDENT_RULES = """incident_summary 작성:
- fact_ids는 1~3개입니다. incident-top-type·incident-top-node 근거가 있으면 우선 선택하고, 확인 대상이 될 node·alert_type 근거(incident-node-*)를 하나 더 고르세요.
- observation: 전체 건수와 이전 기간 차이를 쓰고, 최다 알림 종류의 대상·건수·비율 토큰과 이전 기간 건수 토큰(0이면 새로 나타난 종류라고 설명)을 쓰고, 최다 노드의 대상·건수·비율 토큰을 쓰세요. 비율은 이 클러스터 저장 사건 중 비율입니다.
- meaning: 알림이 한 종류나 한 노드에 몰렸는지 흩어졌는지를 비율에 근거해 설명하고, 저장된 알림 기록이며 시험 알림이 섞일 수 있고 같은 GPU의 반복 장애·원인·복구는 이 보고서로 확정하지 않는다는 한계를 쓰세요. 발생 중 건수는 작성 시점 기준입니다.
- next_check: 선택한 node·alert_type 대상과 기간 토큰을 지정해 그 알림의 발생 시각을 기존 RCA 결과·점검 기록과 대조하고, 발생 중 건수가 있으면 해제 여부를 확인하라고 쓰세요. 같은 알림이 다른 노드에도 있으면 발생 시각이 겹치는지 보라고 제안할 수 있습니다.
- 사건 건수를 평균이나 GPU 활동률로 설명하지 마세요. 건수 감소를 복구로, 알림 해제를 복구 확인으로 쓰지 마세요. 점검 불필요·현재 정상이라고 쓰지 마세요.
- Namespace의 comparison_status나 시간대 비교 제한을 이 주제에 적용하지 마세요.
- 이 주제만 {{target:fact_id}}, {{value:metric_id}}, {{period:metric_id}}를 씁니다. 숫자·노드·알림 이름을 직접 쓰지 마세요. 필드마다 짧은 두세 문장, 450자 이내입니다.
"""


def add_concentration_findings(topic, put, refs):
    summary = topic["summary"]
    incidents = {r["id"]: r for r in summary.get("incidents", [])}
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
        previous = next(
            m["period"]
            for m in topic["metrics"]
            if m["id"].startswith("incident_summary.previous_count.")
        )
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
        ]
        nodes = ", ".join(category["nodes"]) or "노드 미확인"
        topic["findings"].append(
            {
                "id": f"incident-top-type-{cluster_id}",
                "target": target,
                "value_refs": ids,
                "evidence_refs": refs,
                "text": f"{cluster_id} / {category['name']}: 이번 기간 {count}건으로 이 클러스터 저장 사건의 {share:.1f}%입니다(이전 기간 {category['previous_count']}건, 발생 노드 {nodes}). 동일 원인이나 같은 GPU의 반복 장애를 뜻하지 않으며 시험 알림이 포함될 수 있습니다.",
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
        node, events = min(nodes.items(), key=lambda item: (-len(item[1]), item[0]))
        target = {"cluster_id": cluster_id, "node": node}
        count, share = len(events), round(len(events) / total * 100, 1)
        firing = sum(e.get("alarm_status") == "firing" for _, e in events)
        types = Counter(name for name, _ in events)
        breakdown = ", ".join(
            f"{name} {n}건"
            for name, n in sorted(types.items(), key=lambda item: (-item[1], item[0]))
        )
        topic["findings"].append(
            {
                "id": f"incident-top-node-{cluster_id}",
                "target": target,
                "value_refs": [
                    put("top_node_count", count, "events", target),
                    put("top_node_share", share, "percent", target),
                    put("top_node_firing", firing, "events", target),
                ],
                "evidence_refs": refs,
                "text": f"{cluster_id} / {node}: 이번 기간 {count}건으로 이 클러스터 저장 사건의 {share:.1f}%입니다({breakdown}). 보고서 작성 당시 발생 중 {firing}건. 동일 원인을 뜻하지 않습니다.",
            }
        )


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
