"""Deterministic runbook retrieval primitives for the runbook-first pipeline.

This module does not decide applicability or causality. It only ranks already
authorized runbook revisions; callers must still verify compatibility and facts.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from agent_common.parsers import ERROR_CODE as XID

TOKEN = re.compile(r"[a-z0-9가-힣]+")
TOKENIZER_REVISION = "gpu-lexical-v3"
TEXT_FIELDS = (
    "alertname",
    "summary",
    "description",
    "message",
    "symptom",
    "event_name",
    "event_names",
    "producer_events",
    "error_codes",
    "reason",
    "component",
)
SEARCH_WEIGHTS = {
    "codes": 8,
    "producer_events": 5,
    "aliases": 4,
    "title": 3,
    "category": 3,
    "symptoms": 2,
    "description": 1,
}


def normalize_text(value):
    text = str(value or "").lower().replace("_", " ").replace("-", " ")
    codes = [f"{kind.lower()}:{int(number)}" for kind, number in XID.findall(text)]
    # Keep Xid/SXid namespaces intact; do not match the bare number across them.
    return TOKEN.findall(XID.sub(" ", text)) + codes


def _strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        yield str(value)


def incident_terms(source):
    """Use only declared clue fields, including grouped Grafana alert envelopes.

    Callers must split grouped alerts by incident identity before production use.
    Identity, timestamps, URLs and untrusted verified_facts are not search text.
    """

    def clues(obj):
        if not isinstance(obj, dict):
            return
        for field in TEXT_FIELDS:
            value = obj.get(field)
            if isinstance(value, str):
                yield value
            elif isinstance(value, list):
                yield from (item for item in value if isinstance(item, str))
        for field in (
            "alert",
            "evidence",
            "labels",
            "annotations",
            "commonLabels",
            "commonAnnotations",
        ):
            yield from clues(obj.get(field))
        for alert in (
            obj.get("alerts", []) if isinstance(obj.get("alerts"), list) else []
        ):
            yield from clues(alert)

    return normalize_text(" ".join(clues(source)))


def runbook_fields(row):
    content = row.get("content", {})
    if not isinstance(content, dict):
        raise TypeError("runbook content must be an object")
    search = content.get("search", {})
    classification = content.get("classification", {})
    if not isinstance(search, dict) or not isinstance(classification, dict):
        raise TypeError("runbook search/classification must be objects")
    fields = {
        "codes": search.get("codes", []),
        "producer_events": search.get("producer_events", []),
        "aliases": search.get("aliases", []),
        "title": content.get("title", ""),
        "category": classification.get("category", ""),
        "symptoms": search.get("symptoms", []),
        "description": content.get("description", content.get("claim", "")),
    }
    return {
        name: normalize_text(" ".join(_strings(value)))
        for name, value in fields.items()
    }


def retrieve_runbooks(rows, source, top_k=5, exact_code_boost=12.0):
    """Weighted sum of per-field BM25 scores; ranking only, not applicability.

    Caller supplies authorized, revision-pinned rows. This experimental function
    does not load a DB, enforce scope/hash/state, calibrate thresholds, or run tools.
    """
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    if (
        isinstance(exact_code_boost, bool)
        or not isinstance(exact_code_boost, (float, int))
        or not math.isfinite(exact_code_boost)
        or exact_code_boost < 0
    ):
        raise ValueError("exact_code_boost must be finite and nonnegative")
    # Duplicate annotations/events must not inflate relevance.
    query = sorted(set(incident_terms(source)))
    if not rows or not query:
        return []
    documents = [runbook_fields(row) for row in rows]
    statistics = {}
    for field in SEARCH_WEIGHTS:
        frequency = Counter()
        for document in documents:
            frequency.update(set(document[field]))
        statistics[field] = (
            frequency,
            sum(len(d[field]) for d in documents) / len(documents),
        )
    count = len(documents)
    query_codes = {term for term in query if term.startswith(("xid:", "sxid:"))}
    ranked = []
    for row, document in zip(rows, documents):
        # Declared trigger codes are an eligibility boundary for retrieval, not
        # just a score boost. Prose overlap cannot select a different code or
        # select a code-specific investigation for a code-free CPU/disk alert.
        document_codes = {
            term for term in document["codes"] if term.startswith(("xid:", "sxid:"))
        }
        if document_codes and not query_codes.intersection(document_codes):
            continue
        field_scores = {}
        for field, weight in SEARCH_WEIGHTS.items():
            frequencies = Counter(document[field])
            document_frequency, average_length = statistics[field]
            field_score = 0.0
            for term in query:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                inverse_document_frequency = math.log(
                    1
                    + (count - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                denominator = frequency + 1.2 * (
                    1 - 0.75 + 0.75 * len(document[field]) / average_length
                )
                field_score += (
                    inverse_document_frequency * frequency * 2.2 / denominator
                )
            field_scores[field] = field_score * weight
        score = sum(field_scores.values())
        # A cross-reference in prose is not a declared trigger code.
        exact_codes = sorted(query_codes & document_codes)
        exact_score = exact_code_boost * len(exact_codes)
        if score + exact_score <= 0:
            continue
        ranked.append(
            {
                "runbook": row,
                "bm25_score": round(score, 6),
                "field_scores": {k: round(v, 6) for k, v in field_scores.items()},
                "tokenizer_revision": TOKENIZER_REVISION,
                "exact_score": exact_score,
                "exact_codes": exact_codes,
                "total_score": round(score + exact_score, 6),
            }
        )
    ranked.sort(
        key=lambda item: (
            -item["total_score"],
            item["runbook"].get("knowledge_key", ""),
            -item["runbook"].get("revision", 0),
            str(item["runbook"].get("id", "")),
        )
    )
    return ranked[:top_k]
