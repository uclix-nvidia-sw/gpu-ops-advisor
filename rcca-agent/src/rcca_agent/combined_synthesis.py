"""One bounded author request, independent interpretation/causal reference domains."""

from copy import deepcopy
import re
import time

from agent_common.contracts import content_hash
from .evidence_interpretation import (
    complete_once,
    INTERPRET_CONTEXT,
    INTERPRET_RULES,
    CRITERIA_PROMPT,
    semantic_criteria,
    validate_interpretation,
    ResponseValidationError,
)
from .analysis_values import resolve_values
from .prompts import SYNTHESIS_CONTEXT, SYNTHESIS_RULES, TRIAGE_CONTEXT
from .synthesis import (
    synthesis_view,
    validate_synthesis,
    identifier_tokens,
    SynthesisValidationError,
)
from .synthesis_context import bounded_context, encoded_size

NUMERIC_REPAIR = (
    "Previous findings were dropped because their prose contained quantities. "
    "Rewrite each finding without digits or number words; cite values only through "
    "the supplied value references. Keep the same evidence references."
)

COMBINED = (
    SYNTHESIS_CONTEXT
    + SYNTHESIS_RULES
    + "\nThe following rules apply inside interpretation only:\n"
    + INTERPRET_CONTEXT
    + INTERPRET_RULES
    + """
Return JSON with exactly these keys:
{"interpretation": {
  "findings": [{"id":"finding-1", "statement":"자료에 기록된 대상·오류·시각과 그 의미",
    "kind":"observed", "evidence_refs":["evidence id"]}],
  "unknowns":[], "conflicts":[], "limitations":[]},
 "hypotheses": [],
 "limitations":[]}
Use supported Korean analysis. Interpretation items are objects:
unknowns: {"statement":"...", "evidence_refs":[], "reason":"..."};
conflicts/limitations: {"statement":"...", "evidence_refs":["actual id"]}.
Separate event time from log time; order is not recovery. Explain reported errors
and connect their observed context, metric behavior and host history. Keep causal
hypotheses distinct from recorded facts; use Runbooks to interpret debugging priorities.
Hypothesis objects have claim, supporting_refs, contradicting_refs, missing_inputs, finding_refs.
finding_refs cite this response. Empty hypotheses are valid; symptoms are not causes.
Hypothesis supporting_refs cite observation_refs, never diagnostics or Runbooks.
Interpretation cites input_evidence_refs; it is not independent evidence.
Top-level limitations and hypothesis missing_inputs are Korean strings.
State limits once. Do not invent causes/actions or self-review.
Use investigation_summary's full-collection comparisons in findings.
Other GPUs' metrics cannot describe the reported device. Error text is not physical proof.
Validation feedback concerns response structure."""
)


def author_prompt(payload):
    return (
        TRIAGE_CONTEXT
        + COMBINED
        + (
            CRITERIA_PROMPT
            + "\nIn this combined response, criterion_assessments belongs only inside "
            "interpretation, never at the top level."
            if semantic_criteria(payload) is not None
            else ""
        )
    )


ITEM_PATH = re.compile(r"^\$\.(findings|unknowns|conflicts|limitations)\[(\d+)\]")


