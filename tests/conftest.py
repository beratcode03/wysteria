from copy import deepcopy

import pytest


@pytest.fixture
def workflow_data():
    return {
        "ir_version": 1,
        "name": "sample",
        "metadata": {"description": "test"},
        "inputs": {"name": {"type": "string"}},
        "nodes": [
            {
                "id": "constant",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "hello"},
                "output_type": "string",
            }
        ],
        "edges": [],
        "capabilities": [],
        "assertions": [],
        "outputs": {"result": {"source": {"node": "constant"}, "type": "string"}},
    }


@pytest.fixture
def copied_workflow(workflow_data):
    return deepcopy(workflow_data)
