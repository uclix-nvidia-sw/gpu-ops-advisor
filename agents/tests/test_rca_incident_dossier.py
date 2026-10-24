"""Synthetic RCA comparisons and complete workflow; no live service calls."""

from copy import deepcopy
import json

import pytest

from agent_common.contracts import content_hash, timestamp
from agent_common.observation import series
from rcca_agent.incident_dossier import (
    ERROR_FILTER,
    current_data,
    dossier_summary,
    log_records,
    operator_view,
    same_device,
)
from rcca_agent.synthesis_context import bounded_context, encoded_size
from rca_replay import replay
from rca_replay_cases import ROOT
from test_fleet_rca import match_case


def dossier_case(kind):
    case = match_case(kind=kind)
    book = case["attempt"]["context"]["runbooks"][0]
    book["content"] = json.loads(
        (ROOT / f"rcca-agent/runbooks/{kind}/{book['knowledge_key']}.json").read_text(
            "utf-8"
        )
    )["content"]
    book["content_hash"] = book["reviewed_content_hash"] = content_hash(book["content"])
    profile = case["attempt"]["profile"]
    for query in sorted({s["query_id"] for s in book["content"]["observation_plan"]}):
        if query not in profile["queries"]:
            profile["queries"][query] = deepcopy(profile["queries"]["D44"])
            profile["queries"][query]["metric"] = "fixture_" + query
    data = case["attempt"]["claim"]["input"]
    data["log_query_target"] = {"node": "node-1", "machine_id": "machine-1"}
    period = current_data(data, case["attempt"]["context"]["data_cutoff_at"])[
        "time_range"
    ]
    query = case["queries"][0]
    query["arguments"].update(
        logql='{} | drop dsx_json_0, dsx_json_0_extracted | json dsx_json_0="resources[\\"k8s.node.name\\"]" | __error__="" | (dsx_json_0="node-1" or dsx_json_0_extracted="node-1")'
        + ERROR_FILTER,
        startRfc3339=period["start"],
        endRfc3339=period["end"],
    )
    return case


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_workflow_collects_metrics_despite_matching_alert_and_no_model_budget(
    kind,
):
    case = dossier_case(kind)
    case["token_budget"] = 0
    result = await replay(case)
    assert not result["missing_inputs"]
    assert "decision_policy" not in case["attempt"]["context"]["runbooks"][0]["content"]
    calls = result["query_calls"]
    logs = [c for c in calls if c["tool"] == "query_loki_logs"]
    assert len(logs) == 1
    assert any(c["matched"] for c in logs), logs
    expected = case["attempt"]["context"]["runbooks"][0]["content"]["required_queries"]
    evidence = result["output"]["evidence"]
    assert set(expected) <= {e["query_id"] for e in evidence}
    source = result["output"]["result"]["quality"]["report"]["source_items"]
    assert any("이번 조회 범위" in s["text"] for s in source)
    assert any("원문 발췌" in s["text"] for s in source)
    assert len(calls) <= case["attempt"]["profile"]["limits"]["max_queries"]
    assert not series([e for e in evidence if e["quality"].get("comparison_role")])


def records_fixture(kind="xid"):
    case = dossier_case(kind)
    query = case["queries"][0]
    data = deepcopy(case["attempt"]["claim"]["input"])
    data["time_range"] = {
        "start": query["arguments"]["startRfc3339"],
        "end": query["arguments"]["endRfc3339"],
    }
    e = dict(
        id="logs",
        query_id="D09",
        cluster_id="c",
        time_range=data["time_range"],
        quality={"complete": True},
        tool_status="ok",
        snapshot=query["response"],
    )
    return data, e


def test_repeated_reports_preserve_raw_and_do_not_count_failures_or_reboots():
    data, e = records_fixture()
    values = e["snapshot"]["data"]["result"][0]["values"]
    repeated = deepcopy(values[-1])
    repeated[0] = str(int(repeated[0]) + 10**9)
    values.append(repeated)
    before = deepcopy(e)
    rows = log_records([e], data)
    assert len(rows) == 3
    text = str(dossier_summary(data, [e], {}))
    assert "보고 2건 수신" in text and "별개 신규 장애 횟수로 세지 않습니다" in text
    assert e == before
    other = deepcopy(rows[0])
    other["gpu"] = "replacement-gpu"
    assert not same_device(rows[0], other)
    other = deepcopy(rows[0])
    other["machine"] = "other-machine"
    assert not same_device(rows[0], other)


