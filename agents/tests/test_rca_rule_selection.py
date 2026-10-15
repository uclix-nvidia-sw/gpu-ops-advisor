from copy import deepcopy
import json
from pathlib import Path

import pytest
from rcca_agent.workflow import rule_followup
from rcca_agent.runbook_contract import validate_runbook

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "kind,key,expected",
    [
        ("xid", "RB-XID-79", ["D44", "D02", "D11"]),
        ("sxid", "RB-SXID-11001", ["D02", "D13"]),
    ],
)
def test_authored_rules_require_scoped_reports(kind, key, expected):
    row = json.loads(
        (ROOT / f"rcca-agent/runbooks/{kind}/{key}.json").read_text("utf-8")
    )
    plan = row["content"]["observation_plan"]
    books = [{"id": "revision-1"}]
    facts = {"reported_error_code", "reported_producer_contract"}
    selected, governed, findings = rule_followup(
        books, {"revision-1": plan}, expected, ["causal_confirmation_evidence"], facts
    )
    assert selected == expected
    assert governed == set(expected)
    assert all(
        f["eligible"] and f["runbook_revision_id"] == "revision-1" for f in findings
    )
    assert facts == {
        "reported_error_code",
        "reported_producer_contract",
    }  # No health/identity promotion.
    for missing in facts:
        selected, _, findings = rule_followup(
            books,
            {"revision-1": plan},
            expected,
            ["causal_confirmation_evidence"],
            facts - {missing},
        )
        assert not selected
        assert all(f["missing_prerequisites"] == [missing] for f in findings)
    assert not rule_followup(
        books, {"revision-1": plan}, expected, ["unknown_value"], facts
    )[0]
    assert not rule_followup(
        books, {"revision-1": plan}, [], ["causal_confirmation_evidence"], facts
    )[0]


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.update(independent=False),
        lambda r: r.update(missing_any=[]),
        lambda r: r.update(missing_any=["invented"]),
        lambda r: r.update(requires_all=["invented"]),
        lambda r: r.update(extra=True),
    ],
)
def test_rule_contract_rejects_invalid_conditions(edit):
    row = json.loads(
        (ROOT / "rcca-agent/runbooks/xid/RB-XID-79.json").read_text("utf-8")
    )
    queries = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))[
        "queries"
    ]
    edit(row["content"]["observation_plan"][1]["selection"])
    with pytest.raises(ValueError):
        validate_runbook(row, queries, list(queries), authoring=True)


def test_rule_priority_and_revision_provenance():
    rule = {
        "missing_any": ["causal_confirmation_evidence"],
        "requires_all": [],
        "independent": True,
    }
    steps = [
        {
            "query_id": q,
            "priority": p,
            "selection": deepcopy(rule),
            "purpose": "context only",
        }
        for q, p in [("D02", 5), ("D44", 2), ("D11", 3), ("D04", 4)]
    ]
    selected, _, findings = rule_followup(
        [{"id": "a"}, {"id": "b"}],
        {"a": steps, "b": steps},
        ["D02", "D44", "D11", "D04"],
        ["causal_confirmation_evidence"],
        set(),
    )
    assert selected == ["D44", "D11", "D04", "D02"]
    assert len(findings) == 8


@pytest.mark.parametrize("value", [False, "true", 1, None])
def test_exploration_requires_boolean_opt_in(value):
    row = json.loads(
        (ROOT / "rcca-agent/runbooks/xid/RB-XID-79.json").read_text("utf-8")
    )
    step = row["content"]["observation_plan"][1]
    step.pop("selection")
    step["exploratory_llm"] = value
    queries = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))[
        "queries"
    ]
    with pytest.raises(ValueError):
        validate_runbook(row, queries, list(queries), authoring=True)


def test_explicit_exploration_contract_and_conflicts():
    row = json.loads(
        (ROOT / "rcca-agent/runbooks/xid/RB-XID-79.json").read_text("utf-8")
    )
    queries = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))[
        "queries"
    ]
    step = row["content"]["observation_plan"][1]
    step["exploratory_llm"] = True
    with pytest.raises(ValueError):
        validate_runbook(row, queries, list(queries), authoring=True)
    step.pop("selection")
    assert validate_runbook(row, queries, list(queries), authoring=True)
    step["required"] = True
    with pytest.raises(ValueError):
        validate_runbook(row, queries, list(queries), authoring=True)
