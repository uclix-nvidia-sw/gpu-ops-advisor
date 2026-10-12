"""Catalog-wide reported-fact admission must not authorize state or actions."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from rcca_agent.retrieval import retrieve_runbooks
from rcca_agent.runbook_contract import validate_runbook
from rcca_agent.workflow import check_conditions, matching_runbooks

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "rcca-agent/runbooks"
PROFILE = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
REVIEW = json.loads((CATALOG / "requirements-review-20261008.json").read_text("utf-8"))
ROWS = [json.loads((CATALOG / e["file"]).read_text("utf-8")) for e in REVIEW["entries"]]
CODE_ROWS = [r for r in ROWS if r["knowledge_key"] != "RB-GENERAL-GPU-NODE"]


@pytest.mark.parametrize("row", CODE_ROWS, ids=lambda r: r["knowledge_key"])
def test_every_code_can_investigate_report_without_promoting_state_or_action(row):
    book = deepcopy(row)
    book["compatibility"] = {"producer_contract": "fleet-component-log-v1"}
    validate_runbook(book, PROFILE["queries"], list(PROFILE["queries"]))
    code = book["content"]["search"]["codes"][0]
    facts = {
        "reported_error_code": code,
        "reported_producer_contract": "fleet-component-log-v1",
    }
    data = {"scope": {"clusters": [{"cluster_id": "arbitrary-cluster"}]}}
    assert matching_runbooks([book], facts, facts, data) == ([book], [])
    for required in facts:
        incomplete = {k: v for k, v in facts.items() if k != required}
        assert matching_runbooks([book], incomplete, incomplete, data) == ([], [book])
    content = book["content"]
    assert content["investigation_only"] is True
    assert not check_conditions(content["applicability_conditions"], facts)
    for rec in content["recommendations"]:
        assert not check_conditions(rec["preconditions"], facts)
        assert rec["execution"] == "not_performed"
    assert "normalized_health" not in facts and "error_code" not in facts
    assert (
        retrieve_runbooks(ROWS, {"summary": code})[0]["runbook"]["knowledge_key"]
        == row["knowledge_key"]
    )


def test_review_covers_every_source_and_preserves_general_adapter_boundary():
    assert len(REVIEW["entries"]) == len(ROWS) == 267
    assert {e["file"] for e in REVIEW["entries"]} == {
        p.relative_to(CATALOG).as_posix() for p in CATALOG.rglob("RB-*.json")
    }
    assert len(CODE_ROWS) == 266
    for e, row in zip(REVIEW["entries"], ROWS):
        digest = hashlib.sha256(
            json.dumps(
                row["content"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert digest == e["after_content_sha256"]
    general = next(r for r in ROWS if r["knowledge_key"] == "RB-GENERAL-GPU-NODE")
    assert general["content"]["required_evidence"] == [
        "observations",
        "producer_contract",
        "normalized_health",
    ]
    assert (
        general["content"]["required_evidence"]
        == json.loads(
            (ROOT / "rcca-agent/src/rcca_agent/general_runbook.json").read_text("utf-8")
        )["required_evidence"]
    )
