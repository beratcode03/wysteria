from pathlib import Path

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()

VALID_PROPOSAL = """
proposal_version: 1
source: llm
proposed_name: check_test
workflow:
  inputs:
    who:
      type: string
  nodes:
    - id: msg
      kind: constant
      config:
        value: hello
      output_type: string
      inputs: {}
  edges: []
  capabilities: []
  assertions: []
  outputs:
    out:
      source: {node: msg}
      type: string
"""

HAPPY_FIXTURE = """
fixture_version: 1
id: test-fix
inputs:
  who: "world"
expected:
  outputs:
    out: "hello"
"""

MISMATCH_FIXTURE = """
fixture_version: 1
id: test-fix
inputs:
  who: "world"
expected:
  outputs:
    out: "bye"
"""

MALFORMED_PROPOSAL = """
proposal_version: [invalid yaml
"""

UNSAFE_PROPOSAL = """
proposal_version: 1
source: llm
workflow:
  inputs: {}
  nodes:
    - id: msg
      kind: constant
      config: {value: hello}
      output_type: string
      inputs: {}
  edges: []
  capabilities: [network.http]
  assertions: []
  outputs: {}
"""

POLICY_DOC = """
policy_version: 1
name: test-policy
forbidden_capabilities: [network.http]
require_assertions: false
require_outputs: false
forbid_unreachable_nodes: false
"""


def test_check_valid_proposal(tmp_path: Path):
    prop_file = tmp_path / "prop.yaml"
    prop_file.write_text(VALID_PROPOSAL)
    fix_file = tmp_path / "fix.yaml"
    fix_file.write_text(HAPPY_FIXTURE)

    result = runner.invoke(app, ["check", str(prop_file), "--fixture", str(fix_file)])
    assert result.exit_code == 0
    assert "PASS" in result.stdout


def test_check_malformed_proposal(tmp_path: Path):
    prop_file = tmp_path / "prop.yaml"
    prop_file.write_text(MALFORMED_PROPOSAL)

    result = runner.invoke(app, ["check", str(prop_file)])
    assert result.exit_code == 2
    assert "error WYS900" in result.stderr


def test_check_unsafe_capability(tmp_path: Path):
    prop_file = tmp_path / "prop.yaml"
    prop_file.write_text(UNSAFE_PROPOSAL)
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(POLICY_DOC)

    result = runner.invoke(app, ["check", str(prop_file), "--policy", str(pol_file)])
    # Based on the contract, validation policy failure returns 1 or 2. We'll adjust if needed.
    assert result.exit_code != 0
    assert "error" in result.stderr or "FAIL" in result.stdout or "BLOCK" in result.stdout


def test_check_fixture_mismatch(tmp_path: Path):
    prop_file = tmp_path / "prop.yaml"
    prop_file.write_text(VALID_PROPOSAL)
    fix_file = tmp_path / "fix.yaml"
    fix_file.write_text(MISMATCH_FIXTURE)

    result = runner.invoke(app, ["check", str(prop_file), "--fixture", str(fix_file)])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "OUTPUT_MISMATCH" in result.stdout


EVIDENCE_PROPOSAL = """
proposal_version: 1
source: llm
proposed_name: evidence_check
workflow:
  inputs: {}
  nodes:
    - id: msg
      kind: constant
      config:
        value: hello
      output_type: string
      inputs: {}
  edges: []
  capabilities: []
  assertions: []
  outputs:
    out:
      source: {node: msg}
      type: string
claims:
  - id: endpoint
    type: api_endpoint
    subject: Example API
    source_url: https://example.com/api
"""


def test_check_evidence_without_snapshot_is_deterministic(tmp_path: Path):
    prop_file = tmp_path / "proposal.yaml"
    prop_file.write_text(EVIDENCE_PROPOSAL)
    result = runner.invoke(app, ["check", str(prop_file), "--evidence"])
    assert result.exit_code == 1
    assert "Evidence" in result.stdout
    assert "needs_evidence" in result.stdout
    assert not (tmp_path / ".wysteria" / "evidence").exists()


def test_check_update_snapshots_requires_evidence(tmp_path: Path):
    prop_file = tmp_path / "proposal.yaml"
    prop_file.write_text(EVIDENCE_PROPOSAL)
    result = runner.invoke(app, ["check", str(prop_file), "--update-snapshots"])
    assert result.exit_code == 4
    assert "--update-snapshots requires --evidence" in result.stderr


def test_check_evidence_uses_existing_snapshot_without_network(tmp_path: Path):
    from wysteria.evidence.models import Claim
    from wysteria.evidence.snapshot import EvidenceSnapshot, claim_hash, content_hash, save_snapshot

    prop_file = tmp_path / "proposal.yaml"
    prop_file.write_text(EVIDENCE_PROPOSAL)
    claim = Claim(
        id="endpoint",
        type="api_endpoint",
        subject="Example API",
        source_url="https://example.com/api",
    )
    snapshot_dir = tmp_path / ".wysteria" / "evidence"
    save_snapshot(
        EvidenceSnapshot(
            claim_id=claim.id,
            claim_hash=claim_hash(claim),
            source=claim.source_url,
            status_code=200,
            content_type="application/json",
            evidence_text='{"ok":true}',
            content_hash=content_hash(b'{"ok":true}'),
            body_base64="eyJvayI6dHJ1ZX0=",
            retrieved_at="2026-01-01T00:00:00Z",
        ),
        snapshot_dir,
    )
    result = runner.invoke(app, ["check", str(prop_file), "--evidence"])
    assert result.exit_code == 1
    assert "unverifiable" in result.stdout
    assert "https://example.com/api" in result.stdout
