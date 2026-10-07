"""Synthetic binding/consumer acceptance tests; never production verification."""

import copy
import json
from pathlib import Path
import time

import pytest

from agent_common.settings import Settings
from agent_common.query_contract import validate_profile, query_definition
from agent_common.observation import Observation, series
from agent_common.normalize import intervals
from agent_common.binding_samples import counter_delta
from ops_agent.workflow import query_ids, calculate
from rcca_agent.workflow import normalized_state
from rcca_agent.runbook_contract import validate_runbook

ROOT = Path(__file__).resolve().parents[2]
PERIOD = {"start": "2026-10-01T00:00:00Z", "end": "2026-10-01T00:01:00Z"}
DATA = {
    "scope": {"clusters": [{"cluster_id": "fixture", "namespaces": None}]},
    "time_range": PERIOD,
}
START = 1790812800


def profile(*, active_defaults=False):
    config = json.loads((ROOT / "agents/config.example.json").read_text("utf-8"))
    if not active_defaults:
        # Tests opt into their own synthetic verification, never deployed evidence.
        for binding in config["bindings"].values():
            binding["verification"]["status"] = "candidate"
    return config


def verified(
    config, query="D02", *, unit="percent", sample_type="gauge", cluster="fixture"
):
    bid = config["queries"][query]["binding_candidates"][0]
    binding = config["bindings"][bid]
    binding.update(
        producer_version="fixture-only-1",
        revision="fixture-binding-1",
        environment={
            "cluster_id": cluster,
            "datasource_uid": "fixture-mimir",
            "selector": {"cluster_id": cluster, "job": "fixture-producer"},
        },
        target_labels={
            "gpu_uuid": "UUID",
            "node": "node",
            "namespace": "namespace",
            "pod": "pod",
            "uid": "uid",
            "scrape_target": "instance",
        },
        unit=unit,
        sample_type=sample_type,
        timestamp_basis="prometheus_sample",
        sample_interval={"seconds": 15},
        max_hold={"seconds": 30},
        invalid_values={"sentinels": [999999], "minimum": 0, "maximum": None},
        counter_reset={"mode": "reject_decrease"}
        if sample_type == "counter"
        else {"mode": "not_applicable", "reason": "not a counter"},
        verification={
            "status": "verified",
            "observed_window": PERIOD,
            "retention_evidence": "fixture-only",
            "evidence_refs": ["fixture-only:binding"],
        },
    )
    config["queries"][query]["selected_binding"] = bid
    return binding


def test_same_uploaded_schema_and_worker_loader_and_chart():
    a = Settings("rca").profile()
    assert a == Settings("report").profile() == profile(active_defaults=True)
    assert len(a["queries"]) == 45
    assert len(a["bindings"]) == 57
    assert not {"D01", "D05", "D08", "D14"} & a["queries"].keys()
    assert (ROOT / "agents/config.example.json").read_bytes() == (
        ROOT / "charts/gpu-ops-advisor/files/agents.json"
    ).read_bytes()


@pytest.mark.parametrize(
    "query", [f"D{i:02}" for i in range(2, 50) if i not in (5, 8, 14)]
)
async def test_unselected_never_calls_any_remote_tool(query):
    async def forbidden(args):
        pytest.fail("unselected binding reached remote tool")

    config = profile()
    obs = Observation(
        dict.fromkeys(
            ("query_prometheus", "list_datasources", "query_loki_logs"), forbidden
        ),
        config,
        DATA,
        time.monotonic() + 30,
    )
    result = await obs.collect(query)
    assert result[0]["quality"]["reason"] == "binding_unselected"
    assert obs.calls == obs.discovery_calls == 0


@pytest.mark.parametrize(
    "field",
    [
        "producer_version",
        "environment",
        "target_labels",
        "unit",
        "sample_type",
        "timestamp_basis",
        "sample_interval",
        "max_hold",
        "invalid_values",
        "counter_reset",
        "verification",
    ],
)
def test_verified_cannot_omit_required_contract(field):
    config = profile()
    binding = verified(config)
    binding[field] = None
    with pytest.raises(ValueError):
        validate_profile(config)


