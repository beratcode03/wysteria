"""Lightweight release readiness checks for Wysteria packaging and distribution."""

from __future__ import annotations

import importlib
import importlib.metadata
import tomllib
from pathlib import Path

from pydantic import Field

from wysteria.ir.models import StrictModel


class ReadinessCheck(StrictModel):
    """Result of a single release readiness check."""

    name: str
    passed: bool
    message: str


class ReleaseReadinessResult(StrictModel):
    """Overall result of release readiness checks."""

    all_passed: bool
    checks: list[ReadinessCheck] = Field(default_factory=list)

    def summary(self) -> str:
        lines = ["Release Readiness:"]
        for c in self.checks:
            mark = "[✓]" if c.passed else "[✗]"
            lines.append(f"  {mark} {c.name}: {c.message}")
        return "\n".join(lines)


def _find_project_dir(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / "pyproject.toml").is_file():
            return directory
    return current


def check_release_readiness(*, project_dir: Path | None = None) -> ReleaseReadinessResult:
    """Run lightweight checks for package metadata, version consistency, required files, buildability, importability, and CLI availability."""
    root = _find_project_dir(project_dir)
    pyproject_path = root / "pyproject.toml"
    readme_path = root / "README.md"
    checks: list[ReadinessCheck] = []

    # 1. Required project files
    files_ok = pyproject_path.is_file() and readme_path.is_file()
    if files_ok:
        readme_content = readme_path.read_text(encoding="utf-8")
        if len(readme_content.strip()) > 50:
            checks.append(
                ReadinessCheck(
                    name="Required project files",
                    passed=True,
                    message="pyproject.toml and non-empty README.md present",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    name="Required project files",
                    passed=False,
                    message="README.md is empty or placeholder",
                )
            )
    else:
        missing = []
        if not pyproject_path.is_file():
            missing.append("pyproject.toml")
        if not readme_path.is_file():
            missing.append("README.md")
        checks.append(
            ReadinessCheck(
                name="Required project files",
                passed=False,
                message=f"missing required file(s): {', '.join(missing)}",
            )
        )

    # Load pyproject.toml if present
    pyproject_data: dict = {}
    if pyproject_path.is_file():
        try:
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomllib.load(f)
        except Exception as err:
            checks.append(
                ReadinessCheck(
                    name="Package metadata",
                    passed=False,
                    message=f"failed to parse pyproject.toml: {err}",
                )
            )

    proj = pyproject_data.get("project", {})

    # 2. Package metadata
    meta_keys = ["name", "version", "description", "requires-python", "license"]
    missing_keys = [k for k in meta_keys if k not in proj]
    if not missing_keys:
        pkg_name = proj.get("name")
        pkg_ver = proj.get("version")
        pkg_desc = proj.get("description")
        if pkg_name and pkg_ver and pkg_desc:
            checks.append(
                ReadinessCheck(
                    name="Package metadata",
                    passed=True,
                    message=f"name='{pkg_name}', version='{pkg_ver}', description is set",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    name="Package metadata",
                    passed=False,
                    message="metadata fields must be non-empty",
                )
            )
    else:
        checks.append(
            ReadinessCheck(
                name="Package metadata",
                passed=False,
                message=f"missing pyproject.toml project fields: {', '.join(missing_keys)}",
            )
        )

    # 3. Version consistency
    proj_version = proj.get("version")
    try:
        import wysteria

        code_version = getattr(wysteria, "__version__", None)
    except Exception:
        code_version = None

    try:
        installed_version = importlib.metadata.version("wysteria")
    except Exception:
        installed_version = None

    if proj_version and code_version and proj_version != code_version:
        checks.append(
            ReadinessCheck(
                name="Version consistency",
                passed=False,
                message=f"pyproject.toml version '{proj_version}' does not match wysteria.__version__ '{code_version}'",
            )
        )
    elif proj_version and installed_version and proj_version != installed_version:
        checks.append(
            ReadinessCheck(
                name="Version consistency",
                passed=False,
                message=f"pyproject.toml version '{proj_version}' does not match installed version '{installed_version}'",
            )
        )
    elif proj_version:
        consistent_ver = proj_version
        checks.append(
            ReadinessCheck(
                name="Version consistency",
                passed=True,
                message=f"version {consistent_ver} is consistent across project definitions",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                name="Version consistency",
                passed=False,
                message="unable to determine project version from pyproject.toml",
            )
        )

    # 4. Build configuration & buildability
    build_sys = pyproject_data.get("build-system", {})
    build_backend = build_sys.get("build-backend")
    build_reqs = build_sys.get("requires", [])
    src_dir = root / "src" / "wysteria"
    if build_backend and build_reqs and src_dir.is_dir() and (src_dir / "__init__.py").is_file():
        checks.append(
            ReadinessCheck(
                name="Build configuration",
                passed=True,
                message=f"backend='{build_backend}', requires={build_reqs}, package sources present",
            )
        )
    else:
        reasons = []
        if not build_backend:
            reasons.append("missing build-backend")
        if not build_reqs:
            reasons.append("missing build-system requires")
        if not src_dir.is_dir():
            reasons.append(f"missing source dir at {src_dir}")
        checks.append(
            ReadinessCheck(
                name="Build configuration",
                passed=False,
                message=f"build configuration invalid: {', '.join(reasons)}",
            )
        )

    # 5. Package importability
    modules_to_test = [
        "wysteria",
        "wysteria.api",
        "wysteria.cli.main",
        "wysteria.artifact",
        "wysteria.ir.models",
        "wysteria.verification.engine",
    ]
    failed_imports = []
    for mod_name in modules_to_test:
        try:
            importlib.import_module(mod_name)
        except Exception as err:
            failed_imports.append(f"{mod_name} ({err})")

    if not failed_imports:
        checks.append(
            ReadinessCheck(
                name="Package importability",
                passed=True,
                message="core Wysteria packages imported successfully",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                name="Package importability",
                passed=False,
                message=f"failed to import: {', '.join(failed_imports)}",
            )
        )

    # 6. CLI availability
    scripts = proj.get("scripts", {})
    cli_entry = scripts.get("wysteria")
    if cli_entry:
        try:
            mod_part, attr_part = cli_entry.split(":")
            mod = importlib.import_module(mod_part)
            app_obj = getattr(mod, attr_part)
            if callable(app_obj):
                checks.append(
                    ReadinessCheck(
                        name="CLI availability",
                        passed=True,
                        message=f"wysteria command mapped to valid callable '{cli_entry}'",
                    )
                )
            else:
                checks.append(
                    ReadinessCheck(
                        name="CLI availability",
                        passed=False,
                        message=f"CLI entrypoint '{cli_entry}' is not callable",
                    )
                )
        except Exception as err:
            checks.append(
                ReadinessCheck(
                    name="CLI availability",
                    passed=False,
                    message=f"CLI entrypoint '{cli_entry}' failed to resolve: {err}",
                )
            )
    else:
        checks.append(
            ReadinessCheck(
                name="CLI availability",
                passed=False,
                message="pyproject.toml does not define [project.scripts] wysteria",
            )
        )

    all_passed = all(c.passed for c in checks)
    return ReleaseReadinessResult(all_passed=all_passed, checks=checks)