@pytest.mark.parametrize("change", ["node", "time", "component", "incomplete"])
def test_invalid_scope_and_incomplete_sources_cannot_support_history(change):
    data, e = records_fixture()
    if change == "node":
        data["target"]["node"] = "other"
    elif change == "time":
        e["time_range"] = {
            "start": "2020-01-01T00:00:00Z",
            "end": "2020-01-01T00:30:00Z",
        }
    elif change == "component":
        e["snapshot"] = json.loads(
            json.dumps(e["snapshot"]).replace(
                "accelerator-nvidia-error-xid", "unknown-producer"
            )
        )
    else:
        e["quality"]["complete"] = False
        e["tool_status"] = "partial"
    assert log_records([e], data) == []


def test_sxid_identity_preserves_switch_function_without_gpu_mapping():
    data, e = records_fixture("sxid")
    row = log_records([e], data)[0]
    assert row["gpu"] is None
    other = {**row, "device": row["device"][:-1] + "1"}
    assert not same_device(row, other)


def test_large_comparison_is_bounded_only_in_model_view():
    payload = {
        "incident_comparison": [
            {"text": "보고 내용 " * 300, "evidence_refs": [f"e{i}"]} for i in range(100)
        ]
    }
    view = bounded_context(payload, 8000)
    assert encoded_size(view) <= 8000
    assert view["context_selection"]["omitted_observations"]["incident_comparison"] > 0
    assert len(payload["incident_comparison"]) == 100


def test_metric_comparison_keeps_scope_gaps_and_counter_semantics():
    data, logs = records_fixture()
    target = log_records([logs], data)[0]
    at = timestamp(data["time_range"]["end"]) - 100
    metric = dict(
        id="replay",
        query_id="D44",
        cluster_id="c",
        time_range=data["time_range"],
        tool_status="ok",
        quality={"complete": True, "original_samples": True, "unit": "count"},
        snapshot={
            "data": {
                "result": [
                    {
                        "metric": {"node": "node-1", "uuid": target["gpu"]},
                        "values": [[at, "2"], [at + 60, "4"], [at + 65, "NaN"]],
                    }
                ]
            }
        },
    )
    data["target"]["machine_id"] = target["machine"]
    comparison = {"targets": [target]}
    view = operator_view(data, [logs, metric], comparison)
    assert view["metrics"][0]["max"] == 4
    text = str(dossier_summary(data, [logs, metric], comparison))
    assert "최소 2, 최대 4 count" in text
    assert "최대 간격 60초" in text
    assert "사건 증가량이나 AER로 해석하지 않습니다" in text
    metric["snapshot"]["data"]["result"][0]["metric"]["node"] = "other-node"
    text = str(dossier_summary(data, [logs, metric], comparison))
    assert "최소 2" not in text
    assert "측정 기록을 확보하지 못했습니다" in text


