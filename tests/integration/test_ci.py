"""Integration tests for CI-oriented CLI behavior, artifacts, annotations, and exit codes."""

import json
from pathlib import Path

from typer.testing import CliRunner

from wysteria.api import DeveloperReport
from wysteria.cli.main import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_WORKFLOW = REPO_ROOT / "examples" / "workflows" / "user_transform_flow.yaml"
EXAMPLE_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_trim_upper.yaml"
EXAMPLE_BASELINE = REPO_ROOT / "examples" / "baselines" / "user_transform_baseline.json"
EXAMPLE_CI_FAILING_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_ci_failing.yaml"

SAMPLE_WORKFLOW_TEXT = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: msg
    kind: construct
    inputs:
      who:
        input: name
    config:
      template:
        greeting: "Hello, ${who}!"
    output_type: object
  - id: check_name
    kind: assert
    inputs:
      value:
        input: name
    config:
      predicate: type_is
      expected: string
    output_type: boolean
edges:
  - source: {input: name}
    target_node: msg
    target_input: who
  - source: {input: name}
    target_node: check_name
    target_input: value
capabilities: []
assertions:
  - id: name_is_valid
    source: {node: check_name}
    predicate: equals
    expected: true
outputs:
  output:
    source: {node: msg}
    type: object
"""

HAPPY_FIXTURE_TEXT = """fixture_version: 1
id: happy-path
name: Happy Path
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, BERAT!"
  assertions:
    check_name: true
    name_is_valid: true
"""

MISMATCH_FIXTURE_TEXT = """fixture_version: 1
id: mismatch-path
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, INCORRECT!"
"""

ASSERTION_FAIL_FIXTURE_TEXT = """fixture_version: 1
id: assert-fail
inputs:
  name: "BERAT"
expected:
  assertions:
    check_name: false
"""

RUNTIME_ERROR_WORKFLOW_TEXT = """ir_version: 1
name: error_wf
inputs:
  user:
    type: object
nodes:
  - id: select_field
    kind: select
    inputs:
      value:
        input: user
    config:
      path: "/missing/key"
    output_type: string
edges:
  - source: {input: user}
    target_node: select_field
    target_input: value
capabilities: []
assertions: []
outputs:
  field:
    source: {node: select_field}
    type: string
