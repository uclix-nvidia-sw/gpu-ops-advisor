import copy
import json
from pathlib import Path
import time
from uuid import uuid4

import pytest

from agent_common.contracts import content_hash, validate_result
from agent_common.llm import RemoteUncertain
from agent_common.runtime import attempt_context
from rcca_agent.synthesis import validate_synthesis
from rcca_agent.workflow import run
from rcca_agent.incident import alert_clues


def analysis_reply(refs):
    return {
        "hypotheses": [
            {
                "claim": "Observed device symptom needs confirmation.",
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
        "unconfigured",
        "invalid",
        "uncertain",
        "missing_runbook",
        "query_failed",
        "invalid_plan",
        "xid",
        "sxid",
        "unsafe_general",
    ],
)
async def test_query_first_collection_analysis_and_failure_boundaries(mode):
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
        (Path(__file__).resolve().parents[2] / "agents/config.example.json").read_text()
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
            if kwargs.get("tools"):
                events.append("plan")
                if mode == "invalid_plan":
                    raise ValueError("malformed response JSON")
                return [
                    {
                        "function": {
                            "name": "investigate",
                            "arguments": json.dumps({"query_id": "D02"}),
                        }
                    }
                ]
            events.append("synthesize")
            assert payload["runbook_plans"][0]["investigation_only"] == books[0][
                "content"
            ].get("investigation_only", False)
            assert (
                payload["runbook_plans"][0]["analysis_guidance"]
                == books[0]["content"]["analysis_guidance"]
            )
            if mode == "invalid":
                return analysis_reply(["unknown"])
            return analysis_reply(payload["observation_refs"])

    books = [general_runbook()]
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
        key, reason = (
            ("RB-XID-79", "Xid 79")
            if mode == "xid"
            else ("RB-SXID-11001", "SXid 11001")
        )
        row = json.loads(
            (
                Path(__file__).resolve().parents[2] / f"rcca-agent/runbooks/{key}.json"
            ).read_text(encoding="utf-8")
        )
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
    if mode == "fast":
        assert events == []
        assert result["result_status"] == "ready"
        assert result["quality"]["analysis"]["fast_path"]
    else:
        assert result["result_status"] != "ready"
        assert all(
            c["causal_status"] == "candidate" for c in result["cause_candidates"]
        )
        assert any(e["query_id"] == "rca_synthesis" for e in output["evidence"])
        if mode in ("followup", "xid", "sxid"):
            assert events == ["collect", "collect", "plan", "collect", "synthesize"]
            assert result["quality"]["analysis"]["followups"] == 1
        elif mode == "unconfigured":
            assert "synthesize" not in events
            assert "synthesis_unconfigured" in result["missing_inputs"]
        elif mode in ("missing_runbook", "unsafe_general"):
            assert events == []
            assert "approved_runbook" in result["missing_inputs"]
        elif mode == "query_failed":
            assert events == ["collect", "collect", "synthesize"]
            assert result["termination_reason"] == "query_failed"
            assert result["quality"]["analysis"]["followups"] == 0
        elif mode == "invalid_plan":
            assert events == ["collect", "collect", "plan", "synthesize"]
            assert result["quality"]["analysis"]["followups"] == 0
            assert result["quality"]["analysis"]["status"] == "complete"
        else:
            assert "synthesis_failed" in result["missing_inputs"]


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