@pytest.mark.parametrize("kind", ["xid", "sxid"])
@pytest.mark.parametrize("failure", [None, "length"])
async def test_single_collection_has_author_and_writer_without_critic(
    kind, failure, monkeypatch
):
    from rca_replay_cases import reply
    from rcca_agent import evaluation, workflow

    def obsolete(*args, **kwargs):
        raise AssertionError(
            "single-collection RCA invoked an obsolete evaluation stage"
        )

    for name in (
        "assess_policies",
        "finish_assessment",
        "model_assessment",
        "rule_followup",
        "choose_followup",
    ):
        monkeypatch.setattr(workflow, name, obsolete, raising=False)
    for name in ("review_analysis", "reserve_review_budget", "interpret_evidence"):
        monkeypatch.setattr(evaluation, name, obsolete, raising=False)

    case = dossier_case(kind)
    case["token_budget"] = 131072
    case["empty_unscripted_queries"] = True
    case["attempt"]["profile"].setdefault("rca", {})["generation_mode"] = "separate"
    author = {
        "interpretation": {
            "findings": [
                {
                    "id": "observed-report",
                    "statement": "노드에서 오류가 보고되었습니다.",
                    "kind": "observed",
                    "evidence_refs": {"$input": "/observation_refs"},
                }
            ],
            "unknowns": [],
            "conflicts": [],
            "limitations": [],
        },
        "hypotheses": [],
        "limitations": [],
    }
    response = reply(author)
    if failure:
        response["finish_reason"] = failure
    case["responses"]["synthesis"] = [response]
    case["responses"].pop("analysis_review", None)
    result = await replay(case)
    output = result["output"]
    assert not result["missing_inputs"]
    stages = [call["stage"] for call in result["model_calls"]]
    assert stages == ["synthesis", "report_writing"]
    assert not any(
        e["query_id"]
        in {
            "analysis_review",
            "evidence_evaluation",
            "investigation_plan_extension",
            "investigation_decision",
        }
        for e in output["evidence"]
    )
    analysis = output["result"]["quality"]["analysis"]
    assert analysis["workflow"] == "single_collection"
    assert "sufficiency" not in analysis and "evidence_evaluation" not in analysis
    assert analysis["followups"] == 0
    assert "review_feedback" not in result["model_calls"][0]["input"]
    assert "decision_assessment" not in result["model_calls"][0]["input"]
    review = output["result"]["quality"]["rca_evaluation"]["review"]
    assert review["reason"] == "not_requested"
    assert review["verdict"] is None and review["evidence_refs"] == []
    author_record = next(
        e for e in output["evidence"] if e["query_id"] == "rca_synthesis"
    )
    assert "budget_allocation" not in author_record["snapshot"]["diagnostics"]
    assert author_record["snapshot"]["status"] == ("failed" if failure else "complete")
    assert "review" not in result["model_calls"][-1]["input"]
    narrative = str(output["result"]["narrative"])
    assert "분석 품질 검토" not in narrative
    assert "조사 종료 이유" not in narrative
    assert "독립 품질 검토" not in narrative


@pytest.mark.parametrize("kind", ["xid", "sxid"])
async def test_single_collection_conflicting_target_does_not_reenter_legacy_review(
    kind,
):
    case = dossier_case(kind)
    case["token_budget"] = 0
    case["attempt"]["claim"]["input"]["target"].update(
        node="node-1", k8s_node_name="different-node"
    )
    result = await replay(case)
    assert result["query_calls"] == []
    evidence = result["output"]["evidence"]
    assert not any(
        e["query_id"] in {"analysis_review", "evidence_evaluation"} for e in evidence
    )
    output = result["output"]["result"]
    assert output["quality"]["analysis"]["workflow"] == "single_collection"
    assert "target_identity_conflict" in output["missing_inputs"]
    assert output["quality"]["rca_evaluation"]["review"]["reason"] == "not_requested"


def test_incident_brief_preserves_full_series_units_windows_and_priority():
    from rcca_agent.incident_dossier import incident_brief

    data, logs = records_fixture()
    target = log_records([logs], data)[0]
    boundary = timestamp(data["incident_time"])
    data["time_range"] = {
        "start": "2026-09-14T23:30:00Z",
        "end": "2026-09-15T00:30:00Z",
    }
    evidence = [logs]
    for query, unit, values in [
        ("D02", "percent", [10, 100, 0]),
        ("D11", "watts", [88.32, 314.024, 88.32]),
        ("D44", "count", [0, 0, 0]),
    ]:
        evidence.append(
            {
                "id": query,
                "query_id": query,
                "cluster_id": "c",
                "time_range": data["time_range"],
                "tool_status": "ok",
                "quality": {"complete": True, "original_samples": True, "unit": unit},
                "snapshot": {
                    "data": {
                        "result": [
                            {
                                "metric": {"node": "node-1", "uuid": target["gpu"]},
                                "values": [
                                    [boundary - 60, str(values[0])],
                                    [boundary, str(values[1])],
                                    [boundary + 60, str(values[2])],
                                ],
                            }
                        ]
                    }
                },
            }
        )
    original = deepcopy(evidence)
    brief = incident_brief(data, evidence, {"targets": [target]}, None)
    metrics = {r["query_id"]: r for r in brief if r["type"] == "metric_comparison"}
    assert set(metrics) == {"D02", "D11", "D44"}
    assert metrics["D11"]["max"] == 314.024
    assert metrics["D11"]["unit"] == "watts"
    assert metrics["D02"]["incident_windows"]["before"]["samples"] == 2
    assert metrics["D02"]["incident_windows"]["at_or_after"]["max"] == 0
    assert metrics["D44"]["kind"] == "counter"
    payload = {
        "incident_brief": brief,
        "raw_excerpts": [{"text": "raw " * 10000, "evidence_refs": ["logs"]}],
    }
    view = bounded_context(payload, 6000)
    assert len(view["incident_brief"]) == len(brief)
    assert not view["raw_excerpts"]
    assert evidence == original


