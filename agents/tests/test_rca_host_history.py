from copy import deepcopy

import pytest

from rcca_agent.store import read_host_history
from rcca_agent.host_history import host_history
from rca_replay import replay
from test_rca_incident_dossier import dossier_case


def history_case():
    case = dossier_case("xid")
    data = case["attempt"]["claim"]["input"]
    item = {
        "body": {
            "id": "00000000-0000-4000-8000-000000000099",
            "cluster_id": "c",
            "target": {
                "node": "node-1",
                "machine_id": "machine-1",
                "gpu_uuid": "GPU-1",
            },
            "occurred_at": "2026-09-14T00:00:00Z",
            "first_seen": "2026-09-14T00:00:00Z",
            "last_seen": "2026-09-14T00:10:00Z",
        },
        "snapshot": {"alert": {"labels": {"reason": "Xid 48"}}},
    }
    history = {
        "period": {"start": "2026-09-01T00:00:00Z", "end": "2026-09-15T00:01:00Z"},
        "complete": True,
        "rows": [item],
    }
    case["attempt"]["context"]["host_incidents"] = history
    data["target"].update(node="node-1", machine_id="machine-1")
    return case, item


def test_history_deduplicates_incident_ids_and_excludes_other_hosts():
    case, item = history_case()
    ctx = case["attempt"]["context"]
    ctx["host_incidents"]["rows"].append(deepcopy(item))
    other = deepcopy(item)
    other["body"].update(
        id="other", target={"node": "node-1", "machine_id": "replacement"}
    )
    ctx["host_incidents"]["rows"].append(other)
    result = host_history(ctx, case["attempt"]["claim"]["input"])
    assert len(result["rows"]) == 1
    assert result["rows"][0]["reported_span_seconds"] == 600
    assert result["rows"][0]["codes"] == ["xid:48"]
    assert result["repeats"] == []


async def test_history_survives_model_failure_in_published_result_contract():
    case, _ = history_case()
    case["token_budget"] = 0
    outcome = await replay(case)
    result = outcome["output"]["result"]
    history = result["quality"]["host_incident_history"]
    assert len(history["rows"]) == 1
    assert history["evidence_refs"]
    assert any(
        "등록 사건 1건" in s["text"]
        for s in result["quality"]["report"]["source_items"]
    )
    assert result["quality"]["analysis"]["collection_max_rounds"] == 1
    assert not any(c["stage"] == "followup_selection" for c in outcome["model_calls"])


@pytest.mark.parametrize("machine", [None, "machine-1"])
async def test_store_history_query_is_scoped_bounded_and_parameterized(machine):
    class Connection:
        async def execute(self, sql, args):
            self.sql, self.args = sql, args
            return self

        async def fetchall(self):
            return [{"body": {"id": str(i)}, "snapshot": {}} for i in range(501)]

    conn = Connection()
    data = {
        "target": {"node": "node-1", "machine_id": machine},
        "scope": {"clusters": [{"cluster_id": "c"}]},
        "time_range": {"end": "2026-10-21T00:00:00Z"},
    }
    result = await read_host_history(conn, data, "2026-10-21T01:00:00+00:00")
    assert "dsx_scope_contains" in conn.sql and "LIMIT 501" in conn.sql
    assert "node-1" not in conn.sql
    assert conn.args[2] == (machine or "node-1")
    assert (conn.args[-1] - conn.args[-2]).days == 14
    assert len(result["rows"]) == 500 and result["complete"] is False


def test_history_uses_unique_reported_uuid_without_inventing_switch_gpu():
    case, item = history_case()
    item["body"]["target"].pop("gpu_uuid")
    gpu = "GPU-11111111-2222-3333-4444-555555555555"
    item["snapshot"]["alert"]["labels"]["reason"] = "Xid 79 UUID:" + gpu
    result = host_history(case["attempt"]["context"], case["attempt"]["claim"]["input"])
    assert result["rows"][0]["gpu_uuid"] == gpu
    item["snapshot"]["alert"]["labels"]["reason"] = "SXid 11001 UUID:" + gpu
    result = host_history(case["attempt"]["context"], case["attempt"]["claim"]["input"])
    assert result["rows"][0]["gpu_uuid"] is None


