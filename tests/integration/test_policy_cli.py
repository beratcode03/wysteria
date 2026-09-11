"""Integration tests for wysteria policy CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()

VALID_WORKFLOW = """ir_version: 1
name: min_flow
inputs:
  val: {type: string}
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config: {value: "hello"}
    output_type: string
edges: []
capabilities: []
assertions:
  - id: a1
    source: {node: n1}
    predicate: exists
outputs:
  out: {source: {node: n1}, type: string}
"""

FIXTURE = """fixture_version: 1
id: fix1
inputs:
  val: "test"
expected:
  outputs:
    out: "hello"
"""

PASSING_POLICY = """policy_version: 1
name: generous-policy
max_nodes: 10
max_edges: 10
require_assertions: true
require_outputs: true
forbid_unreachable_nodes: true
"""

BLOCKING_POLICY = """policy_version: 1
name: strict-policy
max_nodes: 0
"""


def test_cli_policy_check_pass(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(PASSING_POLICY, encoding="utf-8")

    result = runner.invoke(app, ["policy", "check", str(wf_file), "--policy", str(pol_file)])
    assert result.exit_code == 0
    assert "Result" in result.stdout
    assert "✓ PASS" in result.stdout


def test_cli_policy_check_block(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(BLOCKING_POLICY, encoding="utf-8")

    result = runner.invoke(app, ["policy", "check", str(wf_file), "--policy", str(pol_file)])
    assert result.exit_code == 1
    assert "Result" in result.stdout
    assert "✗ BLOCK" in result.stdout
    assert "WYS451" in result.stdout
    assert "max_nodes" in result.stdout


def test_cli_policy_check_format_json(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(BLOCKING_POLICY, encoding="utf-8")

    result = runner.invoke(
        app, ["policy", "check", str(wf_file), "--policy", str(pol_file), "--format", "json"]
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "BLOCK"
    assert data["passed"] is False
    assert len(data["violations"]) == 1
    assert data["violations"][0]["code"] == "WYS451"


def test_cli_policy_check_invalid_workflow(tmp_path: Path):
    wf_file = tmp_path / "broken_wf.yaml"
    wf_file.write_text("invalid yaml text [unclosed", encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(PASSING_POLICY, encoding="utf-8")

    result = runner.invoke(app, ["policy", "check", str(wf_file), "--policy", str(pol_file)])
    assert result.exit_code == 2
    assert "error WYS900" in result.stderr or "error WYS900" in result.stdout


def test_cli_policy_check_invalid_policy(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "broken_policy.yaml"
    pol_file.write_text("policy_version: 1\nextra_unknown_field: true\n", encoding="utf-8")

    result = runner.invoke(app, ["policy", "check", str(wf_file), "--policy", str(pol_file)])
    assert result.exit_code == 3
    assert "WYS450" in result.stderr or "WYS450" in result.stdout


def test_cli_policy_check_missing_policy_file(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    missing_pol = tmp_path / "nonexistent.yaml"

    result = runner.invoke(app, ["policy", "check", str(wf_file), "--policy", str(missing_pol)])
    assert result.exit_code == 3


def test_cli_policy_check_invalid_format(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(PASSING_POLICY, encoding="utf-8")

    result = runner.invoke(
        app, ["policy", "check", str(wf_file), "--policy", str(pol_file), "--format", "yaml"]
    )
    assert result.exit_code == 4
    assert "WYS900" in result.stderr


def test_cli_policy_check_report_file(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(PASSING_POLICY, encoding="utf-8")
    rep_file = tmp_path / "artifacts" / "policy_report.json"

    result = runner.invoke(
        app,
        [
            "policy",
            "check",
            str(wf_file),
            "--policy",
            str(pol_file),
            "--report-file",
            str(rep_file),
        ],
    )
    assert result.exit_code == 0
    assert rep_file.exists()
    data = json.loads(rep_file.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["passed"] is True


def test_cli_policy_check_github_annotations(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(BLOCKING_POLICY, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "policy",
            "check",
            str(wf_file),
            "--policy",
            str(pol_file),
            "--github-annotations",
        ],
    )
    assert result.exit_code == 1
    assert "::error title=WYS451::" in result.stderr


def test_cli_verify_with_policy_pass(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(FIXTURE, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(PASSING_POLICY, encoding="utf-8")

    result = runner.invoke(
        app,
        ["verify", str(wf_file), "--fixture", str(fix_file), "--policy", str(pol_file)],
    )
    assert result.exit_code == 0
    assert "Gate Decision" in result.stdout
    assert "✓ PASS" in result.stdout


def test_cli_verify_with_policy_block(tmp_path: Path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(FIXTURE, encoding="utf-8")
    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(BLOCKING_POLICY, encoding="utf-8")

    result = runner.invoke(
        app,
        ["verify", str(wf_file), "--fixture", str(fix_file), "--policy", str(pol_file)],
    )
    # Verification passed, but policy violation blocks
    assert result.exit_code == 1
    assert "Gate Decision" in result.stdout
    assert "✗ BLOCK" in result.stdout
    assert "policy violation" in result.stdout
