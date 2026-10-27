"""Replay preparation must stay offline and keep evidence separate from interpretation."""

from copy import deepcopy
import asyncio
import json
import socket
import sys
import time
from unittest.mock import AsyncMock

import httpx
import pytest

import ops_replay
from test_namespace_advice import topic, writer_section


PROFILE = {
    "model": "fixture-only",
    "token_budget": 65536,
    "output_tokens": 16384,
    "context_tokens": 65536,
    "deadline_seconds": 300,
    "request_timeout_seconds": 60,
    "medium_effort": True,
}


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("replay preparation must not use the network")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    source = tmp_path / "report.json"
    result = {
        "job_id": "frozen-fixture",
        "topics": [topic(activity=90, pending=2)],
        "quality": {},
        "time_range": {},
        "narrative": [{"text": "historical explanation"}],
        "narrative_status": "complete",
    }
    source.write_text(json.dumps({"result": result}), encoding="utf-8")
    case = tmp_path / "case"
    manifest = ops_replay.prepare(source, case, PROFILE)
    return source, case, manifest


def test_prepare_freezes_source_and_code_control_without_network(frozen):
    source, folder, manifest = frozen
    _, result, control = ops_replay.load_case(folder)
    assert result == json.loads(source.read_text())["result"]
    assert manifest["profile"] == PROFILE
    assert control
    for row in control:
        assert row["control_summary"] == row["decision_option"] + " " + row["evidence"]
        assert row["code_action"] in row["decision_option"]
        assert row["target"]
        assert row["prose_max_chars"] > 0
    with pytest.raises(FileExistsError):
        ops_replay.prepare(source, folder, PROFILE)


def test_control_error_belongs_only_to_its_candidate(frozen, monkeypatch):
    _, folder, _ = frozen
    _, result, _ = ops_replay.load_case(folder)
    payload = ops_replay.payload_for(result)
    fact = deepcopy(payload["topics"][0]["findings"][0])
    fact["fact_id"] += "-long"
    payload["topics"][0]["findings"].append(fact)
    original = ops_replay.writing_decision

    def changed(candidate):
        decision = original(candidate)
        if candidate["fact_id"].endswith("-long"):
            decision["option"] += "긴 설명" * 100
        return decision

    monkeypatch.setattr(ops_replay, "writing_decision", changed)
    rows = ops_replay.controls(payload)
    assert rows[0]["control_validation_error"] is None
    assert rows[-1]["control_validation_error"] == "concise_namespace_summary_required"


@pytest.mark.parametrize("change", ["input", "control", "source"])
def test_changed_case_is_rejected_before_model_call(frozen, monkeypatch, change):
    _, folder, _ = frozen
    if change == "source":
        monkeypatch.setattr(ops_replay, "source_hashes", lambda: {"changed": "yes"})
    else:
        path = folder / f"{change}.json"
        value = json.loads(path.read_text())
        if change == "input":
            value["topics"][0]["status"] = "changed"
        else:
            value[0]["decision_option"] += "changed"
        path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen case"):
        ops_replay.load_case(folder)


@pytest.mark.parametrize("valid", [True, False])
async def test_replay_keeps_calculations_and_reports_adoption_separately(
    frozen, tmp_path, valid
):
    _, folder, manifest = frozen
    _, original, _ = ops_replay.load_case(folder)
    payload = ops_replay.payload_for(deepcopy(original))
    reply = {"sections": [writer_section(payload["topics"][0]["findings"])]}
    llm = AsyncMock(configured=True, last_failure=None, last_http_status=None)
    llm.usage = {"calls": 1, "total_tokens": 100}
    llm.complete.return_value = reply if valid else {"sections": []}
    output = tmp_path / "run"
    summary = await ops_replay.replay(folder, output, llm)
    result = json.loads((output / "result.json").read_text())
    comparison = json.loads((output / "comparison.json").read_text())
    assert summary["calculations_unchanged"] and summary["payload_unchanged"]
    assert (
        ops_replay.digest(ops_replay.calculated(result)) == manifest["calculation_hash"]
    )
    assert summary["narrative_status"] == ("complete" if valid else "failed")
    assert summary["replay_profile"] == PROFILE
    assert all((row["ai_summary"] is not None) == valid for row in comparison)
    assert {row["ai_status"] for row in comparison} == {
        "accepted" if valid else "failed"
    }
    assert all(row["assessment"] is None for row in comparison)
    if valid:
        assert all(row["reason_status"] == "exact" for row in comparison)
        assert all(
            row["summary_parts"]["decision"]
            == row["ai_reason"] + " " + row["code_action"]
            for row in comparison
        )
    assert 1 <= llm.complete.await_count <= 2
    assert json.loads((folder / "input.json").read_text()) == original
    with pytest.raises(FileExistsError):
        await ops_replay.replay(folder, output, llm)


