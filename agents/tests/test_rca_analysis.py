from evaluation_fixtures import interpretation_reply, review_reply
import copy
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from agent_common.contracts import content_hash, validate_result
from agent_common.llm import RemoteUncertain
from agent_common.runtime import attempt_context
from rcca_agent import workflow
from rcca_agent.synthesis import validate_synthesis
from rcca_agent.workflow import run
from rcca_agent.incident import alert_clues


def analysis_reply(refs):
    return {
        "hypotheses": [
            {
                "claim": "관측한 장비 증상은 추가 확인이 필요합니다.",
                "supporting_refs": refs,
                "contradicting_refs": [],
                "missing_inputs": ["producer_confirmation"],
            }
        ],
        "limitations": [],
    }


def test_model_cannot_promote_causality_or_reference_unknown_evidence():
    reply = analysis_reply(["e1"])
    assert validate_synthesis(reply, ["e1"])[0]["causal_status"] == "candidate"
    for edit in (
        {"supporting_refs": ["invented"]},
        {"supporting_refs": []},
        {"causal_status": "confirmed"},
        {"claim": "Invented GPU temperature is 999 degrees."},
        {"contradicting_refs": ["e1"]},
    ):
        invalid = copy.deepcopy(reply)
        invalid["hypotheses"][0].update(edit)
        with pytest.raises(ValueError):
            validate_synthesis(invalid, ["e1"])
    reply["next_query_id"] = "arbitrary-query"
    with pytest.raises(ValueError):
        validate_synthesis(reply, ["e1"])


