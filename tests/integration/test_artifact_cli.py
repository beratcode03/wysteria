"""Integration tests for the wysteria artifact CLI commands."""

import json
from pathlib import Path

from typer.testing import CliRunner

from wysteria.artifact import load_ci_artifact
from wysteria.cli.main import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = REPO_ROOT / "examples" / "workflows" / "user_transform_flow.yaml"
FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_trim_upper.yaml"
MISMATCH_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_mismatch.yaml"
BASELINE = REPO_ROOT / "examples" / "baselines" / "user_transform_baseline.json"
POLICY = REPO_ROOT / "examples" / "policies" / "security_policy.yaml"


def test_cli_artifact_default_command(tmp_path):
    # Tests calling "wysteria artifact WORKFLOW --fixture FIXTURE" without "generate"
    res = runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(FIXTURE)],
    )
    assert res.exit_code == 0
    assert "PASS" in res.stdout
    assert "Workflow:" in res.stdout
    assert "Gate Decision" in res.stdout


def test_cli_artifact_explicit_generate(tmp_path):
    # Tests calling "wysteria artifact generate WORKFLOW --fixture FIXTURE"
    res = runner.invoke(
        app,
        ["artifact", "generate", str(WORKFLOW), "--fixture", str(FIXTURE)],
    )
    assert res.exit_code == 0
    assert "PASS" in res.stdout


def test_cli_artifact_format_json(tmp_path):
    res = runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(FIXTURE), "--format", "json"],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["artifact_version"] == 1
    assert data["gate_decision"] == "PASS"
    assert "developer_report" in data
    assert "provenance" in data
    assert data["workflow"]["display_name"] == "examples/workflows/user_transform_flow.yaml"


def test_cli_artifact_output_file(tmp_path):
    out = tmp_path / "ci-artifact.json"
    res = runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(FIXTURE), "--output", str(out)],
    )
    assert res.exit_code == 0
    assert out.is_file()
    assert "CI Artifact created:" in res.stdout

    # Validate output file
    loaded = load_ci_artifact(out)
    assert loaded.artifact_version == 1
    assert loaded.gate_decision == "PASS"


def test_cli_artifact_report_file_alias(tmp_path):
    out = tmp_path / "ci-artifact-alias.json"
    res = runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(FIXTURE), "--report-file", str(out)],
    )
    assert res.exit_code == 0
    assert out.is_file()
    loaded = load_ci_artifact(out)
    assert loaded.gate_decision == "PASS"


def test_cli_artifact_with_baseline(tmp_path):
    res = runner.invoke(
        app,
        [
            "artifact",
            str(WORKFLOW),
            "--fixture",
            str(FIXTURE),
            "--baseline",
            str(BASELINE),
            "--format",
            "json",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["baseline"] is not None
    assert data["baseline"]["matches"] is True


def test_cli_artifact_fail_exit_code(tmp_path):
    out = tmp_path / "fail.json"
    res = runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(MISMATCH_FIXTURE), "--output", str(out)],
    )
    assert res.exit_code == 1
    assert out.is_file()
    loaded = load_ci_artifact(out)
    assert loaded.gate_decision == "FAIL"
    assert loaded.failed is True


def test_cli_artifact_policy_integration(tmp_path):
    # Restrictive policy triggers BLOCK
    pol_file = tmp_path / "restrictive.yaml"
    pol_file.write_text("policy_version: 1\nname: strict\nmax_nodes: 2\n", encoding="utf-8")

    out = tmp_path / "blocked.json"
    res = runner.invoke(
        app,
        [
            "artifact",
            str(WORKFLOW),
            "--fixture",
            str(FIXTURE),
            "--policy",
            str(pol_file),
            "--output",
            str(out),
        ],
    )
    assert res.exit_code == 1
    assert out.is_file()
    loaded = load_ci_artifact(out)
    assert loaded.gate_decision == "BLOCK"
    assert loaded.blocked is True


def test_cli_artifact_validate_success(tmp_path):
    art_file = tmp_path / "art.json"
    runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(FIXTURE), "--output", str(art_file)],
    )

    # Human format validate
    res = runner.invoke(app, ["artifact", "validate", str(art_file)])
    assert res.exit_code == 0
    assert "PASS" in res.stdout
    assert "is a valid CI Artifact v1" in res.stdout

    # JSON format validate
    res_json = runner.invoke(app, ["artifact", "validate", str(art_file), "--format", "json"])
    assert res_json.exit_code == 0
    parsed = json.loads(res_json.stdout)
    assert parsed["valid"] is True
    assert parsed["artifact_version"] == 1
    assert parsed["gate_decision"] == "PASS"


def test_cli_artifact_validate_failure(tmp_path):
    # Nonexistent file
    res = runner.invoke(app, ["artifact", "validate", str(tmp_path / "nonexistent.json")])
    assert res.exit_code == 1
    assert "error WYS950" in res.output

    # Invalid JSON file
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    res_bad = runner.invoke(app, ["artifact", "validate", str(bad_json)])
    assert res_bad.exit_code == 1
    assert "error WYS950" in res_bad.output

    # Invalid version
    art_file = tmp_path / "valid.json"
    runner.invoke(
        app,
        ["artifact", str(WORKFLOW), "--fixture", str(FIXTURE), "--output", str(art_file)],
    )
    data = json.loads(art_file.read_text(encoding="utf-8"))
    data["artifact_version"] = 42
    bad_ver_file = tmp_path / "bad_ver.json"
    bad_ver_file.write_text(json.dumps(data), encoding="utf-8")

    res_ver = runner.invoke(app, ["artifact", "validate", str(bad_ver_file)])
    assert res_ver.exit_code == 1
    assert "error WYS950" in res_ver.output
    assert "unsupported artifact version" in res_ver.output


def test_cli_artifact_github_annotations(tmp_path):
    res = runner.invoke(
        app,
        [
            "artifact",
            str(WORKFLOW),
            "--fixture",
            str(MISMATCH_FIXTURE),
            "--format",
            "json",
            "--github-annotations",
        ],
    )
    assert res.exit_code == 1
    # stdout is pure JSON
    parsed = json.loads(res.stdout)
    assert parsed["gate_decision"] == "FAIL"

    # stderr contains annotations
    stderr_content = res.stderr if res.stderr else res.output
    assert "::error" in stderr_content
    assert "WYS852" in stderr_content


def test_cli_doctor_with_release_flag():
    res = runner.invoke(app, ["doctor", "--release"])
    assert res.exit_code == 0
    assert "Release Readiness:" in res.stdout
    assert "[✓]" in res.stdout
