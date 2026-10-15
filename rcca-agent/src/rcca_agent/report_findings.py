"""Operator-facing statements built only from deterministic incident findings.

The RCA scope is the GPU node. Kubernetes workload identity is not reported here.
"""

import re
from datetime import datetime, timedelta, timezone

from agent_common.contracts import timestamp

from .report_labels import query_label

KST = timezone(timedelta(hours=9))
ACTION_NAMES = {
    "RESTART_BM": "호스트(bare-metal) 재시작",
    "RESTART_VM": "VM 재시작",
    "RESET_GPU": "GPU 리셋",
    "RESTART_APP": "애플리케이션 재시작",
    "CONTACT_SUPPORT": "공급사 기술 지원 요청",
    "IGNORE": "즉시 조치 불필요",
    "REBOOT_SYSTEM": "시스템 재부팅",
    "HARDWARE_INSPECTION": "하드웨어 점검",
}
RESTARTS = {"RESTART_BM", "RESTART_VM", "RESET_GPU"}
SEVERITY = {"Fatal": "높음", "Critical": "높음"}
ACTIVITY_QUERY = "D02"
# Published notes may phrase candidates conditionally; report the candidates only.
CONDITIONAL_NOTE = re.compile(r"^(?:.*?라면\s*)?(.+?)\s*등을 조사할 수 있습니다\.?$")


def kst(value, date=False):
    at = datetime.fromtimestamp(timestamp(value), timezone.utc).astimezone(KST)
    return at.strftime("%Y-%m-%d %H:%M:%S KST" if date else "%H:%M:%S")


def number(value):
    return f"{value:g}"


def code_name(code):
    return code.upper().replace(":", " ")


def address(value):
    return str(value).removeprefix("PCI:")


def action_name(code):
    return f"{ACTION_NAMES.get(code, code)}({code})"


def first_sentence(text):
    return re.split(r"(?<=다\.)\s+", text.strip())[0] if text else ""


def gpu_name(identity):
    parts = []
    if len(identity.get("gpu_indexes", [])) == 1:
        parts.append(f"GPU {identity['gpu_indexes'][0]}")
    if len(identity.get("models", [])) == 1:
        parts.append(identity["models"][0])
    return f"({', '.join(parts)})" if parts else ""


def source_name(source):
    return {
        "fleet_inventory": "Fleet 인벤토리(D09)",
        "fleet_status_message": "Fleet 상태 보고 원문(D09)",
    }.get(
        source["source"],
        f"{query_label(source.get('query_id', '?'))} 지표 라벨({source['producer']})",
    )


def unit_text(unit):
    return "%" if unit == "percent" else f" {unit}" if unit else ""


def metric_text(m):
    label = query_label(m["query_id"])
    window = f"{kst(m['start'])}–{kst(m['end'])}"
    if m["kind"] == "counter":
        text = f"{label}: {window} 이 GPU 값 {number(m['first'])}→{number(m['last'])}"
        if m["reset"]:
            return text + "(감소 구간이 있어 증가량 판단 불가)."
        if m["first"] == m["last"]:
            return (
                text + f", 증가 없음(같은 노드 {m['node_series']}개 중 "
                f"{m['node_series_unchanged']}개 변화 없음, 표본 {m['samples']}개)."
            )
        return text + f", {number(m['last'] - m['first'])} 증가."
    unit = unit_text(m.get("unit"))
    if m["window_max"] == 0:
        return (
            f"{label}: {window} 동안 0{unit} 유지"
            f"(같은 노드 {m['node_series']}개 중 {m['node_series_zero']}개가 같은 상태)."
        )
    text = f"{label}: 사건 직전 {number(m['before_event'])}{unit}"
    if m["before_event"] == 0 and m["last_nonzero_at"]:
        text += f", 마지막 0 초과 값은 {kst(m['last_nonzero_at'])}"
        together = m.get("node_series_stopped_together", 0)
        if together > 1:
            text += (
                f"(같은 노드 {m['node_series']}개 중 {together}개가 같은 시각에 0이 됨)"
            )
    else:
        text += f", 구간 범위 {number(m['window_min'])}–{number(m['window_max'])}{unit}"
    return text + "."


