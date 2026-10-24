"""Catalog-wide reported-fact admission must not authorize state or actions."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from rcca_agent.retrieval import retrieve_runbooks
from rcca_agent.runbook_contract import validate_runbook
from rcca_agent.workflow import check_conditions, matching_runbooks

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "rcca-agent/runbooks"
PROFILE = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
REVIEW = json.loads((CATALOG / "requirements-review-20261008.json").read_text("utf-8"))
INCIDENT_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "incident-report-review-20261015.json").read_text("utf-8")
    )["entries"]
}
# Newest catalog-wide reviews: restore their previous values before the older chains.
REPORT_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "operator-report-review-20261022.json").read_text("utf-8")
    )["entries"]
}
XID_ACTION_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "xid-catalog-action-review-20261023.json").read_text("utf-8")
    )["entries"]
}
TRIAGE_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "triage-guidance-review-20261022.json").read_text("utf-8")
    )["entries"]
}
COVERAGE_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "metric-coverage-review-20261024.json").read_text("utf-8")
    )["entries"]
}
MEMORY_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "xid48-memory-review-20261023.json").read_text("utf-8")
    )["entries"]
}
WORDING_REVIEW = {
    e["file"]: e
    for e in json.loads(
        (CATALOG / "operator-wording-review-20261023.json").read_text("utf-8")
    )["entries"]
}
ROWS = [json.loads((CATALOG / e["file"]).read_text("utf-8")) for e in REVIEW["entries"]]
CODE_ROWS = [r for r in ROWS if r["knowledge_key"] != "RB-GENERAL-GPU-NODE"]


@pytest.mark.parametrize("row", CODE_ROWS, ids=lambda r: r["knowledge_key"])
def test_every_code_can_investigate_report_without_promoting_state_or_action(row):
    book = deepcopy(row)
    book["compatibility"] = {"producer_contract": "fleet-component-log-v1"}
    validate_runbook(book, PROFILE["queries"], list(PROFILE["queries"]))
    code = book["content"]["search"]["codes"][0]
    facts = {
        "reported_error_code": code,
        "reported_producer_contract": "fleet-component-log-v1",
    }
    data = {"scope": {"clusters": [{"cluster_id": "arbitrary-cluster"}]}}
    assert matching_runbooks([book], facts, facts, data) == ([book], [])
    for required in facts:
        incomplete = {k: v for k, v in facts.items() if k != required}
        assert matching_runbooks([book], incomplete, incomplete, data) == ([], [book])
    content = book["content"]
    assert content["investigation_only"] is True
    assert not check_conditions(content["applicability_conditions"], facts)
    for rec in content["recommendations"]:
        assert not check_conditions(rec["preconditions"], facts)
        assert rec["execution"] == "not_performed"
    assert "normalized_health" not in facts and "error_code" not in facts
    assert (
        retrieve_runbooks(ROWS, {"summary": code})[0]["runbook"]["knowledge_key"]
        == row["knowledge_key"]
    )


def test_review_covers_every_source_and_preserves_general_adapter_boundary():
    assert len(REVIEW["entries"]) == len(ROWS) == 267
    # Component runbooks were authored after this anchor review; they have no chain.
    assert {e["file"] for e in REVIEW["entries"]} == {
        p.relative_to(CATALOG).as_posix()
        for p in CATALOG.rglob("RB-*.json")
        if p.parent.name != "component"
    }
    assert len(CODE_ROWS) == 266
    for e, row in zip(REVIEW["entries"], ROWS):
        digest = hashlib.sha256(
            json.dumps(
                row["content"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        # Newest review first: metric coverage, memory guidance, wording, catalog
        # actions, triage, then the report review.
        for review in (
            COVERAGE_REVIEW,
            MEMORY_REVIEW,
            WORDING_REVIEW,
            XID_ACTION_REVIEW,
            TRIAGE_REVIEW,
            REPORT_REVIEW,
        ):
            report = review.get(e["file"])
            if not report:
                continue
            assert digest == report["after_content_sha256"]
            row = deepcopy(row)
            for field in report["added_fields"]:
                row["content"].pop(field)
            row["content"].update(deepcopy(report["previous_values"]))
            digest = hashlib.sha256(
                json.dumps(
                    row["content"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            assert digest == report["before_content_sha256"]
        if row["knowledge_key"] == "RB-GENERAL-GPU-NODE":
            followup = json.loads(
                (CATALOG / "general-requirements-review-20261012.json").read_text(
                    "utf-8"
                )
            )
            assert followup["before_content_sha256"] == e["after_content_sha256"]
            assert digest == followup["after_content_sha256"]
        elif row["knowledge_key"] in {"RB-XID-79", "RB-SXID-11001"}:
            followups = json.loads(
                (CATALOG / "operator-guidance-review-20261013.json").read_text("utf-8")
            )
            followup = next(
                item for item in followups["entries"] if item["file"] == e["file"]
            )
            assert followup["before_content_sha256"] == e["after_content_sha256"]
            selection_review = json.loads(
                (CATALOG / "auxiliary-selection-review-20261014.json").read_text(
                    "utf-8"
                )
            )
            selection = next(
                item
                for item in selection_review["entries"]
                if item["file"] == e["file"]
            )
            assert (
                selection["before_content_sha256"] == followup["after_content_sha256"]
            )
            original = deepcopy(row["content"])
            revision = INCIDENT_REVIEW.get(e["file"])
            if revision:
                fabric = revision.get("fabric_guidance_update")
                if fabric:
                    assert fabric["status"] == "local_review_not_published"
                    assert digest == fabric["after_content_sha256"]
                    assert set(fabric["previous_values"]) == {
                        "operator_guidance",
                        "sources",
                    }
                    original.update(deepcopy(fabric["previous_values"]))
                    digest = hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    assert digest == fabric["before_content_sha256"]
                single_phase = revision.get("single_phase_update")
                if single_phase:
                    assert single_phase["status"] == "local_review_not_published"
                    assert digest == single_phase["after_content_sha256"]
                    assert "decision_policy" not in original
                    original.update(deepcopy(single_phase["previous_values"]))
                    digest = hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    assert digest == single_phase["before_content_sha256"]
                reader_update = revision.get("reader_guidance_update")
                if reader_update:
                    assert reader_update["status"] == "local_review_not_published"
                    assert digest == reader_update["after_content_sha256"]
                    original.update(deepcopy(reader_update["previous_values"]))
                    digest = hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    assert digest == reader_update["before_content_sha256"]
                identity_update = revision.get("identity_guidance_update")
                if identity_update:
                    assert identity_update["status"] == "local_review_not_published"
                    assert digest == identity_update["after_content_sha256"]
                    assert set(identity_update["previous_values"]) == {
                        "operator_guidance"
                    }
                    original.update(deepcopy(identity_update["previous_values"]))
                    digest = hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    assert digest == identity_update["before_content_sha256"]
                guidance_update = revision.get("guidance_update")
                if guidance_update:
                    assert guidance_update["status"] == "local_review_not_published"
                    assert digest == guidance_update["after_content_sha256"]
                    original.update(deepcopy(guidance_update["previous_values"]))
                    digest = hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    assert digest == guidance_update["before_content_sha256"]
                policy_update = revision.get("decision_policy_update")
                if policy_update:
                    assert policy_update["status"] == "local_review_not_published"
                    assert digest == policy_update["after_content_sha256"]
                    assert (
                        policy_update["before_content_sha256"]
                        == revision["after_content_sha256"]
                    )
                    assert policy_update["added_fields"] == ["decision_policy"]
                    for field in policy_update["added_fields"]:
                        original.pop(field)
                    original.update(policy_update["previous_values"])
                    digest = hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                # Newest local review first: restore its previous values, then the chain.
                assert digest == revision["after_content_sha256"]
                original.update(deepcopy(revision["previous_values"]))
                digest = hashlib.sha256(
                    json.dumps(
                        original,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                assert digest == revision["before_content_sha256"]
            collection = selection.get("collection_update")
            if collection:
                assert collection["status"] == "local_review_not_published"
                assert digest == collection["after_content_sha256"]
                assert set(collection["previous_values"]) == {"observation_plan"}
                original.update(collection["previous_values"])
                digest = hashlib.sha256(
                    json.dumps(
                        original,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                assert digest == collection["before_content_sha256"]
            amendment = selection.get("operator_guidance_update")
            if amendment:
                assert amendment["status"] == "local_review_not_published"
                assert (
                    amendment["before_content_sha256"]
                    == selection["after_content_sha256"]
                )
                assert digest == amendment["after_content_sha256"]
                assert set(amendment["previous_values"]) == {
                    "sources",
                    "analysis_guidance",
                    "recommendations",
                    "operator_guidance",
                }
                original.update(amendment["previous_values"])
                assert (
                    hashlib.sha256(
                        json.dumps(
                            original,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode()
                    ).hexdigest()
                    == selection["after_content_sha256"]
                )
            else:
                assert digest == selection["after_content_sha256"]
            for step in original["observation_plan"]:
                step.pop("selection", None)
            del original["operator_guidance"]
            assert (
                hashlib.sha256(
                    json.dumps(
                        original,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                == e["after_content_sha256"]
            )
        else:
            assert digest == e["after_content_sha256"]
    general = next(r for r in ROWS if r["knowledge_key"] == "RB-GENERAL-GPU-NODE")
    assert general["content"]["required_evidence"] == [
        "observations",
    ]
    assert (
        general["content"]["required_evidence"]
        == json.loads(
            (ROOT / "rcca-agent/src/rcca_agent/general_runbook.json").read_text("utf-8")
        )["required_evidence"]
    )


def test_general_observations_do_not_require_or_establish_health():
    book = deepcopy(
        next(r for r in ROWS if r["knowledge_key"] == "RB-GENERAL-GPU-NODE")
    )
    book["compatibility"] = {"cluster_id": "fixture"}
    data = {"scope": {"clusters": [{"cluster_id": "fixture"}]}}
    assert matching_runbooks([book], {}, {"observations": True}, data) == ([book], [])
    assert matching_runbooks([book], {}, {}, data) == ([], [book])
    assert book["content"]["investigation_only"] is True
    assert book["content"]["recommendations"] == []
    assert not check_conditions(
        [{"field": "normalized_health", "equals": "unhealthy"}], {}
    )
    old = deepcopy(book)
    old["content"]["required_evidence"] = [
        "observations",
        "producer_contract",
        "normalized_health",
    ]
    assert matching_runbooks([old], {}, {"observations": True}, data) == ([], [old])


def test_every_code_has_operator_report_material_from_verified_queries():
    chart = json.loads(
        (ROOT / "charts/gpu-ops-advisor/files/agents.json").read_text("utf-8")
    )
    verified = {
        key.split(".")[1]
        for key, binding in chart["bindings"].items()
        if binding.get("verification", {}).get("status") == "verified"
    }
    curated = {"xid/RB-XID-79.json", "sxid/RB-SXID-11001.json"}
    assert (
        set(REPORT_REVIEW)
        == {e["file"] for e in REVIEW["entries"] if "/" in e["file"]} - curated
    )
    for row in CODE_ROWS:
        content = row["content"]
        assert content["operator_guidance"]["schema"] == "gpu-rca-guidance/1.0"
        planned = {step["query_id"] for step in content["observation_plan"]}
        assert "D09" in planned and planned <= verified


def test_new_code_revisions_opt_into_incident_report_but_legacy_stays():
    from rcca_agent.incident_dossier import enabled

    assert all(enabled([row]) for row in CODE_ROWS)
    legacy = json.loads(
        (ROOT / "agents/tests/fixtures/RB-XID-79-published-legacy.json").read_text(
            "utf-8"
        )
    )
    assert not enabled([legacy])
    general = next(r for r in ROWS if r["knowledge_key"] == "RB-GENERAL-GPU-NODE")
    assert not enabled([general])
