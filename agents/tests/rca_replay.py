"""Offline RCA replay: real workflow/accounting, fixture-only model and query IO."""

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import time

import httpx

from rca_report_fixture import report_reply

from agent_common.contracts import content_hash, validate_result
from agent_common.llm import LLM
from agent_common.runtime import attempt_context
from agent_common.settings import Settings
from rcca_agent import workflow
from rcca_agent.analysis_review import review_analysis
from rcca_agent.report_labels import label, query_label


def bind(value, payload):
    """Bind explicit JSON pointers to this request's generated IDs, not guessed IDs."""
    if isinstance(value, dict):
        if set(value) == {"$input"}:
            if not isinstance(value["$input"], str) or not value["$input"].startswith(
                "/"
            ):
                raise ValueError("fixture binding requires an absolute JSON pointer")
            selected = payload
            for key in value["$input"].split("/")[1:]:
                key = key.replace("~1", "/").replace("~0", "~")
                selected = (
                    selected[int(key)] if isinstance(selected, list) else selected[key]
                )
            return deepcopy(selected)
        return {key: bind(item, payload) for key, item in value.items()}
    if isinstance(value, list):
        return [bind(item, payload) for item in value]
    return value


class FixtureSettings(Settings):
    def model_for(self, stage):
        # Ambient LLM_MODEL_<STAGE> must not alter a frozen offline case.
        return self.llm_model


class ReplayLLM(LLM):
    async def complete(self, system, data, stage="synthesis"):
        # The existing editor uses the synthesis stage; keep its costs separate.
        role = (
            "report_writing"
            if "source_items" in data
            else "report_ordering"
            if "facts" in data
            else stage
        )
        record = {
            "stage": role,
            "transport_stage": stage,
            "system": system,
            "system_hash": content_hash(system),
            "input": deepcopy(data),
            "input_hash": content_hash(data),
            "budget_before": self.request_budget(system, data, stage),
            "requests": [],
        }
        self.trace.append(record)
        self.current = record
        before = dict(self.usage)
        response = await super().complete(system, data, stage)
        record.update(
            failure=self.last_failure,
            budget_remaining=self.remaining,
            usage={key: self.usage[key] - before[key] for key in before},
        )
        # Validated/adopted text belongs to workflow evidence; never store rejected prose.
        return response


def source_manifest():
    import agent_common
    import rcca_agent

    return {
        package.__name__: {
            str(path.relative_to(root)): content_hash(path.read_text(encoding="utf-8"))
            for path in sorted(root.rglob("*"))
            if path.suffix in {".py", ".json"}
        }
        for package in (agent_common, rcca_agent)
        for root in [Path(package.__file__).parent]
    }


