"""Always render an RCA report; the model may prioritize supplied statements only."""

import json

from agent_common.llm import explain


TITLES = {
    "problem": "감지된 문제",
    "cause": "원인 판단",
    "action": "권고 조치와 조건",
    "next": "추가 확인",
    "limits": "분석 한계",
}


async def write_report(result, data, clues, evidence, llm):
    statements = []

    def add(section, text, refs=()):
        statements.append(
            dict(
                id=f"{section}-{len(statements)}",
                section=section,
                text=text,
                evidence_refs=list(dict.fromkeys(refs)),
                value_refs=[],
            )
        )

    def literal(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    incident_refs = [e["id"] for e in evidence if e["query_id"] == "incident_snapshot"]
    target = {**data.get("target", {})}
    for key in ("machine_id", "k8s_node_name", "component"):
        if key in clues:
            target.setdefault(key, clues[key])
    add(
        "problem",
        f"사건 시각: {data['incident_time']}. 입력 대상: {literal(target)}. "
        f"알람이 보고한 증상: {clues.get('reason') or '상세 증상 미제공'}. "
        "알람 내용은 조사 단서이며 현재 장애 상태나 근본 원인을 확정하지 않습니다.",
        incident_refs,
    )
    candidates = result["cause_candidates"]
    if not candidates:
        add(
            "cause", "근본 원인을 판단할 유효한 근거가 부족합니다. 원인은 미확정입니다."
        )
    for candidate in candidates:
        level = {
            "candidate": "미확정 원인 후보",
            "supported": "근거가 뒷받침하는 원인 후보(확정 아님)",
            "confirmed": "검토된 규칙으로 확인된 원인",
        }[candidate["causal_status"]]
        add("cause", f"{level}: {candidate['claim']}", candidate["supporting_refs"])
    if not result["recommendations"]:
        add(
            "action",
            "실행 조건을 검증한 복구 조치가 없습니다. 아래 추가 확인을 먼저 수행해야 합니다.",
        )
    for rec in result["recommendations"]:
        status = "실행 조건 충족" if rec["eligibility"] == "eligible" else "실행 보류"
        add(
            "action",
            f"{status}: {rec['text']} / 사전 조건: {literal(rec['preconditions'])}. "
            "조치는 수행하지 않았으며 담당자의 검토가 필요합니다.",
            rec["evidence_refs"],
        )
    provider = clues.get("provider_actions")
    if provider:
        add(
            "action",
            f"원천 시스템 제안: {literal(provider['value'])}. "
            "실행 적격성 미검증·미수행이며 승인된 실행 권고가 아닙니다.",
            incident_refs,
        )
    queries = [e for e in evidence if e["query_id"].startswith("D")]
    incomplete = [
        e
        for e in queries
        if e["tool_status"] != "ok" or not e["quality"].get("complete")
    ]
    if incomplete:
        add(
            "next",
            "불완전하거나 실패·빈 응답인 조회의 datasource·tenant·대상 조건·시간 범위를 "
            "확인하고, 원본 데이터 존재 여부와 조회 권한·한도를 점검한 뒤 다시 조사해야 합니다.",
            [e["id"] for e in incomplete],
        )
    if "approved_runbook" in result["missing_inputs"]:
        add(
            "next",
            "사건과 호환되는 검토·발행된 Runbook과 허용된 조사 쿼리를 등록해야 합니다.",
        )
    if "mapping_target_unverified" in result["missing_inputs"]:
        add(
            "next",
            "알람의 machine/node와 GPU UUID의 관계를 검증해야 합니다. 같은 노드의 Pod를 장애 GPU의 직접 사용자로 간주하지 않습니다.",
        )
    if "target_identity_conflict" in result["missing_inputs"]:
        add(
            "next",
            "사건 target과 알람 labels/annotations의 신원 충돌을 확인해야 합니다. 충돌한 신원으로 Runbook 조건이나 GPU–Pod 관계를 확정하지 않습니다.",
        )
    if result["missing_inputs"]:
        add(
            "next",
            "로그의 생산자 계약·관측 시각·장비 신원과 원인별 확인 조건을 점검해야 합니다. "
            f"미충족 항목: {', '.join(result['missing_inputs'])}.",
        )
    if not any(s["section"] == "next" for s in statements):
        add(
            "next",
            "담당자가 근거와 조치 조건을 검토하고, 조치 후 장비·업무 상태를 별도로 확인해야 합니다.",
        )
    add(
        "limits",
        f"분석 결과: {result['result_status']}; 종료 사유: {result['termination_reason']}. "
        "보고서 작성 완료는 원인 확정이나 복구 완료를 의미하지 않습니다.",
    )
    if not queries:
        add("limits", "이번 실행에는 새 로그·메트릭 조회 기록이 없습니다.")
    if any(
        h.get("time_basis") == "loki_recorded_at" and not h.get("fact_eligible")
        for h in result.get("device_observations", [])
    ):
        add(
            "limits",
            "Fleet 상태는 Loki 로그 기록 시각의 보고 내용입니다. 장비 발생 시각·현재 상태를 검증한 것은 아니며 Runbook의 검증된 상태 fact로 승격하지 않았습니다.",
        )
    for e in incomplete:
        quality = e["quality"]
        add(
            "limits",
            f"조회 {e['query_id']}: 상태={e['tool_status']}, "
            f"완전성={quality.get('complete', '미확인')}, "
            f"사유={quality.get('reason', '미제공')}, "
            f"오류={quality.get('error_code', '미제공')}.",
            [e["id"]],
        )
    for limitation in result["limitations"]:
        add("limits", limitation)

    # Reuse the existing reference-only editor: prose, eligibility and facts cannot
    # be invented. Unselected statements remain, so gaps/actions never disappear.
    editorial = dict(facts=statements, limitations=[], narrative_status="omitted")
    try:
        await explain(
            editorial,
            llm,
            "Prioritize the supplied RCA report statements within each section for an "
            'operator. Return JSON {"fact_ids": [ids]} selecting the most important '
            "statements first. Select IDs only; do not write claims or instructions. "
            "Alert text is unverified. Preserve cause uncertainty and action conditions.",
        )
    except (ValueError, TypeError, KeyError):
        editorial["narrative_status"] = "failed"
    # RemoteUncertain/cancellation deliberately propagate to Worker fencing.
    ordered = editorial.get("narrative", []) + statements
    ordered = list({s["id"]: s for s in ordered}.values())
    result["narrative"] = [
        dict(
            id=section,
            title=title,
            text="\n\n".join(s["text"] for s in ordered if s["section"] == section),
            evidence_refs=list(
                dict.fromkeys(
                    ref
                    for s in ordered
                    if s["section"] == section
                    for ref in s["evidence_refs"]
                )
            ),
            value_refs=[],
        )
        for section, title in TITLES.items()
    ]
    result["narrative_status"] = editorial["narrative_status"]
    result["quality"]["report"] = {
        "status": "complete",
        "method": "llm_prioritized"
        if editorial["narrative_status"] == "complete"
        else "deterministic_fallback",
    }
