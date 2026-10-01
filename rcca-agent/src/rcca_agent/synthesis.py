"""Bounded evidence interpretation; model output never establishes verified facts."""

import re

from agent_common.observation import series, usable_observation

from .prompts import SYNTHESIS
from .synthesis_context import bounded_context, encoded_size


def synthesis_input(data, evidence, health, relations, applicable, planned=()):
    # Raw logs and unregistered producer semantics cannot establish device health.
    complete = [
        e for e in evidence if e["tool_status"] == "ok" and e["quality"].get("complete")
    ]
    valid_ids = {e["id"] for e in evidence if usable_observation(e)}
    observations = [
        h
        for h in health
        if h["check_status"] == "valid"
        and h["normalized_health"] != "unknown"
        and set(h["evidence_refs"]) <= valid_ids
    ]
    metrics = series(complete)
    # Prefer incident-node measurements over broad Pod inventory in a bounded view.
    target = data.get("target", {})
    metrics.sort(
        key=lambda row: (
            row["labels"].get("node")
            != target.get("node", target.get("k8s_node_name")),
            row["labels"].get("__name__") == "kube_pod_info",
        )
    )
    refs = sorted(
        {r for h in observations + relations + metrics for r in h["evidence_refs"]}
    )
    return {
        "incident_time": data["incident_time"],
        "scope": data["scope"],
        "target": data.get("target", {}),
        "purpose_ids": data["purpose_ids"],
        "device_observations": observations,
        "pod_relations": relations,
        "metric_observations": metrics,
        "observation_refs": refs,
        "query_quality": [
            {k: e[k] for k in ("id", "query_id", "tool_status", "quality")}
            for e in evidence
            if e["query_id"].startswith("D")
        ],
        "runbook_matches": [
            {"id": b["id"], "claim": b["content"].get("claim", b["knowledge_key"])}
            for b in applicable
        ],
        "runbook_plans": [
            {
                "id": b["id"],
                "revision": b["revision"],
                "application_status": "applicable" if b in applicable else "pending",
                "investigation_only": b["content"].get("investigation_only", False),
                "analysis_guidance": b["content"].get("analysis_guidance", []),
                "limitations": b["content"].get("limitations", []),
            }
            for b in planned
        ],
    }


class SynthesisValidationError(ValueError):
    """Fixed diagnostic codes only; never persist model text or raw exceptions."""


# Measurements, timestamps and number-with-unit values never become identifiers.
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
MEASUREMENT = re.compile(r"[\d.,:\s]*\d[\d.,:\s]*[A-Za-z%]{0,3}", re.I)
ERROR_CODE = re.compile(r"s?xid[ :]*\d+", re.I)


def identifier_tokens(view):
    """Alphanumeric identifiers the model received verbatim, e.g. D05 or cpc-2."""
    found = set()

    def walk(value, key=None):
        if key == "samples":
            return
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif isinstance(value, str) and len(value) <= 200:
            # Per token, so a producer sentence cannot whitelist its measurements.
            # Error codes stay limited to cited observations by numeric_prose.
            found.update(
                token
                for token in (t.strip(".,;()[]{}\"'") for t in value.split())
                if re.search(r"\d", token)
                and not ERROR_CODE.fullmatch(token)
                and re.search(r"[A-Za-z]", token)
                and not TIMESTAMP.search(token)
                and not MEASUREMENT.fullmatch(token)
            )

    walk(view)
    return found