async def test_calculation_mutation_is_not_accepted(frozen, tmp_path, monkeypatch):
    _, folder, _ = frozen

    async def corrupt(result, llm):
        result["topics"][0]["status"] = "corrupted"

    monkeypatch.setattr(ops_replay, "interpret_report", corrupt)
    llm = AsyncMock()
    llm.usage = {}
    with pytest.raises(ValueError, match="calculated evidence"):
        await ops_replay.replay(folder, tmp_path / "corrupt", llm)
    assert not (tmp_path / "corrupt" / "result.json").exists()
    summary = json.loads((tmp_path / "corrupt" / "summary.json").read_text())
    assert summary["outcome"] == "failed"
    assert not summary["calculations_unchanged"]


@pytest.mark.parametrize("cancel", [False, True])
async def test_transport_failure_keeps_usage_and_unknown_state(
    frozen, tmp_path, cancel
):
    _, folder, _ = frozen
    http = AsyncMock()
    http.post.side_effect = (
        asyncio.CancelledError("private transport detail")
        if cancel
        else httpx.ReadTimeout("private transport detail")
    )
    settings = ops_replay.PinnedSettings(
        kind="report",
        llm_routed=False,
        llm_base_url="https://fixture.invalid/v1",
        llm_api_key="fixture-secret",
        llm_model="fixture-only",
    )
    llm = ops_replay.LLM(settings, time.monotonic() + 60, 65536, None, http=http)
    output = tmp_path / "failed"
    with pytest.raises(
        asyncio.CancelledError if cancel else ops_replay.RemoteUncertain
    ):
        await ops_replay.replay(folder, output, llm)
    summary = json.loads((output / "summary.json").read_text())
    assert summary["remote_states"] == ["running", "unknown"]
    assert summary["remote_state"] == "unconfirmed"
    assert summary["last_remote_state"] == "unknown"
    assert summary["llm_usage"]["request_attempts"] == 1
    assert summary["narrative_status"] is None
    assert summary["seconds"] >= 0
    assert summary["calculations_unchanged"]
    assert summary["replay_profile"] == PROFILE
    assert summary["request_repair_keys"] == [[]]
    assert {p.name for p in output.iterdir()} == {"started.json", "summary.json"}
    assert "private transport detail" not in json.dumps(summary)
    assert "fixture-secret" not in json.dumps(summary)
    assert http.post.await_count == 1


@pytest.mark.parametrize(
    "keys,scope",
    [
        (None, "none"),
        ([], "unknown"),
        (["summary_repair"], "namespace_usage"),
        (["section_repair"], "incident_summary"),
        (["summary_repair", "section_repair"], "mixed"),
    ],
)
async def test_only_repair_key_names_are_recorded(
    frozen, tmp_path, monkeypatch, keys, scope
):
    _, folder, _ = frozen
    payloads = [{"topics": "PRIVATE_INPUT"}]
    if keys is not None:
        payloads.append({key: "PRIVATE_REPAIR_CONTENT" for key in keys})

    async def respond(result, llm):
        for payload in payloads:
            await llm.complete("PRIVATE_SYSTEM", payload, json_object=True)
        result["narrative"] = []
        result["narrative_status"] = "failed"
        result["quality"]["report"] = {"reason": "model_response_unavailable"}

    monkeypatch.setattr(ops_replay, "interpret_report", respond)
    llm = AsyncMock()
    llm.usage = {}
    llm.complete.return_value = {"text": "PRIVATE_REPLY"}
    original_complete = llm.complete
    summary = await ops_replay.replay(folder, tmp_path / "trace", llm)
    assert summary["repair_scope"] == scope
    assert summary["request_repair_keys"] == ([[]] if keys is None else [[], keys])
    assert "PRIVATE_" not in json.dumps(summary)
    assert "failure_topic" not in summary
    assert llm.complete is original_complete
    for call, payload in zip(llm.complete.await_args_list, payloads, strict=True):
        assert call.args == ("PRIVATE_SYSTEM", payload)
        assert call.kwargs == {"json_object": True}


