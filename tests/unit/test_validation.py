from copy import deepcopy

import pytest

from wysteria.api import parse_workflow, validate_workflow


def validate(data):
    import json

    return validate_workflow(parse_workflow(json.dumps(data), filename="workflow.json"))


def codes(result):
    return {item.code for item in result.diagnostics}


def test_valid_workflow_passes(workflow_data):
    assert validate(workflow_data).valid


def test_unknown_fields_are_rejected(workflow_data):
    workflow_data["unexpected"] = True
    assert "WYS101" in codes(validate(workflow_data))


def test_missing_fields_are_rejected(workflow_data):
    del workflow_data["outputs"]
    assert "WYS102" in codes(validate(workflow_data))


def test_duplicate_node_ids_are_rejected(workflow_data):
    workflow_data["nodes"].append(deepcopy(workflow_data["nodes"][0]))
    assert "WYS200" in codes(validate(workflow_data))


def test_dangling_node_reference_is_rejected(workflow_data):
    workflow_data["outputs"]["result"]["source"] = {"node": "missing"}
    assert "WYS301" in codes(validate(workflow_data))


def test_undeclared_input_is_rejected(workflow_data):
    workflow_data["nodes"][0]["inputs"] = {"value": {"input": "missing"}}
    workflow_data["edges"] = [
        {"source": {"input": "missing"}, "target_node": "constant", "target_input": "value"}
    ]
    assert "WYS300" in codes(validate(workflow_data))


def test_edges_are_required_for_node_inputs(workflow_data):
    workflow_data["nodes"][0]["inputs"] = {"value": {"input": "name"}}
    assert "WYS202" in codes(validate(workflow_data))


def test_cycle_is_rejected(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "first",
            "kind": "select",
            "inputs": {"value": {"node": "second"}},
            "config": {},
            "output_type": "string",
        },
        {
            "id": "second",
            "kind": "select",
            "inputs": {"value": {"node": "first"}},
            "config": {},
            "output_type": "string",
        },
    ]
    workflow_data["edges"] = [
        {"source": {"node": "second"}, "target_node": "first", "target_input": "value"},
        {"source": {"node": "first"}, "target_node": "second", "target_input": "value"},
    ]
    workflow_data["outputs"]["result"]["source"] = {"node": "first"}
    assert "WYS205" in codes(validate(workflow_data))


def test_capability_is_default_denied(workflow_data):
    workflow_data["capabilities"] = ["network.http"]
    result = validate(workflow_data)
    assert result.blocked
    assert "WYS400" in codes(result)


@pytest.mark.parametrize("kind", ["shell", "python", "sql"])
def test_unknown_node_kind_is_rejected(workflow_data, kind):
    workflow_data["nodes"][0]["kind"] = kind
    assert "WYS103" in codes(validate(workflow_data))
