"""Reviewed Runbook presentation data; never an observation or action approval."""

from copy import deepcopy


def validate_operator_guidance(value, sources):
    def require(condition):
        if not condition:
            from .runbook_contract import RunbookContractError

            raise RunbookContractError(
                "operator_guidance: invalid presentation contract"
            )

    def text(item):
        return isinstance(item, str) and bool(item.strip()) and len(item) <= 2000

    require(isinstance(value, dict))
    require(
        set(value) == {"schema", "meaning", "next_checks", "references", "cause_note"}
    )
    require(value["schema"] == "gpu-rca-guidance/1.0")
    require(text(value["meaning"]) and text(value["cause_note"]))
    for field, keys in (
        ("next_checks", {"title", "text"}),
        ("references", {"title", "text", "source_indices"}),
    ):
        entries = value[field]
        require(isinstance(entries, list) and 0 < len(entries) <= 12)
        for entry in entries:
            require(isinstance(entry, dict) and set(entry) == keys)
            require(text(entry["title"]) and text(entry["text"]))
            if field == "references":
                indexes = entry["source_indices"]
                require(isinstance(indexes, list) and bool(indexes))
                require(all(type(i) is int and 0 <= i < len(sources) for i in indexes))


def project_guidance(evidence, reported=None):
    """Copy only the selected published immutable evidence, with provenance."""
    output = []
    for entry in evidence:
        if (
            entry.get("query_id") != "runbook"
            or entry.get("quality", {}).get("origin") != "published"
        ):
            continue
        content = entry.get("snapshot", {})
        guidance = content.get("operator_guidance")
        if guidance is None:
            continue
        validate_operator_guidance(guidance, content.get("sources", []))
        applicability = {}
        if content.get("classification", {}).get("category") == "general_investigation":
            # Selection keeps the general Runbook only when nothing dedicated applies.
            applicability = {"report_applicability": "general_fallback"}
        elif reported is not None:
            applies = content.get("decision_policy", {}).get("applies_when", {})
            codes = content.get("search", {}).get("codes", [])
            matched = (
                all(reported.get(key) == value for key, value in applies.items())
                if applies
                else bool(codes) and reported.get("reported_error_code") in codes
            )
            applicability = {
                "report_applicability": "matched" if matched else "reference_only"
            }
        output.append(
            {
                "evidence_id": entry["id"],
                "revision": entry.get("query_version"),
                "title": content.get("title", "Runbook"),
                "guidance": deepcopy(guidance),
                "sources": deepcopy(content["sources"]),
                **applicability,
            }
        )
    return output