@pytest.mark.parametrize(
    "parts,status,reason",
    [
        ({"decision": "관측 이유입니다. 확인하세요."}, "exact", "관측 이유입니다."),
        ({"decision": "확인하세요. 관측 이유입니다."}, "action_suffix_mismatch", None),
        ({"decision": " 확인하세요."}, "action_suffix_mismatch", None),
        (None, "parts_missing", None),
    ],
)
def test_reason_split_requires_exact_nonempty_suffix(parts, status, reason):
    item = {"summary": "original unchanged", "summary_parts": parts}
    original = deepcopy(item)
    row = ops_replay.comparison_row({"code_action": "확인하세요."}, item, True)
    assert row["reason_status"] == status
    assert row["ai_reason"] == reason
    assert row["summary_parts"] == parts
    assert row["ai_summary"] == "original unchanged"
    assert item == original


async def test_not_selected_is_distinct_from_failed(frozen, tmp_path, monkeypatch):
    _, folder, _ = frozen

    async def omit(result, llm):
        result["narrative"] = [{"topic_id": "namespace_usage", "advice": []}]
        result["narrative_status"] = "complete"
        result["quality"]["report"] = {"method": "llm_interpreted"}

    monkeypatch.setattr(ops_replay, "interpret_report", omit)
    llm = AsyncMock()
    llm.usage = {}
    await ops_replay.replay(folder, tmp_path / "omitted", llm)
    rows = json.loads((tmp_path / "omitted" / "comparison.json").read_text())
    assert {row["ai_status"] for row in rows} == {"not_selected"}


def test_cli_keeps_request_timeout_separate_from_deadline(
    frozen, tmp_path, monkeypatch
):
    _, folder, _ = frozen
    captured = {}

    def llm(settings, deadline, budget, state):
        captured.update(settings=settings, deadline=deadline, budget=budget)
        return AsyncMock(configured=True)

    monkeypatch.setattr(ops_replay, "LLM", llm)
    monkeypatch.setattr(ops_replay, "replay", AsyncMock(return_value={"mocked": True}))
    monkeypatch.setattr(
        sys,
        "argv",
        ["ops_replay.py", "run", str(folder), "--output", str(tmp_path / "run")],
    )
    started = time.monotonic()
    ops_replay.main()
    assert captured["settings"].llm_request_timeout_seconds == 60
    assert 299 <= captured["deadline"] - started <= 301


@pytest.mark.parametrize("failed_topic", ["namespace_usage", "incident_summary"])
async def test_replay_classifies_partially_retained_topics(tmp_path, failed_topic):
    from test_report_interpretation import result as base_result, reply_for

    result = base_result.__wrapped__()
    result["topics"][0] = topic(activity=90, pending=2)
    source = tmp_path / "report.json"
    source.write_text(json.dumps(result), encoding="utf-8")
    case, output = tmp_path / "case", tmp_path / "run"
    ops_replay.prepare(source, case, PROFILE)
    reply = reply_for(ops_replay.payload_for(result))
    broken = next(s for s in reply["sections"] if s["topic_id"] == failed_topic)
    if failed_topic == "namespace_usage":
        broken["advice"][0]["summary"] = ""
        repair = {"advice": [deepcopy(broken["advice"][0])]}
    else:
        broken["meaning"] = "XID 79가 기록됐습니다."
        repair = {"sections": [deepcopy(broken)]}
    llm = AsyncMock(configured=True, last_failure=None, last_http_status=None)
    llm.usage = {"calls": 2, "total_tokens": 100}
    llm.complete.side_effect = [reply, repair]
    summary = await ops_replay.replay(case, output, llm)
    comparison = json.loads((output / "comparison.json").read_text())
    assert summary["diagnostic"]["method"] == "partial_interpretation"
    assert summary["calculations_unchanged"] and summary["payload_unchanged"]
    assert {row["ai_status"] for row in comparison} == {
        "failed" if failed_topic == "namespace_usage" else "accepted"
    }