def test_brief_history_excludes_current_and_keeps_host_device_scope():
    from rcca_agent.incident_dossier import incident_brief

    data, logs = records_fixture()
    history = {
        "period": data["time_range"],
        "complete": False,
        "evidence_refs": ["history"],
        "rows": [
            {
                "current": True,
                "codes": ["xid:79"],
                "gpu_uuid": "GPU-A",
                "occurred_at": data["incident_time"],
            },
            {
                "current": False,
                "codes": ["xid:79"],
                "gpu_uuid": "GPU-B",
                "occurred_at": data["incident_time"],
            },
        ],
    }
    row = next(
        r
        for r in incident_brief(data, [logs], {}, history)
        if r["type"] == "host_history"
    )
    assert row["previous_incidents"] == 1 and row["current_excluded"]
    assert row["device_counts"] == {"GPU-B": 1}
    assert row["complete"] is False


def test_enum_brief_keeps_gpu_scope_and_no_health_mapping():
    from rcca_agent.incident_dossier import incident_brief

    data, logs = records_fixture("sxid")
    target = log_records([logs], data)[0]
    at = timestamp(data["time_range"]["end"]) - 10
    metric = {
        "id": "fm",
        "query_id": "D47",
        "cluster_id": "c",
        "time_range": data["time_range"],
        "tool_status": "ok",
        "quality": {"complete": True, "original_samples": True, "unit": "enum"},
        "snapshot": {
            "data": {
                "result": [
                    {
                        "metric": {"node": "node-1", "uuid": "GPU-A"},
                        "values": [[at, "0"]],
                    }
                ]
            }
        },
    }
    row = next(
        r
        for r in incident_brief(data, [logs, metric], {"targets": [target]}, None)
        if r["type"] == "metric_comparison"
    )
    assert row["scope"] == "node_gpu_context"
    assert row["gpu_uuids"] == ["GPU-A"] and row["kind"] == "enum"
    assert row["enum_mapping"] is None
    assert row["last_value"] == 0
    assert "no health" in row["interpretation_limits"]