def salvage_interpretation(value, refs, criteria, observation_refs, dropped):
    """Drop invalid list items one at a time; structural errors still reject all."""
    value = deepcopy(value)
    unknown = [
        {
            "criterion_id": key,
            "status": "unknown",
            "finding_refs": [],
            "evidence_refs": [],
        }
        for key in sorted(criteria or ())
    ]
    # ponytail: re-validates per repaired item; bounded by 4 lists x 16 items
    # (strip then drop) + criteria.
    for _ in range(2 * 4 * 16 + 2):
        try:
            return validate_interpretation(value, refs, criteria, observation_refs)
        except ResponseValidationError as exc:
            detail, item = exc.diagnostic, ITEM_PATH.match(exc.diagnostic["path"])
            if (
                item
                and detail["rule"] == "unexpected_fields"
                and isinstance(value, dict)
                and detail["path"] == item[0]
            ):
                # Extra keys add no meaning to a statement; keep the item, including
                # its caveat, instead of dropping it and withholding the goal.
                keep = {"statement", "evidence_refs", "reason"} | (
                    {"id", "kind"} if item[1] == "findings" else set()
                )
                rows = value[item[1]]
                rows[int(item[2])] = {
                    k: v for k, v in rows[int(item[2])].items() if k in keep
                }
                dropped.append(
                    {
                        **detail,
                        "path": "$.interpretation" + detail["path"][1:],
                        "action": "stripped",
                    }
                )
                continue
            if item and isinstance(value, dict):
                del value[item[1]][int(item[2])]
            elif (
                criteria is not None
                and isinstance(value, dict)
                and detail["path"].startswith("$.criterion_assessments")
                and value.get("criterion_assessments") != unknown
            ):
                # An invalid semantic answer means "not established", never "satisfied".
                value["criterion_assessments"] = unknown
            else:
                raise
            dropped.append(
                {
                    **detail,
                    "path": "$.interpretation" + detail["path"][1:],
                    "action": "dropped",
                }
            )
            if (
                item
                and item[1] != "findings"
                and criteria is not None
                and value.get("criterion_assessments") != unknown
            ):
                # Unknowns, conflicts and limitations bound the conclusion. Losing one
                # would make it look surer, so semantic criteria cannot complete the goal.
                value["criterion_assessments"] = unknown
                dropped.append(
                    {
                        "code": "criterion_withheld",
                        "path": "$.interpretation.criterion_assessments",
                        "rule": "caveat_dropped",
                        "action": "withheld",
                    }
                )
    raise ResponseValidationError("interpretation_list", "$", "salvage_limit")


def analysis_path(detail):
    code = detail["code"]
    path = "$.limitations" if code == "invalid_limitations" else "$.hypotheses"
    if "limitation_index" in detail:
        path += f"[{detail['limitation_index']}]"
    if "hypothesis_index" in detail:
        path += f"[{detail['hypothesis_index']}]"
        if code == "finding_dependency":
            path += ".finding_refs"
        elif code not in {
            "invalid_hypothesis_shape",
            "invalid_hypothesis_references",
            "invalid_evidence_references",
        }:
            path += ".claim"
    return path


