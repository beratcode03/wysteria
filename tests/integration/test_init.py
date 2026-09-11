"""Integration tests for the wysteria init CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from wysteria.api import (
    evaluate_policy,
    load_fixture_document,
    load_policy,
    load_workflow,
    validate_workflow,
    verify_fixture,
)
from wysteria.cli.main import app

runner = CliRunner()


def test_init_creates_workspace(tmp_path: Path) -> None:
    target_dir = tmp_path / "my-pipeline"
    result = runner.invoke(app, ["init", str(target_dir)])

    assert result.exit_code == 0
    assert "Initializing Wysteria workspace" in result.output
    assert "Created:" in result.output

    # Check files exist
    assert (target_dir / "workflow.yaml").exists()
    assert (target_dir / "fixture.yaml").exists()
    assert (target_dir / "policy.yaml").exists()
    assert (target_dir / ".github" / "workflows" / "wysteria.yml").exists()

    # Load and parse everything (goes through actual engine)
    workflow = load_workflow(target_dir / "workflow.yaml")
    val_result = validate_workflow(workflow)
    assert val_result.valid is True
    assert val_result.workflow is not None

    fixture = load_fixture_document(target_dir / "fixture.yaml")
    policy = load_policy(target_dir / "policy.yaml")

    # Verify fixture
    verify_res = verify_fixture(val_result.workflow, fixture)
    assert verify_res.success is True
    assert verify_res.status.value == "PASSED"

    # Evaluate policy
    policy_res = evaluate_policy(val_result.workflow, policy)
    assert policy_res.passed is True


def test_init_fails_if_exists_without_force(tmp_path: Path) -> None:
    target_dir = tmp_path / "my-pipeline"
    target_dir.mkdir()
    (target_dir / "workflow.yaml").write_text("existing")

    result = runner.invoke(app, ["init", str(target_dir)])
    assert result.exit_code == 1
    assert "error: Target directory already contains Wysteria files" in result.output
    assert "Use --force to overwrite" in result.output

    # Content shouldn't be overwritten
    assert (target_dir / "workflow.yaml").read_text() == "existing"


def test_init_force_overwrites(tmp_path: Path) -> None:
    target_dir = tmp_path / "my-pipeline"
    target_dir.mkdir()
    (target_dir / "workflow.yaml").write_text("existing")
    unrelated_file = target_dir / "unrelated.txt"
    unrelated_file.write_text("keep me")

    result = runner.invoke(app, ["init", str(target_dir), "--force"])
    assert result.exit_code == 0
    assert "Initializing Wysteria workspace" in result.output

    # Workflow is overwritten
    assert (target_dir / "workflow.yaml").read_text() != "existing"
    assert "ir_version" in (target_dir / "workflow.yaml").read_text()

    # Unrelated files are kept
    assert unrelated_file.exists()
    assert unrelated_file.read_text() == "keep me"
