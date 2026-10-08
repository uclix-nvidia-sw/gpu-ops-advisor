"""Offline audit and runtime selection must agree without changing input rows."""

from copy import deepcopy
import json
from pathlib import Path

from agent_common.contracts import content_hash
from rcca_agent.runbook_audit import audit, main
from rcca_agent.workflow import select_runbooks


ROOT = Path(__file__).resolve().parents[2]


def fixtures():
    profile = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    row = json.loads(
        (ROOT / "rcca-agent/runbooks/xid/RB-XID-79.json").read_text("utf-8")
    )
    row.update(
        id="fixture-revision",
        revision=2,
        compatibility={"producer_contract": "fixture-v1"},
    )
    row.update(
        content_hash=content_hash(row["content"]),
        reviewed_content_hash=content_hash(row["content"]),
    )
    return profile, row


def test_removed_query_is_invalid_even_for_matching_xid():
    profile, row = fixtures()
    row["content"]["observation_plan"][0]["query_id"] = "D05"
    row["content"]["required_queries"] = ["D05"]
    row.update(
        content_hash=content_hash(row["content"]),
        reviewed_content_hash=content_hash(row["content"]),
    )
    before = deepcopy(row)
    output = audit([row], profile)
    assert output["failure_reasons"] == {
        "observation_plan: unregistered or disallowed query": 1
    }

    class Evidence:
        data = {"time_range": {}}

        def _evidence(self, *args):
            self.diagnostics = args[3]

    obs = Evidence()
    selected, _ = select_runbooks([row], {"summary": "xid:79"}, profile, obs)
    assert not any(book["id"] == row["id"] for book in selected)
    assert obs.diagnostics[0]["reason"] == output["results"][0]["reason"]
    assert row == before


def test_valid_unrelated_book_is_not_an_invalid_contract():
    profile, row = fixtures()
    assert audit([row], profile)["counts"] == {"contract_valid": 1}
    # Applicability is deliberately outside the audit's content contract.
    row["compatibility"] = {"cluster_id": "another-cluster"}
    assert audit([row], profile)["counts"] == {"contract_valid": 1}


def test_hash_mismatch_and_draft_checks_are_separate():
    profile, row = fixtures()
    row["content"]["title"] = "Changed after review"
    assert audit([row], profile)["failure_reasons"] == {"unreviewed_content": 1}
    row["compatibility"] = {}
    assert audit([row], profile, authoring=True)["counts"] == {"contract_valid": 1}


def test_untrusted_value_is_not_copied_into_failure_reason():
    profile, row = fixtures()
    row["content"]["sources"][0]["checked_at"] = "secret-sentinel"
    row.update(
        content_hash=content_hash(row["content"]),
        reviewed_content_hash=content_hash(row["content"]),
    )
    output = audit([row], profile)
    assert output["counts"] == {"invalid_contract": 1}
    assert "secret-sentinel" not in json.dumps(output)


def test_cli_audits_all_rows_and_returns_failure(tmp_path, capsys):
    profile, row = fixtures()
    snapshot = tmp_path / "rows.json"
    config = tmp_path / "profile.json"
    snapshot.write_text(json.dumps([row, None]), encoding="utf-8")
    config.write_text(json.dumps(profile), encoding="utf-8")
    assert main([str(snapshot), "--profile", str(config)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["total"] == 2
    assert output["counts"] == {"contract_valid": 1, "invalid_contract": 1}
    assert output["writes"] == 0


def test_structural_success_does_not_approve_source_or_health_semantics():
    profile, row = fixtures()
    manifest = {
        "entries": [
            {
                "knowledge_key": row["knowledge_key"],
                "source_status": "definition_conflict",
            }
        ]
    }
    before = deepcopy(row)
    result = audit([row], profile, manifest=manifest)["results"][0]
    assert result["status"] == "contract_valid"
    assert "fleet_observation_time_unverified" in result["review"]["findings"]
    assert "source_applicability_review_required" in result["review"]["findings"]
    assert result["review"]["operational_approval"] == "not_assessed"
    assert row == before


def test_documented_source_and_time_gate_do_not_approve_content():
    profile, row = fixtures()
    profile["health_contracts"]["fleet-component-log-v1"][
        "loki_timestamp_is_observed_at"
    ] = True
    manifest = {
        "entries": [
            {"knowledge_key": row["knowledge_key"], "source_status": "documented"}
        ]
    }
    review = audit([row], profile, manifest=manifest)["results"][0]["review"]
    assert review["findings"] == ["error_specific_evidence_review_required"]
    assert review["operational_approval"] == "not_assessed"


def test_code_only_requirement_still_exposes_fleet_time_gate():
    profile, row = fixtures()
    row["content"]["required_evidence"] = ["error_code"]
    review = audit([row], profile, authoring=True, manifest={})["results"][0]["review"]
    assert review["fleet_time_gated_facts"] == ["error_code"]
    assert "fleet_observation_time_unverified" in review["findings"]


def test_observations_only_does_not_require_health_fact_time_gate():
    profile, row = fixtures()
    row["content"]["required_evidence"] = ["observations"]
    review = audit([row], profile, authoring=True, manifest={})["results"][0]["review"]
    assert review["fleet_time_gated_facts"] == []
    assert "fleet_observation_time_unverified" not in review["findings"]


def test_rejected_old_revision_still_exposes_query_migration_work():
    profile, row = fixtures()
    row["content"]["observation_plan"][0]["query_id"] = "D05"
    row["content"]["required_queries"] = ["D05"]
    output = audit([row, None], profile, authoring=True, manifest={})
    rejected, malformed = output["results"]
    assert rejected["status"] == "invalid_contract"
    assert rejected["review"]["unregistered_queries"] == ["D05"]
    assert "required_facts_not_in_required_plan" in rejected["review"]["findings"]
    assert malformed["status"] == "invalid_contract"
    assert malformed["review"]["findings"] == ["review_input_malformed"]
