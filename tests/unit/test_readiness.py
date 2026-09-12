"""Unit tests for release readiness checks."""

from pathlib import Path

from wysteria.release import check_release_readiness

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_release_readiness_current_repo():
    result = check_release_readiness(project_dir=REPO_ROOT)
    assert result.all_passed is True
    assert len(result.checks) == 6
    summary = result.summary()
    assert "[✓] Required project files" in summary
    assert "[✓] Package metadata" in summary
    assert "[✓] Version consistency" in summary
    assert "[✓] Build configuration" in summary
    assert "[✓] Package importability" in summary
    assert "[✓] CLI availability" in summary


def test_missing_required_files(tmp_path):
    # Empty dir with no pyproject.toml or README.md
    result = check_release_readiness(project_dir=tmp_path)
    assert result.all_passed is False
    check_files = next(c for c in result.checks if c.name == "Required project files")
    assert check_files.passed is False
    assert "missing required file" in check_files.message


def test_metadata_validation(tmp_path):
    # Create invalid pyproject.toml missing metadata
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        """[project]
name = "wysteria"
# missing version, description, etc.
""",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text("# Test Project\n" + "hello " * 20, encoding="utf-8")

    result = check_release_readiness(project_dir=tmp_path)
    assert result.all_passed is False
    meta_check = next(c for c in result.checks if c.name == "Package metadata")
    assert meta_check.passed is False
    assert "missing pyproject.toml project fields" in meta_check.message


def test_version_consistency_mismatch(tmp_path):
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        """[project]
name = "wysteria"
version = "9.9.9"
description = "A deterministic verifier."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "Apache-2.0" }
""",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text("# Test Project\n" + "hello " * 20, encoding="utf-8")

    result = check_release_readiness(project_dir=tmp_path)
    ver_check = next(c for c in result.checks if c.name == "Version consistency")
    assert ver_check.passed is False
    assert "does not match wysteria.__version__" in ver_check.message


def test_cli_availability_missing(tmp_path):
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text(
        """[project]
name = "wysteria"
version = "0.1.1"
description = "A verifier."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "Apache-2.0" }
# no scripts
""",
        encoding="utf-8",
    )
    readme = tmp_path / "README.md"
    readme.write_text("# Test Project\n" + "hello " * 20, encoding="utf-8")

    result = check_release_readiness(project_dir=tmp_path)
    cli_check = next(c for c in result.checks if c.name == "CLI availability")
    assert cli_check.passed is False
    assert "does not define [project.scripts]" in cli_check.message
