import copy
import pytest
from agent_common.contracts import validate_input
from ops_agent.workflow import calculate, query_ids
from test_report_observation import DATA, collected


@pytest.mark.parametrize(
    "groups",
    [
        None,
        {},
        {"O08": ["namespace"]},
        {"O01": ["namespace"], "O08": ["namespace"]},
        {"O01": ["cluster"], "O08": ["namespace", "namespace"]},
    ],
)
def test_bad_topic_group_maps_are_rejected(groups):
    data = dict(
        copy.deepcopy(DATA),
        timezone="UTC",
        topic_ids=["O01", "O08"],
        group_by=["cluster"],
        topic_group_by=groups,
    )
    with pytest.raises(ValueError):
        validate_input("report", data)


def test_per_topic_input_is_applied_without_mutation_and_requires_namespace_criteria():
    data = dict(
        copy.deepcopy(DATA),
        timezone="UTC",
        topic_ids=["O01", "O08"],
        group_by=["cluster"],
        topic_group_by={"O01": ["cluster"], "O08": ["namespace"]},
    )
    before = copy.deepcopy(data)
    validate_input("report", data)
    result = calculate("O08", data, collected(), {}, {}, criteria_version="1.2")
    assert result["quality"]["requested_group_by"] == ["namespace"]
    assert result["quality"]["applied_group_by"] == ["namespace"]
    assert data == before
    with pytest.raises(ValueError):
        calculate("O08", data, collected(), {}, {}, criteria_version="1.1")
    assert query_ids("O10", data={**data, "comparison_range": DATA["time_range"]}) == ()
    assert query_ids(
        "O10",
        data={
            **data,
            "comparison_range": DATA["time_range"],
            "action_record_ids": ["fixture"],
        },
    )
