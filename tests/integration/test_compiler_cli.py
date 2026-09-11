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
    result = runner.invoke(app, ["compile", str(proposal_path), "--verify", "--fixture", str(fixture_path)])
    assert result.exit_code == 0
    assert "PASS" in result.output
