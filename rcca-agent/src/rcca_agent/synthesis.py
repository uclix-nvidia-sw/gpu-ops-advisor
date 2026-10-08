"""Bounded evidence interpretation; model output never establishes verified facts."""

import re
import time
import copy
import json

from agent_common.observation import series, usable_observation

from .prompts import SYNTHESIS
from .synthesis_context import bounded_context, encoded_size


def synthesis_input(
    data, evidence, health, relations, applicable, planned=(), events=()
):
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
    events = [event for event in events if set(event["evidence_refs"]) <= valid_ids]
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
        {
            r
            for h in observations + events + relations + metrics
            for r in h["evidence_refs"]
        }
    )
    return {
        "incident_time": data["incident_time"],
        "scope": data["scope"],
        "target": data.get("target", {}),
        "device_observations": observations,
        "error_events": events,
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

    def __init__(self, code, *, rule="shape", index=None, tokens=()):
        super().__init__(code)
        self.diagnostic = {"code": code, "rule": rule, "tokens": list(tokens)[:10]}
        if index is not None:
            self.diagnostic[
                "limitation_index"
                if code == "invalid_limitations"
                else "hypothesis_index"
            ] = index


# Measurements, timestamps and number-with-unit values never become identifiers.
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
MEASUREMENT = re.compile(r"[\d.,:\s]*\d[\d.,:\s]*[A-Za-z%]{0,3}", re.I)
ERROR_CODE = re.compile(r"s?xid[ :]*\d+", re.I)


# Unicode word boundaries exclude ordinary words beginning with number syllables.
# Particles are allowed only after explicit counters; e.g. 두 개의, never 두께.
NUMBER_WORD = re.compile(
    r"(?<![\w])(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million|billion|percent|half|dozen|single|double|twice)(?![\w])"
    r"|(?<![\w])(?:하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열|스물)(?:의|는|가|를|만|도)?(?![\w])"
    r"|(?<![\w])(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|스무|스물)"
    r"\s*(?:대|개|번|건|명|장|시간|분|초)(?:은|는|이|가|을|를|의|에|만|도|씩)?(?![\w])"
    r"|(?<![\w])(?:영|일|이|삼|사|오|육|칠|팔|구|십|백|천)+"
    r"\s*(?:퍼센트|프로|%)(?:는|가|를|의|에|만|도)?(?![\w])"
    r"|전혀\s*(?:없|없는|없음)",
    re.I,
)
PRECISION_LOSS = re.compile(
    r"time_precision_reduced|(?:time|timestamp)\s+precision\s+(?:loss|reduc\w*)"
    r"|정밀도.{0,12}(?:손실|축소|저하)|(?:손실|축소|저하).{0,12}정밀도",
    re.I,
)
# Deliberately narrow: broad Korean copula matching would reject valid uncertainty.
ASSERTION = re.compile(
    r"원인(?:이다|입니다)|고장(?:이다|입니다)|원인(?:이|으로)\s*확정(?:되었|됐|됨)"
    r"|physically|(?:사용률|활동률|표본).{0,30}(?:유휴|고장|정상)(?:이다|입니다)",
    re.I,
)


def identifier_tokens(view):
    """Input identifiers, including digit-free node/Pod names in typed fields."""
    found = set()

    def walk(value, key=None):
        if key == "samples":
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if re.fullmatch(r"[a-z][a-z0-9]*_[a-z0-9_]+", k):
                    found.add(k)
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
                if (
                    re.fullmatch(r"[a-z][a-z0-9]*_[a-z0-9_]+", token)
                    or re.search(r"\d", token)
                    or key
                    in {
                        "node",
                        "k8s_node_name",
                        "pod",
                        "pod_uid",
                        "gpu_uuid",
                        "machine_id",
                        "cluster_id",
                        "namespace",
                    }
                )
                and not ERROR_CODE.fullmatch(token)
                and re.search(r"[A-Za-z]", token)
                and not TIMESTAMP.search(token)
                and not MEASUREMENT.fullmatch(token)
            )

    walk(view)
    return found


