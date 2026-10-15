"""Keep one immutable Runbook source from selection through review."""

from copy import deepcopy

import pytest

from agent_common.runtime import attempt_context
import test_rca_analysis as cases


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "fast",
        "followup",
        "review_followup",
        "missing_runbook",
        "unconfigured",
        "xid",
        "sxid",
    ],
)
async def test_selected_sources_precede_collection_and_keep_their_references(
    mode, monkeypatch
):
    run = cases.run
    checked = []

    async def inspect(tools):
        books = deepcopy(attempt_context.get()["context"]["runbooks"])
        output = await run(tools)
        assert attempt_context.get()["context"]["runbooks"] == books
        evidence = output["evidence"]
        index = {entry["id"]: i for i, entry in enumerate(evidence)}
        sources = {
            entry["input"]["revision_id"]: entry
            for entry in evidence
            if entry["query_id"] == "runbook"
        }
        assert len(sources) == sum(entry["query_id"] == "runbook" for entry in evidence)
        selection = next(
            entry for entry in evidence if entry["query_id"] == "runbook_selection"
        )
        plan = next(
            entry for entry in evidence if entry["query_id"] == "investigation_plan"
        )
        assert plan["snapshot"]["selection_evidence_id"] == selection["id"]
        expected = {row["revision_id"] for row in plan["snapshot"]["runbooks"]}
        assert set(plan["snapshot"]["evidence_refs"]) == {
            sources[revision]["id"] for revision in expected
        }
        for revision in expected:
            assert (
                index[selection["id"]]
                < index[sources[revision]["id"]]
                < index[plan["id"]]
            )
        queries = [entry for entry in evidence if entry["query_id"].startswith("D")]
        assert all(index[plan["id"]] < index[entry["id"]] for entry in queries)
        extensions = [
            entry
            for entry in evidence
            if entry["query_id"] == "investigation_plan_extension"
        ]
        if mode in {"xid", "sxid"}:
            assert extensions
            assert index[queries[0]["id"]] < index[extensions[0]["id"]]
        if mode == "fast":
            assert len(sources) == 1 and "builtin-general" not in sources
        for entry in evidence:
            if entry["query_id"] == "investigation_plan_extension":
                revision = entry["snapshot"]["runbook_revision_id"]
                expected.add(revision)
                assert entry["snapshot"]["evidence_refs"] == [sources[revision]["id"]]
                assert index[sources[revision]["id"]] < index[entry["id"]]
        assert set(sources) == expected
        for source in sources.values():
            assert source["quality"]["selection_evidence_id"] == selection["id"]
        for book in books:
            if book["id"] in sources:
                assert sources[book["id"]]["snapshot"] == book["content"]
                assert sources[book["id"]]["query_version"] == str(book["revision"])
        for entry in evidence:
            if entry["query_id"] == "rca_analysis_draft":
                for source in (
                    entry["snapshot"].get("input_view", {}).get("rule_sources", [])
                ):
                    assert (
                        source["id"] in index
                        and index[source["id"]] < index[entry["id"]]
                    )
        checked.append(True)
        return output

    monkeypatch.setattr(cases, "run", inspect)
    # Reuse the real workflow fixture's existing query/result/validation assertions.
    await cases.test_query_first_collection_analysis_and_failure_boundaries(
        mode, monkeypatch
    )
    assert checked
