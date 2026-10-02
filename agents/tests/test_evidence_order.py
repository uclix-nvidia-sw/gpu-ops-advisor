"""Creation order survives deterministic parallel merge and deferred persistence."""

import json

from agent_common.observation import evidence_stamp
from agent_common.store import prepare_evidence


def test_record_time_and_sequence_survive_storage(monkeypatch):
    monkeypatch.setattr(
        "agent_common.observation.now", lambda: "2026-10-02T04:00:00.123456Z"
    )
    first, second = evidence_stamp(), evidence_stamp()
    assert first["record_sequence"] < second["record_sequence"]
    evidence = dict(scope={}, input={}, quality={"round": 0}, snapshot={}, **first)
    quality = json.loads(prepare_evidence(evidence)[2].obj)
    assert quality["recorded_at"] == first["collected_at"]
    assert quality["record_sequence"] == first["record_sequence"]
    assert evidence["quality"] == {"round": 0}