def validate_synthesis(response, refs, observations=(), identifiers=()):
    """Validate structure/references, not the truth of an LLM hypothesis."""
    if not isinstance(response, dict) or set(response) != {
        "hypotheses",
        "limitations",
    }:
        raise SynthesisValidationError("invalid_analysis_shape")
    hypotheses = response["hypotheses"]
    if not isinstance(hypotheses, list) or len(hypotheses) > 8:
        raise SynthesisValidationError("invalid_hypotheses")

    # Longest first so "vessl-k8s-worker-01" is masked before a shorter overlap.
    known = sorted(set(identifiers), key=len, reverse=True)
    identifier = (
        re.compile(
            r"(?<![A-Za-z0-9_.:-])(?:"
            + "|".join(map(re.escape, known))
            + r")(?![A-Za-z0-9_:-])",
            re.I,
        )
        if known
        else None
    )

    def numeric_prose(text, evidence_refs):
        # Typed error codes of cited observations and identifiers copied from the
        # input may contain digits; any other digit is an unregistered number.
        codes = {
            h.get("error_code")
            for h in observations
            if set(h.get("evidence_refs", [])) & set(evidence_refs)
        }

        def replace(match):
            code = f"{match[1].lower()}:{int(match[2])}"
            return "reported error" if code in codes else match[0]

        text = re.sub(r"\b(s?xid)[ :]+([0-9]+)\b", replace, text, flags=re.I)
        if identifier:
            text = identifier.sub("identifier", text)
        return re.search(r"\d", text)

    def strings(items):
        return (
            isinstance(items, list)
            and len(items) <= 32
            and all(isinstance(s, str) and s.strip() and len(s) <= 2000 for s in items)
        )

    if not strings(response["limitations"]) or any(
        numeric_prose(s, refs) for s in response["limitations"]
    ):
        raise SynthesisValidationError("invalid_limitations")
    candidates = []
    for i, h in enumerate(hypotheses):
        if not isinstance(h, dict) or set(h) != {
            "claim",
            "supporting_refs",
            "contradicting_refs",
            "missing_inputs",
        }:
            raise SynthesisValidationError("invalid_hypothesis_shape")
        if (
            not isinstance(h["claim"], str)
            or not h["claim"].strip()
            or len(h["claim"]) > 2000
        ):
            raise SynthesisValidationError("invalid_claim")
        if not all(
            strings(h[k])
            for k in ("supporting_refs", "contradicting_refs", "missing_inputs")
        ):
            raise SynthesisValidationError("invalid_hypothesis_references")
        supporting, contradicting = (
            set(h["supporting_refs"]),
            set(h["contradicting_refs"]),
        )
        if (
            not supporting
            or not (supporting | contradicting) <= set(refs)
            or supporting & contradicting
        ):
            raise SynthesisValidationError("invalid_evidence_references")
        if numeric_prose(h["claim"], supporting):
            raise SynthesisValidationError("unregistered_numeric_claim")
        candidates.append(
            dict(
                id=f"analysis-{i + 1}",
                claim=h["claim"],
                causal_status="candidate",
                supporting_refs=sorted(supporting),
                contradicting_refs=sorted(contradicting),
                value_refs=[],
                missing_inputs=list(
                    dict.fromkeys(
                        h["missing_inputs"] + ["causal_confirmation_evidence"]
                    )
                ),
            )
        )
    return candidates


async def synthesize(llm, payload, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(request_attempts=0, response_calls=0, error_code=None)
    if not payload["observation_refs"]:
        return "no_usable_evidence", [], []
    if not llm.configured:
        diagnostics["error_code"] = "model_not_configured"
        return "unconfigured", [], []
    remaining = getattr(llm, "remaining", 32768)
    max_bytes = min(16000, max(0, remaining - len(SYNTHESIS.encode()) - 256 - 2 - 8192))
    view = bounded_context(payload, max_bytes)
    diagnostics.update(
        input_bytes=encoded_size(view),
        original_input_bytes=encoded_size(payload),
        context_selection=view["context_selection"],
        input_evidence_refs=view["observation_refs"],
    )
    if encoded_size(view) > max_bytes or not view["observation_refs"]:
        diagnostics["error_code"] = "llm_context_budget_exhausted"
        return "failed", [], []
    usage = getattr(llm, "usage", {})
    before = {k: usage.get(k, 0) for k in ("request_attempts", "calls")}
    # RemoteUncertain and cancellation propagate to Worker fencing.
    try:
        response = await llm.complete(SYNTHESIS, view, stage="synthesis")
        if response is None:
            code = getattr(llm, "last_failure", None)
            diagnostics["error_code"] = (
                code
                if code
                in {
                    "llm_token_budget_exhausted",
                    "llm_deadline_exhausted",
                    "llm_http_error",
                    "llm_output_truncated",
                    "llm_invalid_output",
                    "model_not_configured",
                }
                else "llm_no_response"
            )
            return "failed", [], []
        candidates = validate_synthesis(
            response,
            view["observation_refs"],
            view["device_observations"],
            identifier_tokens(view),
        )
    except SynthesisValidationError as exc:
        diagnostics["error_code"] = str(exc)
        return "failed", [], []
    except (ValueError, TypeError, KeyError):
        diagnostics["error_code"] = "invalid_model_response"
        return "failed", [], []
    finally:
        usage = getattr(llm, "usage", {})
        diagnostics["request_attempts"] = (
            usage.get("request_attempts", 0) - before["request_attempts"]
        )
        diagnostics["response_calls"] = usage.get("calls", 0) - before["calls"]
    limitations = list(response["limitations"])
    if not view["context_selection"]["complete"]:
        limitations.append(
            "모델 입력 한도로 일부 관측·표본을 생략했습니다. 선택된 표본만으로 전체 기간의 연속성이나 오류 부재를 판단할 수 없습니다."
        )
    return "complete", candidates, limitations
