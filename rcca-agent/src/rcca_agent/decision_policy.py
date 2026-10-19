"""Runbook investigation objectives; never promote report facts into causes."""

from copy import deepcopy

from agent_common.rca_evaluation import review_scope_status

from .analysis_review import ACCEPTED_VERDICTS
from .requirement_diagnostics import _scoped_reports, reported_facts

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


def assess_policies(books, data, health, events, gaps):
    """Use existing scoped report parsing; missing or contradictory links stay unknown."""
    policies = [book for book in books if book["content"].get("decision_policy")]
    if not policies:
        return None
    reports, scoped_events = _scoped_reports(health, events, data)
    facts = reported_facts(health, events, data)
    refs = sorted(
        {ref for row in reports + scoped_events for ref in row.get("evidence_refs", [])}
    )
    codes = {
        row["error_code"] for row in reports + scoped_events if row.get("error_code")
    }
    blockers = {
        "scope_unverified": "satisfied" if refs else "unknown",
        "identity_conflict": "not_satisfied"
        if data.get("identity_conflicts")
        or any(e.get("device_mapping") == "conflicting" for e in events)
        else "satisfied",
        "required_query_incomplete": "not_satisfied"
        if any(g.startswith("required_query:") for g in gaps)
        else "satisfied",
        "conflicting_reports": "unknown"
        if len(codes) > 1
        else "satisfied"
        if codes
        else "unknown",
    }
    rows = []
    for book in policies:
        policy = book["content"]["decision_policy"]
        policy_blockers = dict(blockers)
        if "reported_component" in policy["applies_when"]:
            # A component report goal must not require an NVIDIA numeric code.
            # Mixed reported states still block completion; recorded time alone
            # cannot establish a recovery transition.
            states = {
                r.get("normalized_health")
                for r in reports
                if r.get("component") == policy["applies_when"]["reported_component"]
            }
            policy_blockers["conflicting_reports"] = (
                "satisfied" if states == {"unhealthy"} else "unknown"
            )
        matched = all(
            facts.get(key) == value for key, value in policy["applies_when"].items()
        )
        criteria = []
        for criterion in policy["completion_criteria"]:
            state = "unknown"
            if criterion["method"] == "code":
                state = (
                    (
                        "satisfied"
                        if matched
                        else "not_satisfied"
                        if all(key in facts for key in policy["applies_when"])
                        else "unknown"
                    )
                    if criterion["id"] == "reported_error"
                    else ("satisfied" if refs else "unknown")
                )
            criteria.append(
                {
                    **criterion,
                    "key": book["id"] + ":" + criterion["id"],
                    "status": state,
                    "evidence_refs": refs if criterion["method"] == "code" else [],
                    "finding_refs": [],
                }
            )
        rows.append(
            {
                "runbook_revision_id": book["id"],
                "content_hash": book["content_hash"],
                "goal": policy["goal"],
                "applicable": matched,
                "unmet_required_evidence": sorted(
                    set(book["content"].get("required_evidence", [])) & set(gaps)
                ),
                "criteria": criteria,
                "blocking_conditions": [
                    {"id": key, "status": value, "evidence_refs": refs}
                    for key, value in policy_blockers.items()
                ],
                "non_blocking_unknowns": policy["non_blocking_unknowns"],
                "followup_links": policy["followup_links"],
            }
        )
    return {
        "schema_version": "1",
        "policies": rows,
        "compatible": len(policies) == len(books),
        "status": "unknown",
        "scope": deepcopy(data["scope"]),
        "target": deepcopy(data.get("target", {})),
        "time_range": deepcopy(data["time_range"]),
    }


def finish_assessment(
    assessment, interpretation, review, analysis_id, caveat_withheld=False
):
    value = deepcopy(assessment)
    if not value:
        return None
    answers = {
        r["criterion_id"]: r
        for r in (interpretation or {}).get("criterion_assessments", [])
    }
    # Without a retained finding nothing explains the report; a caveat lost to
    # format repair would make the reviewed draft look surer than the author wrote.
    scope = (
        review_scope_status(review)
        if (interpretation or {}).get("findings") and not caveat_withheld
        else "unknown"
    )
    for policy in value["policies"]:
        for row in policy["criteria"]:
            if row["method"] == "llm":
                # The author's self-assessment is advisory; the independent review
                # rubric decides whether the conclusion stayed within the evidence.
                row.update(
                    status=scope,
                    evidence_refs=list(review["evidence_refs"]),
                    finding_refs=[],
                    author_status=answers.get(row["key"], {}).get("status"),
                )
    criteria_met = value["compatible"] and all(
        p["applicable"]
        and not p["unmet_required_evidence"]
        and all(r["status"] == "satisfied" for r in p["criteria"] if r["required"])
        and all(r["status"] == "satisfied" for r in p["blocking_conditions"])
        for p in value["policies"]
    )
    value.update(
        status="achieved"
        if criteria_met
        and review["execution_status"] == "complete"
        and review["verdict"] in ACCEPTED_VERDICTS
        and review["analysis_id"] == analysis_id
        else "not_achieved",
        analysis_id=analysis_id,
        review_evidence_refs=review["evidence_refs"],
    )
    return value


def model_assessment(value):
    """Preserve objective/criteria; omit optional query prose and repeated code refs."""
    result = deepcopy(value)
    for policy in result["policies"]:
        policy["followup_links"] = [
            r for r in policy["followup_links"] if r["required"]
        ]
        for row in policy["blocking_conditions"]:
            row.pop("evidence_refs", None)
        for row in policy["criteria"]:
            if row["method"] == "code":
                row.pop("question", None)
                row.pop("finding_refs", None)
    result["input_selection"] = (
        "required_queries_and_criteria; optional_query_prose_omitted"
    )
    return result
