from copy import deepcopy
from uuid import uuid4

import pytest

from test_aggregate_report import DATA, fixture
from ops_agent.aggregate_report import build_result
from ops_agent.report_contract import VERSION, previous_period
from ops_agent.report_queries import memory_queries
from ops_agent.report_interpretation import payload_for
from agent_common.contracts import validate_result
from agent_common.artifacts import render


def memory_fixture(activity=None):
    e = deepcopy((activity or fixture())[0])
    labels = {
        k: v for k, v in e["snapshot"]["series"][0]["metric"].items() if k != "measure"
    }
    times = [at for at, _ in e["snapshot"]["series"][0]["values"]]
    e.update(id=str(uuid4()), query_id="hourly_gpu_memory")
    e["snapshot"]["series"] = [
        {
            "metric": {**labels, "measure": f"{f}_{m}"},
            "values": [[at, str(v)] for at in times],
        }
        for f, size in (("used", 4096), ("free", 12288))
        for m, v in (("sum", size * 240), ("count", 240), ("min", size), ("max", size))
    ]
    return e


def result(evidence):
    context = {
        "data_cutoff_at": DATA["time_range"]["end"],
        "incidents": [],
        "previous_incidents": [],
    }
    claim = {
        "job_id": str(uuid4()),
        "kind": "report",
        "input": DATA,
        "versions": {"criteria": VERSION},
    }
    return build_result(claim, context, evidence)


def test_memory_preserves_activity_and_stores_referenced_metrics_and_csv():
    evidence = fixture() + fixture(previous_period(DATA))
    before = result(evidence)
    memory = memory_fixture(evidence)
    after = result(evidence + [memory])
    a, b = before["topics"][0], after["topics"][0]
    assert {k: v for k, v in b["rows"][0].items() if k != "gpu_memory"} == {
        k: v for k, v in a["rows"][0].items() if k != "gpu_memory"
    }
    assert b["metrics"][: len(a["metrics"])] == a["metrics"]
    assert after["result_status"] == before["result_status"]
    assert after["topics"][1] == before["topics"][1]
    assert b["rows"][0]["gpu_memory"]["used_gib_per_gpu"] == 4
    assert b["rows"][0]["gpu_memory"]["free_gib_per_gpu"] == 12
    assert b["findings"][0]["memory_refs"]
    assert memory["id"] in b["findings"][0]["evidence_refs"]
    validate_result(after, evidence + [memory])
    assert b"memory_used" in render(after)["csv"]
    assert payload_for(after)["topics"][0]["findings"][0]["memory_refs"]


@pytest.mark.parametrize(
    "problem",
    [
        "missing",
        "duplicate",
        "count",
        "sentinel",
        "negative",
        "nan",
        "labels",
        "unavailable",
        "transition",
    ],
)
def test_optional_memory_rejects_unverified_data_without_losing_activity(problem):
    evidence = fixture()
    mem = memory_fixture(evidence)
    series = mem["snapshot"]["series"]
    if problem == "missing":
        series.pop()
    elif problem == "duplicate":
        series.append(deepcopy(series[0]))
    elif problem in {"count", "sentinel", "negative", "nan"}:
        measure, value = {
            "count": ("used_count", "239"),
            "sentinel": ("used_max", "9223372036854775794"),
            "negative": ("free_min", "-1"),
            "nan": ("used_sum", "NaN"),
        }[problem]
        for s in series:
            if s["metric"]["measure"] == measure:
                s["values"] = [[at, value] for at, _ in s["values"]]
    elif problem == "labels":
        for s in series:
            s["metric"]["namespace"] = "other"
    elif problem == "unavailable":
        mem["tool_status"] = "unavailable"
    else:
        other = deepcopy(evidence[0])
        for s in other["snapshot"]["series"]:
            s["metric"]["pod"] = "different"
        evidence.append(other)
    baseline = result(evidence)
    actual = result(evidence + [mem])
    row = actual["topics"][0]["rows"][0]
    assert row["gpu_memory"]["status"] == "unavailable"
    assert (
        row["activity_percent"] == baseline["topics"][0]["rows"][0]["activity_percent"]
    )
    assert actual["result_status"] == baseline["result_status"]


