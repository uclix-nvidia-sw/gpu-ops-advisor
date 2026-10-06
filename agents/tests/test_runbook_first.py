"""Runbook-first execution uses no purpose code and preserves unknown evidence."""

import copy
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest

from agent_common.contracts import content_hash, validate_input, validate_result
from agent_common.runtime import attempt_context
from rcca_agent.runbook_contract import validate_runbook
from rcca_agent.workflow import run
from test_rca_analysis import general_runbook
from test_incident_snapshot import rca_input


def test_input_without_purposes_preserves_snapshot():
    for version in ("1.4", "1.5"):
        data = rca_input({"alert": {"labels": {}, "annotations": {}}})
        data.pop("purpose_ids")
        if version == "1.4":
            data.pop("analysis_profile_revision")
        data["incident_snapshot"]["input"] = {
            k: copy.deepcopy(v) for k, v in data.items() if k != "incident_snapshot"
        }
        original = copy.deepcopy(data)
        validate_input("rca", data, version)
        assert data == original
        data["purpose_ids"] = ["R01"]
        with pytest.raises(ValueError, match="purpose_ids"):
            validate_input("rca", data, version)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode", ["specific", "missing", "incompatible", "unexpected", "failed", "stop"]
)
async def test_runbook_controls_queries_and_unknown_policy(mode):
    root = Path(__file__).resolve().parents[2]
    profile = json.loads(
        (root / "agents/tests/fixtures/config-v7.json").read_text("utf-8")
    )
    profile["clusters"] = {
        "c": {
            "mimir_uid": "m",
            "metric_selector": {},
            "loki_uid": "l",
            "loki_selector": {},
        }
    }
    book = general_runbook()
    book["knowledge_key"] = "RB-TEMPERATURE"
    book["content"].update(
        title="온도 조사",
        search={"aliases": ["thermal"]},
        required_queries=["D04"],
        observation_plan=[
            dict(
                query_id="D04",
                priority=1,
                required=True,
                fact_names=["observations"],
                purpose="Check temperature",
                binding="execution_profile",
                time_range="incident",
                freshness="query_contract",
            )
        ],
        unexpected_evidence=dict(
            on=["unknown_value", "missing_evidence", "query_failed"],
            additional_queries=[] if mode == "stop" else ["D03"],
            fallback="stop",
        ),
    )
    book.update(
        content_hash=content_hash(book["content"]),
        reviewed_content_hash=content_hash(book["content"]),
    )
    if mode == "incompatible":
        book["knowledge_key"] = profile["rca"]["general_runbook_key"]
        book["compatibility"] = {"cluster_id": "other-cluster"}
    validate_runbook(book, profile["queries"], list(profile["queries"]))
    period = {"start": "2026-09-15T00:00:00Z", "end": "2026-09-15T00:01:00Z"}
    data = dict(
        incident_id=str(uuid4()),
        evidence_version=1,
        scope={"clusters": [{"cluster_id": "c", "namespaces": None}]},
        target={"gpu_uuid": "GPU-1", "node": "node-1"},
        incident_time=period["start"],
        time_range=period,
        incident_snapshot={"alert": {"annotations": {"summary": "thermal"}}},
    )
    calls = []

    async def metrics(args):
        calls.append(args["expr"])
        if mode == "failed":
            raise OSError("fixture")
        if mode in ("unexpected", "stop"):
            return {"data": {"result": []}}
        return {
            "data": {
                "result": [
                    {
                        "metric": {"uuid": "GPU-1", "node": "node-1"}
                        if args["expr"].startswith("dcgm_fi_dev_gpu_temp{")
                        else {"UUID": "GPU-1"},
                        "values": [[1789430400, "40"], [1789430415, "41"]],
                    }
                ]
            }
        }

    async def logs(args):
        calls.append("logs")
        return {
            "data": {
                "result": [
                    {
                        "stream": {},
                        "values": [
                            ["1789430400000000000", '{"health":"UNREGISTERED"}']
                        ],
                    }
                ]
            }
        }

    class Model:
        configured = False
        usage = {}

    token = attempt_context.set(
        dict(
            claim=dict(
                job_id=str(uuid4()),
                kind="rca",
                input=data,
                versions={"input_contract": "1.5"},
            ),
            profile=profile,
            context=dict(
                data_cutoff_at=period["end"],
                runbooks=[] if mode == "missing" else [book],
                incidents=[],
            ),
            deadline=time.monotonic() + 30,
            llm=Model(),
        )
    )
    try:
        output = await run({"query_prometheus": metrics, "query_loki_logs": logs})
    finally:
        attempt_context.reset(token)
    validate_result(output["result"], output["evidence"])
    ids = {e["query_id"] for e in output["evidence"]}
    assert "purpose_plan" not in ids and "investigation_plan" in ids
    assert all("purpose_id" not in a for a in output["result"]["assessments"])
    assert output["result"]["result_status"] != "ready"
    if mode in ("missing", "incompatible"):
        assert {"D09", "D02", "unexpected_evidence"} <= ids
        assert output["result"]["runbook_revisions"][0]["id"] == "builtin-general"
    else:
        assert "D04" in ids  # Former procedure allowlists excluded temperature.
        temperature_queries = [
            q for q in calls if q.startswith("dcgm_fi_dev_gpu_temp{")
        ]
        assert temperature_queries and all(
            'uuid="GPU-1"' in q and 'node="node-1"' in q and "UUID=" not in q
            for q in temperature_queries
        )
        assert "D08" not in ids and "D06" not in ids
        assert ("D03" in ids) == (mode != "stop")
        if mode == "specific":
            temperature = next(e for e in output["evidence"] if e["query_id"] == "D04")
            assert temperature["snapshot"]["data"]["result"][0]["metric"] == {
                "uuid": "GPU-1",
                "node": "node-1",
            }
    if mode in ("unexpected", "failed", "stop"):
        assert "required_query:D04" in output["result"]["missing_inputs"]


def test_unregistered_fallback_queries_are_rejected():
    row = general_runbook()
    row["content"]["unexpected_evidence"]["additional_queries"] = ["arbitrary_query"]
    with pytest.raises(ValueError, match="unregistered"):
        validate_runbook(row, {"D02": {}, "D05": {}, "D09": {}}, ["D02", "D05", "D09"])


def test_packaged_fallback_matches_authored_general_runbook():
    root = Path(__file__).resolve().parents[2] / "rcca-agent"
    assert (
        json.loads((root / "src/rcca_agent/general_runbook.json").read_text("utf-8"))
        == json.loads((root / "runbooks/RB-GENERAL-GPU-NODE.json").read_text("utf-8"))[
            "content"
        ]
    )
