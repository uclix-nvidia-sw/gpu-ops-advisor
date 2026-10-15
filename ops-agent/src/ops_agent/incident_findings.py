"""Node/alert editorial facts from the existing report snapshot, not RCA."""

from collections import defaultdict


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
