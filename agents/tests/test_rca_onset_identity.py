from rcca_agent.incident_dossier import state_onset


def test_onset_requires_the_alert_code_and_pci_not_another_switch():
    selector = dict(
        component="accelerator-nvidia-error-sxid",
        error_code="sxid:19056",
        pci="PCI:0000:c6:00.0",
        k8s_node_name="dgx01",
        cluster_id="cpc-1",
    )
    base = dict(
        component=selector["component"],
        cluster_id="cpc-1",
        target={"node": "dgx01"},
        evidence_refs=["state"],
        raw_health="Unhealthy",
        observed_at="2026-10-29T07:13:00Z",
    )
    wrong_code = dict(
        base, error_code="sxid:11001", reported_pci_addresses=[selector["pci"]]
    )
    wrong_pci = dict(
        base,
        error_code=selector["error_code"],
        reported_pci_addresses=["PCI:0000:c7:00.0"],
    )
    healthy_node = dict(base, raw_health="Healthy", observed_at="2026-10-29T07:00:00Z")
    assert (
        state_onset(
            [wrong_code, wrong_pci, healthy_node],
            {"node": "dgx01"},
            [selector["error_code"]],
            selector,
        )
        is None
    )
    right = dict(
        base,
        error_code=selector["error_code"],
        reported_pci_addresses=[selector["pci"]],
    )
    onset = state_onset(
        [healthy_node, wrong_code, wrong_pci, right],
        {"node": "dgx01"},
        [selector["error_code"]],
        selector,
    )
    assert onset["code"] == "sxid:19056"
    assert onset["pci"] == selector["pci"]
    assert onset["last_healthy_at"] is None
    assert onset["first_unhealthy_at"] == right["observed_at"]