def test_cluster_selection_is_explicit_and_alternative_requires_equivalence():
    config = profile()
    original = copy.deepcopy(verified(config))
    alternate = "fixture.alternative.D02"
    config["bindings"][alternate] = original
    config["queries"]["D02"]["binding_candidates"].append(alternate)
    config["clusters"] = {"fixture": {"bindings": {"D02": alternate}}}
    with pytest.raises(ValueError, match="equivalence"):
        validate_profile(config)
    original["equivalence_evidence_refs"] = ["fixture-only:same-unit-and-meaning"]
    validate_profile(config)
    before = copy.deepcopy(config)
    assert query_definition(config, "D02", "fixture")["binding_id"] == alternate
    assert config == before
    config["clusters"]["fixture"]["bindings"]["D02"] = None
    assert query_definition(config, "D02", "fixture")["reason"] == "binding_unselected"


def test_d09_binding_preserves_producer_time_and_freshness_fact_gates():
    from types import SimpleNamespace
    from test_fleet_rca import evidence, PERIOD as log_period

    config = profile()
    e = evidence()
    e["quality"].update(health_contract="fleet-component-log-v1", max_hold_seconds=30)
    data = {
        "scope": {"clusters": [{"cluster_id": "c", "namespaces": None}]},
        "time_range": log_period,
        "incident_time": log_period["end"],
        "target": {"machine_id": "machine-1", "k8s_node_name": "node-1"},
    }
    obs = SimpleNamespace(evidence=[e])
    state = normalized_state(obs, {"D09": [e]}, data, config, {})
    assert state[0][0]["normalized_health"] == "unhealthy"
    assert state[1] == {}
    config["health_contracts"]["fleet-component-log-v1"][
        "loki_timestamp_is_observed_at"
    ] = True
    state = normalized_state(obs, {"D09": [e]}, data, config, {})
    assert state[1]["error_code"] == "sxid:11001"
    e["quality"]["max_hold_seconds"] = 0
    assert normalized_state(obs, {"D09": [e]}, data, config, {})[1] == {}


def test_unverified_selected_and_retired_and_expression_are_rejected():
    config = profile()
    config["queries"]["D15"]["selected_binding"] = config["queries"]["D15"][
        "binding_candidates"
    ][0]
    with pytest.raises(ValueError, match="must be verified"):
        validate_profile(config)
    config = profile()
    config["queries"]["D01"] = config["queries"]["D02"]
    with pytest.raises(ValueError, match="retired"):
        validate_profile(config)
    config = profile()
    verified(config)["metric"] = "sum(DCGM_FI_DEV_GPU_UTIL)"
    with pytest.raises(ValueError, match="single metric"):
        validate_profile(config)


async def test_selected_binding_controls_uid_filters_and_provenance_without_discovery():
    config = profile()
    verified(config)
    calls = []

    async def query(args):
        calls.append(args)
        return {
            "data": [{"metric": {"UUID": "g", "node": "n"}, "values": [[START, "0"]]}]
        }

    obs = Observation(
        {"query_prometheus": query},
        config,
        {**DATA, "target": {"gpu_uuid": "g"}},
        time.monotonic() + 30,
    )
    result = await obs.collect("D02")
    assert obs.discovery_calls == 0 and len(calls) == 1
    assert calls[0]["datasourceUid"] == "fixture-mimir"
    assert (
        'job="fixture-producer"' in calls[0]["expr"] and 'UUID="g"' in calls[0]["expr"]
    )
    quality = result[0]["quality"]
    assert quality["binding_id"] == "nvidia_dcgm_exporter.D02"
    assert quality["binding_revision"] == "fixture-binding-1"
    assert quality["producer_version"] == "fixture-only-1"
    assert quality["allocation_semantics"] == "observed_pod_labels"
    assert series(result)[0]["labels"]["gpu_uuid"] == "g"
    assert result[0]["snapshot"]["data"][0]["metric"] == {"UUID": "g", "node": "n"}


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("environment", "binding_environment_mismatch"),
        ("namespace", "binding_scope_unavailable"),
    ],
)
async def test_unverified_projection_never_widens_scope(kind, reason):
    config = profile()
    binding = verified(config, cluster="other" if kind == "environment" else "fixture")
    data = copy.deepcopy(DATA)
    if kind == "namespace":
        binding["target_labels"].pop("namespace")
        data["scope"]["clusters"][0]["namespaces"] = ["a"]
    obs = Observation({}, config, data, time.monotonic() + 30)
    assert (await obs.collect("D02"))[0]["quality"]["reason"] == reason
    assert obs.calls == obs.discovery_calls == 0