def statements(findings, result, data, clues, evidence, guidance):
    """Return {section: [(text, refs)]} or None when findings cannot lead the report."""
    identity = findings.get("identity")
    if not identity:
        return None
    sections = ("problem", "impact", "cause", "action", "next", "guidance", "limits")
    out = {k: [] for k in sections}
    event = next(
        e
        for e in result["quality"]["analysis"]["error_events"]
        if e["event_time"] == findings["event_time"]
    )
    refs = list(event["evidence_refs"])
    code = code_name(findings["error_code"])
    node = findings["node"]
    gpu = identity["gpu_uuid"]
    conflicting = identity["status"] == "conflicting"
    target = f"GPU {gpu}{gpu_name(identity)}" if gpu and not conflicting else "오류 GPU"
    terms = findings.get("catalog") or {}
    health = findings.get("health")
    metrics = findings.get("metrics", [])
    meaning = next(
        (first_sentence(e["guidance"]["meaning"]) for e in guidance), ""
    ) or (f"{terms['fleet_name']}." if terms.get("fleet_name") else "")
    incident_refs = [e["id"] for e in evidence if e["query_id"] == "incident_snapshot"]

    # 발생 내용
    head = (
        f"{kst(findings['event_time'], date=True)}, {event['cluster_id']} / {node}의 "
        f"PCI {address(identity['reported_device'])}에서 {code}가 보고됐습니다."
    )
    if conflicting:
        head += (
            " 수집된 식별자가 서로 달라 오류 GPU를 하나로 특정하지 못했습니다: "
            + ", ".join(sorted({s["gpu_uuid"] for s in identity["sources"]}))
            + "."
        )
    else:
        basis = (
            "수집된 인벤토리와 지표 라벨상"
            if identity["status"] == "corroborated"
            else "수집된 인벤토리상"
        )
        head += f" {basis} 해당 주소는 GPU {gpu}{gpu_name(identity)}와 일치합니다."
    out["problem"].append((head, refs))
    source_refs = [r for s in identity["sources"] for r in s["evidence_refs"]]
    names = ", ".join(dict.fromkeys(source_name(s) for s in identity["sources"]))
    if identity["status"] == "corroborated":
        out["problem"].append(
            (
                f"장치 연결 근거: {names}가 모두 같은 PCI↔GPU UUID 매핑을 보고했습니다"
                f"(독립 생산자 {len(identity['producers'])}개). 다른 매핑은 없습니다.",
                source_refs,
            )
        )
    elif identity["status"] == "single_source":
        out["problem"].append(
            (
                f"장치 연결 근거: {names} 1개 생산자의 매핑입니다. "
                "다른 생산자의 PCI↔GPU UUID 매핑은 이번 수집에 없습니다.",
                source_refs,
            )
        )
    else:
        out["problem"].append(
            (f"장치 연결 충돌: {names}의 매핑이 서로 다릅니다.", source_refs)
        )
    if health:
        text = "시각 정합: Fleet 상태 보고가 "
        if health["last_healthy_at"]:
            text += f"{kst(health['last_healthy_at'])} Healthy → "
        text += f"{kst(health['first_unhealthy_at'])} {health['first_unhealthy_state']}({code})"
        text += (
            f"로 바뀌었고, 이벤트 시각 {kst(findings['event_time'])}은 그 사이입니다."
            if health["brackets_event"]
            else "로 보고됐습니다. 이벤트 이전의 정상 보고는 수집 범위에 없습니다."
        )
        text += " 상태 보고 시각은 Loki 기록 시각입니다."
        out["problem"].append((text, health["evidence_refs"]))
    lag = timestamp(data["incident_time"]) - timestamp(findings["event_time"])
    out["problem"].append(
        (
            f"사건 기준 시각: {data['incident_time']}\n"
            + (
                f"알람 접수 시각이며, 오류 발생 시각은 위 이벤트 시각입니다(접수까지 {round(lag)}초)."
                if lag >= 0
                else "알람 접수 시각이며, 오류 발생 시각은 위 이벤트 시각입니다."
            ),
            incident_refs,
        )
    )

    # 영향과 심각도
    if meaning:
        out["impact"].append(
            (f"의미: {meaning}", [e["evidence_id"] for e in guidance] or refs)
        )
    if health and health["persisted"]:
        out["impact"].append(
            (
                f"확인된 영향: {target}는 {kst(health['first_unhealthy_at'])}부터 마지막 수집 "
                f"보고({kst(health['last_report_at'])})까지 {health['first_unhealthy_state']}로 보고됐고 "
                "회복 보고가 없습니다. 이 GPU는 복구 전까지 사용할 수 없는 상태입니다.",
                health["evidence_refs"],
            )
        )
    else:
        out["impact"].append(
            (
                f"확인된 영향: {target}의 {code}가 보고됐습니다. 보고 이후 상태 지속 여부는 "
                "수집 범위에 없습니다.",
                refs,
            )
        )
    activity = next((m for m in metrics if m["query_id"] == ACTIVITY_QUERY), None)
    if activity and activity["kind"] == "gauge":
        if activity["window_max"] == 0:
            load = (
                f"GPU 부하: 수집 구간 동안 이 GPU 사용률은 0%였고 같은 노드 "
                f"{activity['node_series']}개 중 {activity['node_series_zero']}개가 0%였습니다. "
                "오류 시점에 이 GPU에서 진행 중인 연산은 관측되지 않았습니다."
            )
        elif activity["before_event"] == 0:
            load = (
                f"GPU 부하: 이 GPU 사용률은 {kst(activity['last_nonzero_at'])} 이후 0%였습니다. "
                "오류 시점에 진행 중인 연산은 관측되지 않았습니다."
            )
        else:
            load = (
                f"GPU 부하: 오류 직전 이 GPU 사용률은 {number(activity['before_event'])}%였습니다. "
                "이 GPU에서 진행 중이던 연산은 중단된 것으로 보아야 합니다."
            )
        out["impact"].append((load, activity["evidence_refs"]))
    if terms.get("fleet_event_type"):
        level = SEVERITY.get(terms["fleet_event_type"])
        out["impact"].append(
            (
                (f"심각도: {level}. " if level else "심각도: ")
                + f"Fleet 카탈로그는 {code}를 {terms['fleet_event_type']}로 분류합니다"
                + (
                    ". 해당 GPU의 접근 상실이 회복되지 않은 상태입니다."
                    if health and health["persisted"]
                    else "."
                ),
                terms["evidence_refs"],
            )
        )

    # 원인 분석: 판단 → 근거 → 남은 후보
    counters = [m for m in metrics if m["kind"] == "counter"]
    quiet = counters and all(
        m["first"] == m["last"] and not m["reset"] for m in counters
    )
    short = (
        f"GPU {identity['gpu_indexes'][0]}"
        if len(identity.get("gpu_indexes", [])) == 1 and not conflicting
        else target
    )
    judgement = f"판단: {node} {short} 한 장치에서 {code}가 발생했"
    if health and health["persisted"]:
        judgement += "고, 수집 종료까지 회복되지 않았"
    judgement += "습니다."
    clauses = []
    if not findings["companion_codes"]:
        clauses.append("같은 노드의 동반 오류 이벤트")
    if quiet:
        clauses.append(
            "누적 오류 카운터(" + ", ".join(m["query_id"] for m in counters) + ") 증가"
        )
    if clauses:
        judgement += " " + "·".join(clauses) + " 없이 한 번에 발생했습니다."
    out["cause"].append(
        (judgement, refs + [r for m in counters for r in m["evidence_refs"]])
    )
    facts = [metric_text(m) for m in metrics]
    if findings["companion_codes"]:
        facts.insert(
            0,
            "같은 노드에서 함께 보고된 오류: "
            + ", ".join(code_name(c) for c in findings["companion_codes"])
            + ".",
        )
    supported = findings.get("xid154_supported")
    if supported is not None and findings["error_code"].startswith("xid:"):
        driver = identity["drivers"][0]
        linkage = f"R{terms['xid154_driver']}"
        if "xid:154" in findings["companion_codes"]:
            facts.append(f"드라이버 {driver}에서 XID 154가 함께 보고됐습니다.")
        elif supported:
            facts.append(
                f"드라이버 {driver}는 XID 154 연계 조건({linkage} 이상)에 해당하며, "
                "수집 범위에서 XID 154는 보고되지 않았습니다."
            )
        else:
            facts.append(
                f"드라이버 {driver}는 XID 154 연계 조건({linkage} 이상)보다 낮아 "
                "XID 154 부재를 판단에 사용하지 않습니다."
            )
    if facts:
        out["cause"].append(
            (
                "확인한 근거:\n" + "\n".join(f"- {f}" for f in facts),
                list(dict.fromkeys(r for m in metrics for r in m["evidence_refs"])),
            )
        )
    note = next((e["guidance"].get("cause_note") for e in guidance), None)
    if note:
        match = CONDITIONAL_NOTE.match(note.strip())
        candidates = f"{match.group(1)} 등이 있습니다." if match else note.strip()
        out["cause"].append(
            (
                f"남은 원인 후보(발행 지침): {candidates} 수집 근거로는 이 중 하나로 좁혀지지 "
                "않으며 근본 원인은 미확정입니다. 재시작 후 같은 GPU에서 재발하면 하드웨어 "
                "결함 쪽으로 판단합니다.",
                [e["evidence_id"] for e in guidance],
            )
        )
    else:
        out["cause"].append(
            (
                "남은 원인 후보: 수집 근거로는 근본 원인이 하나로 좁혀지지 않습니다. 재시작 후 "
                "같은 GPU에서 재발하면 하드웨어 결함 쪽으로 판단합니다.",
                refs,
            )
        )

    # 권고 조치: 한 문단으로 순서를 보존한다.
    immediate = terms.get("immediate")
    applicability = findings.get("model_applicability")
    model = identity["models"][0] if len(identity["models"]) == 1 else "미확인"
    listed = ", ".join(terms.get("applies", [])) or "기재 없음"
    if immediate in ACTION_NAMES and not conflicting:
        steps = []
        preserved = ["오류 원문(D09)", "장치 매핑"] + [
            query_label(m["query_id"]) for m in metrics
        ]
        steps.append(
            "근거 보존(자동 완료): "
            + ", ".join(dict.fromkeys(preserved))
            + " 표본을 이 분석의 근거로 보존했습니다. 재시작하면 사라지는 호스트 진단 자료"
            "(nvidia-bug-report.sh 결과·커널 로그)만 재시작 전에 수집하십시오."
        )
        restart = immediate in RESTARTS
        if restart:
            if activity and activity.get("window_max") == 0:
                steps.append(
                    f"작업 확인: 수집 구간 동안 {node}의 GPU {activity['node_series_zero']}개가 "
                    "사용률 0%로, 배출할 GPU 부하는 관측되지 않았습니다. 남은 작업이 없는지 확인하고 "
                    "유지보수 승인을 받으십시오."
                )
            else:
                steps.append(
                    f"작업 배출: {node}에서 GPU를 사용하는 작업을 중지하거나 다른 서버로 옮기고 "
                    "유지보수 승인을 받으십시오."
                )
        provider = (clues.get("provider_actions") or {}).get("value", {})
        same = (
            " Fleet 원천 권고("
            + ", ".join(provider["repair_actions"])
            + ")도 같은 방향입니다."
            if provider.get("repair_actions")
            else ""
        )
        if applicability == "applies":
            step = (
                f"복구: {node} {action_name(immediate)}을 권고합니다. NVIDIA 카탈로그의 즉시 조치이며 "
                f"{model} 모델은 적용 대상({listed})입니다.{same}"
            )
            if immediate == "RESTART_BM":
                step += (
                    " VM(패스스루) 환경이면 호스트 대신 해당 VM을 재시작하고, "
                    "로그 주입 시험이었다면 재시작하지 않습니다."
                )
        elif applicability == "excluded":
            step = (
                f"복구: {model} 모델은 NVIDIA 카탈로그의 {immediate} 적용 대상이 아닙니다"
                f"(적용: {listed}). 이 조치를 그대로 적용하지 말고 해당 세대 문헌을 확인하십시오."
            )
        else:
            step = (
                f"복구: NVIDIA 카탈로그의 즉시 조치는 {action_name(immediate)}입니다(적용: {listed}). "
                f"GPU 모델({model})의 적용 여부를 먼저 확인하십시오.{same}"
            )
        steps.append(step)
        if restart:
            steps.append(
                f"조치 후 확인: 같은 GPU UUID({gpu})가 다시 인식되고 Fleet XID 상태가 Healthy로 "
                "돌아왔는지 확인합니다. 수행한 조치와 확인 결과를 함께 기록합니다."
            )
        if terms.get("investigatory") == "CONTACT_SUPPORT":
            steps.append(
                "재발 대응: 조치 후에도 같은 GPU에서 재발하거나 접근이 회복되지 않으면 오류 원문·"
                "GPU 식별 정보·진단 자료·조치 이력을 첨부해 공급사 지원(CONTACT_SUPPORT)을 요청하십시오."
            )
        out["action"].append(
            (
                "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
                + "\n이 시스템은 조치를 실행하지 않습니다. 수행 여부는 운영자가 결정합니다.",
                terms["evidence_refs"] + incident_refs,
            )
        )
        if immediate == "RESTART_BM":
            out["next"].append(
                (
                    "운영 모드: bare-metal인지 VM(패스스루)인지는 수집 지표에 없습니다. "
                    "VM이면 복구 조치가 VM 재시작으로 바뀝니다.",
                    [],
                )
            )
    out["next"].append(
        (
            "시험 주입 여부: 오류 원문만으로는 로그 주입 시험과 실제 장애를 구분할 수 없습니다. "
            "이 노드에서 XID 주입 시험을 했다면 재시작하지 마십시오.",
            refs,
        )
    )
    if any(
        "AER" in line
        for e in evidence
        if e.get("query_id") == "runbook" and e["id"] in terms.get("evidence_refs", [])
        for line in e.get("snapshot", {}).get("analysis_guidance", [])
    ):
        out["next"].append(
            (
                f"커널 PCIe 오류(AER): 수집 원천(D09)에는 커널 로그가 없습니다. 원인을 좁히려면 "
                f"{node}의 커널 로그에서 {kst(findings['event_time'])} 전후 PCI "
                f"{address(identity['reported_device'])}의 AER 기록을 확인하십시오.",
                [],
            )
        )
    if identity["status"] != "corroborated":
        out["next"].append(
            (
                "장치 연결: 다른 생산자의 PCI↔GPU UUID 매핑이 없어 오류 GPU를 교차 확인하지 "
                "못했습니다. 호스트의 GPU 목록에서 PCI 주소를 대조하십시오.",
                source_refs,
            )
        )

    # 이 오류에 대한 참고 안내: 발행 지침의 카탈로그 정보를 이번 장비에 맞춰 정리한다.
    if terms:
        book_refs = terms["evidence_refs"]
        if terms.get("fleet_event_type"):
            out["guidance"].append(
                (
                    f"{code}"
                    + (f" ({terms['fleet_name']})" if terms.get("fleet_name") else "")
                    + (f": {meaning}" if meaning else "")
                    + f" Fleet 분류 {terms['fleet_event_type']}, 기본 조치 "
                    + ", ".join(action_name(a) for a in terms.get("fleet_actions", []))
                    + ".",
                    book_refs,
                )
            )
        if immediate:
            text = (
                f"NVIDIA 조치 분류: 즉시 조치 {action_name(immediate)}, "
                f"조사 조치 {action_name(terms['investigatory'])}. 적용 모델 {listed}"
                + (
                    f"; 제외 {', '.join(terms['excludes'])}"
                    if terms.get("excludes")
                    else ""
                )
                + "."
            )
            if model != "미확인":
                text += f" 이번 GPU {model}: " + {
                    "applies": "적용 대상.",
                    "excluded": "제외 모델.",
                    "unlisted": "표에 없는 제품(해당 세대 문헌 확인).",
                }.get(applicability, "적용 여부 미확인.")
            out["guidance"].append((text, book_refs))
        if terms.get("xid154_linkage") and terms.get("xid154_driver"):
            text = (
                f"XID 154 연계: {terms['xid154_linkage'].replace('; GPU driver ', '·드라이버 ')} 이상 환경에서는 같은 장치의 복구 조치 "
                "안내(XID 154)가 함께 보고될 수 있습니다."
            )
            if supported is not None:
                text += f" 이번 드라이버 {identity['drivers'][0]}: " + (
                    "조건 해당, XID 154 미보고."
                    if supported and "xid:154" not in findings["companion_codes"]
                    else "조건 해당, XID 154 보고됨."
                    if supported
                    else "조건 미해당."
                )
            out["guidance"].append((text, book_refs))
        if terms.get("sources"):
            out["guidance"].append(
                (
                    "출처: "
                    + "; ".join(
                        f"{s.get('section') or '문헌'} — {s['url']}"
                        for s in terms["sources"]
                    ),
                    book_refs,
                )
            )

    synthesis = result["quality"]["analysis"].get("synthesis", {})
    if synthesis.get("error_code") == "llm_context_budget_exhausted":
        remaining = synthesis.get("budget_allocation", {}).get("remaining_tokens")
        out["limits"].append(
            (
                "LLM 원인 분석의 마지막 작성 단계는 토큰 예산 부족으로 실행되지 않았습니다"
                + (f"(남은 예산 {remaining})" if remaining is not None else "")
                + ". 위 판단은 코드가 수집 근거에서 직접 계산한 값입니다.",
                [],
            )
        )
    return out