def test_gpu_series_split_by_workload_labels_become_one_metric_with_workloads():
    data, logs = records_fixture()
    target = log_records([logs], data)[0]
    end = timestamp(data["time_range"]["end"])
    base = {"node": "node-1", "uuid": target["gpu"], "modelName": "NVIDIA A100"}
    metric = dict(
        id="util",
        query_id="D02",
        cluster_id="c",
        time_range=data["time_range"],
        tool_status="ok",
        quality={"complete": True, "original_samples": True, "unit": "percent"},
        snapshot={
            "data": {
                "result": [
                    {"metric": base, "values": [[end - 600, "0"]]},
                    {
                        "metric": {**base, "namespace": "ns", "pod": "worker-a"},
                        "values": [[end - 300, "100"], [end - 240, "90"]],
                    },
                    {
                        "metric": {**base, "namespace": "ns", "pod": "worker-b"},
                        "values": [[end - 120, "0"]],
                    },
                    # The same pod also holds another GPU of the node.
                    {
                        "metric": {
                            **base,
                            "uuid": "GPU-OTHER",
                            "gpu": "1",
                            "namespace": "ns",
                            "pod": "worker-a",
                        },
                        "values": [[end - 300, "100"]],
                    },
                ]
            }
        },
    )
    data["target"]["machine_id"] = target["machine"]
    health = [
        dict(
            component="accelerator-nvidia-error-xid",
            target={"node": "node-1"},
            raw_health=state,
            error_code=code,
            observed_at=at,
            evidence_refs=[state],
        )
        for state, code, at in (
            ("Healthy", None, "2026-01-01T00:00:00Z"),
            ("Unhealthy", target["code"], "2026-01-01T00:01:00Z"),
        )
    ]
    view = operator_view(data, [logs, metric], {"targets": [target]}, health)
    assert [m["query_id"] for m in view["metrics"]] == ["D02"]
    assert view["metrics"][0]["gpu_uuid"] == target["gpu"]
    assert view["metrics"][0]["samples"] == 4 and view["metrics"][0]["max"] == 100
    assert [(w["gpu_uuid"], w["pod"]) for w in view["workloads"]] == [
        (target["gpu"], "worker-a"),
        ("GPU-OTHER", "worker-a"),
        (target["gpu"], "worker-b"),
    ]
    gpus = {g["gpu_uuid"]: g for g in view["gpus"]}
    assert gpus[target["gpu"]] == {"gpu_uuid": target["gpu"], "model": "NVIDIA A100"}
    assert gpus["GPU-OTHER"]["gpu_index"] == "1"
    assert view["workload_label_source"] == "dcgm_exporter_labels"
    # Fleet exporter series: model under another label name and no pod mapping at all.
    fleet = dict(metric, id="nvlink", query_id="D33")
    fleet["snapshot"] = {
        "data": {
            "result": [
                {
                    "metric": {
                        "node": "node-1",
                        "uuid": target["gpu"],
                        "model_name": "H100",
                    },
                    "values": [[end - 300, "1"]],
                }
            ]
        }
    }
    other = operator_view(data, [logs, fleet], {"targets": [target]}, health)
    assert other["gpus"] == [{"gpu_uuid": target["gpu"], "model": "H100"}]
    assert other["workloads"] == [] and other["workload_label_source"] is None
    assert view["onset"]["last_healthy_at"] == "2026-01-01T00:00:00Z"
    assert view["onset"]["first_unhealthy_at"] == "2026-01-01T00:01:00Z"


async def test_transient_gateway_error_is_retried_once_and_recorded():
    from rcca_agent.evidence_interpretation import complete_once

    class Model:
        deadline = float("inf")

        def __init__(self, statuses):
            self.statuses = list(statuses)

        async def complete(self, prompt, payload, stage):
            status = self.statuses.pop(0)
            self.last_http_status = status
            self.last_failure = "llm_http_error" if status else None
            return None if status else {"ok": True}

    for status in (500, 503):
        diagnostics = {}
        assert await complete_once(
            Model([status, None]), "p", {}, "s", diagnostics
        ) == {"ok": True}
        assert diagnostics == {"transient_retry_status": status}
    diagnostics = {}
    model = Model([400])
    assert await complete_once(model, "p", {}, "s", diagnostics) is None
    assert diagnostics == {"http_status": 400} and model.statuses == []


async def test_gateway_rejection_is_retried_once_with_a_lower_output_cap():
    from rcca_agent.evidence_interpretation import complete_once

    class Model:
        deadline = float("inf")

        def __init__(self, statuses):
            self.statuses, self.caps = list(statuses), []

        def request_budget(self, prompt, payload, stage):
            return {"configured_output_tokens": 65536}

        async def complete(self, prompt, payload, stage, max_tokens=None):
            self.caps.append(max_tokens)
            status = self.statuses.pop(0)
            self.last_http_status = status
            self.last_failure = "llm_http_error" if status else None
            self.last_error_type = "BadRequestError:output_tokens" if status else None
            return None if status else {"ok": True}

    model, diagnostics = Model([400, None]), {}
    assert await complete_once(model, "p", {}, "s", diagnostics) == {"ok": True}
    assert model.caps == [None, 16384]
    assert diagnostics == {
        "reduced_output_retry": {
            "after_status": 400,
            "after_error_type": "BadRequestError:output_tokens",
            "max_tokens": 16384,
            "succeeded": True,
        }
    }
    # A 500 is retried as transient first, then once with the lower cap.
    model, diagnostics = Model([500, 500, 500]), {}
    assert await complete_once(model, "p", {}, "s", diagnostics) is None
    assert model.caps == [None, None, 16384]
    assert diagnostics["http_status"] == 500
    assert diagnostics["error_type"] == "BadRequestError:output_tokens"


