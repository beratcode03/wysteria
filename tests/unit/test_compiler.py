import json

import pytest

from wysteria.api import compile_proposal, parse_proposal
from wysteria.compiler.models import ProposalSource, WorkflowProposal
from wysteria.errors import WorkflowParseError
from wysteria.ir.models import Workflow


def test_parse_valid_proposal():
    text = """
    proposal_version: 1
    source: llm
    intent: test
    proposed_name: my_test
    workflow:
      nodes: []
    """
    prop = parse_proposal(text, format="yaml")
    assert prop.source == ProposalSource.LLM
    assert prop.intent == "test"
    assert prop.proposed_name == "my_test"
    assert prop.workflow == {"nodes": []}

def test_compile_valid_proposal():
    prop = WorkflowProposal(
        proposal_version=1,
        source=ProposalSource.LLM,
        proposed_name="test_wf",
        workflow={
            "inputs": {"who": {"type": "string"}},
            "nodes": [
                {
                    "id": "node1",
                    "kind": "constant",
                    "config": {"value": "hello"},
                    "output_type": "string",
                    "inputs": {}
                }
            ],
            "edges": [],
            "capabilities": [],
            "assertions": [],
            "outputs": {
                "res": {"source": {"node": "node1"}, "type": "string"}
            }
        }
    )
    result = compile_proposal(prop)
    assert result.success is True
    assert isinstance(result.workflow, Workflow)
    assert result.workflow.name == "test_wf"
    
def test_compile_invalid_proposal():
    prop = WorkflowProposal(
        proposal_version=1,
        workflow={
            "inputs": {},
            "nodes": [{"id": "bad", "kind": "unknown"}],
            "outputs": {}
        }
    )
    result = compile_proposal(prop)
    assert result.success is False
    assert result.workflow is None
    assert len(result.diagnostics) > 0

def test_adversarial_proposal_oversized():
    # Attempt to parse a huge document
    text = "proposal_version: 1\nworkflow:\n" + "  a: 1\n" * 100000
    with pytest.raises(WorkflowParseError):
        parse_proposal(text, format="yaml")
        
def test_adversarial_deeply_nested():
    text = "proposal_version: 1\nworkflow:\n"
    for i in range(100):
        text += "  " * i + "a:\n"
    text += "  " * 100 + "b: 1\n"
    with pytest.raises(WorkflowParseError):
        parse_proposal(text, format="yaml")

def test_adversarial_graph_cycles():
    prop = WorkflowProposal(
        proposal_version=1,
        proposed_name="test",
        workflow={
            "nodes": [
                {"id": "n1", "kind": "select", "config": {"path": ""}, "output_type": "string", "inputs": {"dep": {"node": "n2"}}},
                {"id": "n2", "kind": "select", "config": {"path": ""}, "output_type": "string", "inputs": {"dep": {"node": "n1"}}},
            ],
            "outputs": {}
        }
    )
    result = compile_proposal(prop)
    if not result.success:
        print(result.diagnostics)
    assert result.success is False

def test_compiler_determinism():
    prop1 = WorkflowProposal(
        proposal_version=1,
        proposed_name="test",
        workflow={
            "nodes": [{"id": "n1", "kind": "constant", "config": {"value": 1}, "output_type": "integer", "inputs": {}}],
            "outputs": {"res": {"source": {"node": "n1"}, "type": "integer"}},
            "edges": [], "capabilities": [], "assertions": [], "inputs": {}
        }
    )
    prop2 = WorkflowProposal(
        proposal_version=1,
        proposed_name="test",
        workflow={
            "outputs": {"res": {"source": {"node": "n1"}, "type": "integer"}},
            "nodes": [{"inputs": {}, "output_type": "integer", "config": {"value": 1}, "kind": "constant", "id": "n1"}],
            "edges": [], "assertions": [], "inputs": {}, "capabilities": []
        }
    )
    r1 = compile_proposal(prop1)
    r2 = compile_proposal(prop2)
    
    r1 = compile_proposal(prop1)
    r2 = compile_proposal(prop2)
    
    if not r1.success:
        print(r1.diagnostics)
    assert r1.success and r2.success
    # The normalized JSON representation should be identical
    from wysteria.api import normalize_workflow
    assert json.dumps(normalize_workflow(r1.workflow), sort_keys=True) == json.dumps(normalize_workflow(r2.workflow), sort_keys=True)