def test_history_marks_query_boundary_instead_of_claiming_last_observation():
    case, item = history_case()
    item["body"]["last_seen"] = "2026-09-16T00:00:00Z"
    result = host_history(case["attempt"]["context"], case["attempt"]["claim"]["input"])
    assert result["rows"][0]["last_report_capped"] is True
    assert result["rows"][0]["last_report"] == "2026-09-15T00:01:00Z"


def test_host_totals_include_both_identified_and_unidentified_devices():
    case, item = history_case()
    rows = case["attempt"]["context"]["host_incidents"]["rows"]
    for i, gpu in enumerate(["GPU-1", None, None]):
        other = deepcopy(item)
        other["body"]["id"] = f"other-{i}"
        other["body"]["target"]["gpu_uuid"] = gpu
        rows.append(other)
    result = host_history(case["attempt"]["context"], case["attempt"]["claim"]["input"])
    assert {
        (r["gpu_uuid"], r["code"]): r["incident_count"] for r in result["repeats"]
    } == {
        (None, "xid:48"): 4,
        ("GPU-1", "xid:48"): 2,
    }


async def test_legacy_plan_passes_host_history_to_analysis_not_only_the_report():
    from test_fleet_rca import match_case
    from rcca_agent.incident_dossier import enabled

    source, _ = history_case()
    case = match_case(kind="xid")
    assert not enabled(case["attempt"]["context"]["runbooks"])
    case["attempt"]["context"]["host_incidents"] = source["attempt"]["context"][
        "host_incidents"
    ]
    case["attempt"]["claim"]["input"]["target"].update(
        node="node-1", machine_id="machine-1"
    )
    case["token_budget"] = 131072
    outcome = await replay(case)
    call = next(c for c in outcome["model_calls"] if c["stage"] == "synthesis")
    rows = call["input"]["incident_comparison"]
    assert any("등록 사건 1건" in row["text"] for row in rows)
    history = outcome["output"]["result"]["quality"]["host_incident_history"]
    assert all(row["evidence_refs"] == history["evidence_refs"] for row in rows)


def test_switch_history_uses_full_pci_not_alert_gpu_label():
    case, item = history_case()
    item["snapshot"]["alert"]["labels"]["reason"] = "SXid 11001 PCI:0000:ca:00.0"
    result = host_history(case["attempt"]["context"], case["attempt"]["claim"]["input"])
    row = result["rows"][0]
    assert row["device"] == "NVSwitch PCI:0000:ca:00.0"
    assert row["gpu_uuid"] is None


async def test_prior_rca_uses_only_published_cutoff_scoped_results():
    from rcca_agent.store import read_prior_rca

    case, item = history_case()
    history = case["attempt"]["context"]["host_incidents"]

    class Connection:
        async def execute(self, sql, args):
            self.sql, self.args = sql, args
            return self

        async def fetchall(self):
            return [
                {
                    "incident_id": item["body"]["id"],
                    "job_id": "job",
                    "result_id": "result",
                    "content_hash": "hash",
                    "result_status": "partial",
                    "narrative_status": "complete",
                    "cause_candidates": [
                        {"claim": "과거 후보", "causal_status": "hypothesis"}
                    ],
                }
            ]

    conn = Connection()
    await read_prior_rca(conn, case["attempt"]["claim"]["input"], history)
    assert "published_result_id" in conn.sql and "a.ended_at<=%s" in conn.sql
    assert "dsx_scope_contains" in conn.sql and "LIMIT 500" in conn.sql
    assert conn.args[-1] == history["period"]["end"]
    assert item["prior_rca"]["content_hash"] == "hash"
    assert item["prior_rca"]["result_status"] == "partial"
    result = host_history(case["attempt"]["context"], case["attempt"]["claim"]["input"])
    assert (
        result["rows"][0]["prior_rca"]["cause_candidates"][0]["causal_status"]
        == "hypothesis"
    )