def validate_synthesis(
    response, refs, observations=(), identifiers=(), query_quality=()
):
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

    def prose(text, evidence_refs):
        # Typed error codes of cited observations and identifiers copied from the
        # input may contain digits; any other digit is an unregistered number.
        codes = {
            h.get("error_code")
            for h in observations
            if set(h.get("evidence_refs", [])) & set(evidence_refs)
        }

        def replace(match):
            code = f"{match[1].lower()}:{int(match[2])}"
            return " " if code in codes else match[0]

        text = re.sub(
            r"(?<![A-Za-z0-9_])(s?xid)[ :]*([0-9]+)(?![A-Za-z0-9_])",
            replace,
            text,
            flags=re.I,
        )
        if identifier:
            text = identifier.sub(" ", text)
        return text

    def numeric_prose(text, evidence_refs):
        text = prose(text, evidence_refs)
        return re.search(r"\d", text) or NUMBER_WORD.search(text)

    def korean(text, evidence_refs):
        text = prose(text, evidence_refs)
        hangul = len(re.findall(r"[가-힣]", text))
        latin = len(re.findall(r"[a-z]", text, re.I))
        return hangul > 0 and latin <= hangul

    precision_reduced = any(
        q.get("quality", {}).get("reason") == "time_precision_reduced"
        for q in query_quality
    )

    def strings(items):
        return (
            isinstance(items, list)
            and len(items) <= 32
            and all(isinstance(s, str) and s.strip() and len(s) <= 2000 for s in items)
        )

    if (
        not isinstance(response["limitations"], list)
        or len(response["limitations"]) > 32
    ):
        raise SynthesisValidationError("invalid_limitations")
    for i, text in enumerate(response["limitations"]):
        rule = (
            "shape"
            if not strings([text])
            else "numeric"
            if numeric_prose(text, refs)
            else "non_korean"
            if not korean(text, refs)
            else "precision_loss"
            if not precision_reduced and PRECISION_LOSS.search(text)
            else None
        )
        if rule:
            # Do not retain arbitrary model tokens (which may contain secrets).
            # Fixed offending-token classes provide bounded repair feedback.
            raise SynthesisValidationError(
                "invalid_limitations", rule=rule, index=i, tokens=[rule]
            )
    candidates = []
    for i, h in enumerate(hypotheses):
        if not isinstance(h, dict) or set(h) != {
            "claim",
            "supporting_refs",
            "contradicting_refs",
            "missing_inputs",
        }:
            raise SynthesisValidationError("invalid_hypothesis_shape", index=i)
        if (
            not isinstance(h["claim"], str)
            or not h["claim"].strip()
            or len(h["claim"]) > 2000
        ):
            raise SynthesisValidationError("invalid_claim", index=i)
        if not all(
            strings(h[k])
            for k in ("supporting_refs", "contradicting_refs", "missing_inputs")
        ):
            raise SynthesisValidationError("invalid_hypothesis_references", index=i)
        supporting, contradicting = (
            set(h["supporting_refs"]),
            set(h["contradicting_refs"]),
        )
        if (
            not supporting
            or not (supporting | contradicting) <= set(refs)
            or supporting & contradicting
        ):
            rule = (
                "empty_supporting_refs"
                if not supporting
                else "unknown_observation_refs"
                if not (supporting | contradicting) <= set(refs)
                else "overlapping_evidence_refs"
            )
            raise SynthesisValidationError(
                "invalid_evidence_references", rule=rule, index=i
            )
        if numeric_prose(h["claim"], supporting):
            raise SynthesisValidationError(
                "unregistered_numeric_claim",
                rule="numeric",
                index=i,
                tokens=["numeric"],
            )
        if not korean(h["claim"], supporting):
            raise SynthesisValidationError(
                "non_korean_claim", rule="non_korean", index=i, tokens=["non_korean"]
            )
        if ASSERTION.search(prose(h["claim"], supporting)):
            raise SynthesisValidationError(
                "unsupported_assertion", rule="assertion", index=i, tokens=["assertion"]
            )
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
    fallback = None
    feedback = []
    diagnostics.update(
        repair_attempts=0, repair_status="not_needed", validation_failures=[]
    )
    try:
        for attempt in range(2):
            request = dict(view)
            if attempt:
                request["validation_feedback"] = feedback
                # Match the transport's conservative UTF-8 accounting; reserve output.
                bound = (
                    len(
                        (
                            SYNTHESIS + json.dumps(request, ensure_ascii=False) + "[]"
                        ).encode()
                    )
                    + 256
                    + 8192
                )
                if (
                    getattr(llm, "remaining", 32768) < bound
                    or getattr(llm, "deadline", float("inf")) <= time.monotonic()
                ):
                    diagnostics["repair_status"] = "budget_or_deadline_exhausted"
                    break
                diagnostics.update(repair_attempts=1, repair_status="failed")
            response = await llm.complete(SYNTHESIS, request, stage="synthesis")
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
                break
            args = (
                view["observation_refs"],
                view["device_observations"] + view.get("error_events", []),
                identifier_tokens(view),
                view.get("query_quality", []),
            )
            filtered = copy.deepcopy(response)
            rejected = []
            if (
                isinstance(filtered, dict)
                and isinstance(filtered.get("limitations"), list)
                and len(filtered["limitations"]) <= 32
            ):
                accepted = []
                for index, limitation in enumerate(filtered["limitations"]):
                    try:
                        validate_synthesis(
                            {"hypotheses": [], "limitations": [limitation]}, *args
                        )
                        accepted.append(limitation)
                    except SynthesisValidationError as exc:
                        rejected.append({**exc.diagnostic, "limitation_index": index})
                filtered["limitations"] = accepted
            diagnostics["rejected_limitations"] = len(rejected)
            feedback = rejected
            try:
                candidates = validate_synthesis(filtered, *args)
                fallback = (candidates, filtered["limitations"], rejected)
                if not rejected:
                    if attempt:
                        diagnostics["repair_status"] = "repaired"
                    break
                diagnostics["error_code"] = "invalid_limitations"
            except SynthesisValidationError as exc:
                diagnostics["error_code"] = str(exc)
                feedback += [exc.diagnostic]
            diagnostics["validation_failures"].append(
                {"attempt": attempt + 1, "violations": feedback}
            )
    except (ValueError, TypeError, KeyError):
        diagnostics["error_code"] = "invalid_model_response"
    finally:
        usage = getattr(llm, "usage", {})
        diagnostics["request_attempts"] = (
            usage.get("request_attempts", 0) - before["request_attempts"]
        )
        diagnostics["response_calls"] = usage.get("calls", 0) - before["calls"]
    if fallback is None:
        return "failed", [], []
    candidates, limitations, rejected = fallback
    limitations = list(limitations)
    diagnostics["rejected_limitations"] = len(rejected)
    if diagnostics["repair_status"] == "failed":
        diagnostics["repair_error_code"] = diagnostics["error_code"]
    diagnostics["error_code"] = None
    if rejected:
        limitations.append(
            "모델의 일부 한계 문장이 검증을 통과하지 못해 제외했습니다. 검증된 근거와 아래 미충족 조건을 함께 확인해야 합니다."
        )
    if not view["context_selection"]["complete"]:
        limitations.append(
            "모델 입력 한도로 일부 관측·표본을 생략했습니다. 선택된 표본만으로 전체 기간의 연속성이나 오류 부재를 판단할 수 없습니다."
        )
    return "complete", candidates, limitations
