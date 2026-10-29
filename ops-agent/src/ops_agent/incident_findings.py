"""Node/alert editorial facts from the existing report snapshot, not RCA."""

from collections import Counter, defaultdict


INCIDENT_RULES = """incident_summary 작성:
- observation과 check_target은 코드가 작성합니다. observation은 빈 문자열 ""을 반환하세요. fact_ids도 코드가 정하므로 응답 값은 쓰이지 않습니다.
- focus는 코드가 선정한 관측과 확인 대상입니다. focus.ids의 근거만 해석하세요. 전체 알림의 노드별 합계와 특정 종류의 노드별 건수를 섞지 마세요. 일부 내역이나 선정 제외가 있으면 전체 분포로 일반화하지 마세요.
- meaning은 두 문장입니다. 첫 문장에는 focus.check_context의 상태로 보아 이 확인 대상에서 아직 확인되지 않은 것 하나를 확인이 필요한 이유와 함께 쓰세요. 확인 대상의 이름·알림 종류·건수·기간은 check_target에 있으므로 meaning에 쓰지 말고 '이 확인 대상'으로 지칭하세요. 숫자를 한글 수사로 바꿔 쓰지 마세요. 둘째 문장은 다음 문장을 그대로 쓰세요: 저장 알림 기록이며 시험 알림이 섞일 수 있고 원인·같은 GPU 반복·복구는 확정하지 않습니다. 코드가 별도 한계를 표시해도 이 둘째 문장은 생략하지 마세요. 한계 문장만 단독으로 반환하지 마세요.
- 관측 사실을 다시 열거하지 말고 핵심 이유 하나를 쓰세요. 내부 키와 숫자 값을 그대로 옮기지 마세요. observation·check_target의 건수·발생 중 건수·공개 RCA 수는 반복하지 마세요. next_check의 대조 행동을 다시 쓰지 마세요. 후보 선정 순위·위험도·심각도·알림 코드의 뜻·장비 상태는 해석하지 마세요. 집중·분산 판단은 쓰지 마세요. 네 분석 항목은 해석의 근거이며 meaning에서 각각을 모두 설명할 의무는 없습니다. 구체적인 대조 대상·방법은 next_check에만 쓰세요. 입력에 알림별 발생 시각은 없으므로 선후·연쇄·시간 겹침을 사실로 단정하지 마세요. 작성 지시를 옮기지 마세요. 새 유형·최초 발생·공통 원인·동시 발생 표현은 부정문에서도 쓰지 마세요. 시각 비교는 발생 시각이 겹치는지 확인할 사항으로 표현하세요.
- type_previous_count는 확인 대상과 같은 클러스터·알림 종류의 이전 비교기간 건수이며 노드별 이전 기록이 아닙니다. null이면 해당 종류의 이전 비교를 생략하고 다른 종류나 전체 이전 건수로 대신하지 마세요. 0이면 이전 비교기간에는 이 클러스터의 해당 종류 기록이 없었다고 쓰세요. 양수일 때도 노드별 이전 기록으로 확대하지 말고, 확인 이유에 필요한 경우에만 같은 클러스터·종류의 비교 범위로 설명하세요.
- meaning·next_check에는 때문에·때문이다, 원인으로 판단·확인·판명, 원인입니다·원인이다, 고장입니다·고장으로, 복구됐·복구되었·복구 완료, 해결됐·해결되었, 정상화됐·정상화되었, 회수·재배분·증설·감축·낭비 같은 표현을 이유 설명이나 부정문·한계 문장에서도 쓰지 마세요. 확인 이유는 '~이 있어', '~이므로'로 이으세요. meaning의 확인 목적은 '~했는지·~됐는지' 대신 '~ 여부'로 쓰세요.
- next_check: 위 확인 목적에 맞춰 어떤 기록의 무엇을 대조할지 짧게 쓰세요. 아래 rca_count 조건에 해당하는 결과 유무 확인 또는 공개 결과와의 대조 목적을 빠짐없이 쓰세요. 다른 알림·점검 기록을 제안하더라도 이 목적을 생략하지 마세요. 대상·기간 토큰을 반복하지 마세요. firing이 양수면 작성 이후 알림 상태와 후속 점검 기록을, 0이면 기간 중 알림 발생 시각과 당시 점검·조치 기록을 대조하도록 제안하고 발생 중 건의 해제 여부를 다시 확인하라고 하지 마세요. 같은 종류의 여러 노드나 같은 노드의 다른 종류는 해당 알림 시각과 조사 기록으로 선후·시간 겹침을 확인할 대상으로 제안하세요. 이 기록들과 이후 상태는 앞으로 확인할 자료이며 이미 조회한 사실처럼 쓰지 마세요.
- rca_count가 0이면 RCA 결과 유무·작업 생성 여부와 상태를 확인하도록 쓰세요. 일부 사건에만 결과가 있으면 공개된 결과가 있는 사건만, 전부 있으면 연결된 공개 결과를 알림 시각·점검 기록과 대조해 해당 시각을 다루는지 확인하도록 쓰세요. 결과 연결은 본문 열람·원인 확인·조사 완료·복구 확인을 뜻하지 않습니다. RCA 내용이나 작업 진행·실패를 확인한 것처럼 쓰지 마세요. check_context가 없으면 노드 식별 정보와 수집 라벨 확인을 제안하세요.
- 건수 감소를 복구로, 알림 해제를 복구 확인으로 쓰지 마세요. 점검 불필요·현재 정상이라고 쓰지 마세요. 건수를 평균이나 GPU 활동률로 설명하지 마세요.
- focus.ids로 선택된 fact의 target에 있는 클러스터·노드·알림 종류 이름은 next_check에서 같은 노드의 다른 알림이나 같은 종류의 다른 노드를 가리킬 때만 철자·대소문자·공백을 그대로 짧게 쓸 수 있습니다. 단, 실제 선택된 근거에 있는 이름만 쓰세요. 바로 앞뒤에 영문·숫자를 붙이지 마세요. 한글 조사·공백·문장부호는 허용됩니다. {{target:fact_id}}도 계속 사용할 수 있습니다.
- 이름 속 숫자만 예외입니다. 건수·비율은 {{value:metric_id}}, 기간은 {{period:metric_id}} 토큰으로만 쓰거나 생략하세요. 다른 주제의 이름 직접 작성 금지는 유지합니다. AI가 작성하는 필드는 각각 450자 이내입니다.
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
    """Use the same selected facts for model context, observation and check target."""
    ids = []
    metrics = {
        f["fact_id"]: {v["metric_id"].split(".")[1]: v for v in f["values"]}
        for f in findings
    }

    def value(fact, name):
        return metrics[fact["fact_id"]][name]["value"]

    def token(kind, fact, name=None):
        fid = fact["fact_id"]
        if fid not in ids:
            ids.append(fid)
        key = fid if kind == "target" else metrics[fid][name]["metric_id"]
        return "{{" + kind + ":" + key + "}}"

    top_types = [f for f in findings if f["fact_id"].startswith("incident-top-type-")]
    nodes = [f for f in findings if f["fact_id"].startswith("incident-node-")]
    observations, clusters = [], set()
    for fact in top_types:
        clusters.add(fact["target"]["cluster_id"])
        text = (
            f"{token('target', fact)} · {token('period', fact, 'top_type_count')}: "
            f"클러스터 저장 사건 {token('value', fact, 'top_type_cluster_count')} 중 "
            f"{token('value', fact, 'top_type_count')}"
            f"(이전 비교기간 이 종류 {token('value', fact, 'top_type_previous_count')})."
        )
        matching = [
            n
            for n in nodes
            if all(
                n["target"][k] == fact["target"][k]
                for k in ("cluster_id", "alert_type")
            )
        ]
        if matching:
            complete = sum(value(n, "node_alert_count") for n in matching) == value(
                fact, "top_type_count"
            )
            text += " 노드별: " if complete else " 확인된 일부 노드 내역: "
            text += (
                " · ".join(
                    f"{token('target', n)} {token('value', n, 'node_alert_count')}"
                    for n in matching
                )
                + "."
            )
            if not complete:
                text += " 나머지 사건의 노드별 내역은 이 해석에 포함하지 않았습니다."
        else:
            text += " 이 종류의 노드별 내역은 이 해석에 포함하지 않았습니다."
        observations.append(text)
    for fact in nodes:
        cluster = fact["target"]["cluster_id"]
        if cluster not in clusters:
            observations.append(
                f"{token('target', fact)} · {token('period', fact, 'node_alert_count')}: "
                f"저장 사건 {token('value', fact, 'node_alert_count')}."
            )
            clusters.add(cluster)
    if not observations:
        fact = next(
            (f for f in findings if f["fact_id"] == "incident-period-summary"), None
        )
        if fact:
            observations.append(
                f"{token('target', fact)} · {token('period', fact, 'count')}: "
                f"저장 사건 {token('value', fact, 'count')}"
                f"(이전 비교기간 {token('value', fact, 'previous_count')})."
            )
    check = next(
        (f for f in nodes if value(f, "node_alert_firing") > 0),
        nodes[0] if nodes else None,
    )
    target, context = "", None
    if check:
        target = (
            f"{token('target', check)} · {token('period', check, 'node_alert_count')}: "
            f"저장 사건 {token('value', check, 'node_alert_count')}"
        )
        if value(check, "node_alert_firing") > 0:
            target += (
                f", 작성 당시 발생 중 {token('value', check, 'node_alert_firing')}"
            )
        target += (
            f", 공개 RCA 결과가 있는 사건 {token('value', check, 'node_alert_rca')}."
        )
        others = [
            n
            for n in nodes
            if n is not check
            and all(
                n["target"][k] == check["target"][k] for k in ("cluster_id", "node")
            )
        ]
        if others:
            target += (
                " 같은 노드의 다른 알림: "
                + " · ".join(
                    f"{token('target', n)} {token('value', n, 'node_alert_count')}"
                    for n in others
                )
                + "."
            )
        same_type = [
            n
            for n in nodes
            if all(
                n["target"][k] == check["target"][k]
                for k in ("cluster_id", "alert_type")
            )
        ]
        for fact in same_type:
            if fact["fact_id"] not in ids:
                ids.append(fact["fact_id"])
        context = {
            "fact_id": check["fact_id"],
            "count": value(check, "node_alert_count"),
            "firing": value(check, "node_alert_firing"),
            "rca_count": value(check, "node_alert_rca"),
            "same_type_fact_ids": [f["fact_id"] for f in same_type],
            "other_alert_fact_ids": [f["fact_id"] for f in others],
            "type_previous_count": next(
                (
                    value(fact, "top_type_previous_count")
                    for fact in top_types
                    if all(
                        fact["target"][key] == check["target"][key]
                        for key in ("cluster_id", "alert_type")
                    )
                ),
                None,
            ),
        }
    return {
        "ids": ids,
        "observation": " ".join(observations),
        "check_target": target,
        "check_context": context,
    }


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
            candidates.append((category, node, events, len(nodes)))
    for i, (category, node, events, _) in enumerate(
        sorted(
            candidates,
            key=lambda x: (
                -sum(e.get("alarm_status") == "firing" for e in x[2]),
                -x[3],
                -len(x[2]),
                x[0]["cluster_id"],
                x[1],
                x[0]["name"],
            ),
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
        rca = put(
            "node_alert_rca",
            sum(bool(e.get("result_id")) for e in events),
            "events",
            target,
        )
        topic["findings"].append(
            {
                "id": f"incident-node-{i}",
                "target": target,
                "value_refs": [count, firing, rca],
                "evidence_refs": refs,
                "text": f"{category['cluster_id']} / {node} / {category['name']}: 저장 사건입니다. {len(events)}건 중 보고서 작성 당시 발생 중 {sum(e.get('alarm_status') == 'firing' for e in events)}건. 공개 RCA 결과가 있는 사건 {sum(bool(e.get('result_id')) for e in events)}건. 같은 GPU의 반복 장애나 원인 확정이 아닙니다. 이 노드의 해당 알림 시각과 기존 조사·점검 기록을 대조하세요. 시험 알림이 포함될 수 있습니다.",
            }
        )
