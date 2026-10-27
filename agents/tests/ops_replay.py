"""Freeze an Ops interpretation case, then replay it without collection or publication."""

import argparse
import asyncio
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time

from agent_common.llm import LLM, RemoteUncertain
from agent_common.settings import Settings
from ops_agent.namespace_advice import summary_context, writing_decision
from ops_agent.report_interpretation import (
    interpret_report,
    payload_for,
    validate_written_advice,
    writing_context,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def source_hashes():
    import agent_common
    import ops_agent

    hashes = {
        f"{package.__name__}/{path.relative_to(root)}": hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for package in (agent_common, ops_agent)
        for root in [Path(package.__file__).parent]
        for path in sorted(root.rglob("*.py"))
    }
    hashes["ops_replay.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return hashes


def calculated(result):
    value = deepcopy(result)
    for key in ("narrative", "narrative_status", "llm_usage"):
        value.pop(key, None)
    value.get("quality", {}).pop("report", None)
    return value


def controls(payload):
    rows = []
    for topic in payload["topics"]:
        if not topic.get("advice_mode"):
            continue
        for fact in topic["findings"]:
            decision = writing_decision(fact)
            context = summary_context(fact)
            evidence = re.sub(
                r"\{\{([a-z_]+)\}\}",
                lambda match: context["summary_tokens"]["{{" + match[1] + "}}"],
                context["summary_start"],
            )
            try:
                validate_written_advice(
                    {
                        "advice": [
                            {"fact_id": fact["fact_id"], "summary": decision["option"]}
                        ]
                    },
                    {"findings": [fact]},
                )
                error = None
            except (ValueError, KeyError, TypeError) as exc:
                error = str(exc).split(":", 1)[0]
            rows.append(
                {
                    "fact_id": fact["fact_id"],
                    "kind": fact["kind"],
                    "target": fact["target"],
                    "period": fact["period"],
                    "decision_option": decision["option"],
                    "code_action": decision["action"],
                    "evidence": evidence,
                    "control_summary": decision["option"] + " " + evidence,
                    "scope": decision["scope"],
                    "prose_max_chars": writing_context(fact)["prose_max_chars"],
                    "control_validation_error": error,
                }
            )
    return rows


def write_json(path, value):
    # Real evidence stays local; refuse overwrites and restrict newly written files.
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prepare(report, output, profile):
    raw = report.read_bytes()
    saved = json.loads(raw)
    result = deepcopy(saved.get("result", saved)) if isinstance(saved, dict) else None
    if not isinstance(result, dict) or not isinstance(result.get("topics"), list):
        raise ValueError("an aggregate report result JSON is required")
    payload = payload_for(result)
    control = controls(payload)
    if not control:
        raise ValueError("this comparison requires Namespace advice candidates")
    manifest = {
        "schema": "ops-replay/1",
        "report_id": result.get("job_id"),
        "time_range": result["time_range"],
        "input_file_sha256": hashlib.sha256(raw).hexdigest(),
        "result_hash": digest(result),
        "payload_hash": digest(payload),
        "control_hash": digest(control),
        "calculation_hash": digest(calculated(result)),
        "sources": source_hashes(),
        "profile": profile,
    }
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name, value in (
        ("input.json", result),
        ("control.json", control),
        ("manifest.json", manifest),
    ):
        write_json(output / name, value)
    return manifest


def load_case(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((folder / "input.json").read_text(encoding="utf-8"))
    control = json.loads((folder / "control.json").read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "ops-replay/1"
        or manifest["sources"] != source_hashes()
        or manifest["result_hash"] != digest(result)
        or manifest["control_hash"] != digest(control)
        or manifest["payload_hash"] != digest(payload_for(result))
        or manifest["control_hash"] != digest(controls(payload_for(result)))
    ):
        raise ValueError("frozen case or implementation changed; prepare a new case")
    return manifest, result, control


class PinnedSettings(Settings):
    def model_for(self, stage):
        # Ambient stage aliases must not change a frozen comparison's model.
        return self.llm_model


def repair_scope(request_keys):
    # Request shape identifies repair scope, not the cause of a later failure.
    if len(request_keys) == 1:
        return "none"
    return (
        {
            ("summary_repair",): "namespace_usage",
            ("section_repair",): "incident_summary",
            ("summary_repair", "section_repair"): "mixed",
        }.get(tuple(request_keys[1]), "unknown")
        if len(request_keys) == 2
        else "unknown"
    )


def comparison_row(row, item, namespace_accepted):
    parts = deepcopy(item.get("summary_parts")) if item else None
    decision = parts.get("decision") if isinstance(parts, dict) else None
    suffix = " " + row["code_action"]
    reason = None
    status = "not_accepted" if item is None else "parts_missing"
    if isinstance(decision, str):
        status = "action_suffix_mismatch"
        if decision.endswith(suffix) and decision[: -len(suffix)].strip():
            reason = decision[: -len(suffix)]
            status = "exact"
    return {
        **row,
        "ai_summary": item.get("summary") if item else None,
        "summary_parts": parts,
        "ai_reason": reason,
        "reason_status": status,
        "ai_status": "accepted"
        if item is not None
        else "not_selected"
        if namespace_accepted
        else "failed",
        "assessment": None,
    }


async def replay(folder, output, llm):
    manifest, result, control = load_case(folder)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(output / "started.json", {"case_hash": digest(manifest)})
    before = digest(calculated(result))
    started = time.monotonic()
    states = []
    llm.state = states.append
    request_keys = []
    complete = llm.complete

    async def record_request(system, data, *args, **kwargs):
        request_keys.append(
            [key for key in ("summary_repair", "section_repair") if key in data]
        )
        return await complete(system, data, *args, **kwargs)

    llm.complete = record_request
    try:
        await interpret_report(result, llm)
        if (
            before != digest(calculated(result))
            or source_hashes() != manifest["sources"]
        ):
            raise ValueError(
                "calculated evidence or implementation changed during replay"
            )
    except (Exception, asyncio.CancelledError) as exc:
        last_state = states[-1] if states else None
        write_json(
            output / "summary.json",
            {
                "case_hash": digest(manifest),
                "replay_profile": manifest["profile"],
                "request_repair_keys": request_keys,
                "repair_scope": repair_scope(request_keys),
                "outcome": "failed",
                "error_type": type(exc).__name__,
                "narrative_status": None,
                "seconds": round(time.monotonic() - started, 3),
                "remote_state": "unconfirmed"
                if isinstance(exc, RemoteUncertain)
                or last_state in ("running", "unknown")
                else last_state or "not_observed",
                "last_remote_state": last_state,
                "remote_states": states,
                "llm_usage": dict(llm.usage),
                "calculations_unchanged": before == digest(calculated(result)),
                "model_revision_verified": False,
            },
        )
        raise
    finally:
        llm.complete = complete
    namespace_accepted = any(
        section.get("topic_id") == "namespace_usage" and "advice" in section
        for section in result["narrative"]
    )
    selected = {
        item["fact_id"]: item
        for section in result["narrative"]
        for item in section.get("advice", [])
    }
    comparison = [
        comparison_row(row, selected.get(row["fact_id"]), namespace_accepted)
        for row in control
    ]
    result["llm_usage"] = dict(llm.usage)
    summary = {
        "case_hash": digest(manifest),
        "replay_profile": manifest["profile"],
        "request_repair_keys": request_keys,
        "repair_scope": repair_scope(request_keys),
        "seconds": round(time.monotonic() - started, 3),
        "narrative_status": result["narrative_status"],
        "diagnostic": result["quality"]["report"],
        "llm_usage": result["llm_usage"],
        "remote_states": states,
        "calculations_unchanged": True,
        "payload_unchanged": digest(payload_for(result)) == manifest["payload_hash"],
        "model_revision_verified": False,
    }
    for name, value in (
        ("result.json", result),
        ("comparison.json", comparison),
        ("summary.json", summary),
    ):
        write_json(output / name, value)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser(
        "prepare", help="offline: freeze input and code control"
    )
    freeze.add_argument("report", type=Path)
    freeze.add_argument("--model", required=True)
    freeze.add_argument("--token-budget", type=int, required=True)
    freeze.add_argument("--output-tokens", type=int, required=True)
    freeze.add_argument("--context-tokens", type=int, required=True)
    freeze.add_argument("--deadline-seconds", type=int, required=True)
    freeze.add_argument("--request-timeout-seconds", type=int, required=True)
    freeze.add_argument("--medium-effort", action="store_true")
    freeze.add_argument("--output", type=Path, required=True)
    run = commands.add_parser(
        "run", help="live: one interpretation, existing repair limit"
    )
    run.add_argument("case", type=Path)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        profile = {
            key: getattr(args, key)
            for key in (
                "model",
                "token_budget",
                "output_tokens",
                "context_tokens",
                "deadline_seconds",
                "request_timeout_seconds",
                "medium_effort",
            )
        }
        if (
            any(
                profile[k] <= 0
                for k in (
                    "token_budget",
                    "output_tokens",
                    "deadline_seconds",
                    "request_timeout_seconds",
                )
            )
            or profile["context_tokens"] < 0
        ):
            parser.error("positive budgets/deadline and nonnegative context required")
        manifest = prepare(args.report, args.output, profile)
        print(
            json.dumps(
                {"state": "prepared_no_model_call", "case_hash": digest(manifest)}
            )
        )
        return
    manifest, _, _ = load_case(args.case)
    profile = manifest["profile"]
    settings = PinnedSettings(
        kind="report",
        database_url="",
        jc_url="",
        llm_routed=False,
        llm_model=profile["model"],
        ops_llm_medium_effort=profile["medium_effort"],
        llm_synthesis_max_tokens=profile["output_tokens"],
        llm_context_tokens=profile["context_tokens"],
        llm_request_timeout_seconds=profile["request_timeout_seconds"],
    )
    llm = LLM(
        settings,
        time.monotonic() + profile["deadline_seconds"],
        profile["token_budget"],
        None,  # replay installs the state recorder before any model call.
    )
    if not llm.configured:
        parser.error("run requires LLM_BASE_URL and LLM_API_KEY in the environment")
    # No worker lifecycle, database, MCP collection or artifact publication is invoked.
    print(json.dumps(asyncio.run(replay(args.case, args.output, llm))))


if __name__ == "__main__":
    main()