"""


def test_cli_verify_report_file_generation(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")
    fix_file = tmp_path / "fix.yaml"
    fix_file.write_text(HAPPY_FIXTURE_TEXT, encoding="utf-8")
    report_file = tmp_path / "artifacts" / "nested" / "verification-report.json"

    res = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--report-file",
            str(report_file),
        ],
    )
    assert res.exit_code == 0
    assert report_file.is_file()

    # Must be valid DeveloperReport representation
    report = DeveloperReport.model_validate_json(report_file.read_text(encoding="utf-8"))
    assert report.status == "PASSED"
    assert report.overall_status == "PASS"
    assert report.success is True
    assert report.workflow_fingerprint is not None
    assert len(report.traces) == 2


def test_cli_verify_github_annotations_mode(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")
    fix_mismatch = tmp_path / "mismatch.yaml"
    fix_mismatch.write_text(MISMATCH_FIXTURE_TEXT, encoding="utf-8")
    report_file = tmp_path / "report.json"

    # 1. Normal mode without --github-annotations does not contain ::error
    res_normal = runner.invoke(
        app,
        ["verify", str(wf_file), "--fixture", str(fix_mismatch)],
    )
    assert res_normal.exit_code == 1
    assert "::error" not in res_normal.stdout
    assert "::error" not in res_normal.stderr

    # 2. Explicit --github-annotations mode emits ::error
    res_annotated = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_mismatch),
            "--report-file",
            str(report_file),
            "--github-annotations",
        ],
    )
    assert res_annotated.exit_code == 1
    assert "::error" in res_annotated.stderr
    assert "WYS852" in res_annotated.stderr
    assert "output mismatch" in res_annotated.stderr

    # Human stdout exposes status, workflow, fixture, fingerprint, failure category, expected vs actual
    assert "FAIL" in res_annotated.stdout
    assert "OUTPUT_MISMATCH" in res_annotated.stdout
    assert "Workflow:" in res_annotated.stdout
    assert "Fixture:" in res_annotated.stdout
    assert "Fingerprint:" in res_annotated.stdout
    assert "expected:" in res_annotated.stdout
    assert "actual:" in res_annotated.stdout

    # Report file is written even on failure
    assert report_file.is_file()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["status"] == "OUTPUT_MISMATCH"
    assert data["success"] is False


def test_cli_verify_json_format_with_github_annotations(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")
    fix_mismatch = tmp_path / "mismatch.yaml"
    fix_mismatch.write_text(MISMATCH_FIXTURE_TEXT, encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_mismatch),
            "--format",
            "json",
            "--github-annotations",
        ],
    )
    assert res.exit_code == 1

    # stdout MUST be valid JSON (annotations must not pollute stdout)
    parsed_json = json.loads(res.stdout)
    assert parsed_json["status"] == "OUTPUT_MISMATCH"

    # stderr contains the workflow annotations
    assert (
        "::error" in res_annotated_stderr
        if (res_annotated_stderr := res.stderr)
        else "::error" in res.output
    )


def test_cli_verify_all_failure_exit_codes(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")

    # Exit code 1: Output mismatch
    fix_mismatch = tmp_path / "mismatch.yaml"
    fix_mismatch.write_text(MISMATCH_FIXTURE_TEXT, encoding="utf-8")
    res1 = runner.invoke(
        app,
        ["verify", str(wf_file), "--fixture", str(fix_mismatch), "--github-annotations"],
    )
    assert res1.exit_code == 1

    # Exit code 1: Assertion failure
    fix_assert = tmp_path / "assert.yaml"
    fix_assert.write_text(ASSERTION_FAIL_FIXTURE_TEXT, encoding="utf-8")
    res1b = runner.invoke(
        app,
        ["verify", str(wf_file), "--fixture", str(fix_assert), "--github-annotations"],
    )
    assert res1b.exit_code == 1

    # Exit code 2: Invalid workflow schema
    bad_wf = tmp_path / "bad_wf.yaml"
    bad_wf.write_text("ir_version: 1\nname: broken\ninputs: {}\n", encoding="utf-8")
    fix_happy = tmp_path / "happy.yaml"
    fix_happy.write_text(HAPPY_FIXTURE_TEXT, encoding="utf-8")
    res2 = runner.invoke(
        app,
        ["verify", str(bad_wf), "--fixture", str(fix_happy), "--github-annotations"],
    )
    assert res2.exit_code == 2

    # Exit code 3: Invalid fixture schema
    bad_fix = tmp_path / "bad_fix.yaml"
    bad_fix.write_text("fixture_version: 1\ninputs: {}\n", encoding="utf-8")
    res3 = runner.invoke(
        app,
        ["verify", str(wf_file), "--fixture", str(bad_fix), "--github-annotations"],
    )
    assert res3.exit_code == 3

    # Exit code 4: Runtime error
    err_wf = tmp_path / "err_wf.yaml"
    err_wf.write_text(RUNTIME_ERROR_WORKFLOW_TEXT, encoding="utf-8")
    err_fix = tmp_path / "err_fix.yaml"
    err_fix.write_text("fixture_version: 1\nid: err\ninputs:\n  user: {}\n", encoding="utf-8")
    res4 = runner.invoke(
        app,
        ["verify", str(err_wf), "--fixture", str(err_fix), "--github-annotations"],
    )
    assert res4.exit_code == 4


def test_cli_baseline_check_ci_options(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")
    fix_file = tmp_path / "fix.yaml"
    fix_file.write_text(HAPPY_FIXTURE_TEXT, encoding="utf-8")
    base_file = tmp_path / "baseline.json"
    report_file = tmp_path / "baseline-report.json"

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
    assert base_file.is_file()

    # 1. Matching baseline check with CI options
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
            "--report-file",
            str(report_file),
            "--github-annotations",
        ],
    )
    assert res_match.exit_code == 0
    assert "MATCH" in res_match.stdout
    assert report_file.is_file()

    match_report_data = json.loads(report_file.read_text(encoding="utf-8"))
    assert match_report_data["status"] == "PASSED"
    assert match_report_data["baseline"]["matches"] is True

    # 2. Modify workflow to trigger regression
    mod_wf = tmp_path / "mod_wf.yaml"
    mod_wf.write_text(
        SAMPLE_WORKFLOW_TEXT.replace("Hello, ${who}!", "Greetings, ${who}!"),
        encoding="utf-8",
    )
    fix_mod = tmp_path / "fix_mod.yaml"
    fix_mod.write_text(
        HAPPY_FIXTURE_TEXT.replace("Hello, BERAT!", "Greetings, BERAT!"),
        encoding="utf-8",
    )

    reg_report_file = tmp_path / "reg-report.json"
    res_reg = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(mod_wf),
            "--fixture",
            str(fix_mod),
            "--baseline",
            str(base_file),
            "--report-file",
            str(reg_report_file),
            "--github-annotations",
        ],
    )
    assert res_reg.exit_code == 1
    assert "REGRESSION" in res_reg.stdout
    assert "::error" in res_reg.stderr
    assert reg_report_file.is_file()

    reg_report_data = json.loads(reg_report_file.read_text(encoding="utf-8"))
    assert reg_report_data["status"] == "REGRESSION"
    assert reg_report_data["baseline"]["matches"] is False


def test_ci_deterministic_repeated_output(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")
    fix_file = tmp_path / "fix.yaml"
    fix_file.write_text(HAPPY_FIXTURE_TEXT, encoding="utf-8")
    report1 = tmp_path / "report1.json"
    report2 = tmp_path / "report2.json"

    res1 = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--report-file",
            str(report1),
            "--github-annotations",
        ],
    )
    res2 = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--report-file",
            str(report2),
            "--github-annotations",
        ],
    )
    assert res1.exit_code == 0
    assert res2.exit_code == 0
    assert res1.stdout == res2.stdout
    assert res1.stderr == res2.stderr
    assert report1.read_text(encoding="utf-8") == report2.read_text(encoding="utf-8")


def test_repository_example_ci_scenario_passes(tmp_path):
    assert EXAMPLE_WORKFLOW.is_file(), f"Missing example workflow: {EXAMPLE_WORKFLOW}"
    assert EXAMPLE_FIXTURE.is_file(), f"Missing example fixture: {EXAMPLE_FIXTURE}"
    assert EXAMPLE_BASELINE.is_file(), f"Missing example baseline: {EXAMPLE_BASELINE}"

    report_file = tmp_path / "ci-report.json"
    base_report_file = tmp_path / "ci-base-report.json"

    # Verify example workflow passes
    res_verify = runner.invoke(
        app,
        [
            "verify",
            str(EXAMPLE_WORKFLOW),
            "--fixture",
            str(EXAMPLE_FIXTURE),
            "--report-file",
            str(report_file),
            "--github-annotations",
        ],
    )
    assert res_verify.exit_code == 0
    assert "PASS" in res_verify.stdout
    assert report_file.is_file()

    # Baseline check passes
    res_baseline = runner.invoke(
        app,
        [
            "baseline",
            "check",
            str(EXAMPLE_WORKFLOW),
            "--fixture",
            str(EXAMPLE_FIXTURE),
            "--baseline",
            str(EXAMPLE_BASELINE),
            "--report-file",
            str(base_report_file),
            "--github-annotations",
        ],
    )
    assert res_baseline.exit_code == 0
    assert "MATCH" in res_baseline.stdout
    assert base_report_file.is_file()


def test_repository_deliberately_failing_ci_scenario(tmp_path):
    assert EXAMPLE_CI_FAILING_FIXTURE.is_file(), (
        f"Missing failing fixture: {EXAMPLE_CI_FAILING_FIXTURE}"
    )

    report_file = tmp_path / "failing-report.json"
    res = runner.invoke(
        app,
        [
            "verify",
            str(EXAMPLE_WORKFLOW),
            "--fixture",
            str(EXAMPLE_CI_FAILING_FIXTURE),
            "--report-file",
            str(report_file),
            "--github-annotations",
        ],
    )
    assert res.exit_code == 1
    assert "FAIL" in res.stdout
    assert "OUTPUT_MISMATCH" in res.stdout
    assert "Workflow:" in res.stdout
    assert "Fixture:" in res.stdout
    assert "Fingerprint:" in res.stdout
    assert "expected:" in res.stdout
    assert "actual:" in res.stdout
    assert "::error" in res.stderr

    assert report_file.is_file()
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["status"] == "OUTPUT_MISMATCH"
    assert data["success"] is False