def general_runbook(cluster="c"):
    # Use shipped content, binding it only to the isolated fixture cluster.
    row = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "rcca-agent/runbooks/RB-GENERAL-GPU-NODE.json"
        ).read_text(encoding="utf-8")
    )
    content = row["content"]
    return dict(
        id=str(uuid4()),
        knowledge_id=str(uuid4()),
        knowledge_key="RB-GENERAL-GPU-NODE",
        revision=1,
        content=content,
        compatibility={"cluster_id": cluster},
        content_hash=content_hash(content),
        reviewed_content_hash=content_hash(content),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "fast",
        "followup",
        "review_followup",
        "unconfigured",
        "invalid",
        "uncertain",
        "missing_runbook",
        "query_failed",
        "invalid_plan",
        "xid",
        "sxid",
        "unsafe_general",
        "budget_followup",
        "accepted_rule_followup",
    ],
)
async def test_query_first_collection_analysis_and_failure_boundaries(
    mode, monkeypatch
):
    period = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T01:00:00Z"}
    data = dict(
        incident_id=str(uuid4()),
        evidence_version=1,
        incident_time=period["start"],
        scope={"clusters": [{"cluster_id": "c", "namespaces": None}]},
        target={"gpu_uuid": "GPU-1"},
        time_range=period,
        purpose_ids=["R01"],
        incident_snapshot={"evidence": {}},
    )
    profile = json.loads(
        (
            Path(__file__).resolve().parents[2] / "agents/tests/fixtures/config-v7.json"
        ).read_text()
    )
    profile["clusters"] = {
        "c": {
            "loki_uid": "logs",
            "loki_selector": {},
            "mimir_uid": "metrics",
            "metric_selector": {},
        }
    }
    profile["health_contracts"] = {
        "fixture": {
            "producer_contract": "fixture",
            "revision": "v1",
            "checks": {"valid": "valid"},
            "health": {
                "Degraded": {"normalized_health": "degraded", "severity": "warning"}
            },
        }
    }
    events = []
    if mode == "budget_followup":
        evaluate = workflow.evaluate_analysis

        async def exhausted_review(*args, **kwargs):
            result = await evaluate(*args, **kwargs)
            result["stop_reason"] = "llm_budget_exhausted"
            return result

        monkeypatch.setattr(workflow, "evaluate_analysis", exhausted_review)

    async def logs(args):
        events.append("collect")
        if mode == "query_failed" and len(events) == 1:
            raise OSError("fixture failure")
        return {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1",
                                json.dumps(
                                    {
                                        "producer_contract": "fixture",
                                        "health": "Degraded",
                                        "check_status": "valid",
                                        "target": data["target"],
                                        "component": "gpu",
                                        "observed_at": period["start"],
                                    }
                                ),
                            ]
                        ],
                    }
                ]
            }
        }

    async def metrics(args):
        events.append("collect")
        return {
            "data": {
                "result": [{"metric": {"UUID": "GPU-1"}, "values": [[1789430400, "2"]]}]
            }
        }

    class LLM:
        configured = mode != "unconfigured"
        usage = {}

        async def complete(self, system, payload, **kwargs):
            if mode == "uncertain":
                raise RemoteUncertain("fixture")
            if kwargs.get("stage") == "evidence_interpretation":
                events.append("interpret")
                return interpretation_reply()
            if kwargs.get("stage") == "analysis_review":
                events.append("review")
                reply = review_reply(
                    payload,
                    "acceptable"
                    if mode == "accepted_rule_followup"
                    else "undetermined",
                )
                if mode == "review_followup" and payload["allowed_queries"]:
                    reply["followup_questions"] = [
                        {
                            "question": "사건 전후 사용률을 확인하세요.",
                            "expected_effect": "영향 범위를 좁힐 수 있습니다.",
                            "query_ids": ["D02"],
                        }
                    ]
                return reply
            if "source_items" in payload:
                from rca_report_fixture import report_reply

                events.append("report")
                return report_reply(payload)
            if "facts" in payload:
                events.append("report")
                return {"fact_ids": [f["id"] for f in payload["facts"]]}
            if "available_queries" in payload:
                assert not kwargs.get("tools")
                events.append("plan")
                if mode == "review_followup":
                    assert payload["review_questions"][0]["query_ids"] == ["D02"]
                if mode == "invalid_plan":
                    raise ValueError("malformed response JSON")
                return {
                    "query_ids": payload["available_queries"][:3]
                    if mode == "xid"
                    else ["D02"]
                }
            events.append("synthesize")
            if payload["runbook_plans"]:
                expected = (
                    True
                    if mode in ("missing_runbook", "unsafe_general")
                    else books[0]["content"].get("investigation_only", False)
                )
                assert payload["runbook_plans"][0]["investigation_only"] == expected
            else:
                assert (
                    payload["context_selection"]["omitted_observations"][
                        "runbook_plans"
                    ]
                    > 0
                )
            if mode == "invalid":
                return analysis_reply(["unknown"])
            return analysis_reply(payload["observation_refs"])

    books = [general_runbook()]
    if mode == "accepted_rule_followup":
        for step in books[0]["content"]["observation_plan"]:
            if not step["required"]:
                step["selection"] = dict(
                    missing_any=["causal_confirmation_evidence"],
                    requires_all=["observations"],
                    independent=True,
                )
        books[0].update(
            content_hash=content_hash(books[0]["content"]),
            reviewed_content_hash=content_hash(books[0]["content"]),
        )
    if mode in ("followup", "invalid_plan", "review_followup"):
        books[0]["content"]["unexpected_evidence"]["additional_queries"] = []
        books[0]["content"]["unexpected_evidence"]["fallback"] = "general_runbook"
        for step in books[0]["content"]["observation_plan"]:
            if not step["required"]:
                step["exploratory_llm"] = True
        books[0].update(
            content_hash=content_hash(books[0]["content"]),
            reviewed_content_hash=content_hash(books[0]["content"]),
        )
    if mode == "review_followup":
        profile["queries"]["D09"]["max_hold_seconds"] = 60
        monkeypatch.setattr(
            workflow,
            "retrieve_runbooks",
            lambda rows, source: [
                {"runbook": row, "total_score": 1, "tokenizer_revision": "fixture"}
                for row in rows
            ],
        )
        content = books[0]["content"]
        content["classification"]["category"] = "fixture_specific"
        content["investigation_only"] = False
        content["required_evidence"] = ["normalized_health"]
        content["applicability_conditions"] = [
            {"field": "normalized_health", "equals": "degraded"}
        ]
        books[0].update(
            knowledge_key="fixture-specific",
            content_hash=content_hash(content),
            reviewed_content_hash=content_hash(content),
        )
    if mode == "unsafe_general":
        content = books[0]["content"]
        content["investigation_only"] = False
        content["applicability_conditions"] = [
            {"field": "normalized_health", "equals": "degraded"}
        ]
        books[0].update(
            content_hash=content_hash(content),
            reviewed_content_hash=content_hash(content),
        )
    if mode in ("xid", "sxid"):
        # The current XID draft adds replay context absent from the v7 fixture.
        # Register a fixture query; this test's model still selects D02.
        if mode == "xid":
            profile["queries"]["D44"] = dict(
                source="mimir",
                metric="fixture_pcie_replay",
                unit="count",
                max_hold_seconds=30,
                revision="fixture-v1",
                validated=True,
                target_labels={"gpu_uuid": "UUID", "node": "node"},
            )
        key, reason = (
            ("RB-XID-79", "Xid 79")
            if mode == "xid"
            else ("RB-SXID-11001", "SXid 11001")
        )
        row = json.loads(
            (
                Path(__file__).resolve().parents[2]
                / f"agents/tests/fixtures/{key}-published-legacy.json"
            ).read_text(encoding="utf-8")
        )
        # This fixture explicitly tests the permitted exploratory path.
        row["content"]["schema"] = "gpu-rca-runbook/1.0"
        row["content"].pop("decision_policy", None)
        for step in row["content"]["observation_plan"]:
            step.pop("selection", None)
            if not step["required"]:
                step["exploratory_llm"] = True
        books[0].update(
            knowledge_key=key,
            content=row["content"],
            content_hash=content_hash(row["content"]),
            reviewed_content_hash=content_hash(row["content"]),
        )
        data["incident_snapshot"] = {"alert": {"labels": {"reason": reason}}}
    if mode == "missing_runbook":
        books = []
    if mode == "fast":
        source = {
            "producer_contract": "fixture",
            "verified_facts": {"error_code": "known", "producer_contract": "fixture"},
        }
        data["incident_snapshot"] = {"evidence": source}
        content = {
            "required_evidence": ["error_code"],
            "applicability_conditions": [{"field": "error_code", "equals": "known"}],
        }
        books = [
            dict(
                id=str(uuid4()),
                knowledge_key="fixture",
                revision=1,
                content=content,
                compatibility={"producer_contract": "fixture"},
                content_hash=content_hash(content),
                reviewed_content_hash=content_hash(content),
            )
        ]
    token = attempt_context.set(
        dict(
            claim={
                "job_id": str(uuid4()),
                "kind": "rca",
                "input": data,
                "versions": {},
            },
            profile=profile,
            context={
                "data_cutoff_at": period["end"],
                "runbooks": books,
                "incidents": [],
            },
            deadline=time.monotonic() + 30,
            llm=LLM(),
        )
    )
    try:
        if mode == "uncertain":
            with pytest.raises(RemoteUncertain):
                await run({"query_loki_logs": logs, "query_prometheus": metrics})
            return
        output = await run({"query_loki_logs": logs, "query_prometheus": metrics})
    finally:
        attempt_context.reset(token)
    result = output["result"]
    validate_result(result, output["evidence"])
    assert {s["id"] for s in result["narrative"]} >= {
        "problem",
        "cause",
        "action",
        "limits",
    }
    assert all(section["text"] for section in result["narrative"])
    assert result["quality"]["report"]["status"] == "complete"
    if mode != "unconfigured":
        assert events.pop() == "report"
        assert result["narrative_status"] == "complete"
    else:
        assert result["narrative_status"] == "omitted"
    assert result["quality"]["analysis"]["workflow"] == "single_collection"
    assert result["quality"]["analysis"]["followups"] == 0
    assert not result["quality"]["analysis"]["fast_path"]
    assert not {
        "analysis_review",
        "evidence_evaluation",
        "investigation_plan_extension",
    } & {e["query_id"] for e in output["evidence"]}
    assert "review" not in events and "plan" not in events and "interpret" not in events
    assert events.count("synthesize") <= 1
    assert result["quality"]["rca_evaluation"]["review"]["reason"] == "not_requested"
    if mode == "unconfigured":
        assert "synthesis_failed" in result["missing_inputs"]
        assert (
            result["quality"]["analysis"]["synthesis"]["error_code"]
            == "model_not_configured"
        )
    if mode == "query_failed":
        assert any(e["tool_status"] == "unavailable" for e in output["evidence"])
    assert all(c["causal_status"] != "confirmed" for c in result["cause_candidates"])