async def test_invalid_sentinel_breaks_interval_and_raw_evidence_is_unchanged():
    config = profile()
    verified(config)
    raw = {
        "data": [
            {
                "metric": {"UUID": "g"},
                "values": [[START, "20"], [START + 15, "999999"], [START + 30, "30"]],
            }
        ]
    }

    async def query(args):
        return raw

    result = await Observation(
        {"query_prometheus": query}, config, DATA, time.monotonic() + 30
    ).collect("D02")
    spans = intervals(result, PERIOD)[0]["intervals"]
    assert spans == [(START, START + 15, 20), (START + 30, START + 60, 30)]
    assert raw["data"][0]["values"][1][1] == "999999"
    assert counter_delta([[0, 5], [15, 1]], 30) is None
    assert counter_delta([[0, 5], [60, 6]], 30) is None
    assert counter_delta([[0, 5], [15, 8]], 30) == 3


@pytest.mark.parametrize("criteria", ["1.1", "1.2"])
def test_all_report_plans_use_new_ids_and_legacy_plans_stay_available(criteria):
    config = profile()
    for i in range(1, 12):
        plan = query_ids(f"O{i:02}", criteria, profile=config)
        assert not {"D01", "D05", "D08"} & set(plan)
        assert len(plan) == len(set(plan))
        assert set(plan) <= config["queries"].keys()
    assert "D01" in query_ids("O01")
    assert "D08" in query_ids("O08")


def test_runbook_cannot_request_health_from_metric_binding():
    config = profile()
    row = json.loads(
        (ROOT / "rcca-agent/runbooks/RB-GENERAL-GPU-NODE.json").read_text("utf-8")
    )
    row["content"]["observation_plan"][0]["query_id"] = "D15"
    row["content"]["required_queries"] = ["D15"]
    with pytest.raises(ValueError, match="cannot produce"):
        validate_runbook(
            row, config["queries"], list(config["queries"]), authoring=True
        )


async def test_d02_d06_zero_activity_mapping_and_o08_match_old_inputs():
    from test_report_observation import evidence, row

    config = profile()
    gpu = evidence(
        "D02",
        [
            row(
                {"UUID": "g", "node": "n", "namespace": "a", "pod": "p"},
                "0",
                start=START,
                end=START + 60,
            )
        ],
        cluster="fixture",
    )
    pod = evidence(
        "D06",
        [
            row(
                {"node": "n", "namespace": "a", "pod": "p", "uid": "uid-1"},
                "1",
                start=START,
                end=START + 60,
            )
        ],
        cluster="fixture",
    )
    for e in (gpu, pod):
        e.update(time_range=PERIOD)
        e["quality"].update(
            complete=True, unit="percent", allocation_semantics="observed_pod_labels"
        )
    collected = {"D02": [gpu], "D06": [pod]}
    old = {**collected, "D01": [gpu], "D08": [gpu]}
    data = {
        **DATA,
        "group_by": ["namespace"],
        "incident_time": PERIOD["start"],
        "target": {"gpu_uuid": "g"},
    }
    for criteria in ("1.1", "1.2"):
        before = calculate("O08", data, old, {}, {}, criteria_version=criteria)
        after = calculate(
            "O08", data, collected, {}, {}, criteria_version=criteria, profile=config
        )
        assert [(m["value"], m["unit"], m["target"]) for m in after["metrics"]] == [
            (m["value"], m["unit"], m["target"]) for m in before["metrics"]
        ]
    obs = Observation({}, config, data, time.monotonic() + 30)
    obs.evidence = [gpu, pod]
    assert (
        normalized_state(obs, collected, data, config, {})[3][0]["pod_uid"] == "uid-1"
    )
    assert normalized_state(obs, {"D02": [gpu]}, data, config, {})[3] == []