async def replay(case):
    """Replay one frozen case without JC, DB, live MCP or live model access."""
    case = deepcopy(case)
    if case.get("schema") != "rca-replay/1" or case.get("data_origin") not in {
        "synthetic",
        "sanitized",
    }:
        raise ValueError(
            "explicit replay schema and synthetic/sanitized origin required"
        )
    if case.get("mode") not in {"workflow", "review"}:
        raise ValueError("unknown replay mode")
    if not case.get("expectations"):
        raise ValueError("fix human expectations before replay")
    budget = case["token_budget"]
    if type(budget) is not int or budget < 0:
        raise ValueError("nonnegative integer token budget required")
    trace, queries, missing = [], [], list(case.get("missing_inputs", []))
    counters = Counter()
    scripts = deepcopy(case["responses"])
    settings = FixtureSettings(
        kind="rca",
        database_url="",
        jc_url="http://fixture.invalid",
        llm_base_url="http://fixture.invalid/v1",
        llm_model="offline-fixture",
        llm_api_key="fixture-not-a-credential",
        llm_routed=False,
        llm_request_timeout_seconds=10,
        llm_default_max_tokens=case["output_caps"]["default"],
        llm_synthesis_max_tokens=case["output_caps"]["synthesis"],
    )

    def respond(request):
        record = llm.current
        stage = record["stage"]
        index = counters[stage]
        counters[stage] += 1
        body = json.loads(request.content)
        inputs = json.loads(body["messages"][1]["content"])
        supplied = scripts.get(stage, [])
        detail = {
            "model": body["model"],
            "temperature": body["temperature"],
            "output_cap": body["max_tokens"],
            "input_bytes": len(request.content),
        }
        record["requests"].append(detail)
        if index >= len(supplied):
            missing.append(f"model_fixture:{stage}:{index}")
            detail.update(finish_reason=None, output_bytes=None, fixture_missing=True)
            return httpx.Response(400, json={"error": "missing replay response"})
        scripted = supplied[index]
        text = scripted.get("raw_text")
        if text is None:
            try:
                text = json.dumps(
                    report_reply(inputs)
                    if scripted.get("compose_sources")
                    else bind(scripted["response"], inputs),
                    ensure_ascii=False,
                )
            except (ValueError, KeyError, IndexError, TypeError):
                missing.append(f"fixture_binding:{stage}:{index}")
                detail.update(
                    finish_reason=None, output_bytes=None, fixture_missing=True
                )
                return httpx.Response(400, json={"error": "invalid fixture binding"})
        finish = scripted.get("finish_reason", "stop")
        detail.update(
            finish_reason=finish,
            output_bytes=len(text.encode()),
            output_chars=len(text),
            response_hash=content_hash(text),
            fixture_usage=scripted.get("usage"),
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": finish, "message": {"content": text}}],
                **({"usage": scripted["usage"]} if "usage" in scripted else {}),
            },
        )

    def fixture_tool(name):
        async def query(args):
            matches = [
                row
                for row in case.get("queries", [])
                if row["tool"] == name and row["arguments"] == args
            ]
            queries.append(
                {
                    "tool": name,
                    "arguments": deepcopy(args),
                    "matched": len(matches) == 1,
                }
            )
            if len(matches) != 1:
                missing.append(f"query_fixture:{name}:{content_hash(args)}")
                raise ValueError("missing or ambiguous query fixture")
            row = matches[0]
            if row.get("error"):
                raise OSError("scripted query failure")
            return deepcopy(row["response"])

        return query

    class FixtureTools(dict):
        def __missing__(self, name):
            return fixture_tool(name)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), trust_env=False
    ) as http:
        deadline = time.monotonic() + 60
        llm = ReplayLLM(settings, deadline, budget, lambda _: None, http)
        llm.trace = trace
        if case["mode"] == "review":
            output, diagnostics = await review_analysis(
                llm, case["draft"], case["view"], case["allowed_queries"]
            )
            result = {"review": output, "diagnostics": diagnostics}
        else:
            context = deepcopy(case["attempt"])
            context.update(deadline=deadline, llm=llm)
            token = attempt_context.set(context)
            try:
                result = await workflow.run(FixtureTools())
            finally:
                attempt_context.reset(token)
            validate_result(result["result"], result["evidence"])
    output = {
        "schema": "rca-replay-result/1",
        "case_id": case["id"],
        "execution": "offline_fixture",
        "semantic_quality": "not_measured",
        "input_hash": content_hash(case),
        "input": case,
        "source_manifest": source_manifest(),
        "runner_hash": content_hash(Path(__file__).read_text(encoding="utf-8")),
        "replay_status": "partial" if missing else "complete",
        "missing_inputs": missing,
        "model_calls": trace,
        "query_calls": queries,
        "usage": llm.usage,
        "remaining_tokens": llm.remaining,
        "output": result,
    }
    output["summary"] = summarize(output)
    return output


def summarize(replayed):
    evidence = replayed["output"].get("evidence", [])
    by_kind = {}
    for entry in evidence:
        by_kind.setdefault(entry["query_id"], []).append(entry["snapshot"])
    interpretations = by_kind.get("evidence_interpretation", [])
    synthesis = by_kind.get("rca_synthesis", [])
    interpretations += [
        {"round": row["round"], "execution_status": row.get("interpretation_status")}
        for row in synthesis
        if row.get("generation_mode") == "combined"
    ]
    decisions = by_kind.get("investigation_decision", [])
    requests = [req for call in replayed["model_calls"] for req in call["requests"]]
    return {
        "replay_status": replayed["replay_status"],
        "semantic_quality": "not_measured",
        "transport_calls": len(requests),
        "fixture_reported_tokens": replayed["usage"]["total_tokens"]
        if any(
            req.get("fixture_usage", {}).get("total_tokens") is not None
            for req in requests
            if req.get("fixture_usage") is not None
        )
        else None,
        "charged_tokens": replayed["usage"]["charged_tokens"],
        "usage_missing_calls": replayed["usage"]["usage_missing_calls"],
        "truncated_responses": sum(
            req.get("finish_reason") == "length" for req in requests
        ),
        "interpretation_statuses": [
            row.get("status", row.get("execution_status")) for row in interpretations
        ],
        "synthesis_statuses": [row.get("status") for row in synthesis],
        "interpretation_only_rounds": sum(
            row.get("execution_status") == "complete"
            and not any(
                syn.get("status") == "complete" and syn["round"] == row["round"]
                for syn in synthesis
            )
            for row in interpretations
        ),
        "review_verdicts": [
            (row.get("review") or {}).get("verdict")
            for row in by_kind.get("analysis_review", [])
        ],
        "decisions": [
            {
                key: row.get(key)
                for key in ("round", "action", "reason", "selected_queries")
            }
            for row in decisions
        ],
        "review_only_verdict": (replayed["output"].get("review") or {}).get("verdict"),
    }