def validate_author(response, view, criteria, details=None, dropped=None):
    details = details if details is not None else []
    dropped = dropped if dropped is not None else []
    interpretation, candidates, limitations, errors = None, [], [], []
    if not isinstance(response, dict) or set(response) != {
        "interpretation",
        "hypotheses",
        "limitations",
    }:
        details.append({"code": "author_shape", "path": "$", "rule": "shape"})
        return None, [], [], ["author_shape"]
    try:
        interpretation = salvage_interpretation(
            response["interpretation"],
            view["input_evidence_refs"],
            criteria,
            view["observation_refs"],
            dropped,
        )
    except (ValueError, TypeError, KeyError) as exc:
        errors.append("interpretation_invalid")
        detail = (
            exc.diagnostic
            if isinstance(exc, ResponseValidationError)
            else {
                "code": "invalid_stage_value",
                "path": "$",
                "rule": "unexpected_value_type",
            }
        )
        details.append({**detail, "path": "$.interpretation" + detail["path"][1:]})
    if interpretation is not None and "incident_brief" in view:
        retained = []
        for index, finding in enumerate(interpretation["findings"]):
            try:
                prose, expanded = resolve_values(
                    finding["statement"], finding["evidence_refs"], view
                )
                validate_synthesis(
                    {"hypotheses": [], "limitations": [prose]},
                    finding["evidence_refs"],
                    view["device_observations"] + view["error_events"],
                    identifier_tokens(view),
                    view["query_quality"],
                )
                retained.append({**finding, "statement": expanded})
            except ValueError as exc:
                dropped.append(
                    {
                        "code": "invalid_finding_prose",
                        "path": f"$.interpretation.findings[{index}]",
                        "rule": getattr(exc, "diagnostic", {}).get(
                            "rule", "invalid_value_reference"
                        ),
                        "action": "dropped",
                    }
                )
        interpretation["findings"] = retained
        if not retained and view.get("incident_brief"):
            errors.append("empty_incident_analysis")
            details.append(
                {
                    "code": "empty_incident_analysis",
                    "path": "$.interpretation.findings",
                    "rule": "no_retained_findings",
                }
            )
    try:
        findings = {row["id"] for row in (interpretation or {}).get("findings", [])}
        hypotheses = response["hypotheses"]
        if interpretation is None:
            raise SynthesisValidationError("interpretation_dependency")
        if not isinstance(hypotheses, list) or len(hypotheses) > 8:
            raise SynthesisValidationError("invalid_hypotheses")
        hypotheses = list(hypotheses)
        stated = response["limitations"]
        stated = list(stated) if isinstance(stated, list) else stated
        # ponytail: one dropped claim per pass; bounded by 8 hypotheses + 32 limitations.
        for _ in range(8 + 32 + 1):
            try:
                plain = []
                for index, h in enumerate(hypotheses):
                    if not isinstance(h, dict):
                        raise SynthesisValidationError(
                            "invalid_hypothesis_shape", index=index
                        )
                    if (
                        not isinstance(h.get("finding_refs"), list)
                        or not h["finding_refs"]
                        or any(
                            not isinstance(ref, str) or ref not in findings
                            for ref in h["finding_refs"]
                        )
                    ):
                        raise SynthesisValidationError(
                            "finding_dependency", index=index
                        )
                    plain.append({k: v for k, v in h.items() if k != "finding_refs"})
                candidates = validate_synthesis(
                    {"hypotheses": plain, "limitations": stated},
                    view["observation_refs"],
                    view["device_observations"] + view["error_events"],
                    identifier_tokens(view),
                    view["query_quality"],
                )
                break
            except SynthesisValidationError as exc:
                # A rejected claim is removed, not rewritten; shape errors reject all.
                detail = dict(exc.diagnostic)
                if "hypothesis_index" in detail:
                    del hypotheses[detail["hypothesis_index"]]
                elif "limitation_index" in detail:
                    del stated[detail["limitation_index"]]
                else:
                    raise
                dropped.append(
                    {**detail, "path": analysis_path(detail), "action": "dropped"}
                )
        else:
            raise SynthesisValidationError("invalid_hypotheses", rule="salvage_limit")
        for candidate, hypothesis in zip(candidates, hypotheses, strict=True):
            candidate["finding_refs"] = hypothesis["finding_refs"]
        limitations = stated
    except (SynthesisValidationError, ValueError, TypeError, KeyError) as exc:
        candidates = []
        errors.append("analysis_invalid")
        # The typed exception contains fixed codes/offsets only, never rejected text.
        detail = (
            dict(exc.diagnostic)
            if isinstance(exc, SynthesisValidationError)
            else {"code": "invalid_analysis_value", "rule": "shape"}
        )
        details.append({**detail, "path": analysis_path(detail)})
    return interpretation, candidates, limitations, errors


