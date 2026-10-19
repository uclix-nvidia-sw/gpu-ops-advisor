"""Validate RCA evaluation versions while retaining historical result readers."""

STOP_REASONS = {
    "review_accepted",
    "goal_achieved",
    "goal_not_met",
    "no_available_followup",
    "followup_not_selected",
    "selection_conditions_missing",
    "query_budget_exhausted",
    "llm_budget_exhausted",
    "round_limit_reached",
    "revision_limit_reached",
    "analysis_unresolved",
    "no_usable_evidence",
    "model_unavailable",
    "fast_path",
}


def validate_evaluation(result, evidence):
    from .contracts import content_hash

    evaluation = result.get("quality", {}).get("rca_evaluation")
    if evaluation is None:
        return
    if not isinstance(evaluation, dict) or evaluation.get("schema_version") not in {
        "1",
        "2",
    }:
        raise ValueError("unsupported RCA evaluation schema")
    combined = (
        evaluation.get("schema_version") == "2"
        and evaluation.get("generation_mode") == "combined"
    )
    if evaluation.get("schema_version") == "2" and evaluation.get(
        "generation_mode"
    ) not in {"combined", "separate"}:
        raise ValueError("invalid generation mode")
    by_id = {e["id"]: e for e in evidence}
    collection = evaluation["collection"]
    if collection["status"] not in {"complete", "partial", "failed", "not_requested"}:
        raise ValueError("invalid collection status")
    for row in collection["query_results"]:
        if row["execution_status"] not in {"executed", "skipped"} or not isinstance(
            row["complete"], bool
        ):
            raise ValueError("invalid query result")
        entries = [by_id[ref] for ref in row["evidence_refs"]]
        if row["execution_status"] == "skipped":
            if (
                entries
                or row["complete"]
                or row["tool_status"] is not None
                or not row.get("reason")
            ):
                raise ValueError("invalid skipped query")
        elif not entries or any(
            e["query_id"] != row["query_id"] or e["tool_status"] != row["tool_status"]
            for e in entries
        ):
            raise ValueError("query evidence mismatch")
        if row["complete"] and any(
            e["tool_status"] not in {"ok", "empty"} or not e["quality"].get("complete")
            for e in entries
        ):
            raise ValueError("query completeness mismatch")
    rows = collection["query_results"]
    expected_collection = (
        "complete"
        if rows and all(r["complete"] for r in rows)
        else "partial"
        if any(r["tool_status"] in {"ok", "empty", "partial"} for r in rows)
        else "failed"
    )
    if collection["status"] == "not_requested":
        if rows or not collection.get("reason"):
            raise ValueError("invalid unrequested collection")
    elif collection["status"] != expected_collection or (
        collection["status"] != "complete" and not collection.get("reason")
    ):
        raise ValueError("collection aggregate mismatch")
    analysis_id = evaluation["analysis_id"]
    drafts = [
        e["snapshot"]
        for e in evidence
        if e["query_id"] == "rca_analysis_draft"
        and e["snapshot"].get("analysis_id") == analysis_id
    ]
    if not drafts:
        raise ValueError("missing final draft")
    draft = drafts[-1]
    body = {
        key: draft[key]
        for key in (
            "claims",
            "cause_candidates",
            "recommendations",
            "limitations",
            "input_view_hash",
        )
    }
    if "interpretation" in draft:
        body["interpretation"] = draft["interpretation"]
    if (
        content_hash(body) != analysis_id
        or content_hash(draft["input_view"]) != body["input_view_hash"]
    ):
        raise ValueError("draft hash mismatch")
    if any(
        result[key] != draft[key]
        for key in ("cause_candidates", "recommendations", "limitations")
    ):
        raise ValueError("final result changed after review")
    for key, query in (
        ("evidence", "rca_synthesis" if combined else "evidence_interpretation"),
        ("review", "analysis_review"),
    ):
        stage = evaluation[key]
        if stage["execution_status"] not in {"complete", "failed", "skipped"}:
            raise ValueError("invalid evaluation execution status")
        if stage["execution_status"] != "complete" and not stage.get("reason"):
            raise ValueError("missing evaluation failure reason")
        records = [by_id[ref] for ref in stage["evidence_refs"]]
        if any(
            e["query_id"]
            not in ({query, "evidence_validation"} if key == "evidence" else {query})
            for e in records
        ):
            raise ValueError("evaluation stage reference mismatch")
        if stage["execution_status"] == "complete" and not any(
            e["query_id"] == query for e in records
        ):
            raise ValueError("missing evaluation evidence")
        if (
            key == "evidence"
            and combined
            and stage["execution_status"] == "complete"
            and not any(
                e["query_id"] == "rca_synthesis"
                and e["snapshot"].get("generation_mode") == "combined"
                and e["snapshot"].get("interpretation_status") == "complete"
                and isinstance(e["snapshot"].get("interpretation"), dict)
                for e in records
            )
        ):
            raise ValueError("combined interpretation missing")
        if key == "review":
            if stage["analysis_id"] != analysis_id:
                raise ValueError("review draft mismatch")
            if stage["execution_status"] == "complete":
                if stage["verdict"] not in {
                    "acceptable",
                    "acceptable_after_feedback",
                    "revision_required",
                    "undetermined",
                }:
                    raise ValueError("invalid review verdict")
                if any(
                    e["snapshot"]["analysis_id"] != analysis_id
                    or e["snapshot"]["review"]["verdict"] != stage["verdict"]
                    for e in records
                ):
                    raise ValueError("review evidence mismatch")
                if stage.get("rubric_version") not in (
                    {"1", "2"} if evaluation["schema_version"] == "2" else {"1"}
                ) or any(
                    e["snapshot"]["review"]["criteria"] != stage.get("criteria")
                    for e in records
                ):
                    raise ValueError("review criteria mismatch")
            elif stage["verdict"] is not None:
                raise ValueError("unreviewed verdict must be null")
    investigation = evaluation["investigation"]
    if (
        investigation["status"] != "finished"
        or investigation["stop_reason"] not in STOP_REASONS
    ):
        raise ValueError("invalid investigation state")

    if investigation["stop_reason"] == "goal_achieved":
        objective = investigation.get("objective", {})
        decisions = [
            by_id[ref]["snapshot"]
            for ref in investigation["evidence_refs"]
            if by_id[ref]["query_id"] == "investigation_decision"
        ]
        if (
            evaluation["schema_version"] != "2"
            or objective.get("status") != "achieved"
            or objective.get("analysis_id") != analysis_id
            or evaluation["review"]["execution_status"] != "complete"
            or evaluation["review"]["verdict"]
            not in {"acceptable", "acceptable_after_feedback"}
            or evaluation["review"].get("rubric_version") != "2"
            or not objective.get("compatible")
            or not objective.get("policies")
            or not decisions
            or decisions[-1].get("decision_assessment") != objective
            or any(
                not policy["applicable"]
                or policy.get("unmet_required_evidence")
                or not policy["criteria"]
                or not policy["blocking_conditions"]
                or any(
                    row["status"] != "satisfied"
                    for row in policy["criteria"]
                    if row["required"]
                )
                or any(
                    row["status"] != "satisfied"
                    for row in policy["blocking_conditions"]
                )
                for policy in objective["policies"]
            )
        ):
            raise ValueError("invalid investigation completion")
        answers = {
            row["criterion_id"]: row
            for row in draft.get("interpretation", {}).get("criterion_assessments", [])
        }
        if any(
            row["method"] == "llm"
            and (
                row["key"] not in answers
                or any(
                    row[key] != answers[row["key"]][key]
                    for key in ("status", "finding_refs", "evidence_refs")
                )
            )
            for policy in objective["policies"]
            for row in policy["criteria"]
        ):
            raise ValueError("completion does not match reviewed interpretation")


def source_evaluation(body):
    """Ops carries source judgments without treating foreign IDs as local evidence."""
    value = body.get("quality", {}).get("rca_evaluation")
    if not value:
        return {
            "schema_version": None,
            "review_status": "legacy_unreviewed",
            "limitations": body.get("limitations", []),
        }
    if value.get("schema_version") not in {"1", "2"}:
        return {
            "schema_version": value.get("schema_version"),
            "review_status": "unsupported_schema",
            "review_verdict": None,
            "limitations": body.get("limitations", []),
        }
    return {
        "schema_version": value.get("schema_version"),
        "analysis_id": value.get("analysis_id"),
        "generation_mode": value.get("generation_mode"),
        "objective_status": value.get("investigation", {})
        .get("objective", {})
        .get("status"),
        "collection_status": value.get("collection", {}).get("status"),
        "evidence_status": value.get("evidence", {}).get("execution_status"),
        "review_status": value.get("review", {}).get("execution_status"),
        "review_verdict": value.get("review", {}).get("verdict"),
        "review_reason": value.get("review", {}).get("reason"),
        "stop_reason": value.get("investigation", {}).get("stop_reason"),
        "limitations": body.get("limitations", []),
    }