def test_error_type_keeps_class_and_limit_hint_only():
    from agent_common.llm import error_type

    class Response:
        def __init__(self, body):
            self.body = body

        def json(self):
            if self.body is None:
                raise ValueError
            return self.body

    secret = "prompt text sk-secret"
    body = {
        "error": {
            "message": f"litellm.BadRequestError: max_tokens is too large {secret}",
            "type": "invalid_request_error",
        }
    }
    assert (
        error_type(Response(body))
        == "BadRequestError:invalid_request_error:output_tokens"
    )
    assert secret not in (error_type(Response(body)) or "")
    assert error_type(Response(None)) is None
    assert error_type(Response({"error": "plain"})) is None


async def test_numeric_findings_get_one_repair_request_in_combined_author():
    from rca_replay_cases import reply

    def author(statement):
        return reply(
            {
                "interpretation": {
                    "findings": [
                        {
                            "id": "observed-report",
                            "statement": statement,
                            "kind": "observed",
                            "evidence_refs": {"$input": "/observation_refs"},
                        }
                    ],
                    "unknowns": [],
                    "conflicts": [],
                    "limitations": [],
                },
                "hypotheses": [],
                "limitations": [],
            }
        )

    case = dossier_case("xid")
    case["token_budget"] = 131072
    case["empty_unscripted_queries"] = True
    case["attempt"]["profile"].setdefault("rca", {})["generation_mode"] = "combined"
    case["responses"]["synthesis"] = [
        author("같은 GPU에서 사건이 34건 반복됐습니다."),
        author("노드에서 오류가 보고되었습니다."),
    ]
    case["responses"].pop("analysis_review", None)
    result = await replay(case)
    record = next(
        e["snapshot"]
        for e in result["output"]["evidence"]
        if e["query_id"] == "rca_synthesis"
    )
    assert record["diagnostics"]["numeric_repair"] == "applied"
    assert record["diagnostics"]["adoption"] == "validated_response"
    assert [c["stage"] for c in result["model_calls"]][:2] == ["synthesis"] * 2