async def generate(llm, payload, diagnostics):
    prompt = author_prompt(payload)
    before = dict(getattr(llm, "usage", {}))
    _, limit = synthesis_view(
        payload,
        getattr(llm, "remaining", 32768),
        getattr(llm, "reserved_tokens", 0),
        prompt,
    )
    # Send the same bounded view the budget planned; a smaller fixed cap dropped
    # every auxiliary metric source in production (D09 only, ~5.9KB).
    view = bounded_context(payload, limit)
    dropped = []
    check = {
        "input_bytes": encoded_size(view),
        "max_input_bytes": limit,
        "model_called": False,
    }
    if hasattr(llm, "request_budget"):
        check.update(llm.request_budget(prompt, view, "synthesis"))
    trace = {
        "attempt": 1,
        "input_view": deepcopy(view),
        "input_view_hash": content_hash(view),
        "request_hash": content_hash(view),
        "request_check": check,
        "interpretation": "excluded",
        "analysis": "excluded",
    }
    diagnostics.update(
        generation_mode="combined",
        response_schema="rca-author/1",
        requests=[trace],
        validation_failures=[],
        error_code=None,
        input_bytes=encoded_size(view),
        original_input_bytes=encoded_size(payload),
    )
    interpretation, candidates, limitations, errors = None, [], [], []
    if not llm.configured:
        diagnostics["error_code"] = "model_not_configured"
    elif (
        encoded_size(view) > limit
        or not view["observation_refs"]
        or check.get("output_token_cap", 1) <= 0
    ):
        diagnostics["error_code"] = "llm_context_budget_exhausted"
    else:
        if time.monotonic() >= getattr(llm, "deadline", float("inf")):
            raise TimeoutError("RCA author deadline exhausted")
        check["model_called"] = True
        request_limit = getattr(llm, "request_attempt_limit", 3)
        llm.request_attempt_limit = 1
        try:
            response = await complete_once(llm, prompt, view, "synthesis", diagnostics)
        finally:
            llm.request_attempt_limit = request_limit
        if response is None:
            diagnostics["error_code"] = (
                getattr(llm, "last_failure", None) or "llm_no_response"
            )
        else:
            details = []
            interpretation, candidates, limitations, errors = validate_author(
                response, view, semantic_criteria(payload), details, dropped
            )
            if errors and any(d.get("rule") == "numeric" for d in dropped):
                # One repair request with fixed feedback; the same view is revalidated.
                repair = {**view, "repair_feedback": NUMERIC_REPAIR}
                llm.request_attempt_limit = 1
                try:
                    retry = await complete_once(
                        llm, prompt, repair, "synthesis", diagnostics
                    )
                finally:
                    llm.request_attempt_limit = request_limit
                diagnostics["numeric_repair"] = "failed"
                if retry is not None:
                    retry_details, retry_dropped = [], []
                    result = validate_author(
                        retry,
                        view,
                        semantic_criteria(payload),
                        retry_details,
                        retry_dropped,
                    )
                    if not result[3]:
                        interpretation, candidates, limitations, errors = result
                        details, dropped[:] = retry_details, retry_dropped
                        diagnostics["numeric_repair"] = "applied"
            if errors:
                diagnostics["error_code"] = "invalid_author_response"
                diagnostics["validation_failures"] = [
                    {"attempt": 1, "reasons": errors, "details": details}
                ]
    valid = interpretation is not None and not errors
    trace.update(
        interpretation="validated_response"
        if interpretation is not None
        else "excluded",
        analysis="validated_response" if valid else "excluded",
        excluded_reasons=errors,
    )
    usage = getattr(llm, "usage", {})
    diagnostics.update(
        request_attempts=usage.get("request_attempts", 0)
        - before.get("request_attempts", 0),
        response_calls=usage.get("calls", 0) - before.get("calls", 0),
        dropped_items=dropped,
        input_view=view,
        input_view_hash=content_hash(view),
        input_evidence_refs=view["input_evidence_refs"],
        context_selection=view["context_selection"],
        response_attempt=1 if interpretation is not None else None,
        interpretation_status="complete" if interpretation is not None else "failed",
        adoption="validated_response"
        if valid
        else "interpretation_only"
        if interpretation is not None
        else "none",
        rewrite_status="same_evidence_rewrite_blocked" if not valid else "not_needed",
    )
    return dict(
        interpretation=interpretation,
        candidates=candidates,
        limitations=limitations,
        input_view=view,
        response_attempt=diagnostics["response_attempt"],
        analysis_valid=valid,
        status="complete" if valid else "failed",
    )
