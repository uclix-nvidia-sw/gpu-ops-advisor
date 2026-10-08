import copy

import pytest
from rcca_agent.retrieval import incident_terms, retrieve_runbooks


def runbook(key, title, codes=(), aliases=(), symptoms=()):
    return {
        "knowledge_key": key,
        "revision": 1,
        "content": {
            "title": title,
            "classification": {"domain": "GPU_DEVICE", "category": "GPU_ACCESS_LOST"},
            "search": {
                "codes": list(codes),
                "aliases": list(aliases),
                "symptoms": list(symptoms),
            },
        },
    }


def test_normalizes_xid_variants_without_changing_source():
    source = {"alert": {"summary": "NVRM Xid_79: GPU has fallen off the bus"}}
    assert "xid:79" in incident_terms(source)
    assert source["alert"]["summary"].startswith("NVRM")


def test_exact_error_code_outranks_shared_words():
    rows = [
        runbook("xid-79", "GPU access failure", ["xid:79"], ["fallen off the bus"]),
        runbook("generic-access", "GPU access failure", symptoms=["device missing"]),
    ]
    ranked = retrieve_runbooks(
        rows, {"alert": {"message": "XID 79 GPU access failure"}}
    )
    assert [item["runbook"]["knowledge_key"] for item in ranked] == [
        "xid-79",
        "generic-access",
    ]
    assert ranked[0]["exact_codes"] == ["xid:79"]
    assert ranked[0]["exact_score"] == 12


def test_no_overlap_abstains_instead_of_returning_every_runbook():
    rows = [runbook("xid-79", "GPU fallen off bus", ["xid:79"])]
    assert retrieve_runbooks(rows, {"alert": {"summary": "disk filesystem full"}}) == []


def test_ranking_is_deterministic_for_ties():
    rows = [runbook("b", "thermal issue"), runbook("a", "thermal issue")]
    ranked = retrieve_runbooks(rows, {"alert": {"summary": "thermal issue"}})
    assert [item["runbook"]["knowledge_key"] for item in ranked] == ["a", "b"]


def test_identity_and_untrusted_fact_fields_do_not_drive_search():
    rows = [runbook("xid-79", "GPU access failure", ["xid:79"])]
    source = {
        "alert": {
            "labels": {"node": "xid-79", "gpu_uuid": "GPU-79"},
            "verified_facts": {"error_code": "xid:79"},
        }
    }
    assert retrieve_runbooks(rows, source) == []


def test_grafana_grouped_alert_annotations_are_searchable():
    source = {"alert": {"alerts": [{"annotations": {"summary": "Xid 79"}}]}}
    assert "xid:79" in incident_terms(source)


def test_real_kernel_xid_format_preserves_code():
    source = {"alert": {"message": "NVRM: Xid (PCI:0000:07:00): 79, GPU lost"}}
    assert "xid:79" in incident_terms(source)


def test_reference_to_other_code_is_not_exact_match():
    book = runbook("xid-48", "Memory ECC Xid 48", ["xid:48"])
    book["content"]["description"] = "Unlike Xid 79, this is a memory issue"
    result = retrieve_runbooks([book], {"alert": {"message": "Xid 79"}})
    assert result == []


def test_repeating_alert_does_not_inflate_score():
    rows = [runbook("xid-79", "GPU access failure", ["xid:79"])]
    once = retrieve_runbooks(rows, {"alert": {"message": "Xid 79"}})
    repeated = retrieve_runbooks(rows, {"alert": {"message": "Xid 79 " * 30}})
    assert once[0]["total_score"] == repeated[0]["total_score"]


@pytest.mark.parametrize("top_k", [-1, 0, True, 1.5])
def test_invalid_top_k_is_rejected(top_k):
    with pytest.raises(ValueError, match="top_k"):
        retrieve_runbooks([], {}, top_k=top_k)


@pytest.mark.parametrize("boost", [-1, float("nan"), float("inf")])
def test_invalid_boost_is_rejected(boost):
    with pytest.raises(ValueError, match="exact_code_boost"):
        retrieve_runbooks([], {}, exact_code_boost=boost)


def test_inputs_are_unchanged():
    rows = [runbook("xid-79", "GPU access failure", ["xid:79"])]
    source = {"alert": {"annotations": {"summary": "Xid 79"}}}
    original = copy.deepcopy((rows, source))
    retrieve_runbooks(rows, source)
    assert (rows, source) == original


def test_xid_and_sxid_are_distinct():
    rows = [runbook("xid-79", "", ["xid:79"])]
    assert retrieve_runbooks(rows, {"alert": {"message": "SXid 79"}}) == []


@pytest.mark.parametrize("component", ["cpu", "disk"])
def test_code_free_component_error_cannot_select_code_specific_plan(component):
    rows = [
        runbook("xid-100", "error calculating CPU usage", ["xid:100"]),
        runbook("sxid-100", "error calculating CPU usage", ["sxid:100"]),
        runbook("general", "error calculating CPU usage"),
    ]
    ranked = retrieve_runbooks(
        rows,
        {"labels": {"component": component, "reason": "error calculating CPU usage"}},
    )
    assert [r["runbook"]["knowledge_key"] for r in ranked] == ["general"]


def test_matching_multiple_declared_codes_preserves_relevant_investigations():
    rows = [
        runbook("ecc", "GPU error", ["xid:48", "xid:63"]),
        runbook("access", "GPU error", ["xid:79"]),
        runbook("switch", "GPU error", ["sxid:79"]),
    ]
    ranked = retrieve_runbooks(rows, {"message": "GPU error Xid 48 and Xid 79"})
    assert {r["runbook"]["knowledge_key"] for r in ranked} == {"ecc", "access"}


def test_real_catalog_xid79_does_not_select_unrelated_codes():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "rcca-agent" / "runbooks"
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in root.rglob("RB-*.json")]
    ranked = retrieve_runbooks(
        rows,
        {
            "labels": {
                "component": "accelerator-nvidia-error-xid",
                "reason": "XID 79 ROBUST_CHANNEL_GPU_HAS_FALLEN_OFF_THE_BUS GPU has fallen off the bus detected on GPU PCI:0000:01:00",
            }
        },
    )
    assert ranked[0]["runbook"]["knowledge_key"] == "RB-XID-79"
    assert all(
        not r["runbook"]["content"].get("search", {}).get("codes")
        or r["exact_codes"] == ["xid:79"]
        for r in ranked
    )