def test_alert_clues_preserve_namespace_actions_and_conflicts():
    actions = json.dumps(
        {"description": "Fixture", "repair_actions": ["reboot", "inspect"]}
    )
    source = {
        "alert": {
            "labels": {
                "reason": "XID 79; SXID 11001",
                "suggested_actions": actions,
                "k8s_node_name": "a",
            },
            "annotations": {"k8s_node_name": "b"},
        }
    }
    original = copy.deepcopy(source)
    clues = alert_clues(source)
    assert source == original
    assert clues["error_codes"] == ["sxid:11001", "xid:79"]
    assert clues["suggested_actions"] == actions
    assert clues["provider_actions"]["value"]["repair_actions"] == ["reboot", "inspect"]
    assert clues["provider_actions"]["execution"] == "not_performed"
    assert clues["provider_actions"]["eligibility"] == "withheld"
    assert clues["conflicts"] == ["k8s_node_name"] and "k8s_node_name" not in clues
    source["alert"]["labels"]["suggested_actions"] = "broken JSON"
    assert alert_clues(source)["provider_actions_status"] == "invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    ["fallback_node", "explicit_node", "component_only", "conflicting", "native"],
)
async def test_fleet_query_clues_preserve_claim_and_semantic_health_target(
    monkeypatch, mode
):
    period = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T00:01:00Z"}
    labels = {"k8s_node_name": "fleet-node", "component": "alert-component"}
    annotations = {}
    if mode == "component_only":
        labels.pop("k8s_node_name")
    elif mode == "conflicting":
        annotations = {"k8s_node_name": "other-node", "component": "other-component"}
    elif mode == "native":
        labels = {}
    target = {} if mode == "fallback_node" else {"node": "claimed-node"}
    effective_target = target or {"node": "fleet-node"}
    query_target = (
        {"node": effective_target["node"], "component": "alert-component"}
        if mode in ("fallback_node", "explicit_node")
        else {"component": "alert-component"}
        if mode == "component_only"
        else {}
    )
    data = dict(
        incident_id=str(uuid4()),
        evidence_version=1,
        incident_time=period["start"],
        scope={"clusters": [{"cluster_id": "c", "namespaces": None}]},
        target=target,
        time_range=period,
        purpose_ids=["R05"],
        incident_snapshot={
            "evidence": {
                "producer_contract": "fixture",
                "alert": {"labels": labels, "annotations": annotations},
            }
        },
    )
    profile = json.loads(
        (
            Path(__file__).resolve().parents[2] / "agents/tests/fixtures/config-v7.json"
        ).read_text()
    )
    profile["clusters"] = {"c": {"loki_uid": "logs", "loki_selector": {}}}
    profile["queries"]["D09"]["max_hold_seconds"] = 30
    profile["health_contracts"] = {
        "fixture": {
            "producer_contract": "fixture",
            "revision": "v1",
            "checks": {"valid": "valid"},
            "health": {"Degraded": {"normalized_health": "degraded"}},
        }
    }
    content = {
        "required_queries": ["D09"],
        "required_evidence": ["component", "normalized_health"],
        "applicability_conditions": [{"field": "component", "equals": "gpu"}],
    }
    book = dict(
        id=str(uuid4()),
        knowledge_key="fixture",
        revision=1,
        content=content,
        compatibility={"producer_contract": "fixture"},
        content_hash=content_hash(content),
        reviewed_content_hash=content_hash(content),
    )
    observed_inputs = []

    class CapturingObservation(workflow.Observation):
        def __init__(self, *args):
            super().__init__(*args)
            observed_inputs.append(copy.deepcopy(self.data))

    monkeypatch.setattr(workflow, "Observation", CapturingObservation)

    async def logs(args):
        return {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            [
                                "1",
                                json.dumps(
                                    {
                                        "producer_contract": "fixture",
                                        "health": "Degraded",
                                        "check_status": "valid",
                                        "target": effective_target,
                                        "component": "gpu",
                                        "observed_at": period["start"],
                                    }
                                ),
                            ]
                        ],
                    }
                ]
            }
        }

    class LLM:
        configured = False
        usage = {}

    claim = {"job_id": str(uuid4()), "kind": "rca", "input": data, "versions": {}}
    original = copy.deepcopy(claim)
    token = attempt_context.set(
        dict(
            claim=claim,
            profile=profile,
            context={
                "data_cutoff_at": period["end"],
                "runbooks": [book],
                "incidents": [],
            },
            deadline=time.monotonic() + 30,
            llm=LLM(),
        )
    )
    try:
        output = await run({"query_loki_logs": logs})
    finally:
        attempt_context.reset(token)
    assert claim == original
    projected = dict(effective_target)
    if mode not in ("conflicting", "native"):
        projected["component"] = "alert-component"
    if mode in ("fallback_node", "explicit_node"):
        projected["k8s_node_name"] = "fleet-node"
    assert observed_inputs[0]["target"] == projected
    assert observed_inputs[0]["log_query_target"] == query_target
    snapshot = next(
        e for e in output["evidence"] if e["query_id"] == "incident_snapshot"
    )
    assert snapshot["snapshot"] == original["input"]["incident_snapshot"]
    # The actual producer component still selects this runbook. Adding the alert
    # component to target, or promoting it as a fact, would withhold this match.
    assert any(
        candidate["id"] == book["id"] and candidate["causal_status"] == "supported"
        for candidate in output["result"]["cause_candidates"]
    ) == (mode not in ("explicit_node", "conflicting"))
    validate_result(output["result"], output["evidence"])
