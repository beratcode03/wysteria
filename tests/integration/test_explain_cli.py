"""Integration tests for wysteria explain CLI command."""

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
assertions: []
outputs:
  out: {source: {node: n1}, type: string}
"""

CAPABILITY_WORKFLOW = """ir_version: 1
name: cap_flow
inputs: {}
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config: {value: "data"}
    output_type: string
edges: []
capabilities:
  - network.http
assertions: []
outputs:
  res: {source: {node: n1}, type: string}
"""

FIXTURE_PASS = """fixture_version: 1
id: fix_pass
inputs:
  val: "test"
expected:
  outputs:
    out: "hello"
"""

FIXTURE_FAIL = """fixture_version: 1
id: fix_fail
inputs:
  val: "test"
expected:
  outputs:
    out: "mismatch"
"""

POLICY_BLOCK = """policy_version: 1
name: forbid_network
forbidden_capabilities:
  - network.http
"""

POLICY_PASS = """policy_version: 1
name: allow_basic
max_nodes: 10
"""

BLOCKING_POLICY = """policy_version: 1
name: strict-policy
max_nodes: 0
"""


def test_cli_explain_pass_human(tmp_path: Path):
    """Verify wysteria explain outputs concise PASS human format with fingerprint."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix)])
    assert result.exit_code == 0
    assert "DECISION: PASS" in result.stdout
    assert "Reasons:" in result.stdout
    assert "PASS: passing verification" in result.stdout
    assert "Fingerprint:" in result.stdout


def test_cli_explain_pass_json(tmp_path: Path):
    """Verify wysteria explain --format json outputs valid, canonical JSON."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix), "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["provenance_version"] == 1
    assert data["gate_decision"] == "PASS"
    assert data["decision"] == "PASS"
    assert len(data["reasons"]) == 1
    assert data["reasons"][0]["severity"] == "PASS"
    assert data["reasons"][0]["message"] == "passing verification"
    assert data["workflow_fingerprint"] is not None


def test_cli_explain_fail_mismatch_human(tmp_path: Path):
    """Verify wysteria explain on output mismatch outputs DECISION: FAIL with WYS852 reason."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_FAIL, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix)])
    assert result.exit_code == 1
    assert "DECISION: FAIL" in result.stdout
    assert "FAIL WYS852: output mismatch" in result.stdout
    assert "output: out" in result.stdout


def test_cli_explain_fail_mismatch_json(tmp_path: Path):
    """Verify wysteria explain --format json on mismatch outputs structured FAIL reason."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_FAIL, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix), "--format", "json"])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["gate_decision"] == "FAIL"
    assert any(r["code"] == "WYS852" for r in data["reasons"])
    assert any(r["target"] == "out" for r in data["reasons"])


def test_cli_explain_policy_block(tmp_path: Path):
    """Verify wysteria explain with --policy produces DECISION: BLOCK with exit code 1."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    pol = tmp_path / "policy.yaml"

    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")
    pol.write_text(BLOCKING_POLICY, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix), "--policy", str(pol)])
    assert result.exit_code == 1
    assert "DECISION: BLOCK" in result.stdout
    assert "BLOCK WYS451:" in result.stdout


def test_cli_explain_report_file(tmp_path: Path):
    """Verify wysteria explain writes canonical provenance JSON to --report-file."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    rep_file = tmp_path / "artifacts" / "explain-report.json"

    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")

    result = runner.invoke(
        app,
        ["explain", str(wf), "--fixture", str(fix), "--report-file", str(rep_file)],
    )
    assert result.exit_code == 0
    assert rep_file.exists()

    data = json.loads(rep_file.read_text(encoding="utf-8"))
    assert data["provenance_version"] == 1
    assert data["gate_decision"] == "PASS"


def test_cli_explain_github_annotations(tmp_path: Path):
    """Verify wysteria explain emits GitHub Actions workflow commands with --github-annotations."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    pol = tmp_path / "policy.yaml"

    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")
    pol.write_text(BLOCKING_POLICY, encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "explain",
            str(wf),
            "--fixture",
            str(fix),
            "--policy",
            str(pol),
            "--github-annotations",
        ],
    )
    assert result.exit_code == 1
    assert "::error title=WYS451::" in result.stderr


def test_cli_explain_invalid_format(tmp_path: Path):
    """Verify --format foo fails with exit code 4."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix), "--format", "yaml"])
    assert result.exit_code == 4
    assert "WYS900" in result.stderr


def test_cli_explain_invalid_workflow(tmp_path: Path):
    """Verify invalid workflow fails with exit code 2."""
    wf = tmp_path / "bad_wf.yaml"
    fix = tmp_path / "fixture.yaml"
    wf.write_text("ir_version: 99\n", encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix)])
    assert result.exit_code == 2
    assert "DECISION: FAIL" in result.stdout or "FAIL" in result.stdout


def test_cli_explain_invalid_fixture(tmp_path: Path):
    """Verify invalid fixture fails with exit code 3."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "bad_fix.yaml"
    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text("fixture_version: 99\n", encoding="utf-8")

    result = runner.invoke(app, ["explain", str(wf), "--fixture", str(fix)])
    assert result.exit_code == 3


def test_cli_explain_with_baseline_regression(tmp_path: Path):
    """Verify wysteria explain with --baseline detects regression and reports FAIL."""
    wf = tmp_path / "workflow.yaml"
    fix = tmp_path / "fixture.yaml"
    base = tmp_path / "baseline.json"

    wf.write_text(VALID_WORKFLOW, encoding="utf-8")
    fix.write_text(FIXTURE_PASS, encoding="utf-8")

    # Create baseline first
    res_create = runner.invoke(
        app,
        ["baseline", "create", str(wf), "--fixture", str(fix), "--output", str(base)],
    )
    assert res_create.exit_code == 0

    # Modify workflow to output something else
    modified_wf = VALID_WORKFLOW.replace('"hello"', '"goodbye"')
    wf.write_text(modified_wf, encoding="utf-8")
    # And fixture expecting goodbye so verification passes but baseline regresses
    mod_fix = FIXTURE_PASS.replace('"hello"', '"goodbye"')
    fix.write_text(mod_fix, encoding="utf-8")

    result = runner.invoke(
        app,
        ["explain", str(wf), "--fixture", str(fix), "--baseline", str(base)],
    )
    assert result.exit_code == 1
    assert "DECISION: FAIL" in result.stdout
    assert "regression" in result.stdout.lower() or "baseline" in result.stdout.lower()
