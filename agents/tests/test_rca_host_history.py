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
