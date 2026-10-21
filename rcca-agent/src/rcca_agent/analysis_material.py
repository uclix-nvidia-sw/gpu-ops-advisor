"""Immutable RCA claims and their original source references."""

from copy import deepcopy
from agent_common.contracts import content_hash


def analysis_draft(
    candidates, recommendations, limitations, input_view, interpretation=None
):
    claims = [
        {
            "id": f"cause:{c['id']}",
            "source": "runbook" if c["causal_status"] == "supported" else "analysis",
            "statement": c["claim"],
            "supporting_refs": c["supporting_refs"],
            "contradicting_refs": c["contradicting_refs"],
            "value_refs": c.get("value_refs", []),
        }
        for c in candidates
    ]
    claims += [
        {
            "id": f"recommendation:{i}",
            "source": "runbook",
            "statement": r["text"],
            "supporting_refs": r["evidence_refs"],
            "contradicting_refs": [],
            "value_refs": r.get("value_refs", []),
        }
        for i, r in enumerate(recommendations)
    ]
    body = {
        "claims": claims,
        "cause_candidates": candidates,
        "recommendations": recommendations,
        "limitations": limitations,
        "input_view_hash": content_hash(input_view),
    }
    if interpretation is not None:
        body["interpretation"] = deepcopy(interpretation)
        for section in ("findings", "unknowns", "conflicts", "limitations"):
            for index, row in enumerate(interpretation.get(section, [])):
                claims.append(
                    {
                        "id": f"interpretation:{section}:{row.get('id', index)}",
                        "source": "interpretation",
                        "statement": row["statement"],
                        "supporting_refs": row["evidence_refs"],
                        "contradicting_refs": [],
                        "value_refs": [],
                    }
                )
        # Author criterion self-assessments are not reviewable claims: the goal
        # criterion is derived from this review's own rubric instead.
    return deepcopy({"analysis_id": content_hash(body), **body})
