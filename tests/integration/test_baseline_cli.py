"""Integration tests for wysteria baseline CLI commands."""

import json

from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()

SAMPLE_WORKFLOW = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: n1
    kind: transform
    inputs:
      value:
        input: name
    config:
      operation: uppercase
    output_type: string
  - id: a1
    kind: assert
    inputs:
      value:
        input: name
    config:
      predicate: exists
    output_type: boolean
edges:
  - source: {input: name}
    target_node: n1
    target_input: value
  - source: {input: name}
    target_node: a1
    target_input: value
capabilities: []
assertions:
  - id: name_is_valid
    source: {node: a1}
    predicate: equals
    expected: true
outputs:
  greeting:
    source: {node: n1}
    type: string
"""

MODIFIED_WORKFLOW = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: n1
    kind: transform
    inputs:
      value:
        input: name
    config:
      operation: lowercase
    output_type: string
  - id: a1
    kind: assert
    inputs:
      value:
        input: name
    config:
      predicate: exists
    output_type: boolean
edges:
  - source: {input: name}
    target_node: n1
    target_input: value
  - source: {input: name}
    target_node: a1
    target_input: value
capabilities: []
assertions:
  - id: name_is_valid
    source: {node: a1}
    predicate: equals
    expected: true
outputs:
  greeting:
    source: {node: n1}
    type: string
"""

HAPPY_FIXTURE = """fixture_version: 1
id: happy-path
inputs:
  name: "berat"
expected:
  outputs:
    greeting: "BERAT"
  assertions:
    a1: true
    name_is_valid: true
"""

MISMATCH_FIXTURE = """fixture_version: 1
id: happy-path
inputs:
  name: "berat"
expected:
  outputs:
    greeting: "DIFFERENT"
"""

INVALID_WORKFLOW = """ir_version: 1
name: broken
inputs: {}
nodes: []
"""

INVALID_FIXTURE = """fixture_version: 1
id: missing-inputs
"""


def test_cli_baseline_create_success(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    result = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )
    assert result.exit_code == 0
    assert "Baseline created" in result.stdout
    assert base_file.is_file()

    # Validate JSON contents
    data = json.loads(base_file.read_text(encoding="utf-8"))
    assert data["baseline_version"] == 1
    assert data["fixture_id"] == "happy-path"
    assert data["result"]["status"] == "PASSED"
    assert data["result"]["actual_outputs"]["greeting"] == "BERAT"


def test_cli_baseline_create_refuses_overwrite_without_force(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    # Initial create
    res1 = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )
    assert res1.exit_code == 0

    # Second create without --force fails with exit code 4
    res2 = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )
    assert res2.exit_code == 4
    assert "already exists" in res2.stderr
    assert "--force" in res2.stderr


def test_cli_baseline_create_with_force_overwrites(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    # Initial create
    runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )

    # Overwrite with --force succeeds with exit code 0
    res = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
            "--force",
        ],
    )
    assert res.exit_code == 0
    assert "Baseline created" in res.stdout


def test_cli_baseline_create_invalid_workflow(tmp_path):
    wf_file = tmp_path / "broken_wf.yaml"
    wf_file.write_text(INVALID_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    res = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )
    assert res.exit_code == 2
    assert not base_file.exists()


def test_cli_baseline_create_invalid_fixture(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "broken_fix.yaml"
    fix_file.write_text(INVALID_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    res = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )
    assert res.exit_code == 3
    assert not base_file.exists()


def test_cli_baseline_create_failing_verification_rejected(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(MISMATCH_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    res = runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )
    assert res.exit_code == 1
    assert "OUTPUT_MISMATCH" in res.stderr
    assert not base_file.exists()


def test_cli_baseline_check_matching(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    # Create baseline
    runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )

    # Check baseline matches
    res = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--baseline",
            str(base_file),
        ],
    )
    assert res.exit_code == 0
    assert "MATCH" in res.stdout
    assert "fingerprint matches" in res.stdout
    assert "Result: MATCH" in res.stdout


def test_cli_baseline_check_regression(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    # Create baseline with original workflow
    runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )

    # Modify workflow
    wf_mod = tmp_path / "workflow_mod.yaml"
    wf_mod.write_text(MODIFIED_WORKFLOW, encoding="utf-8")

    # Fixture for modified workflow that would pass on its own
    fix_mod = tmp_path / "fixture_mod.yaml"
    fix_mod.write_text(
        """fixture_version: 1
id: happy-path
inputs:
  name: "berat"
expected:
  outputs:
    greeting: "berat"
  assertions:
    a1: true
    name_is_valid: true
""",
        encoding="utf-8",
    )

    # Check against original baseline -> detects regression
    res = runner.invoke(
        app,
        ["baseline", "check", str(wf_mod), "--fixture", str(fix_mod), "--baseline", str(base_file)],
    )
    assert res.exit_code == 1
    assert "REGRESSION" in res.stdout
    assert "Workflow fingerprint changed" in res.stdout
    assert "Outputs" in res.stdout
    assert "Result: REGRESSION" in res.stdout


def test_cli_baseline_check_json_output(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    runner.invoke(
        app,
        [
            "baseline",
            "create",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--output",
            str(base_file),
        ],
    )

    # Check with --format json for match
    res_match = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--baseline",
            str(base_file),
            "--format",
            "json",
        ],
    )
    assert res_match.exit_code == 0
    data_match = json.loads(res_match.stdout)
    assert data_match["status"] == "MATCH"
    assert data_match["matches"] is True
    assert data_match["workflow_changed"] is False
    assert data_match["outputs_changed"] is False

    # Check with modified workflow for regression
    wf_mod = tmp_path / "workflow_mod.yaml"
    wf_mod.write_text(MODIFIED_WORKFLOW, encoding="utf-8")
    fix_mod = tmp_path / "fixture_mod.yaml"
    fix_mod.write_text(
        """fixture_version: 1
id: happy-path
inputs:
  name: "berat"
expected:
  outputs:
    greeting: "berat"
  assertions:
    a1: true
    name_is_valid: true
""",
        encoding="utf-8",
    )

    res_reg = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(wf_mod),
            "--fixture",
            str(fix_mod),
            "--baseline",
            str(base_file),
            "--format",
            "json",
        ],
    )
    assert res_reg.exit_code == 1
    data_reg = json.loads(res_reg.stdout)
    assert data_reg["status"] == "REGRESSION"
    assert data_reg["matches"] is False
    assert data_reg["workflow_changed"] is True
    assert data_reg["outputs_changed"] is True


def test_cli_baseline_check_missing_baseline(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    nonexistent = tmp_path / "missing.json"

    res = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--baseline",
            str(nonexistent),
        ],
    )
    assert res.exit_code == 4
    assert "WYS600" in res.stderr or "not a readable regular file" in res.stderr


def test_cli_baseline_check_invalid_baseline(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    bad_base = tmp_path / "bad.json"
    bad_base.write_text("{ unclosed", encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--baseline",
            str(bad_base),
        ],
    )
    assert res.exit_code == 4


def test_cli_baseline_check_invalid_format(tmp_path):
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")
    base_file = tmp_path / "baseline.json"

    res = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--baseline",
            str(base_file),
            "--format",
            "yaml",
        ],
    )
    assert res.exit_code == 5
    assert "must be 'human' or 'json'" in res.stderr