def compare(before, after):
    for result in (before, after):
        if (
            result.get("schema") != "rca-replay-result/1"
            or content_hash(result["input"]) != result["input_hash"]
        ):
            raise ValueError("invalid or modified replay input/hash")
    if before["input_hash"] != after["input_hash"]:
        raise ValueError("different frozen inputs: not a controlled code comparison")
    return {
        key: {"before": value, "after": after["summary"].get(key)}
        for key, value in before["summary"].items()
        if value != after["summary"].get(key)
    }


def readable_summary(result):
    summary = result["summary"]
    lines = [
        f"# RCA 재생: {result['case_id']}",
        "",
        "고정 조회·모델 응답으로 기존 RCA 코드를 실행했습니다. 실제 모델의 판단 정확도·비용은 측정하지 않았습니다.",
        "",
        f"- 재생 자료: {'완비' if result['replay_status'] == 'complete' else '일부 누락 — 부분 재생'}",
        f"- 모델 전송: {summary['transport_calls']}회 (고정 응답용 전송)",
        f"- 해석만 보존된 라운드: {summary['interpretation_only_rounds']}개",
        f"- 출력 잘림: {summary['truncated_responses']}건",
        f"- 예산 차감: {summary['charged_tokens']}토큰 (fixture usage 또는 기존 코드의 보수적 추정)",
        "",
        "| 단계 | 실행 상태 | 실패·생략 사유 / 판정 |",
        "|---|---|---|",
    ]
    names = {
        "evidence_interpretation": "증거 해석",
        "rca_synthesis": "RCA 분석",
        "analysis_review": "품질 검토",
    }
    statuses = {"complete": "완료", "skipped": "생략", "failed": "실패"}
    for entry in result["output"].get("evidence", []):
        kind, row = entry["query_id"], entry["snapshot"]
        if kind not in names:
            continue
        state = row.get("execution_status", row.get("status", "미기록"))
        reason = row.get("reason") or row.get("diagnostics", {}).get("error_code")
        verdict = (row.get("review") or {}).get("verdict")
        conclusion = (
            label("reasons", reason)
            if reason
            else {
                "acceptable": "확보된 근거 범위에서 타당",
                "revision_required": "설명 수정 필요",
                "undetermined": "판단 불가",
                None: "문제 기록 없음",
            }[verdict]
        )
        lines.append(
            f"| {row['round'] + 1}차 {names[kind]} | {statuses.get(state, state)} | {conclusion} |"
        )
    lines += ["", "다음 행동:", ""]
    for decision in summary["decisions"]:
        action = (
            "추가 수집 "
            + ", ".join(query_label(q) for q in decision["selected_queries"])
            if decision["action"] == "collect"
            else "조사 종료"
        )
        reason = {
            "review_accepted": "현재 초안의 검토를 통과했고 우선 실행할 명시 규칙 조회가 없음",
            "authorized_followup": "현재 증거 부족 조건에 맞는 허용 조회를 선택함",
            "no_remaining_queries": "현재 계획에서 더 실행할 조회가 없음",
        }.get(decision["reason"], label("reasons", decision["reason"]))
        lines.append(
            f"- {decision['round'] + 1}차: {action}. {reason} (`{decision['reason']}`)."
        )
    if not summary["decisions"]:
        lines.append(
            f"- 검토자 단독 실행. 판정: `{summary['review_only_verdict'] or '판정 없음'}`."
        )
    if result["missing_inputs"]:
        lines += ["", "누락 자료: " + ", ".join(result["missing_inputs"])]
    lines += [
        "",
        "입력은 `input.json`, 실제 모델 입력·예산·검증된 응답·근거·결정은 `result.json`에 있습니다.",
        "조사 종료·검토 통과는 원인 확정을 뜻하지 않습니다.",
        "",
    ]
    return "\n".join(lines)


def main():
    import asyncio
    from rca_replay_cases import cases

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=sorted(cases()))
    parser.add_argument(
        "--input", type=Path, help="Previously frozen, sanitized case JSON"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New local output directory"
    )
    parser.add_argument(
        "--baseline", type=Path, help="Prior result.json with identical inputs"
    )
    args = parser.parse_args()
    if bool(args.case) == bool(args.input):
        parser.error("choose exactly one of --case or --input")
    case = (
        json.loads(args.input.read_text(encoding="utf-8"))
        if args.input
        else cases()[args.case]
    )
    args.output.mkdir(parents=True, exist_ok=False)
    result = asyncio.run(replay(case))
    files = {"input.json": case, "result.json": result}
    if args.baseline:
        files["comparison.json"] = compare(
            json.loads(args.baseline.read_text(encoding="utf-8")), result
        )
    for name, content in files.items():
        (args.output / name).write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (args.output / "summary.md").write_text(readable_summary(result), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
