"""Integration tests for wysteria diff and baseline diff CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_FLOW = REPO_ROOT / "examples" / "workflows" / "user_transform_flow.yaml"
EXAMPLE_PROPOSAL = REPO_ROOT / "examples" / "workflows" / "user_transform_proposal.yaml"
EXAMPLE_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_trim_upper.yaml"
EXAMPLE_BASELINE = REPO_ROOT / "examples" / "baselines" / "user_transform_baseline.json"

MINIMAL_WORKFLOW = """ir_version: 1
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

MODIFIED_WORKFLOW = """ir_version: 1
name: min_flow
inputs:
  val: {type: string}
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config: {value: "world"}
    output_type: string
edges: []
capabilities: []
assertions: []
outputs:
  out: {source: {node: n1}, type: string}
"""

INVALID_WORKFLOW = """ir_version: 1
name: broken
inputs: {}
nodes: []
"""


def test_cli_diff_identical_workflows(tmp_path):
    wf_file = tmp_path / "flow.yaml"
    wf_file.write_text(MINIMAL_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf_file), str(wf_file)])
    assert res.exit_code == 0
    assert "WORKFLOW DIFF" in res.stdout
    assert "No semantic changes." in res.stdout


def test_cli_diff_changes_detected(tmp_path):
    wf1 = tmp_path / "wf1.yaml"
    wf1.write_text(MINIMAL_WORKFLOW, encoding="utf-8")
    wf2 = tmp_path / "wf2.yaml"
    wf2.write_text(MODIFIED_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf1), str(wf2)])
    assert res.exit_code == 1
    assert "WORKFLOW DIFF" in res.stdout
    assert "CHANGES" in res.stdout
    assert "~ node n1" in res.stdout
    assert "BREAKING" in res.stdout
    assert "SUMMARY" in res.stdout
    assert "1 breaking" in res.stdout


def test_cli_diff_json_format(tmp_path):
    wf1 = tmp_path / "wf1.yaml"
    wf1.write_text(MINIMAL_WORKFLOW, encoding="utf-8")
    wf2 = tmp_path / "wf2.yaml"
    wf2.write_text(MODIFIED_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf1), str(wf2), "--format", "json"])
    assert res.exit_code == 1

    parsed = json.loads(res.stdout)
    assert parsed["identical"] is False
    assert parsed["summary"]["breaking_count"] == 1
    assert len(parsed["changes"]) == 1
    assert parsed["changes"][0]["category"] == "CONFIG_CHANGED"
    assert parsed["changes"][0]["change_type"] == "constant_value_changed"


def test_cli_diff_invalid_old_workflow_file_not_found(tmp_path):
    wf2 = tmp_path / "wf2.yaml"
    wf2.write_text(MINIMAL_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(tmp_path / "missing.yaml"), str(wf2)])
    assert res.exit_code == 2
    assert "error WYS900" in res.stderr
    assert "not a readable regular file" in res.stderr


def test_cli_diff_invalid_old_workflow_syntax(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ unclosed", encoding="utf-8")
    wf2 = tmp_path / "wf2.yaml"
    wf2.write_text(MINIMAL_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(bad), str(wf2)])
    assert res.exit_code == 2
    assert "error WYS900" in res.stderr


def test_cli_diff_invalid_old_workflow_schema(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(INVALID_WORKFLOW, encoding="utf-8")
    wf2 = tmp_path / "wf2.yaml"
    wf2.write_text(MINIMAL_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(bad), str(wf2)])
    assert res.exit_code == 2
    assert "error WYS" in res.stderr


def test_cli_diff_invalid_new_workflow_file_not_found(tmp_path):
    wf1 = tmp_path / "wf1.yaml"
    wf1.write_text(MINIMAL_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf1), str(tmp_path / "missing.yaml")])
    assert res.exit_code == 3
    assert "error WYS900" in res.stderr
    assert "not a readable regular file" in res.stderr


def test_cli_diff_invalid_new_workflow_syntax(tmp_path):
    wf1 = tmp_path / "wf1.yaml"
    wf1.write_text(MINIMAL_WORKFLOW, encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ unclosed", encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf1), str(bad)])
    assert res.exit_code == 3
    assert "error WYS900" in res.stderr


def test_cli_diff_invalid_new_workflow_schema(tmp_path):
    wf1 = tmp_path / "wf1.yaml"
    wf1.write_text(MINIMAL_WORKFLOW, encoding="utf-8")
    bad = tmp_path / "bad.yaml"
    bad.write_text(INVALID_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf1), str(bad)])
    assert res.exit_code == 3
    assert "error WYS" in res.stderr


def test_cli_diff_invalid_format_option(tmp_path):
    wf1 = tmp_path / "wf1.yaml"
    wf1.write_text(MINIMAL_WORKFLOW, encoding="utf-8")

    res = runner.invoke(app, ["diff", str(wf1), str(wf1), "--format", "csv"])
    assert res.exit_code == 4
    assert "--format must be 'human' or 'json'" in res.stderr


def test_cli_diff_repository_examples():
    assert EXAMPLE_FLOW.is_file()
    assert EXAMPLE_PROPOSAL.is_file()

    res = runner.invoke(app, ["diff", str(EXAMPLE_FLOW), str(EXAMPLE_PROPOSAL)])
    assert res.exit_code == 1
    assert "WORKFLOW DIFF" in res.stdout
    assert "package_result" in res.stdout
    assert "template" in res.stdout
    assert "BREAKING" in res.stdout
    assert "SUMMARY" in res.stdout
    assert "1 breaking" in res.stdout
    assert "1 informational" in res.stdout


def test_cli_baseline_check_with_baseline_workflow(tmp_path):
    assert EXAMPLE_FLOW.is_file()
    assert EXAMPLE_PROPOSAL.is_file()
    assert EXAMPLE_FIXTURE.is_file()
    assert EXAMPLE_BASELINE.is_file()

    report_file = tmp_path / "report-with-diff.json"

    # Compare proposal against baseline with --baseline-workflow pointing to original flow
    res = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(EXAMPLE_PROPOSAL),
            "--fixture",
            str(EXAMPLE_FIXTURE),
            "--baseline",
            str(EXAMPLE_BASELINE),
            "--baseline-workflow",
            str(EXAMPLE_FLOW),
            "--report-file",
            str(report_file),
        ],
    )
    assert res.exit_code == 1
    assert "REGRESSION" in res.stdout
    assert "Workflow fingerprint changed" in res.stdout
    assert "package_result" in res.stdout
    assert "BREAKING" in res.stdout

    # Report file should contain the workflow_diff
    assert report_file.is_file()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert "workflow_diff" in data
    assert data["workflow_diff"] is not None
    assert data["workflow_diff"]["identical"] is False
    assert data["workflow_diff"]["summary"]["breaking_count"] == 1
    assert data["workflow_diff"]["changes"][0]["node_id"] == "package_result"
