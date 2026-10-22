"""Runbook investigation objectives; never promote report facts into causes."""

BLOCKERS = {
    "scope_unverified",
    "identity_conflict",
    "required_query_incomplete",
    "conflicting_reports",
}
STATUSES = {"satisfied", "not_satisfied", "unknown"}


def validate_policy(content):
    from .runbook_contract import _require, _strings, _text, CODE

    policy = content.get("decision_policy")
    # Single-phase incident plans do not need an iterative goal policy.
    if (
        "decision_policy" not in content
        and content.get("schema") in {"gpu-rca-runbook/1.1", "gpu-rca-runbook/1.2"}
        and content.get("observation_plan")
    ):
        return
    if content.get("schema") not in {"gpu-rca-runbook/1.1", "gpu-rca-runbook/1.2"}:
        _require(policy is None, "decision_policy requires Runbook 1.1")
        return
    _require(
        content.get("investigation_only") is True,
        "decision_policy requires investigation_only",
    )
    _require(
        isinstance(policy, dict)
        and set(policy)
        == {
            "goal",
            "applies_when",
            "completion_criteria",
            "blocking_conditions",
            "non_blocking_unknowns",
            "followup_links",
        },
        "decision_policy: fields",
    )
    goal = policy["goal"]
    _require(
        isinstance(goal, dict)
        and set(goal) == {"id", "question", "conclusion_scope"}
        and goal["id"] == "identify_error_report",
        "decision_policy: goal",
    )
    for value in goal.values():
        _text(value, "decision_policy.goal")
    applies = policy["applies_when"]
    _require(
        isinstance(applies, dict)
        and (
            set(applies) == {"reported_error_code", "reported_producer_contract"}
            or content.get("schema") == "gpu-rca-runbook/1.2"
            and set(applies) - {"reported_reason"}
            == {
                "reported_component",
                "reported_normalized_health",
                "reported_producer_contract",
            }
        ),
        "decision_policy: applies_when",
    )
    if "reported_error_code" in applies:
        _require(
            isinstance(applies["reported_error_code"], str)
            and CODE.fullmatch(applies["reported_error_code"]),
            "decision_policy: error code",
        )
    else:
        _text(applies["reported_component"], "decision_policy.component")
        _require(
            applies["reported_normalized_health"] == "unhealthy",
            "decision_policy: error health",
        )
        if "reported_reason" in applies:
            _text(applies["reported_reason"], "decision_policy.reason")
    _text(applies["reported_producer_contract"], "decision_policy.producer")
    _require(
        set(_strings(policy["blocking_conditions"], "blocking_conditions")) == BLOCKERS,
        "decision_policy: mandatory blockers",
    )
    unknowns = _strings(policy["non_blocking_unknowns"], "non_blocking_unknowns")
    _require(
        set(unknowns)
        <= {
            "causal_confirmation_evidence",
            "current_health",
            "physical_or_synthetic_origin",
        },
        "decision_policy: unknowns",
    )
    criteria, seen = policy["completion_criteria"], set()
    _require(
        isinstance(criteria, list) and 1 <= len(criteria) <= 8,
        "decision_policy: criteria",
    )
    for row in criteria:
        _require(
            isinstance(row, dict)
            and set(row) == {"id", "question", "method", "required"},
            "decision_policy: criterion fields",
        )
        _text(row["id"], "criterion.id")
        _text(row["question"], "criterion.question")
        _require(
            row["id"] not in seen
            and type(row["required"]) is bool
            and row["method"] in {"code", "llm"},
            "decision_policy: criterion",
        )
        _require(
            row["method"] != "code" or row["id"] in {"reported_error", "scoped_source"},
            "decision_policy: code criterion",
        )
        seen.add(row["id"])
    _require(
        {"reported_error", "scoped_source"}
        <= {r["id"] for r in criteria if r["method"] == "code" and r["required"]},
        "decision_policy: required code criteria",
    )
    _require(
        any(r["method"] == "llm" and r["required"] for r in criteria),
        "decision_policy: semantic criterion required",
    )
    steps = {s["query_id"]: s for s in content.get("observation_plan", [])}
    linked = set()
    _require(
        isinstance(policy["followup_links"], list), "decision_policy: followup_links"
    )
    for row in policy["followup_links"]:
        _require(
            isinstance(row, dict)
            and set(row)
            == {"query_id", "criterion_ids", "required", "expected_effect"},
            "decision_policy: followup fields",
        )
        query = row["query_id"]
        _require(
            isinstance(query, str)
            and query in steps
            and query not in linked
            and type(row["required"]) is bool,
            "decision_policy: followup query",
        )
        _require(
            not steps[query]["required"] or row["required"],
            "decision_policy: cannot relax required query",
        )
        _require(
            set(_strings(row["criterion_ids"], "criterion_ids", nonempty=True)) <= seen,
            "decision_policy: criterion link",
        )
        _text(row["expected_effect"], "expected_effect")
        linked.add(query)
    _require(linked == set(steps), "decision_policy: every query needs purpose")
