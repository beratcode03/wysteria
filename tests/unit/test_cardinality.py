import json

from wysteria.api import parse_workflow, validate_workflow


def validate(data: dict):
    return validate_workflow(parse_workflow(json.dumps(data), filename="workflow.json"))


def codes(result):
    return {item.code for item in result.diagnostics}


def test_max_nodes_boundary(workflow_data):
    # Base has 1 node, so add 500 more -> 501 nodes
    nodes = []
    for i in range(501):
        nodes.append(
            {
                "id": f"node_{i}",
                "kind": "constant",
                "inputs": {},
                "config": {"value": i},
                "output_type": "integer",
            }
        )
    workflow_data["nodes"] = nodes
    workflow_data["outputs"]["result"]["source"] = {"node": "node_0"}
    workflow_data["outputs"]["result"]["type"] = "integer"

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS104" in codes(result)
    assert any("nodes" in d.path for d in result.diagnostics)


def test_max_edges_boundary(workflow_data):
    edges = [
        {
            "source": {"input": "name"},
            "target_node": "constant",
            "target_input": f"in_{i}",
        }
        for i in range(1001)
    ]
    workflow_data["edges"] = edges

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS104" in codes(result)
    assert any("edges" in d.path for d in result.diagnostics)


def test_max_inputs_boundary(workflow_data):
    workflow_data["inputs"] = {f"in_{i}": {"type": "string"} for i in range(101)}

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS104" in codes(result)
    assert any("inputs" in d.path for d in result.diagnostics)


def test_max_outputs_boundary(workflow_data):
    workflow_data["outputs"] = {
        f"out_{i}": {"source": {"node": "constant"}, "type": "string"} for i in range(101)
    }

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS104" in codes(result)
    assert any("outputs" in d.path for d in result.diagnostics)


def test_max_assertions_boundary(workflow_data):
    workflow_data["assertions"] = [
        {
            "id": f"assert_{i}",
            "source": {"node": "constant"},
            "predicate": "exists",
            "expected": None,
        }
        for i in range(201)
    ]

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS104" in codes(result)
    assert any("assertions" in d.path for d in result.diagnostics)
