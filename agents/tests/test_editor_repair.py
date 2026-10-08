import asyncio
import copy

import pytest

from agent_common.llm import RemoteUncertain, explain


def result():
    return {
        "facts": [{"id": "cause-1", "text": "원인 미확정", "value_refs": []}],
        "limitations": ["장치 매핑 미확인"],
        "narrative_status": "omitted",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad,reason",
    [
        ("private rejected prose", "response_not_object"),
        ({}, "fact_ids_not_list"),
        ({"fact_ids": []}, "empty_selection"),
        ({"fact_ids": [42]}, "invalid_id_type"),
        ({"fact_ids": ["invented"]}, "unknown_statement_id"),
    ],
)
async def test_editor_repairs_only_selection_and_keeps_evidence(bad, reason):
    calls = []

    class Model:
        configured = True

        async def complete(self, system, payload):
            calls.append(copy.deepcopy(payload))
            return bad if len(calls) == 1 else {"fact_ids": ["cause-1", "cause-1"]}

    output = result()
    original = copy.deepcopy(output)
    diagnostics = await explain(output, Model(), repair_once=True)
    assert diagnostics == {
        "attempts": 2,
        "validation_failures": [reason],
        "reason": "repaired",
    }
    assert output["narrative"] == original["facts"]
    assert output["facts"] == original["facts"]
    assert output["limitations"] == original["limitations"]
    assert calls[1]["facts"] == calls[0]["facts"]
    assert calls[1]["allowed_fact_ids"] == ["cause-1"]
    assert "private rejected prose" not in str(calls[1]) + str(diagnostics)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "llm_token_budget_exhausted",
        "llm_deadline_exhausted",
        "llm_http_error",
        "llm_output_truncated",
        "llm_invalid_output",
    ],
)
async def test_no_retry_after_transport_or_budget_failure(failure):
    class Model:
        configured = True
        last_failure = failure
        calls = 0

        async def complete(self, *args):
            self.calls += 1
            return None

    model = Model()
    output = result()
    diagnostics = await explain(output, model, repair_once=True)
    assert model.calls == 1 and diagnostics["reason"] == failure
    assert output["narrative_status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RemoteUncertain, asyncio.CancelledError])
async def test_repair_preserves_remote_fencing(error):
    class Model:
        configured = True
        calls = 0

        async def complete(self, *args):
            self.calls += 1
            if self.calls == 1:
                return {"fact_ids": ["unknown"]}
            raise error()

    with pytest.raises(error):
        await explain(result(), Model(), repair_once=True)


@pytest.mark.asyncio
async def test_ops_default_remains_one_attempt():
    class Model:
        configured = True
        calls = 0

        async def complete(self, *args):
            self.calls += 1
            return {"fact_ids": ["unknown"]}

    model = Model()
    await explain(result(), model)
    assert model.calls == 1
