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
        if row["knowledge_key"] == "RB-GENERAL-GPU-NODE":
            followup = json.loads(
                (CATALOG / "general-requirements-review-20261012.json").read_text(
                    "utf-8"
                )
            )
            assert followup["before_content_sha256"] == e["after_content_sha256"]
            assert digest == followup["after_content_sha256"]
        elif row["knowledge_key"] in {"RB-XID-79", "RB-SXID-11001"}:
            followups = json.loads(
                (CATALOG / "operator-guidance-review-20261013.json").read_text("utf-8")
            )
            followup = next(
                item for item in followups["entries"] if item["file"] == e["file"]
            )
            assert followup["before_content_sha256"] == e["after_content_sha256"]
            assert digest == followup["after_content_sha256"]
            original = deepcopy(row["content"])
            del original["operator_guidance"]
            assert (
                hashlib.sha256(
                    json.dumps(
                        original,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                == e["after_content_sha256"]
            )
        else:
            assert digest == e["after_content_sha256"]
    general = next(r for r in ROWS if r["knowledge_key"] == "RB-GENERAL-GPU-NODE")
    assert general["content"]["required_evidence"] == [
        "observations",
    ]
    assert (
        general["content"]["required_evidence"]
        == json.loads(
            (ROOT / "rcca-agent/src/rcca_agent/general_runbook.json").read_text("utf-8")
        )["required_evidence"]
    )


def test_general_observations_do_not_require_or_establish_health():
    book = deepcopy(
        next(r for r in ROWS if r["knowledge_key"] == "RB-GENERAL-GPU-NODE")
    )
    book["compatibility"] = {"cluster_id": "fixture"}
    data = {"scope": {"clusters": [{"cluster_id": "fixture"}]}}
    assert matching_runbooks([book], {}, {"observations": True}, data) == ([book], [])
    assert matching_runbooks([book], {}, {}, data) == ([], [book])
    assert book["content"]["investigation_only"] is True
    assert book["content"]["recommendations"] == []
    assert not check_conditions(
        [{"field": "normalized_health", "equals": "unhealthy"}], {}
    )
    old = deepcopy(book)
    old["content"]["required_evidence"] = [
        "observations",
        "producer_contract",
        "normalized_health",
    ]
    assert matching_runbooks([old], {}, {"observations": True}, data) == ([], [old])
