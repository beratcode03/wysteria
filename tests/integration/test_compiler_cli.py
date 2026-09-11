import json
from pathlib import Path

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()


def test_compile_valid_proposal(tmp_path: Path):
    proposal_path = tmp_path / "proposal.yaml"
    proposal_path.write_text("""
proposal_version: 1
source: llm
proposed_name: valid_wf
workflow:
  inputs:
    who:
      type: string
  nodes:
    - id: node1
      kind: constant
      config:
        value: "hello"
      output_type: string
      inputs: {}
  edges: []
  capabilities: []
  assertions: []
  outputs:
    res:
      source:
        node: node1
      type: string
""")
    out_path = tmp_path / "compiled.yaml"
    result = runner.invoke(app, ["compile", str(proposal_path), "--output", str(out_path)])
    assert result.exit_code == 0
    assert "PASS compiled to" in result.output

    # Verify the output
    compiled = json.loads(out_path.read_text())
    assert compiled["name"] == "valid_wf"


def test_compile_invalid_proposal(tmp_path: Path):
    proposal_path = tmp_path / "proposal.yaml"
    proposal_path.write_text("""
proposal_version: 1
workflow:
  inputs: {}
  nodes:
    - id: bad
      kind: unknown
  outputs: {}
""")
    result = runner.invoke(app, ["compile", str(proposal_path)])
    assert result.exit_code == 1
    assert "error WYS103" in result.output


def test_compile_and_verify(tmp_path: Path):
    proposal_path = tmp_path / "proposal.yaml"
    proposal_path.write_text("""
proposal_version: 1
proposed_name: test
workflow:
  inputs:
    who:
      type: string
  nodes:
    - id: node1
      kind: constant
      config:
        value: "hello"
      output_type: string
      inputs: {}
  outputs:
    res:
      source:
        node: node1
      type: string
""")
    fixture_path = tmp_path / "fixture.yaml"
    fixture_path.write_text("""
fixture_version: 1
id: fix1
inputs:
  who: "world"
expected:
  outputs:
    res: "hello"
""")
    result = runner.invoke(
        app, ["compile", str(proposal_path), "--verify", "--fixture", str(fixture_path)]
    )
    assert result.exit_code == 0
    assert "PASS" in result.output


def test_compile_and_verify_http_node(tmp_path: Path):
    proposal_path = tmp_path / "proposal.yaml"
    proposal_path.write_text("""
proposal_version: 1
proposed_name: http_test
workflow:
  nodes:
    - id: req
      kind: http
      config:
        method: GET
        url: https://api.example.com/data
      output_type: object
    - id: sel
      kind: select
      inputs:
        value: {node: req}
      config:
        path: /count
      output_type: integer
  edges:
    - source: {node: req}
      target_node: sel
      target_input: value
  outputs:
    res:
      source: {node: sel}
      type: integer
  capabilities:
    - network.http
""")

    fixture_path = tmp_path / "fixture.yaml"
    fixture_path.write_text("""
fixture_version: 1
id: mock_fix
inputs: {}
mocks:
  req:
    count: 42
expected:
  outputs:
    res: 42
""")
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("""
policy_version: 1
id: allow_http
forbidden_capabilities: []
""")
    result = runner.invoke(
        app, ["compile", str(proposal_path), "--verify", "--fixture", str(fixture_path), "--policy", str(policy_path)]
    )
    print(result.output)
    assert result.exit_code == 0
    assert "PASS" in result.output
