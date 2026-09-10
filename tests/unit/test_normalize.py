import json

from hypothesis import given
from hypothesis import strategies as st

from wysteria.api import fingerprint_workflow, normalize_workflow, parse_workflow, validate_workflow


def workflow_from(data):
    result = validate_workflow(parse_workflow(json.dumps(data), filename="workflow.json"))
    assert result.valid
    return result.workflow


def test_node_order_does_not_change_fingerprint(workflow_data):
    other = dict(workflow_data)
    other["nodes"] = list(reversed(workflow_data["nodes"]))
    assert fingerprint_workflow(workflow_from(workflow_data)) == fingerprint_workflow(
        workflow_from(other)
    )


def test_normalization_is_idempotent(workflow_data):
    workflow = workflow_from(workflow_data)
    assert normalize_workflow(workflow) == normalize_workflow(workflow)


@given(st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), min_size=1, max_size=5))
def test_metadata_key_order_does_not_affect_fingerprint(labels):
    base = {
        "ir_version": 1,
        "name": "sample",
        "metadata": {"labels": [str(key) for key in labels]},
        "inputs": {},
        "nodes": [
            {
                "id": "value",
                "kind": "constant",
                "inputs": {},
                "config": {"value": 1},
                "output_type": "integer",
            }
        ],
        "edges": [],
        "capabilities": [],
        "assertions": [],
        "outputs": {"result": {"source": {"node": "value"}, "type": "integer"}},
    }
    reversed_data = dict(reversed(list(base.items())))
    assert fingerprint_workflow(workflow_from(base)) == fingerprint_workflow(
        workflow_from(reversed_data)
    )
