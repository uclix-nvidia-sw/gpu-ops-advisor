"""Corpus coverage and source distinctions; the runtime contract is tested separately."""

import json
from pathlib import Path
import re

from rcca_agent.retrieval import retrieve_runbooks

ROOT = Path(__file__).resolve().parents[2]
BOOKS = ROOT / "rcca-agent/runbooks"


def test_catalog_coverage_and_code_specific_guidance():
    manifest = json.loads((BOOKS / "catalog-manifest.json").read_text("utf-8"))
    catalog = (
        ROOT / "docs/specs/rca-agent/references/fleet-gpud-error-catalog.md"
    ).read_text("utf-8")
    source_codes = {
        f"{kind}:{int(code)}"
        for code, kind in re.findall(
            r"^\| (\d+) \|.*dsx-ai-factory/[^\n]+/nvidia/(s?xid)/", catalog, re.M
        )
    }
    entries = manifest["entries"]
    codes = {entry["code"] for entry in entries}
    assert len(source_codes) == 264
    assert codes == source_codes | {"xid:133", "sxid:22012"}
    assert len(entries) == len(codes) == 266
    assert manifest["counts"] == {"xid": 173, "sxid": 93, "generic": 1}
    assert {p.relative_to(BOOKS).as_posix() for p in BOOKS.rglob("RB-*.json")} == {
        e["file"] for e in entries
    } | {"RB-GENERAL-GPU-NODE.json"}
    for entry in entries:
        row = json.loads((BOOKS / entry["file"]).read_text("utf-8"))
        content = row["content"]
        assert row["knowledge_key"] == entry["knowledge_key"]
        assert content["search"]["codes"] == [entry["code"]]
        assert content["applicability_conditions"] == [
            {"field": "error_code", "equals": entry["code"]}
        ]
        assert row["compatibility"] == {} and content["investigation_only"] is True
        assert content["analysis_guidance"]
        assert content["sources"] and content["limitations"]
        assert all(
            r["execution"] == "not_performed" for r in content["recommendations"]
        )


def test_conflicting_definitions_decoder_and_fatality_are_preserved():
    def book(key):
        return json.loads(
            (BOOKS / key.split("-")[0].lower() / f"RB-{key}.json").read_text("utf-8")
        )

    def text(key):
        return "\n".join(book(key)["content"]["analysis_guidance"])

    assert "Unrecovered ECC Error" in text("XID-142")
    assert "NVENC3 Error" in text("XID-142")
    assert "정의 충돌" in text("XID-142")
    assert "Unused" in text("XID-1")
    assert "event_type=Warning, PotentialFatal=true, AlwaysFatal=true" in text(
        "SXID-10003"
    )
    assert "PotentialFatal=true, AlwaysFatal=false" in text("SXID-11001")
    assert "재발" in text("SXID-11001")
    assert "PotentialFatal=false, AlwaysFatal=false" in text("SXID-11012")
    assert "R575" in text("XID-145") and "XID_154_EVAL" in text("XID-145")
    assert "미기재" in text("XID-167")
    assert "동반" in text("XID-154") and "완료 증거가 아니다" in text("XID-154")
    rows = [book("XID-48-63-64"), book("XID-63"), book("XID-64")]
    for code in (63, 64):
        ranked = retrieve_runbooks(rows, {"summary": f"Xid {code}"})
        assert ranked[0]["runbook"]["knowledge_key"] == f"RB-XID-{code}"
