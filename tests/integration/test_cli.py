from typer.testing import CliRunner

from wysteria.cli.main import app

runner = CliRunner()


def test_validate_cli_success(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text(
        """ir_version: 1
name: sample
metadata: {}
inputs: {}
nodes:
  - id: value
    kind: constant
    inputs: {}
    config: {value: hello}
    output_type: string
edges: []
capabilities: []
assertions: []
outputs:
  result: {source: {node: value}, type: string}
""",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0
    assert "PASS" in result.stdout


def test_validate_cli_json_failure(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text("ir_version: 1\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path), "--format", "json"])
    assert result.exit_code == 1
    assert '"valid": false' in result.stdout


def test_validate_cli_policy_block(tmp_path):
    path = tmp_path / "workflow.yaml"
    path.write_text(
        """ir_version: 1
name: sample
metadata: {}
inputs: {}
nodes: [{id: value, kind: constant, inputs: {}, config: {value: 1}, output_type: integer}]
edges: []
capabilities: [network.http]
assertions: []
outputs: {result: {source: {node: value}, type: integer}}
""",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["validate", str(path)]).exit_code == 2


def test_schema_and_doctor():
    assert runner.invoke(app, ["schema", "--ir-version", "1"]).exit_code == 0
    assert runner.invoke(app, ["doctor"]).exit_code == 0


# --- Phase 2.2d: CLI & Developer UX Tests ---


SAMPLE_WORKFLOW = """ir_version: 1
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

HAPPY_FIXTURE = """fixture_version: 1
id: happy-path
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

MISMATCH_FIXTURE = """fixture_version: 1
id: happy-path
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, BERATCAN!"
"""

ASSERTION_FAIL_FIXTURE = """fixture_version: 1
id: happy-path
inputs:
  name: "BERAT"
expected:
  assertions:
    check_name: false
"""

SELECT_ERROR_WORKFLOW = """ir_version: 1
name: select_wf
inputs:
  user:
    type: object
nodes:
  - id: select_name
    kind: select
    inputs:
      value:
        input: user
    config:
      path: "/user/name"
    output_type: string
edges:
  - source: {input: user}
    target_node: select_name
    target_input: value
capabilities: []
assertions: []
outputs:
  name:
    source: {node: select_name}
    type: string
"""

EXPECTED_RUNTIME_ERROR_FIXTURE = """fixture_version: 1
id: exp-err
inputs:
  user: {}
expected:
  error: "WYS801"
"""

UNEXPECTED_RUNTIME_ERROR_FIXTURE = """fixture_version: 1
id: unexp-err
inputs:
  user: {}
"""


def test_cli_verify_successful(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 0
    assert "WYSTERIA" in result.stdout
    assert "Workflow valid" in result.stdout
    assert "Fixture valid" in result.stdout
    assert "Execution" in result.stdout
    assert "2 nodes evaluated" in result.stdout
    assert "Outputs" in result.stdout
    assert 'output = {"greeting":"Hello, BERAT!"}' in result.stdout
    assert "Assertions" in result.stdout
    assert "check_name" in result.stdout
    assert "name_is_valid" in result.stdout
    assert "PASS" in result.stdout


def test_cli_verify_output_mismatch(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(MISMATCH_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 1
    assert "Result" in result.stdout
    assert "FAIL" in result.stdout
    assert "OUTPUT_MISMATCH" in result.stdout
    assert "expected:" in result.stdout
    assert "actual:" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_assertion_failure(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(ASSERTION_FAIL_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 1
    assert "Result" in result.stdout
    assert "FAIL" in result.stdout
    assert "ASSERTION_FAILED" in result.stdout
    assert "check_name" in result.stdout
    assert "expected: false" in result.stdout
    assert "actual:   true" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_expected_runtime_error_passes(tmp_path):
    wf_file = tmp_path / "select.yaml"
    wf_file.write_text(SELECT_ERROR_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "expected_err.yaml"
    fix_file.write_text(EXPECTED_RUNTIME_ERROR_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert "Expected error WYS801 occurred" in result.stdout


def test_cli_verify_unexpected_runtime_error(tmp_path):
    wf_file = tmp_path / "select.yaml"
    wf_file.write_text(SELECT_ERROR_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "unexpected_err.yaml"
    fix_file.write_text(UNEXPECTED_RUNTIME_ERROR_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 4
    assert "FAIL" in result.stdout
    assert "RUNTIME_ERROR" in result.stdout
    assert "WYS801" in result.stdout
    assert "Node: select_name" in result.stdout
    assert "JSON Pointer" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_invalid_workflow(tmp_path):
    wf_file = tmp_path / "invalid_wf.yaml"
    # Workflow missing required 'nodes'
    wf_file.write_text("ir_version: 1\nname: broken\ninputs: {}\n", encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 2
    assert "FAIL" in result.stdout
    assert "INVALID_WORKFLOW" in result.stdout
    assert "WYS102" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_invalid_fixture_schema(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "bad_fix.yaml"
    # Fixture missing required 'id'
    fix_file.write_text("fixture_version: 1\ninputs: {}\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 3
    assert "FAIL" in result.stdout
    assert "INVALID_FIXTURE" in result.stdout
    assert "WYS701" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_fixture_workflow_incompatibility(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "incompatible_fix.yaml"
    # Fixture provides integer for string input 'name'
    fix_file.write_text(
        "fixture_version: 1\nid: bad-type\ninputs:\n  name: 12345\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 3
    assert "FAIL" in result.stdout
    assert "INVALID_FIXTURE" in result.stdout
    assert "WYS702" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_malformed_workflow_file(tmp_path):
    wf_file = tmp_path / "malformed.yaml"
    wf_file.write_text("ir_version: [invalid yaml syntax ::::\n", encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 2
    assert "FAIL" in result.stdout
    assert "INVALID_WORKFLOW" in result.stdout
    assert "WYS900" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_malformed_fixture_file(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "malformed_fix.yaml"
    fix_file.write_text("fixture_version: [invalid yaml syntax ::::\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(fix_file)])
    assert result.exit_code == 3
    assert "FAIL" in result.stdout
    assert "INVALID_FIXTURE" in result.stdout
    assert "WYS700" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_missing_workflow_file(tmp_path):
    nonexistent = tmp_path / "does_not_exist.yaml"
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = runner.invoke(app, ["verify", str(nonexistent), "--fixture", str(fix_file)])
    assert result.exit_code == 2
    assert "FAIL" in result.stdout
    assert "INVALID_WORKFLOW" in result.stdout
    assert "WYS900" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_missing_fixture_file(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    nonexistent = tmp_path / "does_not_exist_fix.yaml"

    result = runner.invoke(app, ["verify", str(wf_file), "--fixture", str(nonexistent)])
    assert result.exit_code == 3
    assert "FAIL" in result.stdout
    assert "INVALID_FIXTURE" in result.stdout
    assert "WYS700" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_cli_verify_json_output_success(tmp_path):
    import json

    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = runner.invoke(
        app, ["verify", str(wf_file), "--fixture", str(fix_file), "--format", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "PASSED"
    assert data["success"] is True
    assert data["fixture_id"] == "happy-path"
    assert data["workflow_fingerprint"] is not None
    assert "output" in data["actual_outputs"]
    assert "check_name" in data["actual_assertions"]
    assert len(data["traces"]) == 2


def test_cli_verify_json_output_mismatch(tmp_path):
    import json

    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(MISMATCH_FIXTURE, encoding="utf-8")

    result = runner.invoke(
        app, ["verify", str(wf_file), "--fixture", str(fix_file), "--format", "json"]
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "OUTPUT_MISMATCH"
    assert data["success"] is False
    assert len(data["diagnostics"]) >= 1


def test_cli_verify_deterministic_json_output(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result1 = runner.invoke(
        app, ["verify", str(wf_file), "--fixture", str(fix_file), "--format", "json"]
    )
    result2 = runner.invoke(
        app, ["verify", str(wf_file), "--fixture", str(fix_file), "--format", "json"]
    )
    assert result1.exit_code == 0
    assert result2.exit_code == 0
    assert result1.stdout == result2.stdout


def test_cli_verify_invalid_format_option(tmp_path):
    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = runner.invoke(
        app, ["verify", str(wf_file), "--fixture", str(fix_file), "--format", "xml"]
    )
    assert result.exit_code == 4
    assert "must be 'human' or 'json'" in result.stderr


def test_cli_verify_subprocess_execution(tmp_path):
    import subprocess
    import sys

    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "wysteria.cli.main",
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "WYSTERIA" in proc.stdout
    assert "PASS" in proc.stdout


def test_public_package_api(tmp_path):
    import wysteria

    assert hasattr(wysteria, "verify_fixture")
    assert hasattr(wysteria, "VerificationResult")
    assert hasattr(wysteria, "VerificationStatus")
    assert hasattr(wysteria, "Fixture")
    assert hasattr(wysteria, "Workflow")

    wf_file = tmp_path / "customer.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW, encoding="utf-8")
    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(HAPPY_FIXTURE, encoding="utf-8")

    result = wysteria.verify_fixture(str(wf_file), str(fix_file))
    assert result.status == wysteria.VerificationStatus.PASSED
    assert result.success is True


def test_verify_policy_behavior(tmp_path):
    import json

    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(
        """ir_version: 1
name: showcase
inputs: {}
nodes:
  - id: n1
    kind: constant
    config: {value: "test"}
    output_type: string
edges: []
capabilities: [network.http, file.read]
assertions: []
outputs:
  result:
    source: {node: n1}
    type: string
""",
        encoding="utf-8",
    )

    fix_file = tmp_path / "fixture.yaml"
    fix_file.write_text(
        """fixture_version: 1
id: test-fix
inputs: {}
expected:
  outputs:
    result: "test"
""",
        encoding="utf-8",
    )

    pol_file = tmp_path / "policy.yaml"
    pol_file.write_text(
        """policy_version: 1
name: my-policy
forbidden_capabilities: [process.execute]
require_assertions: false
require_outputs: false
forbid_unreachable_nodes: false
""",
        encoding="utf-8",
    )

    pol_file_strict = tmp_path / "policy_strict.yaml"
    pol_file_strict.write_text(
        """policy_version: 1
name: strict-policy
forbidden_capabilities: [network.http]
require_assertions: false
require_outputs: false
forbid_unreachable_nodes: false
""",
        encoding="utf-8",
    )

    pol_file_max_nodes = tmp_path / "policy_max_nodes.yaml"
    pol_file_max_nodes.write_text(
        """policy_version: 1
name: max-nodes-policy
max_nodes: 0
forbidden_capabilities: []
require_assertions: false
require_outputs: false
forbid_unreachable_nodes: false
""",
        encoding="utf-8",
    )

    # A. verify with showcase policy (forbids process.execute, allows network/file)
    res_a = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--policy",
            str(pol_file),
            "--format",
            "json",
        ],
    )
    assert res_a.exit_code == 0
    data_a = json.loads(res_a.stdout)
    assert data_a["status"] == "PASSED"
    assert data_a["provenance"]["policy_violations"] == []

    # B. verify with strict policy (forbids network.http) -> should fail structural validation (WYS400)
    res_b = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--policy",
            str(pol_file_strict),
            "--format",
            "json",
        ],
    )
    assert res_b.exit_code != 0
    data_b = json.loads(res_b.stdout)
    assert data_b["status"] == "INVALID_WORKFLOW"
    assert any("WYS400" in d["code"] for d in data_b["diagnostics"])

    # C. verify without explicit policy still uses strict default-deny (WYS400)
    res_c = runner.invoke(
        app, ["verify", str(wf_file), "--fixture", str(fix_file), "--format", "json"]
    )
    assert res_c.exit_code != 0
    data_c = json.loads(res_c.stdout)
    assert data_c["status"] == "INVALID_WORKFLOW"
    assert any("WYS400" in d["code"] for d in data_c["diagnostics"])

    # D. policy violations correctly propagated (e.g. from evaluate_policy)
    res_d = runner.invoke(
        app,
        [
            "verify",
            str(wf_file),
            "--fixture",
            str(fix_file),
            "--policy",
            str(pol_file_max_nodes),
            "--format",
            "json",
        ],
    )
    assert res_d.exit_code != 0
    data_d = json.loads(res_d.stdout)
    assert data_d["provenance"]["gate_decision"] == "BLOCK"
    assert len(data_d["provenance"]["policy_violations"]) > 0
    assert any(v["code"] == "WYS451" for v in data_d["provenance"]["policy_violations"])

    # E. policy check and verify agree on capability decisions
    res_e = runner.invoke(
        app, ["policy", "check", str(wf_file), "--policy", str(pol_file), "--format", "json"]
    )
    assert res_e.exit_code == 0
    data_e = json.loads(res_e.stdout)
    assert data_e["passed"] is True

    res_e2 = runner.invoke(
        app, ["policy", "check", str(wf_file), "--policy", str(pol_file_strict), "--format", "json"]
    )
    assert res_e2.exit_code != 0
    data_e2 = json.loads(res_e2.stdout)
    assert data_e2["passed"] is False
    assert any(v["code"] == "WYS453" for v in data_e2.get("violations", []))