def test_component_alert_metrics_are_split_at_the_first_unhealthy_report():
    from rcca_agent.incident_dossier import component_metrics, component_view

    def evidence(query, labels, points, unit="count"):
        return {
            "id": "ev-" + query,
            "query_id": query,
            "cluster_id": "cpc-1",
            "tool_status": "ok",
            "quality": {"complete": True, "original_samples": True, "unit": unit},
            "snapshot": {"data": {"result": [{"metric": labels, "values": points}]}},
        }

    data = {
        "scope": {"clusters": [{"cluster_id": "cpc-1"}]},
        "target": {"node": "dgx01"},
        "time_range": {"start": "2026-10-23T08:00:00Z", "end": "2026-10-23T08:30:00Z"},
        "incident_time": "2026-10-23T08:19:00Z",
    }
    gpu = {"uuid": "GPU-1", "node": "dgx01", "gpu": "0", "model_name": "A100"}
    t0 = 1792742400  # 2026-10-23T08:00:00Z
    rows = [
        evidence("D50", gpu, [[t0 + 60, "0"], [t0 + 1500, "1"]], "enum"),
        evidence(
            "D59",
            {"node": "dgx01", "mount_point": "/"},
            [[t0 + 60, "100"], [t0 + 1500, "120"]],
            "bytes",
        ),
        evidence("D50", {**gpu, "node": "dgx02"}, [[t0 + 60, "1"]], "enum"),
    ]
    health = [
        {
            "component": "disk",
            "raw_health": "Healthy",
            "observed_at": "2026-10-23T08:17:00Z",
            "target": {"node": "dgx01"},
        },
        {
            "component": "disk",
            "raw_health": "Unhealthy",
            "observed_at": "2026-10-23T08:18:00Z",
            "target": {"node": "dgx01"},
        },
    ]
    view = component_view(data, rows, health, "disk")
    assert view["event_boundary"] == "2026-10-23T08:18:00Z"
    assert view["boundary_basis"] == "loki_recorded_at"
    by_name = {m["name"]: m for m in view["metrics"]}
    # Other nodes' series never enter; disk rows are named by mount.
    assert set(by_name) == {"행 재매핑 대기", "디스크 사용량 (/)"}
    pending = by_name["행 재매핑 대기"]
    assert pending["kind"] == "enum"
    assert pending["incident_windows"]["before"]["last_value"] == 0
    assert pending["incident_windows"]["at_or_after"]["last_value"] == 1
    assert by_name["디스크 사용량 (/)"]["mount_point"] == "/"
    assert view["gpus"] == [{"gpu_uuid": "GPU-1", "model": "A100", "gpu_index": "0"}]
    # Without an Unhealthy report the alert time splits the windows.
    assert component_view(data, rows, [], "disk")["boundary_basis"] == "alert_time"
    plan = [{"query_id": "D09"}, {"query_id": "D59"}]
    assert component_metrics(
        [{"knowledge_key": "RB-COMPONENT-DISK", "content": {"observation_plan": plan}}]
    )
    assert not component_metrics(
        [{"knowledge_key": "RB-XID-79", "content": {"observation_plan": plan}}]
    )
    # Selection keeps the general Runbook only when nothing dedicated applies.
    assert component_metrics(
        [
            {
                "knowledge_key": "RB-GENERAL-GPU-NODE",
                "general_investigation": True,
                "content": {"observation_plan": plan},
            }
        ]
    )


def test_host_rows_are_named_by_interface_and_load_window():
    from rcca_agent.incident_dossier import component_view

    t0 = 1792742400  # 2026-10-23T08:00:00Z

    def evidence(query, labels, points, unit, target_labels=None):
        quality = {"complete": True, "original_samples": True, "unit": unit}
        if target_labels:
            quality.update(
                binding_id="fleet_intelligence." + query, target_labels=target_labels
            )
        return {
            "id": "ev-" + query,
            "query_id": query,
            "cluster_id": "cpc-1",
            "tool_status": "ok",
            "quality": quality,
            "snapshot": {"data": {"result": [{"metric": labels, "values": points}]}},
        }

    data = {
        "scope": {"clusters": [{"cluster_id": "cpc-1"}]},
        "target": {"node": "dgx01"},
        "time_range": {"start": "2026-10-23T08:00:00Z", "end": "2026-10-23T08:30:00Z"},
        "incident_time": "2026-10-23T08:19:00Z",
    }
    eth = {"node": "dgx01", "interface": "eth0"}
    rows = [
        evidence("D65", eth, [[t0 + 60, "1"], [t0 + 1500, "0"]], "enum"),
        evidence("D66", eth, [[t0 + 60, "5"], [t0 + 1500, "9"]], "packets"),
        evidence(
            "D19",
            {"node": "dgx01", "load_duration": "1m0s"},
            [[t0 + 60, "2.5"]],
            "load",
            {"node": "node", "window": "load_duration"},
        ),
        evidence("D63", {"node": "dgx01"}, [[t0 + 60, "40"]], "percent"),
    ]
    by_name = {m["name"]: m for m in component_view(data, rows, [], "cpu")["metrics"]}
    assert set(by_name) == {
        "이더넷 링크 상태 (eth0)",
        "이더넷 수신 오류 누적값 (eth0)",
        "CPU 평균 부하 (1분)",
        "메모리 사용률",
    }
    assert by_name["이더넷 링크 상태 (eth0)"]["kind"] == "enum"
    assert by_name["이더넷 링크 상태 (eth0)"]["interface"] == "eth0"
    assert by_name["이더넷 수신 오류 누적값 (eth0)"]["kind"] == "counter"
    assert by_name["CPU 평균 부하 (1분)"]["window"] == "1m0s"
    assert by_name["메모리 사용률"]["kind"] == "gauge"
