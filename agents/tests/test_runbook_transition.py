"""Offline proposals preserve facts and do not imply publication or approval."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from agent_common.contracts import content_hash
from rcca_agent.runbook_admin import check
from rcca_agent.runbook_transition import propose_transition

ROOT = Path(__file__).resolve().parents[2]
BOOKS = ROOT / "rcca-agent/runbooks"


@pytest.mark.parametrize("path", sorted(BOOKS.rglob("RB-*.json")), ids=lambda p: p.stem)
def test_catalog_proposal_preserves_source_and_requires_scoped_facts(path):
    row = json.loads(path.read_text("utf-8"))
    original = deepcopy(row)
    candidate, review = propose_transition(row)
    assert row == original
    if candidate is None:
        assert review["status"] == "held" and review["reasons"]
        return
    profile = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    check(candidate, profile)
    for field in (
        "sources",
        "analysis_guidance",
        "applicability_conditions",
        "required_evidence",
        "recommendations",
    ):
        assert candidate["content"][field] == row["content"][field]
    plan = candidate["content"]["observation_plan"]
    optional = [s for s in plan if not s["required"]]
    assert optional
    assert all(step["selection"]["requires_all"] for step in optional)
    assert "state" not in candidate and "reviewed_content_hash" not in candidate


def test_changed_published_content_cannot_be_proposed_as_reviewed():
    row = json.loads((BOOKS / "xid/RB-XID-54.json").read_text("utf-8"))
    row.update(content_hash=content_hash(row["content"]), reviewed_content_hash="stale")
    proposal, review = propose_transition(row)
    assert proposal is None
    assert "source_hash_mismatch" in review["reasons"]
