"""Operator-facing statements built only from deterministic incident findings.

The RCA scope is the GPU node. Kubernetes workload identity is not reported here.
Sentences follow the catalog action kind so that XID, SXID and non-restart codes
read correctly without assuming an access-loss failure.
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
    "REBOOT_SYSTEM": "시스템 재부팅",
    "RESTART_APP": "애플리케이션 재시작",
    "CONTACT_SUPPORT": "공급사 기술 지원 요청",
    "HARDWARE_INSPECTION": "하드웨어 점검",
    "IGNORE": "즉시 조치 불필요",
    "IGNORE_NO_ACTION_REQUIRED": "즉시 조치 불필요",
    "CHECK_UVM": "UVM 드라이버 점검",
    "CHECK_MECHANICALS": "기계적 연결(보조 전원 등) 점검",
    "UPDATE_SWFW": "소프트웨어·펌웨어 업데이트",
    "XID_154": "XID 154 복구 조치 확인",
    "WORKFLOW_XID_45": "XID 45 처리 절차",
    "WORKFLOW_XID_48": "XID 48 처리 절차",
    "WORKFLOW_NVLINK_ERR": "NVLink 오류 처리 절차",
    "WORKFLOW_NVLINK5_ERR": "NVLink5 오류 처리 절차",
}
SEVERITY = {"Fatal": "높음", "Critical": "높음", "Warning": "중간", "Info": "낮음"}
RESTART_GROUP = {"RESTART_BM", "REBOOT_SYSTEM"}
ACTIVITY_QUERY = "D02"
# Published notes may phrase candidates conditionally; report the candidates only.
CONDITIONAL_NOTE = re.compile(r"^(?:.*?라면\s*)?(.+?)\s*등을 조사할 수 있습니다\.?$")
HEDGES = ("확정할 수", "단정할 수", "라면 ", "확인한 뒤", "판정은 아닙니다")


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


def sentences(text):
    return [s for s in re.split(r"(?<=다\.)\s+", (text or "").strip()) if s]


def plain(text):
    """Keep only sentences that state something; drop deferring qualifiers."""
    return " ".join(s for s in sentences(text) if not any(h in s for h in HEDGES))


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
        "fleet_event": "Fleet 오류 이벤트 원문(D09)",
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


def same_action(a, b):
    return a == b or {a, b} <= RESTART_GROUP


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
    error = f"{code} 오류"
    node = findings["node"]
    switch = identity.get("kind") == "switch"
    gpu = identity["gpu_uuid"]
    conflicting = identity["status"] == "conflicting"
    device = f"PCI {address(identity['reported_device'])}"
    if switch:
        target = short = f"NVSwitch({device})"
    elif gpu and not conflicting:
        target = f"GPU {gpu}{gpu_name(identity)}"
        short = (
            f"GPU {identity['gpu_indexes'][0]}"
            if len(identity.get("gpu_indexes", [])) == 1
            else target
        )
    else:
        target = short = "오류 GPU"
    terms = findings.get("catalog") or {}
    health = findings.get("health")
    metrics = findings.get("metrics", [])
    plan = findings.get("plan") or {}
    kind = plan.get("kind")
    applicability = findings.get("model_applicability")
    models = identity.get("models", [])
    model = models[0] if len(models) == 1 else None
    access_loss = terms.get("category") == "gpu_access_loss"
    fatal = terms.get("fleet_event_type") in ("Fatal", "Critical")
    meaning = next(
        (
            sentences(e["guidance"]["meaning"])[0]
            for e in guidance
            if e["guidance"].get("meaning")
        ),
        "",
    ) or (f"{terms['fleet_name']}." if terms.get("fleet_name") else "")
    incident_refs = [e["id"] for e in evidence if e["query_id"] == "incident_snapshot"]
    book_refs = terms.get("evidence_refs", [])
    guidance_refs = [e["evidence_id"] for e in guidance] or book_refs

    # 발생 내용
    when = (
        f"{kst(findings['event_time'], date=True)}, {event['cluster_id']} / {node}의 "
    )
    if switch:
        head = when + f"NVSwitch {device}에서 {error}가 보고됐습니다."
        if conflicting:
            head += " 이 주소가 수집된 GPU 주소와 겹쳐 오류 장치를 특정하지 못했습니다."
        elif identity["gpu_inventory_size"]:
            head += (
                f" 이 주소는 수집된 GPU {identity['gpu_inventory_size']}개의 PCI 주소에 없어 "
                "GPU가 아닌 NVSwitch 장치입니다."
            )
    else:
        head = when + f"{device}에서 {error}가 보고됐습니다."
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
    if switch:
        out["problem"].append(
            (
                f"장치 근거: {names}에서 같은 NVSwitch PCI 주소가 보고됐습니다. "
                "스위치 포트와 연결된 GPU·파티션은 수집 원천에 없습니다.",
                source_refs,
            )
        )
    elif identity["status"] == "corroborated":
        out["problem"].append(
            (
                f"장치 연결 근거: {names}에서 모두 같은 PCI↔GPU UUID 매핑이 보고됐습니다"
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
            f"로 바뀌었고, 이벤트 시각({kst(findings['event_time'])})은 그 사이입니다."
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
        out["impact"].append((f"의미: {meaning}", guidance_refs or refs))
    if health and health["persisted"]:
        text = (
            f"확인된 영향: {target}는 {kst(health['first_unhealthy_at'])}부터 마지막 수집 "
            f"보고({kst(health['last_report_at'])})까지 Fleet 상태 "
            f"{health['first_unhealthy_state']}로 보고됐고 회복 보고가 없습니다."
        )
        if access_loss and not switch:
            text += " 이 GPU는 복구 전까지 사용할 수 없는 상태입니다."
        elif fatal:
            text += " 복구가 확인될 때까지 이 장치에 작업을 배치하지 마십시오."
        out["impact"].append((text, health["evidence_refs"]))
    else:
        out["impact"].append(
            (
                f"확인된 영향: {target}의 {error}가 보고됐습니다. 보고 이후 상태 지속 여부는 "
                "수집 범위에 없습니다.",
                refs,
            )
        )
    if switch:
        out["impact"].append(
            (
                "영향 범위: 이 스위치 포트에 연결된 GPU·VM·파티션은 수집 원천에 없어 특정하지 "
                "못했습니다. 같은 노드에서 NVLink 통신을 쓰는 작업이 영향 대상입니다.",
                source_refs,
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
                f"GPU 부하: 오류 직전 이 GPU 사용률은 {number(activity['before_event'])}%였습니다."
                + (
                    " 이 GPU에서 진행 중이던 연산은 중단된 것으로 보아야 합니다."
                    if access_loss
                    else ""
                )
            )
        out["impact"].append((load, activity["evidence_refs"]))
    if terms.get("fleet_event_type"):
        level = SEVERITY.get(terms["fleet_event_type"])
        text = (f"심각도: {level}. " if level else "심각도: ") + (
            f"Fleet 카탈로그 분류 {terms['fleet_event_type']}."
        )
        if terms.get("gpud_potential_fatal"):
            text += " GPUd는 잠재적 Fatal(PotentialFatal)로 분류합니다."
        if health and health["persisted"] and fatal:
            text += " 회복 보고 없이 오류 상태가 유지되고 있습니다."
        out["impact"].append((text, book_refs))

    # 원인 분석: 판단 → 근거 → 남은 후보
    counters = [m for m in metrics if m["kind"] == "counter"]
    quiet = counters and all(
        m["first"] == m["last"] and not m["reset"] for m in counters
    )
    judgement = f"판단: {node} {short}에서 {error}가 발생했"
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
        judgement += " " + "·".join(clauses) + " 없이 단독으로 보고됐습니다."
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
    note = next((e["guidance"].get("cause_note") for e in guidance), None) or ""
    match = CONDITIONAL_NOTE.match(note.strip())
    candidates = f"{match.group(1)} 등이 있습니다." if match else plain(note)
    tail = "수집 근거로는 하나로 좁혀지지 않으며 근본 원인은 미확정입니다."
    if kind == "restart":
        tail += (
            f" 조치 후 같은 {'스위치' if switch else 'GPU'}에서 재발하면 하드웨어 결함 쪽으로 "
            "판단합니다."
        )
    out["cause"].append(
        (
            (
                f"남은 원인 후보(발행 지침): {candidates} "
                if candidates
                else "남은 원인 후보: "
            )
            + tail,
            guidance_refs if candidates else refs,
        )
    )

    # 권고 조치: 한 문단으로 순서를 보존한다.
    preserved = ["오류 원문(D09)", "장치 식별 정보"] + [
        query_label(m["query_id"]) for m in metrics
    ]
    host = "nvidia-bug-report.sh 결과·커널 로그" + (
        "·Fabric Manager 로그" if switch else ""
    )
    listed = ", ".join(terms.get("applies", [])) or "기재 없음"
    excluded = ", ".join(terms.get("excludes", []))
    action = plan.get("action")
    steps = []
    if plan and not conflicting:
        restart = kind == "restart"
        blocked = applicability == "excluded"
        steps.append(
            "근거 보존(자동 완료): "
            + ", ".join(dict.fromkeys(preserved))
            + " 표본을 이 분석의 근거로 보존했습니다. "
            + (
                f"재시작하면 사라지는 호스트 진단 자료({host})만 조치 전에 수집하십시오."
                if restart and not blocked
                else f"호스트 진단 자료({host})를 수집해 두십시오."
            )
        )
        basis = {
            "nvidia": "NVIDIA 카탈로그의 즉시 조치",
            "gpud": "GPUd 카탈로그의 기본 조치",
        }.get(plan["source"], "Fleet·GPUd 카탈로그의 기본 조치")
        if blocked:
            steps.append(
                f"조치: {model} 모델은 {basis}인 {action_name(action)}의 적용 대상이 아닙니다"
                + (
                    f"(적용: {listed})"
                    if plan["source"] == "nvidia"
                    else f"(제외: {excluded})"
                )
                + ". 이 조치를 그대로 적용하지 말고 해당 세대 문헌을 확인하십시오."
            )
        elif kind == "none_listed":
            steps.append(
                "조치: 카탈로그에 이 오류의 즉시 조치가 정의돼 있지 않습니다. 같은 장치에서 "
                "반복되면 진단 자료를 첨부해 공급사 지원을 요청하십시오."
            )
        elif kind == "none":
            steps.append(
                f"조치: {basis}상 즉시 조치는 필요하지 않습니다({action}). "
                f"같은 {short}에서 반복되면 다시 조사합니다."
            )
        else:
            if restart:
                if activity and activity.get("window_max") == 0:
                    steps.append(
                        f"작업 확인: 수집 구간 동안 {node}의 GPU {activity['node_series_zero']}개가 "
                        "사용률 0%로, 배출할 GPU 부하는 관측되지 않았습니다. 남은 작업이 없는지 "
                        "확인하고 유지보수 승인을 받으십시오."
                    )
                else:
                    steps.append(
                        f"작업 배출: {node}에서 GPU를 사용하는 작업을 중지하거나 다른 서버로 "
                        "옮기고 유지보수 승인을 받으십시오."
                    )
            if kind == "application":
                step = (
                    f"복구: 이 GPU를 사용하던 애플리케이션(프로세스)을 재시작하십시오({action}). "
                    f"{basis}이며 호스트 재시작은 필요하지 않습니다."
                )
            elif kind == "support":
                step = (
                    f"조치: 공급사 기술 지원을 요청하십시오({action}). {basis}이며 오류 원문·"
                    "장치 식별 정보·진단 자료를 첨부합니다."
                )
            elif kind == "inspection":
                step = f"조치: 하드웨어 점검을 요청하십시오({action}). {basis}입니다."
            elif kind == "procedure":
                step = (
                    f"조치: NVIDIA 카탈로그의 {action_name(action)} 절차를 따르십시오. "
                    "절차 원문은 참고 안내의 출처에 있습니다."
                )
            else:
                step = (
                    f"복구: {node} {action_name(action)}을 권고합니다. {basis}입니다."
                )
            if applicability == "applies" and model:
                if plan["source"] == "nvidia":
                    step += f" {model} 모델은 적용 대상({listed})입니다."
                elif excluded:
                    step += f" {model} 모델은 제외 대상({excluded})이 아닙니다."
            elif plan["source"] == "nvidia" and applicability in (None, "unlisted"):
                step += f" 적용 모델은 {listed}이며 이번 GPU 모델의 적용 여부를 먼저 확인하십시오."
            elif excluded and not model:
                step += f" {excluded}에는 적용하지 않습니다."
            if restart and (action == "RESTART_BM" or switch):
                step += " VM(패스스루) 환경이면 호스트 대신 해당 VM을 재시작합니다."
            if restart:
                step += " 로그 주입 시험이었다면 조치하지 않습니다."
            provider = (clues.get("provider_actions") or {}).get("value", {})
            suggested = provider.get("repair_actions") or []
            if suggested:
                joined = ", ".join(suggested)
                step += (
                    f" Fleet 원천 권고({joined})도 같은 조치입니다."
                    if any(same_action(action, s) for s in suggested)
                    else f" Fleet 원천 권고({joined})는 이 조치와 다르며 카탈로그 조치를 우선합니다."
                )
            steps.append(step)
            if restart or kind == "application":
                if switch:
                    check = (
                        f"조치 후 확인: 같은 NVSwitch({device})에서 SXID가 재발하지 않고 Fleet "
                        "SXID 상태가 Healthy로 돌아왔는지 확인합니다."
                    )
                elif restart:
                    check = (
                        f"조치 후 확인: 같은 GPU UUID({gpu})가 다시 인식되고 Fleet XID 상태가 "
                        "Healthy로 돌아왔는지 확인합니다."
                    )
                else:
                    check = (
                        "조치 후 확인: 애플리케이션 재시작 후 같은 GPU에서 같은 오류가 다시 "
                        "보고되는지 확인합니다."
                    )
                steps.append(check + " 수행한 조치와 확인 결과를 함께 기록합니다.")
            followup = plan.get("followup")
            if followup == "CONTACT_SUPPORT" and kind != "support":
                steps.append(
                    "재발 대응: 조치 후에도 같은 장치에서 재발하거나 회복되지 않으면 오류 원문·"
                    "장치 식별 정보·진단 자료·조치 이력을 첨부해 공급사 지원(CONTACT_SUPPORT)을 "
                    "요청하십시오."
                )
            elif followup == "HARDWARE_INSPECTION":
                steps.append(
                    f"재발 대응: 조치 후 같은 {short}에서 재발하면 하드웨어 점검·수리"
                    "(HARDWARE_INSPECTION)를 요청하십시오. 오류 원문·장치 식별 정보·진단 자료·"
                    "조치 이력을 첨부합니다."
                )
            elif (
                followup and followup not in (action, "IGNORE") and kind != "procedure"
            ):
                steps.append(
                    f"재발 대응: 반복되면 {action_name(followup)}로 이어갑니다."
                )
    if steps:
        out["action"].append(
            (
                "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
                + "\n이 시스템은 조치를 실행하지 않습니다. 수행 여부는 운영자가 결정합니다.",
                book_refs + incident_refs,
            )
        )

    # 추가 확인 사항: 수집 지표로 판정할 수 없는 것만 남긴다.
    acting = (
        kind in ("restart", "application", "inspection") and applicability != "excluded"
    )
    if acting and kind == "restart" and (action == "RESTART_BM" or switch):
        out["next"].append(
            (
                "운영 모드: bare-metal인지 VM(패스스루)인지는 수집 지표에 없습니다. "
                "VM이면 복구 조치가 VM 재시작으로 바뀝니다.",
                [],
            )
        )
    if plan and not model and (terms.get("excludes") or terms.get("applies")):
        out["next"].append(
            (
                "GPU 모델: 수집 지표에 모델 라벨이 없어 카탈로그 적용 여부를 판정하지 못했습니다."
                + (f" {excluded}이면 이 조치를 적용하지 않습니다." if excluded else ""),
                [],
            )
        )
    if acting:
        out["next"].append(
            (
                "시험 주입 여부: 오류 원문만으로는 로그 주입 시험과 실제 장애를 구분할 수 "
                "없습니다. 이 노드에서 오류 주입 시험을 했다면 위 조치를 하지 마십시오.",
                refs,
            )
        )
    if switch:
        out["next"].append(
            (
                "스위치 포트·연결 대상: source port, access/trunk 구분과 연결 GPU·VM·파티션은 "
                f"수집 원천(D09)에 없습니다. {node}의 Fabric Manager 로그에서 "
                f"{kst(findings['event_time'])} 전후 {device}의 포트 정보를 확인하십시오.",
                [],
            )
        )
    if any(
        "AER" in line
        for e in evidence
        if e.get("query_id") == "runbook" and e["id"] in book_refs
        for line in e.get("snapshot", {}).get("analysis_guidance", [])
    ):
        out["next"].append(
            (
                "커널 PCIe 오류(AER): 수집 원천(D09)에는 커널 로그가 없습니다. 원인을 좁히려면 "
                f"{node}의 커널 로그에서 {kst(findings['event_time'])} 전후 "
                f"{device}의 AER 기록을 확인하십시오.",
                [],
            )
        )
    if not switch and identity["status"] != "corroborated":
        out["next"].append(
            (
                "장치 연결: 다른 생산자의 PCI↔GPU UUID 매핑이 없어 오류 GPU를 교차 확인하지 "
                "못했습니다. 호스트의 GPU 목록에서 PCI 주소를 대조하십시오.",
                source_refs,
            )
        )

    # 이 오류에 대한 참고 안내: 발행 지침의 카탈로그 정보를 이번 장비에 맞춰 정리한다.
    if terms:
        if terms.get("fleet_event_type"):
            fleet_actions = terms.get("fleet_actions") or []
            out["guidance"].append(
                (
                    code
                    + (f" ({terms['fleet_name']})" if terms.get("fleet_name") else "")
                    + (f": {meaning}" if meaning else ".")
                    + f" Fleet 분류 {terms['fleet_event_type']}, 기본 조치 "
                    + (", ".join(action_name(a) for a in fleet_actions) or "없음")
                    + ".",
                    book_refs,
                )
            )
        if terms.get("gpud_event_type"):
            out["guidance"].append(
                (
                    f"GPUd 분류: {terms['gpud_event_type']}"
                    + (", 잠재적 Fatal." if terms.get("gpud_potential_fatal") else ".")
                    + (
                        f" 적용 제외 플랫폼: {excluded}." if excluded and switch else ""
                    ),
                    book_refs,
                )
            )
        if terms.get("immediate"):
            text = (
                f"NVIDIA 조치 분류: 즉시 조치 {action_name(terms['immediate'])}, "
                f"조사 조치 {action_name(terms['investigatory'])}. 적용 모델 {listed}"
                + (f"; 제외 {excluded}" if excluded else "")
                + "."
            )
            if model:
                text += f" 이번 GPU {model}: " + {
                    "applies": "적용 대상.",
                    "excluded": "제외 모델.",
                    "not_listed": "NVIDIA 카탈로그에 이 제품군 조치 없음(Fleet 기본 조치 적용).",
                    "unlisted": "표에 없는 제품(해당 세대 문헌 확인).",
                }.get(applicability, "적용 여부 미확인.")
            out["guidance"].append((text, book_refs))
        if terms.get("xid154_linkage") and terms.get("xid154_driver"):
            text = (
                "XID 154 연계: "
                + terms["xid154_linkage"].replace("; GPU driver ", "·드라이버 ")
                + " 이상 환경에서는 같은 장치의 복구 조치 안내(XID 154)가 함께 보고될 수 있습니다."
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
