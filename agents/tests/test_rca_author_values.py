"""10-26 SXID 11001 report: history counts and report times had no value token, so every
finding was dropped by the numeric rule. These rows now carry code-owned tokens."""

import json

from rcca_agent.analysis_values import register_values
from rcca_agent.combined_synthesis import validate_author
from rcca_agent.synthesis import validate_synthesis
from rcca_agent.synthesis_context import bounded_context

LOGS = {
    "type": "log_report_group",
    "code": "xid:79",
    "device": "PCI:0000:07:00",
    "message": "XID 79 GPU has fallen off the bus",
    "first": "2026-10-26T01:41:25.871771Z",
    "last": "2026-10-26T02:07:25.877682Z",
    "reports": 27,
    "event_times": ["2026-10-26T01:41:11Z"],
    "count_basis": "reports_not_incidents",
    "evidence_refs": ["log-ref"],
}
HISTORY = {
    "type": "host_history",
    "code": "sxid:11001",
    "period": {
        "start": "2026-10-12T02:07:48.242000+00:00",
        "end": "2026-10-26T02:07:48.242000+00:00",
    },
    "complete": True,
    "previous_incidents": 33,
    "current_excluded": True,
    "count_basis": "incident_id",
    "device_counts": {
        "NVSwitch PCI:0000:c4:00.0": 10,
        "NVSwitch PCI:0000:00:00.0": 9,
        "NVSwitch PCI:0000:c8:00.0": 2,
    },
    "latest_previous": "2026-10-23T06:15:10+00:00",
    "evidence_refs": ["history-ref"],
}


def view():
    brief = register_values([dict(LOGS), dict(HISTORY)])
    payload = {
        "incident_brief": brief,
        "device_observations": [],
        "error_events": [],
        "query_quality": [],
    }
    return brief, bounded_context(payload, 24000)


def response(findings, limitations=()):
    return {
        "interpretation": {
            "findings": findings,
            "unknowns": [],
            "conflicts": [],
            "limitations": [],
        },
        "hypotheses": [],
        "limitations": list(limitations),
    }


def test_history_and_report_rows_get_code_owned_text():
    brief, _ = view()
    logs, history = brief
    assert logs["value_text"] == (
        "XID 79 보고 27건 (PCI:0000:07:00, 기록 2026-10-26 10:41:25.871771 KST ~ "
        "2026-10-26 11:07:25.877682 KST, 커널 이벤트 시각 2026-10-26 10:41:11 KST, "
        "보고 수이며 사건 수가 아님)"
    )
    assert history["value_text"].startswith(
        "같은 호스트 이력(2026-10-12 11:07:48.242 KST ~ 2026-10-26 11:07:48.242 KST, "
        "이번 사건 제외): SXID 11001 이전 사건 33건, 마지막 2026-10-23 15:15:10 KST"
    )
    # Most frequent device first, so the operator sees where it repeats.
    assert (
        "장치별 NVSwitch PCI:0000:c4:00.0 10건, NVSwitch PCI:0000:00:00.0 9건"
        in (history["value_text"])
    )


def test_history_finding_survives_through_token_and_digits_are_still_dropped():
    brief, bounded = view()
    history = brief[1]
    findings = [
        {
            "id": "finding-1",
            "statement": history["value_token"]
            + "입니다. 여러 스위치에서 반복됐으므로 이 스위치 하나보다 패브릭 전체를 먼저 점검할 근거가 됩니다.",
            "kind": "observed",
            "evidence_refs": history["evidence_refs"],
        },
        {
            "id": "finding-2",
            "statement": "같은 호스트에서 이전 사건이 33건 있었습니다.",
            "kind": "observed",
            "evidence_refs": history["evidence_refs"],
        },
    ]
    dropped = []
    interpretation, _, _, errors = validate_author(
        response(findings), bounded, None, dropped=dropped
    )
    assert not errors
    assert [f["id"] for f in interpretation["findings"]] == ["finding-1"]
    assert history["value_text"] in interpretation["findings"][0]["statement"]
    [drop] = dropped
    assert drop["rule"] == "numeric"
    # Where the number was, never the rejected sentence itself.
    assert drop["numeric_diagnostic"]["matches"][0]["kind"] == "digits"
    assert "33건" not in json.dumps(drop, ensure_ascii=False)


def test_object_shaped_top_level_limitation_keeps_its_statement():
    brief, bounded = view()
    finding = {
        "id": "finding-1",
        "statement": brief[0]["value_token"]
        + "입니다. 같은 노드의 다른 오류와 함께 확인해야 합니다.",
        "kind": "observed",
        "evidence_refs": brief[0]["evidence_refs"],
    }
    limitation = {
        "statement": "스위치 포트 상태는 수집되지 않았습니다.",
        "evidence_refs": [],
    }
    dropped = []
    _, _, limitations, errors = validate_author(
        response([finding], [limitation]), bounded, None, dropped=dropped
    )
    assert not errors
    assert limitations == ["스위치 포트 상태는 수집되지 않았습니다."]
    assert dropped == [
        {
            "code": "limitation_object",
            "path": "$.limitations[0]",
            "rule": "shape",
            "action": "normalized",
        }
    ]


def test_domain_terms_from_inputs_are_korean_prose():
    text = "Fleet가 Healthy에서 Unhealthy로 바뀐 XID 보고는 KST 기준 시각으로 정렬했습니다."
    assert validate_synthesis({"hypotheses": [], "limitations": [text]}, []) == []
