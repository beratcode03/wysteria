import json

import pytest
from typer.testing import CliRunner

from wysteria.api import compile_proposal, diff_workflows
from wysteria.cli.main import app
from wysteria.compiler.models import WorkflowProposal
from wysteria.ir.normalize import fingerprint_workflow

runner = CliRunner()


@pytest.fixture
def minimal_proposal():
    return {
        "proposal_version": 1,
        "proposed_name": "test_workflow",
        "workflow": {
            "outputs": {"result": {"source": {"node": "const"}, "type": "string"}},
            "nodes": [
                {
                    "id": "const",
                    "kind": "constant",
                    "output_type": "string",
                    "config": {"value": "hello"},
                }
            ],
        },
        "claims": [],
    }


def test_no_claims(minimal_proposal):
    res = compile_proposal(WorkflowProposal.model_validate(minimal_proposal))
    assert res.success
    assert res.workflow.claims == []
    assert fingerprint_workflow(res.workflow)


def test_claims_preserved(minimal_proposal):
    minimal_proposal["claims"] = [
        {"id": "claim_1", "type": "factual", "subject": "Test", "node_id": "const"}
    ]
    res = compile_proposal(WorkflowProposal.model_validate(minimal_proposal))
    assert res.success
    assert len(res.workflow.claims) == 1
    assert res.workflow.claims[0].id == "claim_1"


def test_claims_fingerprint(minimal_proposal):
    res1 = compile_proposal(WorkflowProposal.model_validate(minimal_proposal))
    fp1 = fingerprint_workflow(res1.workflow)

    minimal_proposal["claims"] = [
        {"id": "claim_1", "type": "factual", "subject": "Test", "node_id": "const"}
    ]
    res2 = compile_proposal(WorkflowProposal.model_validate(minimal_proposal))
    fp2 = fingerprint_workflow(res2.workflow)

    assert fp1 != fp2


def test_claim_order_canonicalization(minimal_proposal):
    p1 = minimal_proposal.copy()
    p1["claims"] = [
        {"id": "claim_b", "type": "factual", "subject": "B", "node_id": "const"},
        {"id": "claim_a", "type": "factual", "subject": "A", "node_id": "const"},
    ]
    p2 = minimal_proposal.copy()
    p2["claims"] = [
        {"id": "claim_a", "type": "factual", "subject": "A", "node_id": "const"},
        {"id": "claim_b", "type": "factual", "subject": "B", "node_id": "const"},
    ]

    w1 = compile_proposal(WorkflowProposal.model_validate(p1)).workflow
    w2 = compile_proposal(WorkflowProposal.model_validate(p2)).workflow
    assert fingerprint_workflow(w1) == fingerprint_workflow(w2)


def test_claim_diff(minimal_proposal):
    p1 = minimal_proposal.copy()
    p1["claims"] = [
        {"id": "claim_1", "type": "factual", "subject": "A", "node_id": "const"},
        {"id": "claim_2", "type": "factual", "subject": "B", "node_id": "const"},
    ]
    w1 = compile_proposal(WorkflowProposal.model_validate(p1)).workflow

    p2 = minimal_proposal.copy()
    p2["claims"] = [
        {"id": "claim_2", "type": "factual", "subject": "C", "node_id": "const"},
        {"id": "claim_3", "type": "factual", "subject": "D", "node_id": "const"},
    ]
    w2 = compile_proposal(WorkflowProposal.model_validate(p2)).workflow

    diff = diff_workflows(w1, w2)
    assert not diff.identical
    categories = [(c.change_type, c.target_id) for c in diff.changes]
    assert ("claim_removed", "claim_1") in categories
    assert ("claim_changed", "claim_2") in categories
    assert ("claim_added", "claim_3") in categories


def test_cli_verify_evidence(tmp_path):
    workflow_path = tmp_path / "workflow.yaml"
    fixture_path = tmp_path / "fixture.yaml"

    workflow_path.write_text("""
ir_version: 1
name: test
outputs:
  out:
    source: {node: const}
    type: string
nodes:
  - id: const
    kind: constant
    output_type: string
    config: {value: hello}
claims:
  - id: claim_1
    type: factual
    subject: Test
    node_id: const
    source_url: https://example.com/evidence
""")
    fixture_path.write_text("""
fixture_version: 1
id: test-fixture
name: test
inputs: {}
expected:
  outputs:
    out: hello
""")

    # Verify without evidence
    res = runner.invoke(
        app, ["verify", str(workflow_path), "--fixture", str(fixture_path), "--format", "json"]
    )
    assert res.exit_code == 0, res.stdout
    out = json.loads(res.stdout)
    # Evidence results should be missing or None
    assert "evidence_results" not in out or out["evidence_results"] is None

    # Verify with evidence
    res2 = runner.invoke(
        app,
        [
            "verify",
            str(workflow_path),
            "--fixture",
            str(fixture_path),
            "--evidence",
            "--format",
            "json",
        ],
    )
    assert res2.exit_code == 1  # Needs evidence because no snapshot exists
    out2 = json.loads(res2.stdout)
    assert out2["evidence_results"][0]["status"] == "needs_evidence"

    # Verify with update snapshots and blocked policy
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("""
policy_version: 1
forbidden_evidence_hosts: ["example.com"]
""")
    res3 = runner.invoke(
        app,
        [
            "verify",
            str(workflow_path),
            "--fixture",
            str(fixture_path),
            "--policy",
            str(policy_path),
            "--evidence",
            "--update-snapshots",
            "--format",
            "json",
        ],
    )
    assert res3.exit_code == 1
    out3 = json.loads(res3.stdout)
    assert out3["evidence_results"][0]["status"] == "blocked"

    # Trust tier test
    policy2_path = tmp_path / "policy2.yaml"
    policy2_path.write_text("""
policy_version: 1
evidence_host_trust_tiers:
  "example.com": 3
max_evidence_trust_tier: 2
""")
    res4 = runner.invoke(
        app,
        [
            "verify",
            str(workflow_path),
            "--fixture",
            str(fixture_path),
            "--policy",
            str(policy2_path),
            "--evidence",
            "--update-snapshots",
            "--format",
            "json",
        ],
    )
    assert res4.exit_code == 1
    out4 = json.loads(res4.stdout)
    assert out4["evidence_results"][0]["status"] == "blocked"

    # No network access if --evidence is not passed (handled implicitly by first test)
