"""Bounded evidence interpretation; model output never establishes verified facts."""

import re
import hashlib

from agent_common.observation import series, usable_observation

from .prompts import SYNTHESIS
from .synthesis_context import bounded_context
from .investigation_summary import investigation_summary


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
    # Prefer incident-node measurements over broad Pod inventory in a bounded view,
    # and the reported device's series over its siblings on that node.
    target = data.get("target", {})
    devices = {e.get("inventory_gpu_candidate") for e in events} - {None}
    metrics.sort(
        key=lambda row: (
            row["labels"].get("node")
            != target.get("node", target.get("k8s_node_name")),
            not devices & set(map(str, row["labels"].values())),
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
    comparisons = [
        row
        for row in investigation_summary(data, evidence, health, events)
        if row["section"] != "investigation"
    ]
    return {
        "incident_time": data["incident_time"],
        **({"investigation_summary": comparisons} if comparisons else {}),
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

    def __init__(
        self, code, *, rule="shape", index=None, tokens=(), numeric=None, language=None
    ):
        super().__init__(code)
        self.diagnostic = {"code": code, "rule": rule, "tokens": list(tokens)[:10]}
        if numeric is not None:
            self.diagnostic["numeric_diagnostic"] = numeric
        if language is not None:
            self.diagnostic["language_diagnostic"] = language
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

    def prose(text, evidence_refs, preserve_offsets=False):
        # Typed error codes of cited observations and identifiers copied from the
        # input may contain digits; any other digit is an unregistered number.
        codes = {
            h.get("error_code")
            for h in observations
            if set(h.get("evidence_refs", [])) & set(evidence_refs)
        }

        def replace(match):
            code = f"{match[1].lower()}:{int(match[2])}"
            return (
                (" " * len(match[0]) if preserve_offsets else " ")
                if code in codes
                else match[0]
            )

        text = re.sub(
            r"(?<![A-Za-z0-9_])(s?xid)[ :]*([0-9]+)(?![A-Za-z0-9_])",
            replace,
            text,
            flags=re.I,
        )
        if identifier:
            text = identifier.sub(
                lambda m: " " * len(m[0]) if preserve_offsets else " ", text
            )
        return text

    def numeric_prose(text, evidence_refs):
        masked = prose(text, evidence_refs, preserve_offsets=True)
        matches = sorted(
            [(m.start(), m.end(), "digits") for m in re.finditer(r"\d+", masked)]
            + [
                (m.start(), m.end(), "number_word")
                for m in NUMBER_WORD.finditer(masked)
            ]
        )
        if not matches:
            return None
        return {
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "text_length": len(text),
            "offset_unit": "unicode_codepoints",
            "matches": [
                {"start": start, "end": end, "kind": kind}
                for start, end, kind in matches[:10]
            ],
            "truncated": len(matches) > 10,
        }

    def language_diagnostic(text, evidence_refs):
        masked = prose(text, evidence_refs, preserve_offsets=True)
        hangul = len(re.findall(r"[가-힣]", masked))
        # Identifiers were masked above. Permit technical terms, not arbitrary
        # English prose hidden inside a mostly Korean sentence.
        technical = {
            "GPU",
            "CPU",
            "PCI",
            "PCIE",
            "AER",
            "NVLINK",
            "NVSWITCH",
            "CUDA",
            "ECC",
            "HBM",
            "NVML",
            "DCGM",
            "MIG",
            "LLM",
            "BIOS",
            "BMC",
            "NIC",
            "RDMA",
            "NVME",
            "SSD",
            "IO",
            "OS",
            "TESLA",
            "PARTIAL",
            "TRUE",
            "FALSE",
            # Domain terms the code-written inputs themselves use in Korean text.
            "XID",
            "SXID",
            "NVRM",
            "KST",
            "UTC",
            "ID",
            "UUID",
            "FLEET",
            "LOKI",
            "KMSG",
            "HEALTHY",
            "UNHEALTHY",
            "DEGRADED",
            "FABRIC",
            "MANAGER",
            "CRC",
            "SMART",
            "RAID",
            "SEL",
            "NCCL",
        }
        matches = [
            m
            for m in re.finditer(r"[A-Za-z]+", masked)
            if m[0].upper() not in technical
        ]
        if hangul and not matches:
            return None
        return {
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "text_length": len(text),
            "offset_unit": "unicode_codepoints",
            "missing_korean_prose": not bool(hangul),
            "matches": [{"start": m.start(), "end": m.end()} for m in matches[:10]],
            "truncated": len(matches) > 10,
        }

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
            if language_diagnostic(text, refs)
            else "precision_loss"
            if not precision_reduced and PRECISION_LOSS.search(text)
            else None
        )
        if rule:
            # Do not retain arbitrary model tokens (which may contain secrets).
            # Fixed offending-token classes provide bounded repair feedback.
            raise SynthesisValidationError(
                "invalid_limitations",
                rule=rule,
                index=i,
                tokens=[rule],
                numeric=numeric_prose(text, refs) if rule == "numeric" else None,
                language=language_diagnostic(text, refs)
                if rule == "non_korean"
                else None,
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
        # Identity uncertainty is a diagnostic limitation regardless of wording or
        # whether the bounded view retained the inventory relation observation.
        if re.search(
            r"식별|매핑|인벤토리|장치\s*신원|장치\s*목록|GPU\s*목록", h["claim"]
        ) and re.search(
            r"불확실|미확인|불일치|연결되지|매핑되지|식별하지\s*못|확인되지|알\s*수\s*없|인벤토리.{0,20}(?:없는|없어|없다|누락)|목록.{0,20}(?:없는|없어|없다|누락)",
            h["claim"],
        ):
            raise SynthesisValidationError(
                "unsupported_identity_cause", rule="identity_is_not_cause", index=i
            )
        # Unresolved inventory is a limitation, never a causal mechanism.
        cited = [
            o for o in observations if set(o.get("evidence_refs", [])) & supporting
        ]
        if any(
            o.get("pci_inventory_relation")
            in {"not_in_reported_inventory", "switch_inventory_required"}
            for o in cited
        ) and re.search(
            r"물리적|핫\s*제거|장비\s*재조명|존재하지\s*않|잘못된\s*명령|연결\s*불량|연결된\s*GPU|슬롯\s*접촉|전원\s*문제|펌웨어\s*오류|링크\s*문제",
            h["claim"],
        ):
            raise SynthesisValidationError(
                "unsupported_identity_cause", rule="identity_is_not_cause", index=i
            )
        # Error events with unresolved identity cannot distinguish mechanisms.
        # Use event metadata too: bounded input may omit the inventory report.
        unresolved = any(
            o.get("device_mapping") in {"unresolved", "conflicting"}
            or o.get("pci_inventory_relation")
            in {"not_in_reported_inventory", "switch_inventory_required"}
            for o in cited
        )
        if unresolved and re.search(
            r"펌웨어|드라이버|구성\s*오류|전원\s*문제|연결\s*불량|물리적|접촉\s*불량|링크\s*고장",
            h["claim"],
        ):
            raise SynthesisValidationError(
                "unsupported_device_mechanism",
                rule="unresolved_device_mechanism",
                index=i,
            )
        if numeric_prose(h["claim"], supporting):
            raise SynthesisValidationError(
                "unregistered_numeric_claim",
                rule="numeric",
                index=i,
                tokens=["numeric"],
                numeric=numeric_prose(h["claim"], supporting),
            )
        if language_diagnostic(h["claim"], supporting):
            raise SynthesisValidationError(
                "non_korean_claim",
                rule="non_korean",
                index=i,
                tokens=["non_korean"],
                language=language_diagnostic(h["claim"], supporting),
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
                missing_inputs=list(dict.fromkeys(h["missing_inputs"])),
            )
        )
    return candidates


def synthesis_view(payload, remaining, reserved, prompt=SYNTHESIS):
    """Use the same bounded input/output allocation for planning and execution."""
    remaining -= reserved
    output_room = (
        min(8192, max(512, (remaining - len(prompt.encode())) // 3))
        if reserved
        else 8192
    )
    # The deployed route can cap input + output at 32K tokens. Keep planned
    # incident inputs compact; full evidence remains stored and source-balanced.
    input_cap = 24000 if "incident_comparison" in payload else 64000
    max_bytes = min(
        input_cap, max(0, remaining - len(prompt.encode()) - 256 - 2 - output_room)
    )
    view = bounded_context(payload, max_bytes)
    return view, max_bytes
