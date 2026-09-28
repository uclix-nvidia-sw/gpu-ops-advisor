"""Batch preflight, rate limiting, idempotency and resume without a database."""

from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from agent_common.contracts import content_hash
from rcca_agent.runbook_import import import_runbooks, load_runbooks

ROOT = Path(__file__).resolve().parents[2]


def test_import_preflight_retry_and_resume(tmp_path, monkeypatch):
    profile = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    rows = load_runbooks(ROOT / "rcca-agent/runbooks/xid", profile)
    assert len(rows) == 173
    row = rows["RB-XID-63"]
    selected = {row["knowledge_key"]: row}
    requests, sleeps = [], []
    monkeypatch.setattr("rcca_agent.runbook_import.time.sleep", sleeps.append)

    def respond(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(
            201,
            json={
                "knowledge_id": "00000000-0000-0000-0000-000000000001",
                "revision_id": "00000000-0000-0000-0000-000000000002",
                "knowledge_key": row["knowledge_key"],
                "revision": 1,
                "version": 1,
                "state": "draft",
                "content_hash": content_hash(row["content"]),
            },
        )

    with httpx.Client(
        base_url="http://fixture/api/v1", transport=httpx.MockTransport(respond)
    ) as client:
        result = import_runbooks(client, selected, profile, "test", tmp_path)
        assert result == {"total": 1, "registered": 1, "resumed": 0}
        assert sleeps == [1]
        assert (
            requests[0].headers["Idempotency-Key"]
            == requests[1].headers["Idempotency-Key"]
        )
        assert requests[0].content == requests[1].content
        result = import_runbooks(client, selected, profile, "test", tmp_path)
        assert result == {"total": 1, "registered": 0, "resumed": 1}
        assert len(requests) == 2
        changed = deepcopy(selected)
        changed["RB-XID-63"]["compatibility"] = {"cluster_id": "changed"}
        with pytest.raises(ValueError, match="receipt/input mismatch"):
            import_runbooks(client, changed, profile, "test", tmp_path)
        with pytest.raises(ValueError, match="receipt/input mismatch"):
            import_runbooks(client, selected, profile, "different-batch", tmp_path)
        invalid = deepcopy(selected)
        invalid["RB-XID-63"]["content"]["schema"] = "invalid"
        with pytest.raises(ValueError):
            import_runbooks(client, invalid, profile, "test", tmp_path)
        with pytest.raises(ValueError, match="UUID strings"):
            import_runbooks(
                client, selected, profile, "test", tmp_path, {"RB-XID-63": 123}
            )
        assert len(requests) == 2