def test_o01_optional_capacity_calculates_and_failure_preserves_vram():
    from test_report_observation import evidence, row

    def metric_input(query, value):
        e = evidence(
            query,
            [
                row(
                    {"gpu_uuid": "g", "node": "n"},
                    str(value),
                    start=START,
                    end=START + 60,
                )
            ],
            cluster="fixture",
        )
        e.update(time_range=PERIOD)
        e["quality"].update(complete=True, unit="MiB", sample_type="gauge")
        return e

    collected = {
        "D03": [metric_input("D03", 4)],
        "D15": [metric_input("D15", 12)],
        "D16": [metric_input("D16", 16)],
    }
    data = {**DATA, "group_by": ["cluster"]}
    topic = calculate("O01", data, collected, {}, {}, profile=profile())
    values = {m["id"]: m["value"] for m in topic["metrics"]}
    assert values["O01.gpu_memory_used_ratio"] == 0.25
    assert values["O01.gpu_memory_free_mean"] == 12
    collected.pop("D16")
    after = calculate("O01", data, collected, {}, {}, profile=profile())
    assert (
        next(
            m["value"]
            for m in after["metrics"]
            if m["id"] == "O01.gpu_memory_used_ratio"
        )
        is None
    )
    assert [
        (m["id"], m["value"])
        for m in topic["metrics"]
        if not m["quality"].get("optional")
    ] == [
        (m["id"], m["value"])
        for m in after["metrics"]
        if not m["quality"].get("optional")
    ]
    assert topic["status"] == after["status"]


@pytest.mark.parametrize(
    "query,unit,sample_type,dimensions",
    [
        ("D19", "load", "gauge", {"window": "load_duration"}),
        ("D20", "info", "info", {"condition": "condition", "status": "status"}),
    ],
)
def test_o01_binding_requires_consumed_dimensions(query, unit, sample_type, dimensions):
    config = profile()
    binding = verified(config, query, unit=unit, sample_type=sample_type)
    with pytest.raises(ValueError, match="consumer dimension"):
        validate_profile(config)
    binding["target_labels"].update(dimensions)
    validate_profile(config)
    binding["target_labels"][next(iter(dimensions))] = binding["target_labels"]["node"]
    with pytest.raises(ValueError, match="distinct entity and dimension"):
        validate_profile(config)


async def test_fleet_load_duration_reaches_o01_without_merging_windows():
    config = profile()
    binding = verified(config, "D19", unit="load")
    binding["target_labels"] = {"node": "node", "window": "load_duration"}
    snapshot = {
        "data": {
            "result": [
                {
                    "metric": {"node": "fixture-node", "load_duration": window},
                    "values": [[START, value], [START + 30, value]],
                }
                for window, value in (("1m0s", "2"), ("15m0s", "6"))
            ]
        }
    }
    original = copy.deepcopy(snapshot)

    async def query(args):
        assert args["expr"].startswith("cpu_load_average{")
        return copy.deepcopy(snapshot)

    obs = Observation({"query_prometheus": query}, config, DATA, time.monotonic() + 30)
    collected = {"D19": await obs.collect("D19")}
    topic = calculate(
        "O01", {**DATA, "group_by": ["cluster"]}, collected, {}, {}, profile=config
    )
    metrics = [m for m in topic["metrics"] if m["id"] == "O01.node_load_by_window"]
    assert {m["target"]["window"]: m["value"] for m in metrics} == {
        "1m0s": 2,
        "15m0s": 6,
    }
    assert all(m["unit"] == "load" and m["evidence_refs"] for m in metrics)
    assert snapshot == original
    assert collected["D19"][0]["snapshot"] == original


def test_optional_budget_does_not_reject_core_collection():
    from ops_agent.collection import collection_plan

    config = profile()
    verified(config)
    verified(config, "D15", unit="MiB")
    config["limits"]["max_queries"] = 1
    tasks, reason = collection_plan(
        config, {**DATA, "topic_ids": ["O01"]}, ["D02", "D15"], {"D02"}
    )
    assert reason is None
    assert tasks[0]["planned_calls"] == 1
    assert tasks[1]["omitted"] == "optional_query_budget_exhausted"


async def test_optional_collection_cannot_take_core_retry_reservation():
    from ops_agent.collection import collect_report

    config = profile()
    verified(config)
    verified(config, "D15", unit="MiB")
    config["report"]["limits"]["max_queries"] = 8
    seen = []

    async def query(args):
        seen.append(args["expr"])
        return {"data": []}

    _, _, summary = await collect_report(
        {"query_prometheus": query},
        config,
        {**DATA, "topic_ids": ["O01"]},
        time.monotonic() + 30,
        ["D15", "D02"],
        False,
        {"D02"},
    )
    base = next(t for t in summary["tasks"] if t["query_id"] == "D02")
    assert base["reserved_calls"] == 8
    assert seen[0].startswith("DCGM_FI_DEV_GPU_UTIL{")
    assert summary["query_calls"] == 2
