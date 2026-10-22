"""Isolated DB/JC/Worker/MCP publication; upstream and model are fixtures."""

from copy import deepcopy
import json
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb
import pytest
import test_e2e as e2e
from agent_common.contracts import content_hash
from test_e2e import Upstream, ROOT, LOCAL, SCOPE, PERIOD, submit, worker_result


dossier_stack = e2e.stack


@pytest.mark.e2e
@pytest.mark.parametrize("kind,code", [("xid", "79"), ("sxid", "11001")])
def test_dossier_host_history_survives_real_publication(
    dossier_stack, monkeypatch, kind, code
):
    stack = dossier_stack
    monkeypatch.setattr(Upstream, "fleet_reports", True)
    monkeypatch.setattr(Upstream, "fleet_component", "accelerator-nvidia-error-" + kind)
    monkeypatch.setattr(Upstream, "fleet_reason", kind.upper() + " " + code)
    profile = deepcopy(stack["profile"])
    profile["health_contracts"] = json.loads(
        (ROOT / "agents/tests/fixtures/config-v7.json").read_text(encoding="utf-8")
    )["health_contracts"]
    profile["queries"]["D47"] = dict(
        source="mimir",
        metric="fixture_d47",
        unit="state",
        max_hold_seconds=30,
        revision="fixture-v1",
        validated=True,
    )
    config = LOCAL / ("dossier-" + kind + ".json")
    config.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setitem(stack["env"], "AGENT_CONFIG_FILE", str(config))
    book = json.loads(
        (ROOT / f"rcca-agent/runbooks/{kind}/RB-{kind.upper()}-{code}.json").read_text(
            encoding="utf-8"
        )
    )
    iid = str(uuid4())
    target = {"node": "node-1"}
    data = dict(
        scope=SCOPE,
        incident_id=iid,
        evidence_version=1,
        analysis_profile_revision="fixture-v1",
        incident_time=PERIOD["start"],
        time_range=PERIOD,
        purpose_ids=["R01"],
        target=target,
    )
    snapshot = {
        "input": data,
        "alert": {"labels": {"reason": kind.upper() + " " + code}},
    }
    with psycopg.connect(stack["url"]) as conn:
        conn.execute(
            "UPDATE knowledge_revisions SET state='retired' WHERE state='published'"
        )
        conn.execute(
            "INSERT INTO knowledge_revisions(id,knowledge_id,knowledge_key,revision,kind,state,visibility,content,content_hash,reviewed_content_hash,compatibility) VALUES(%s,%s,%s,1,'runbook','published','common',%s,%s,%s,%s)",
            (
                str(uuid4()),
                str(uuid4()),
                book["knowledge_key"],
                Jsonb(book["content"]),
                content_hash(book["content"]),
                content_hash(book["content"]),
                Jsonb({"cluster_id": "cpc-2"}),
            ),
        )
        conn.execute(
            "INSERT INTO incidents(id,cluster_id,scope,target,occurred_at,state,evidence_version) VALUES(%s,'cpc-2',%s,%s,%s,'open',1)",
            (iid, Jsonb(SCOPE), Jsonb(target), data["incident_time"]),
        )
        conn.execute(
            "INSERT INTO incident_evidence_versions(incident_id,revision,snapshot,content_hash) VALUES(%s,1,%s,%s)",
            (iid, Jsonb(snapshot), content_hash(snapshot)),
        )
    jid = submit(stack, "rca", data)
    result, evidence = worker_result(stack, "rca", jid, "-dossier-" + kind)
    assert result["quality"]["analysis"]["collection_max_rounds"] == 1
    history = result["quality"]["host_incident_history"]
    assert any(row["incident_id"] == iid and row["current"] for row in history["rows"])
    assert history["evidence_refs"]
    assert (
        result["quality"]["triage_observations"]["schema"]
        == "rca-triage-observations/1"
    )
    assert set(book["content"]["required_queries"]) <= {q for q, status in evidence}
    assert all(
        status in {"ok", "empty"}
        for q, status in evidence
        if q in book["content"]["required_queries"]
    ), evidence
    assert "analysis_review" not in {q for q, status in evidence}
    assert result["quality"]["rca_evaluation"]["review"]["reason"] == "not_requested"
    assert result["narrative"]
    # Read back the actual published result contract, including partial status.
    import asyncio
    from datetime import datetime, timezone
    from psycopg.rows import dict_row
    from rcca_agent.store import read_prior_rca

    async def published_history():
        async with await psycopg.AsyncConnection.connect(
            stack["url"], row_factory=dict_row
        ) as conn:
            history = {
                "period": {"end": datetime.now(timezone.utc).isoformat()},
                "rows": [{"body": {"id": iid}}],
            }
            await read_prior_rca(conn, {**data, "incident_id": str(uuid4())}, history)
            prior = history["rows"][0]["prior_rca"]
            assert prior["job_id"] == jid
            assert prior["content_hash"]
            assert prior["result_status"] == result["result_status"]
            earlier = {
                "period": {"end": "2000-01-01T00:00:00Z"},
                "rows": [{"body": {"id": iid}}],
            }
            await read_prior_rca(conn, {**data, "incident_id": str(uuid4())}, earlier)
            assert "prior_rca" not in earlier["rows"][0]

    asyncio.run(published_history())
    (LOCAL / ("published-dossier-" + kind + ".json")).write_text(
        json.dumps(result, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.e2e
async def test_sxid_pci_lookup_through_official_grafana_mcp(dossier_stack, monkeypatch):
    import time
    from agent_common.contracts import timestamp
    from agent_common.grafana_mcp import GrafanaMCPClient
    from agent_common.observation import Observation
    from rcca_agent.switch_inventory import collect_switch_pci

    stack = dossier_stack
    monkeypatch.setattr(
        Upstream,
        "prometheus_rows",
        {
            "": [
                {
                    "metric": {
                        "node": "node-1",
                        "cluster_id": "cpc-2",
                        "pci_bus_id": "00000000:CA:00.0",
                    },
                    "values": [[timestamp(PERIOD["start"]), "0"]],
                }
            ]
        },
    )
    async with GrafanaMCPClient(stack["env"]["GRAFANA_MCP_URL"]) as client:
        tool = await client.get_tool("query_prometheus")
        obs = Observation(
            {"query_prometheus": tool.acall},
            stack["profile"],
            {"scope": SCOPE, "target": {"node": "node-1"}, "time_range": PERIOD},
            time.monotonic() + 30,
        )
        # Resolved source metadata is fixture-owned; the request itself uses official MCP.
        obs.evidence.append(
            {
                "query_id": "D47",
                "cluster_id": "cpc-2",
                "quality": {
                    "datasource_uid": "mimir",
                    "resolved_cluster_selector": {"cluster_id": "cpc-2"},
                    "target_labels": {"node": "node"},
                },
            }
        )
        budget = {"queries": 1}
        rows = await collect_switch_pci(
            obs,
            budget,
            {"error_codes": ["sxid:11001"], "reason": "PCI:0000:ca:00.0"},
            [{"code": "sxid:11001", "device": "PCI:00000000:CA:00.0"}],
        )
    assert rows[0]["status"] == "ok"
    assert rows[0]["observed_pci"] == ["00000000:CA:00.0"]
    assert rows[0]["event_pci"] == rows[0]["alert_pci"] == ["0000:ca:00.0"]
    assert obs.evidence[-1]["query_id"] == "nvswitch_pci_inventory"
    assert budget["queries"] == 0
