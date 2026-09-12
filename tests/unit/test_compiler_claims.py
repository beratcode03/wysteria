from wysteria.api import compile_proposal
from wysteria.compiler.models import WorkflowProposal


def test_compile_valid_claim():
    prop = WorkflowProposal(
        proposal_version=1,
        proposed_name="test_wf",
        workflow={
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {},
                }
            ],
            "outputs": {"res": {"source": {"node": "node1"}, "type": "string"}},
        },
        claims=[
            {
                "id": "claim1",
                "type": "factual",
                "subject": "test",
                "node_id": "node1",
            }
        ],
    )
    result = compile_proposal(prop)
    assert result.success is True
    assert result.workflow is not None


def test_compile_duplicate_claim():
    prop = {
        "proposal_version": 1,
        "proposed_name": "test_wf",
        "workflow": {
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {},
                }
            ],
            "outputs": {"res": {"source": {"node": "node1"}, "type": "string"}},
        },
        "claims": [
            {
                "id": "claim1",
                "type": "factual",
                "subject": "test",
                "node_id": "node1",
            },
            {
                "id": "claim1",
                "type": "factual",
                "subject": "test2",
                "node_id": "node1",
            },
        ],
    }
    result = compile_proposal(prop)
    assert result.success is False
    assert result.workflow is None
    assert any(d.message.startswith("duplicate claim id") for d in result.diagnostics)


def test_compile_malformed_claim():
    prop = {
        "proposal_version": 1,
        "proposed_name": "test_wf",
        "workflow": {
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {},
                }
            ],
            "outputs": {"res": {"source": {"node": "node1"}, "type": "string"}},
        },
        "claims": [
            {
                "id": 123,  # Invalid type, should be string
                "type": "factual",
                "subject": "test",
                "node_id": "node1",
            }
        ],
    }
    result = compile_proposal(prop)
    assert result.success is False
    assert result.workflow is None
    assert any(d.message.startswith("malformed claim structure") for d in result.diagnostics)


def test_compile_unsupported_claim():
    prop = WorkflowProposal(
        proposal_version=1,
        proposed_name="test_wf",
        workflow={
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {},
                }
            ],
            "outputs": {"res": {"source": {"node": "node1"}, "type": "string"}},
        },
        claims=[
            {
                "id": "claim1",
                "type": "unknown",
                "subject": "test",
                "node_id": "node1",
            }
        ],
    )
    result = compile_proposal(prop)
    assert result.success is False
    assert result.workflow is None
    assert any(d.message.startswith("unsupported claim type") for d in result.diagnostics)


def test_compile_unrelated_claim():
    prop = WorkflowProposal(
        proposal_version=1,
        proposed_name="test_wf",
        workflow={
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {},
                }
            ],
            "outputs": {"res": {"source": {"node": "node1"}, "type": "string"}},
        },
        claims=[
            {
                "id": "claim1",
                "type": "factual",
                "subject": "test",
                "node_id": "non_existent_node",
            }
        ],
    )
    result = compile_proposal(prop)
    assert result.success is False
    assert result.workflow is None
    assert any(
        "not explicitly associated with a valid workflow node" in d.message
        for d in result.diagnostics
    )


def test_compile_invalid_claim_type():
    prop = {
        "proposal_version": 1,
        "proposed_name": "test_wf",
        "workflow": {
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {},
                }
            ],
            "outputs": {"res": {"source": {"node": "node1"}, "type": "string"}},
        },
        "claims": [
            {
                "id": "claim1",
                "type": "invalid_type",
                "subject": "test",
                "node_id": "node1",
            }
        ],
    }
    result = compile_proposal(prop)
    assert result.success is False
    assert result.workflow is None
    assert any(d.message.startswith("malformed claim structure") for d in result.diagnostics)
