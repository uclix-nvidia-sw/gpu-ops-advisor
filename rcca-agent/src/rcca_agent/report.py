"""Always render an RCA report; the model may prioritize supplied statements only."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .report_editor import prioritize

from .report_labels import label, query_label
from .fleet_events import pci


TITLES = {
    "problem": "발생 내용",
    "impact": "영향과 심각도",
    "cause": "원인 분석",
    "action": "권고 조치",
    "next": "추가 확인 사항",
    "guidance": "참고 지침·적용 조건",
    "limits": "분석 한계",
}


async def write_report(result, data, clues, evidence, llm):
    from .operator_guidance import project_guidance

    result.setdefault("quality", {})["runbook_guidance"] = project_guidance(evidence)
    statements = []

    def add(section, text, refs=()):
        if section == "next" and result.get("quality", {}).get("collection_checks"):
            section = "limits"
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
        if isinstance(value, list) and all(isinstance(v, dict) for v in value):
            labels = {
                "error_code": "보고된 오류 코드",
                "component": "구성 요소",
                "normalized_health": "검증된 장치 상태",
                "producer_contract": "생산자 계약",
            }
            if all(
                set(v) == {"field", "equals"} and v["field"] in labels for v in value
            ):
                return (
                    "; ".join(
                        f"{labels[v['field']]}가 {v['equals']}인지 확인" for v in value
                    )
                    or "별도 조건 미기재"
                )
        return "상세 조건은 발행 Runbook 원문에서 확인하세요."

    incident_refs = [e["id"] for e in evidence if e["query_id"] == "incident_snapshot"]
    target = {**data.get("target", {})}
    for key in ("machine_id", "k8s_node_name", "component"):
        if key in clues:
            target.setdefault(key, clues[key])
    display_title = (
        target.pop("title", None) or target.pop("reason", None) or clues.get("reason")
    )
    target.pop("test_alarm", None)
    if display_title:
        target["alertname"] = display_title
    target_names = {
        "cluster_id": "클러스터",
        "node": "노드",
        "k8s_node_name": "노드",
        "machine_id": "장비",
        "gpu_uuid": "GPU",
        "component": "구성 요소",
        "namespace": "네임스페이스",
        "pod": "Pod",
        "pod_uid": "Pod UID",
        "alertname": "알람",
    }
    reported = result.get("quality", {}).get("analysis", {}).get("reported_errors", [])
    events = result.get("quality", {}).get("analysis", {}).get("error_events", [])
    codes = ", ".join(
        sorted({h["error_code"].upper().replace(":", " ") for h in reported})
    )
    headline = (
        f"{codes} 오류가 보고된 것을 확인했습니다."
        if codes
        else "알람이 발생했습니다. 상세 증상은 아래 원문을 확인하세요."
    )
    for event in events:
        at = datetime.fromisoformat(event["event_time"].replace("Z", "+00:00"))
        at = at.astimezone(timezone(timedelta(hours=9))).strftime(
            "%Y-%m-%d %H:%M:%S KST"
        )
        host = event["target"].get("node") or event["target"]["machine_id"]
        device = event.get("reported_device") or "장치 식별자 미기록"
        text = f"{at}, {event['cluster_id']} / {host}의 {device}에서 {event['error_code'].upper().replace(':', ' ')} 오류 이벤트가 기록됐습니다."
        if event.get("device_mapping") == "inventory_match":
            text += (
                f" 수집 인벤토리의 GPU {event['inventory_gpu_candidate']}와 일치합니다."
            )
        elif event.get("device_mapping") == "conflicting":
            text += " 이벤트 내부 장치 식별자가 충돌하여 연결 대상을 구분해야 합니다."
        elif event["error_code"].startswith("sxid:"):
            text += " 해당 주소의 NVSwitch·포트 연결 정보는 이번 근거에 없습니다."
        add("problem", text, event["evidence_refs"])
    if not events:
        add(
            "problem",
            headline,
            [r for h in reported for r in h["evidence_refs"]] or incident_refs,
        )
        associations = {}
        for observation in result.get("device_observations", []):
            if observation.get("pci_inventory_relation") != "inventory_candidate_only":
                continue
            for address in observation.get("reported_pci_addresses", []):
                matches = {
                    gpu["gpu_uuid"]
                    for gpu in observation.get("gpu_candidates", [])
                    if pci(address) and pci(address) == pci(gpu.get("bus_id"))
                }
                if len(matches) != 1:
                    continue
                node = observation.get("target", {}).get(
                    "node",
                    target.get("node", target.get("k8s_node_name", "노드 미기록")),
                )
                key = (node, address, next(iter(matches)))
                associations.setdefault(key, []).extend(
                    observation.get("evidence_refs", [])
                )
        for (node, address, gpu), refs in associations.items():
            add(
                "problem",
                f"{node}의 오류 주소 {address}는 같은 상태 보고에 수집된 GPU {gpu}와 일치합니다.",
                refs,
            )
    primary = []
    identifiers = []
    if display_title and display_title != clues.get("reason"):
        identifiers.append(f"알람 이름: {display_title}")
    for key, value in target.items():
        if value is None or key == "alertname":
            continue
        line = f"{target_names.get(key, key)}: {value}"
        (
            primary
            if key in {"cluster_id", "node", "k8s_node_name", "namespace", "pod"}
            else identifiers
        ).append(line)
    add(
        "problem",
        "대상\n" + "\n".join(dict.fromkeys(primary or ["대상 미확인"])),
        incident_refs,
    )
    add(
        "problem",
        f"사건 기준 시각: {data['incident_time']}\n"
        + (
            "오류 발생 시각은 위 이벤트 기록을 기준으로 표시했습니다."
            if events
            else "오류 발생 시각은 별도 이벤트 근거가 필요합니다."
        ),
        incident_refs,
    )
    add(
        "problem",
        "알람이 보고한 증상(원문):\n"
        + (clues.get("reason") or display_title or "상세 증상 미제공"),
        incident_refs,
    )
    if identifiers:
        add(
            "problem",
            "대상 식별 정보\n" + "\n".join(dict.fromkeys(identifiers)),
            incident_refs,
        )
    relations = result.get("pod_relations", [])
    for relation in relations:
        add(
            "impact",
            f"사건 시각의 관측 연결: GPU {relation['gpu_uuid']} · "
            f"Namespace {relation['namespace']} · Pod UID {relation['pod_uid']}. "
            "작업 실패·중단 여부는 이 연결 정보만으로 판정하지 않습니다.",
            relation["evidence_refs"],
        )
    add(
        "impact",
        "확인된 업무 영향: 이번 분석에는 작업 실패·서비스 중단을 입증한 결과가 없습니다. "
        + (
            "위 작업을 영향 확인 대상으로 사용하세요."
            if relations
            else "사건 시각의 작업과 오류 장비의 연결 근거가 필요합니다."
        )
        + " 심각도는 오류의 의미와 실제 영향 범위를 함께 판단해야 합니다.",
    )
    for guidance in result["quality"]["runbook_guidance"]:
        add(
            "impact",
            "오류 의미(발행 지침): " + guidance["guidance"]["meaning"],
            [guidance["evidence_id"]],
        )
    for diagnostic in (
        result.get("quality", {}).get("analysis", {}).get("requirement_diagnostics", [])
    ):
        if diagnostic.get("reason") == "reported_but_required_semantics_unverified":
            add(
                "limits",
                f"{label('reasons', diagnostic['requirement'])}: 원본 보고는 확보했지만 "
                "Runbook이 요구하는 대상·시각·상태의 검증 조건은 충족하지 못했습니다. "
                "이는 해당 원본을 조회하지 못했다는 뜻이 아닙니다.",
                diagnostic["evidence_refs"],
            )
    evaluation = result.get("quality", {}).get("rca_evaluation")
    if evaluation:
        review = evaluation["review"]
        verdict = {
            "acceptable": "확보된 근거 범위에서 타당",
            "revision_required": "수정 필요",
            "undetermined": "판단 불가",
        }.get(review["verdict"], "미검토")
        collection = {
            "complete": "계획한 조회 완료",
            "partial": "부분 수집",
            "failed": "수집 실패",
            "not_requested": "수집 불필요",
        }[evaluation["collection"]["status"]]
        add(
            "limits",
            f"수집 상태: {collection}. 분석 품질: {verdict}. 조사 종료는 원인 확정을 뜻하지 않습니다.",
            review["evidence_refs"],
        )
        if review.get("reason"):
            add("limits", "검토 제한: " + review["reason"], review["evidence_refs"])
    candidates = result["cause_candidates"]
    mismatches = [
        h
        for h in result.get("device_observations", [])
        if h.get("pci_inventory_relation") == "not_in_reported_inventory"
    ]
    if mismatches:
        add(
            "problem",
            "장치 연결 미확인: 오류 메시지의 PCI 주소가 같은 로그의 장비 목록과 "
            "일치하지 않습니다. 장비 목록의 GPU를 장애 GPU로 간주하지 않았습니다. "
            "시험 주입 여부와 원본 장치 정보를 대조해야 합니다.",
            [ref for h in mismatches for ref in h.get("evidence_refs", [])],
        )
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
        published_actions = [
            entry
            for entry in evidence
            if entry.get("query_id") == "runbook"
            and entry.get("quality", {}).get("origin") == "published"
            and entry.get("snapshot", {}).get("investigation_only")
            and entry["snapshot"].get("recommendations")
        ]
        add(
            "action",
            "발행 Runbook의 조사 권고를 아래에 제시합니다. 복구 절차의 적용 조건은 별도로 확인하세요."
            if published_actions
            else "이번 결과에는 적용할 권고가 생성되지 않았습니다. 추가 확인 사항과 조회 결과에서 누락된 적용 근거를 확인하세요.",
        )
        for entry in published_actions:
            for rec in entry["snapshot"]["recommendations"]:
                add(
                    "action",
                    "발행 Runbook 권고(적용 조건 확인): "
                    + rec["text"]
                    + "\n적용 조건: "
                    + literal(rec.get("preconditions", [])),
                    [entry["id"]],
                )
    for rec in result["recommendations"]:
        status = "실행 조건 충족" if rec["eligibility"] == "eligible" else "실행 보류"
        add(
            "action",
            f"{status}: {rec['text']}\n사전 조건: {literal(rec['preconditions'])}\n"
            "담당자 검토 후 수행 여부를 결정하세요. 이 시스템은 조치를 실행하지 않습니다.",
            rec["evidence_refs"],
        )
    provider = clues.get("provider_actions")
    if provider:
        add(
            "action",
            "원천 제안 조치: "
            + ", ".join(
                {"REBOOT_SYSTEM": "시스템 재부팅(REBOOT_SYSTEM)"}.get(
                    action, "등록되지 않은 원천 조치"
                )
                for action in provider["value"]["repair_actions"]
            )
            + ". "
            "\n실행 적격성 미검증: 원천 시스템의 제안이며 이 분석이 실행을 권고한 것은 아닙니다.\n"
            "현재 상태와 적용 조건을 먼저 확인하세요. 이 시스템은 조치를 실행하지 않습니다.",
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
            "확인하고, 원본 데이터 존재 여부와 조회 권한·한도를 점검한 뒤 다시 조사해야 합니다. "
            + "대상 조회: "
            + ", ".join(
                query_label(q) for q in sorted({e["query_id"] for e in incomplete})
            ),
            [e["id"] for e in incomplete],
        )
    if "approved_runbook" in result["missing_inputs"]:
        add(
            "next",
            "사건과 호환되는 검토·발행된 Runbook과 허용된 조사 쿼리를 등록해야 합니다.",
        )
    runbooks = result.get("runbook_revisions", [])
    # Published investigation guidance is useful even when device-state gates
    # prevent actionable recommendations. Keep it separate from observed facts
    # and eligible remediation; cite only the selected immutable snapshots.
    for entry in evidence:
        if entry.get("query_id") != "runbook":
            continue
        if entry.get("quality", {}).get("origin") != "published":
            continue
        content = entry.get("snapshot", {})
        if not content.get("investigation_only"):
            continue
        refs = [entry["id"]]
        add(
            "guidance",
            f"{content.get('title', '발행 Runbook')} · revision {entry.get('query_version', '?')}\n"
            "아래는 발행된 조사 지침과 문헌의 적용 조건입니다. 이번 장비에서 확인된 사실이나 "
            "실행 승인으로 해석하지 마세요. 조치는 운영자가 판단하며 자동 실행하지 않습니다.",
            refs,
        )
        for rec in content.get("recommendations", []):
            add(
                "guidance",
                "Runbook 권고 검토: "
                + rec["text"]
                + "\n적용 조건(충족 여부 별도 확인): "
                + literal(rec.get("preconditions", [])),
                refs,
            )
        for guidance in content.get("analysis_guidance", []):
            add("guidance", guidance, refs)
        for limitation in content.get("limitations", []):
            add("guidance", "적용 한계: " + limitation, refs)
    published = any(b.get("origin") == "published" for b in runbooks)
    if any(b.get("origin") == "builtin" for b in runbooks):
        add(
            "limits",
            (
                "발행 Runbook을 조사에 선택하고 기본 일반 조사 템플릿을 추가 사용했습니다. "
                "Runbook 선택은 필수 근거 충족이나 원인 확정을 의미하지 않습니다. "
                if published
                else "발행 Runbook 선택 기록 없이 기본 일반 조사 템플릿을 사용했습니다. "
            )
            + "이 템플릿은 원인 판정 규칙이나 발행된 지식이 아닙니다.",
            [
                e["id"]
                for e in evidence
                if e["query_id"]
                in ("runbook_selection", "evidence_evaluation", "unexpected_evidence")
            ],
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
            "limits",
            "미충족 근거(missing data)는 원본 데이터가 없다는 뜻만은 아닙니다. "
            "조회한 자료가 있어도 대상·시각·상태 의미 또는 원인 확인 조건을 충족하지 못하면 부분 산출로 남습니다.",
        )
        if "causal_confirmation_evidence" in result["missing_inputs"]:
            add(
                "limits",
                "조사 절차와 원천 권고 조치는 원인 확정 근거가 아닙니다. "
                "재부팅 등 원천 권고를 수집했더라도 해당 대상의 조치 적합성·수행·복구가 확인된 것은 아닙니다.",
            )
        if "causal_confirmation_evidence" in result["missing_inputs"]:
            add(
                "next",
                "실제 원인은 확정하지 못했습니다. 해당 오류의 원인을 구분할 추가 근거를 확인해야 합니다.",
            )
        if "normalized_health" in result["missing_inputs"]:
            add(
                "next",
                "현재 장치 상태는 검증하지 못했습니다. 조사 대상 장치의 최신 상태와 관측 시각을 확인해야 합니다.",
            )
        unverified = [
            h
            for h in result.get("device_observations", [])
            if h.get("time_basis") == "loki_recorded_at" and not h.get("fact_eligible")
        ]
        if "unknown_value" in result["missing_inputs"]:
            if unverified:
                add(
                    "next",
                    "수집된 로그 중 상태 의미가 미검증인 관측이 있습니다. 해당 원본의 상태 판정 조건과 장치 연결 정보를 추가 확인해야 합니다.",
                    [ref for h in unverified for ref in h.get("evidence_refs", [])],
                )
            else:
                add(
                    "next",
                    "조사에 필요한 값 중 의미 또는 유효성이 확인되지 않은 항목이 있습니다. 상세 근거에서 해당 관측과 검증 사유를 확인해야 합니다.",
                )
        explained = {
            "causal_confirmation_evidence",
            "normalized_health",
            "unknown_value",
            "approved_runbook",
            "mapping_target_unverified",
            "target_identity_conflict",
        }
        remaining = [code for code in result["missing_inputs"] if code not in explained]
        if remaining:
            add(
                "next",
                "추가로 충족해야 할 조사 조건: "
                + ", ".join(label("reasons", code) for code in remaining)
                + ".",
            )
    if not any(s["section"] == "next" for s in statements):
        add(
            "next",
            "담당자가 근거와 조치 조건을 검토하고, 조치 후 장비·업무 상태를 별도로 확인해야 합니다.",
        )
    checks = result.get("quality", {}).get("collection_checks", [])
    for check in checks:
        status = check["status"]
        label_text = {
            "collected": "자동 수집 완료",
            "connection_required": "추가 원천 연결 필요",
            "plan_required": "발행 조사 계획에 조회 추가 필요",
            "not_collected": "이번 수집 한도에서 실행되지 않음",
            "empty": "자동 조회 완료·해당 범위 표본 없음",
            "failed": "자동 조회 실패",
            "partial": "자동 조회 부분 응답",
            "identity_unresolved": "자동 조회 완료·유효 시각의 장비–작업 연결 없음",
        }[status]
        add(
            "action" if status == "collected" else "limits",
            f"{check['title']}: {label_text}. "
            + (", ".join(check["query_ids"]) or "등록된 조회 없음")
            + (" · " + ", ".join(check["reasons"]) if check["reasons"] else ""),
            check["evidence_refs"],
        )
        if status in {"connection_required", "plan_required", "identity_unresolved"}:
            statements.append(
                dict(
                    id=f"next-{len(statements)}",
                    section="next",
                    text=f"{check['title']}: {label_text}. {check['connection_required']}",
                    evidence_refs=check["evidence_refs"],
                    value_refs=[],
                )
            )
    if checks and not any(s["section"] == "next" for s in statements):
        statements.append(
            dict(
                id=f"next-{len(statements)}",
                section="next",
                text="추가 원천 연결 요청은 없습니다. 자동 조회의 실패·빈 응답·수집 한도와 원인 미확정 사항은 분석 한계에 기록했습니다.",
                evidence_refs=[],
                value_refs=[],
            )
        )
    add(
        "limits",
        f"분석 결과: {label('result_status', result['result_status'])}; "
        f"종료 사유: {label('termination_reason', result['termination_reason'])}. "
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
    if (
        result.get("quality", {}).get("analysis", {}).get("status") == "complete"
        and result["result_status"] == "partial"
    ):
        add(
            "limits",
            "원인 분석 응답 검증은 완료했지만 조사에 필요한 근거가 부족하여 결과는 부분 산출입니다.",
        )
    grouped = defaultdict(list)
    for e in queries:
        grouped[e["query_id"]].append(e)
    for query_id, chunks in sorted(grouped.items()):
        statuses = Counter(e["tool_status"] for e in chunks)
        if len(chunks) == 1:
            e = chunks[0]
            summary = label("tool_status", e["tool_status"])
            count = e["quality"].get("sample_count")
            if isinstance(count, int) and not isinstance(count, bool):
                summary += f" · {count}건"
        else:
            summary = f"{len(chunks)}개 구간: " + ", ".join(
                f"{label('tool_status', status)} {count}개"
                for status, count in sorted(statuses.items())
            )
        completeness = Counter(
            "완전"
            if e["quality"].get("complete") is True
            else "불완전"
            if e["quality"].get("complete") is False
            else "완전성 미확인"
            for e in chunks
        )
        summary += " · " + ", ".join(
            f"{state} {count}개 구간" if len(chunks) > 1 else state
            for state, count in sorted(completeness.items())
        )
        details = Counter(
            (key, e["quality"][key])
            for e in chunks
            for key in ("reason", "error_code")
            if e["quality"].get(key)
        )
        for (key, code), count in sorted(details.items()):
            summary += (
                f" · {'사유' if key == 'reason' else '오류'}: {label('reasons', code)}"
            )
            if len(chunks) > 1:
                summary += f" ({count}개 구간)"
        if all(
            e["tool_status"] == "empty" and e["quality"].get("complete") is True
            for e in chunks
        ):
            summary = "조회는 정상 완료됐으나 데이터 0건"
        if all(e["quality"].get("derived_from") for e in chunks):
            summary += " · 원본 로그에서 파생한 보기(추가 관측 아님)"
        add("limits", f"{query_label(query_id)}: {summary}.", [e["id"] for e in chunks])
    for limitation in dict.fromkeys(result["limitations"]):
        add("limits", limitation)

    # Reuse the existing reference-only editor: prose, eligibility and facts cannot
    # be invented. Unselected statements remain, so gaps/actions never disappear.
    editorial = dict(facts=statements, limitations=[], narrative_status="omitted")
    editor_reason = None
    editor_diagnostics = None
    try:
        editor_diagnostics = await prioritize(editorial, llm)
    except (ValueError, TypeError, KeyError):
        editorial["narrative_status"] = "failed"
        editor_reason = "editor_exception"
    # RemoteUncertain/cancellation deliberately propagate to Worker fencing.
    ordered = editorial.get("narrative", []) + statements
    ordered = list({s["id"]: s for s in ordered}.values())
    # Keep the problem headline/context in a stable reading order.
    ordered = [s for s in statements if s["section"] in {"problem", "guidance"}] + [
        s for s in ordered if s["section"] not in {"problem", "guidance"}
    ]
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
        if section != "guidance" or any(s["section"] == section for s in ordered)
    ]
    result["narrative_status"] = editorial["narrative_status"]
    result["quality"]["report"] = {
        "status": "complete",
        "presentation": "incident-first/1",
        "method": "llm_prioritized"
        if editorial["narrative_status"] == "complete"
        else "deterministic_fallback",
    }
    if editor_diagnostics is not None:
        result["quality"]["report"]["editor"] = editor_diagnostics
    if editorial["narrative_status"] != "complete":
        result["quality"]["report"]["fallback_reason"] = editor_reason or (
            "editor_not_configured"
            if not llm.configured
            else "editor_response_rejected"
            if editorial["narrative_status"] == "failed"
            else "editor_no_selection"
        )