def test_memory_query_is_one_hourly_request_with_source_identity_and_period_boundary():
    query = memory_queries(DATA["scope"]["clusters"][0])
    assert list(query) == ["hourly_gpu_memory"]
    expr = query["hourly_gpu_memory"]
    assert expr.count("offset 1ms") == 8
    assert "sum by" not in expr
    assert 'cluster_id="cpc-1"' in expr
    assert 'collection_path="alloy-direct"' in expr


def test_extra_memory_identity_is_not_silently_deduplicated():
    evidence = fixture()
    mem = memory_fixture(evidence)
    duplicate = deepcopy(mem["snapshot"]["series"])
    for series in duplicate:
        series["metric"]["instance"] = "second-exporter"
    mem["snapshot"]["series"] += duplicate
    row = result(evidence + [mem])["topics"][0]["rows"][0]
    assert row["activity_percent"] == 60
    assert row["gpu_memory"]["status"] == "unavailable"


def test_memory_observation_and_check_scope_are_fixed_from_verified_values():
    from test_report_interpretation import reply_for
    from ops_agent.report_interpretation import validate_sections

    body = result(fixture() + [memory_fixture()])
    payload = payload_for(body)
    reply = reply_for(payload)
    reply["sections"][0].update(
        observation="사용 메모리는 999 GiB입니다.",
        meaning="연산 활동과 메모리 점유를 함께 확인할 필요가 있습니다.",
        next_check="요청량과 상주 프로세스 기록을 확인하세요.",
    )
    accepted = validate_sections(reply, payload, body)[0]
    assert accepted["observation_source"] == "calculated"
    assert "4.00 GiB/GPU" in accepted["observation"]
    assert "12.00 GiB/GPU" in accepted["observation"]
    assert "999" not in accepted["text"]
    assert (
        "test-dept-service" in accepted["next_check"]
        and "KST" in accepted["next_check"]
    )
    reply["sections"][0]["meaning"] = "여유 메모리는 999 GiB입니다."
    with pytest.raises(ValueError, match="unsupported_prose"):
        validate_sections(reply, payload, body)


@pytest.mark.parametrize(
    "claim",
    [
        "메모리 사용량이 증가했습니다.",
        "여유 메모리가 충분합니다.",
        "메모리를 소량 사용하고 있습니다.",
    ],
)
def test_unsupported_memory_interpretations_are_refused(claim):
    from test_report_interpretation import reply_for
    from ops_agent.report_interpretation import validate_sections

    body = result(fixture() + [memory_fixture()])
    payload = payload_for(body)
    reply = reply_for(payload)
    reply["sections"][0]["meaning"] += claim
    with pytest.raises(ValueError, match="unsupported_memory_claim"):
        validate_sections(reply, payload, body)


def test_memory_does_not_relax_model_check_length_limit():
    from ops_agent.report_interpretation import validate_sections
    from test_report_interpretation import reply_for

    data = result(fixture() + [memory_fixture()])
    payload = payload_for(data)
    reply = reply_for(payload)
    section = next(s for s in reply["sections"] if s["topic_id"] == "namespace_usage")
    section["next_check"] = "확인" * 226
    with pytest.raises(ValueError, match="invalid_section_text"):
        validate_sections(reply, payload, data)


def test_memory_uses_sample_weighted_mean_and_marks_partial_hours():
    evidence = fixture()
    mem = memory_fixture(evidence)
    for e in evidence:
        for s in e["snapshot"]["series"]:
            measure = s["metric"].get("measure")
            for i, point in enumerate(s["values"]):
                count = 238 if i == 0 else 242
                if e["query_id"] == "hourly_pod_identity" or measure == "sample_count":
                    point[1] = str(count)
                elif measure == "activity_sum":
                    point[1] = str(60 * count)
    for s in mem["snapshot"]["series"]:
        field, measure = s["metric"]["measure"].split("_")
        s["values"] = s["values"][:2]
        for i, point in enumerate(s["values"]):
            count = 238 if i == 0 else 242
            used = 4096 if i == 0 else 8192
            size = used if field == "used" else 16384 - used
            point[1] = str(
                count
                if measure == "count"
                else size * count
                if measure == "sum"
                else size
            )
    row = result(evidence + [mem])["topics"][0]["rows"][0]
    memory = row["gpu_memory"]
    assert row["activity_percent"] == 60
    assert memory["used_gib_per_gpu"] == pytest.approx((4 * 238 + 8 * 242) / 480)
    assert memory["status"] == "partial"
    assert sum(h["used_gib_per_gpu"] is not None for h in memory["hours"]) == 2
