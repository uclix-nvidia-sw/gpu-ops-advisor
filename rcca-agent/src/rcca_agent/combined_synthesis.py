"""One bounded author request, independent interpretation/causal reference domains."""

from copy import deepcopy
import time

from agent_common.contracts import content_hash
from .evidence_interpretation import (
    INTERPRET_CONTEXT,
    INTERPRET_RULES,
    CRITERIA_PROMPT,
    semantic_criteria,
    validate_interpretation,
    ResponseValidationError,
)
from .prompts import SYNTHESIS_CONTEXT, SYNTHESIS_RULES
from .synthesis import (
    synthesis_view,
    validate_synthesis,
    identifier_tokens,
    SynthesisValidationError,
)
from .synthesis_context import bounded_context, encoded_size

COMBINED = (
    SYNTHESIS_CONTEXT
    + SYNTHESIS_RULES
    + "\nThe following rules apply inside interpretation only:\n"
    + INTERPRET_CONTEXT
    + INTERPRET_RULES
    + """
Return JSON with exactly these keys:
{"interpretation": {
  "findings": [{"id":"finding-1", "statement":"관측한 증상은 추가 확인이 필요합니다.",
    "kind":"observed", "evidence_refs":["evidence id"]}],
  "unknowns":[], "conflicts":[], "limitations":[]},
 "hypotheses": [{"claim":"추가 확인이 필요한 원인 후보일 가능성이 있다",
   "supporting_refs":["evidence id"], "contradicting_refs":[],
   "missing_inputs":["추가 확인 필요"], "finding_refs":["finding-1"]}],
 "limitations":[]}
This is the only top-level output contract. Replace example text and refs with
supported content; never copy placeholders or invent a hypothesis to match the example.
Interpretation limitations are objects with statement/evidence_refs;
top-level limitations and hypothesis missing_inputs are Korean strings.
Each hypothesis also requires finding_refs referencing findings in THIS response.
Hypothesis supporting_refs must cite observation_refs, never diagnostics or Runbook IDs.
Interpretation may cite input_evidence_refs. Interpretation is not independent evidence.
An empty hypotheses list with useful findings and explicit unknowns is valid.
Do not invent a cause to fill the list. Return concise Korean statements.
This is one author request, not a self-review. A separate reviewer checks all claims.
Validation feedback concerns response structure, not new evidence."""
)


def author_prompt(payload):
    return COMBINED + (
        CRITERIA_PROMPT
        + "\nIn this combined response, criterion_assessments belongs only inside "
        "interpretation, never at the top level."
        if semantic_criteria(payload) is not None
        else ""
    )


def validate_author(response, view, criteria, details=None):
    details = details if details is not None else []
    interpretation, candidates, limitations, errors = None, [], [], []
    if not isinstance(response, dict) or set(response) != {
        "interpretation",
        "hypotheses",
        "limitations",
    }:
        details.append({"code": "author_shape", "path": "$", "rule": "shape"})
        return None, [], [], ["author_shape"]
    try:
        interpretation = validate_interpretation(
            response["interpretation"],
            view["input_evidence_refs"],
            criteria,
            view["observation_refs"],
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
    try:
        findings = {row["id"] for row in (interpretation or {}).get("findings", [])}
        hypotheses = response["hypotheses"]
        if interpretation is None:
            raise SynthesisValidationError("interpretation_dependency")
        if not isinstance(hypotheses, list) or len(hypotheses) > 8:
            raise SynthesisValidationError("invalid_hypotheses")
        plain = []
        for index, h in enumerate(hypotheses):
            if not isinstance(h, dict):
                raise SynthesisValidationError("invalid_hypothesis_shape", index=index)
            if (
                not isinstance(h.get("finding_refs"), list)
                or not h["finding_refs"]
                or any(
                    not isinstance(ref, str) or ref not in findings
                    for ref in h["finding_refs"]
                )
            ):
                raise SynthesisValidationError("finding_dependency", index=index)
            plain.append(
                {key: value for key, value in h.items() if key != "finding_refs"}
            )
        candidates = validate_synthesis(
            {"hypotheses": plain, "limitations": response["limitations"]},
            view["observation_refs"],
            view["device_observations"] + view["error_events"],
            identifier_tokens(view),
            view["query_quality"],
        )
        for candidate, hypothesis in zip(candidates, hypotheses, strict=True):
            candidate["finding_refs"] = hypothesis["finding_refs"]
        limitations = response["limitations"]
    except (SynthesisValidationError, ValueError, TypeError, KeyError) as exc:
        candidates = []
        errors.append("analysis_invalid")
        # The typed exception contains fixed codes/offsets only, never rejected text.
        detail = (
            dict(exc.diagnostic)
            if isinstance(exc, SynthesisValidationError)
            else {"code": "invalid_analysis_value", "rule": "shape"}
        )
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
        details.append({**detail, "path": path})
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
    view = bounded_context(payload, min(limit, 6000))
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
            response = await llm.complete(prompt, view, stage="synthesis")
        finally:
            llm.request_attempt_limit = request_limit
        if response is None:
            diagnostics["error_code"] = (
                getattr(llm, "last_failure", None) or "llm_no_response"
            )
        else:
            details = []
            interpretation, candidates, limitations, errors = validate_author(
                response, view, semantic_criteria(payload), details
            )
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
