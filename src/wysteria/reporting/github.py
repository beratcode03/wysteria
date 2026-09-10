"""GitHub Actions workflow command / annotation formatting."""

from __future__ import annotations

from pathlib import Path

from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.reporting.models import DeveloperReport, NormalizedDiagnostic


def escape_github_property(value: str) -> str:
    """Escape property values for GitHub workflow commands according to Actions spec."""
    return (
        str(value)
        .replace("%", "%25")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
        .replace(":", "%3A")
        .replace(",", "%2C")
    )


def escape_github_data(value: str) -> str:
    """Escape data / message values for GitHub workflow commands according to Actions spec."""
    return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def normalize_file_path(path_str: str) -> str:
    """Normalize file paths to forward-slash format for GitHub Actions."""
    p = Path(path_str)
    return p.as_posix()


def format_diagnostic_annotation(diag: Diagnostic | NormalizedDiagnostic) -> str:
    """Format a single diagnostic as a GitHub Actions workflow command (::error or ::warning)."""
    cmd = "error" if diag.severity == Severity.ERROR else "warning"
    props: dict[str, str] = {}
    if diag.location and diag.location.file and not diag.location.file.startswith("<"):
        props["file"] = normalize_file_path(diag.location.file)
        if diag.location.line > 0:
            props["line"] = str(diag.location.line)
        if diag.location.column > 0:
            props["col"] = str(diag.location.column)
    props["title"] = diag.code

    msg = diag.message
    if diag.hint:
        msg = f"{msg} (hint: {diag.hint})"

    props_str = ",".join(f"{k}={escape_github_property(v)}" for k, v in props.items() if v)
    prefix = f"::{cmd} {props_str}::" if props_str else f"::{cmd}::"
    return f"{prefix}{escape_github_data(msg)}"


def format_github_annotations(report: DeveloperReport) -> list[str]:
    """Format GitHub Actions workflow commands (::error, ::warning) for a DeveloperReport.

    Only emitted in explicit CI / GitHub mode (--github-annotations).
    """
    annotations: list[str] = []
    seen: set[str] = set()

    def add_line(line: str) -> None:
        if line not in seen:
            seen.add(line)
            annotations.append(line)

    def add_command(command: str, props: dict[str, str], message: str) -> None:
        props_str = ",".join(f"{k}={escape_github_property(v)}" for k, v in props.items() if v)
        prefix = f"::{command} {props_str}::" if props_str else f"::{command}::"
        add_line(f"{prefix}{escape_github_data(message)}")

    # 1. Normalized diagnostics
    for diag in report.diagnostics:
        add_line(format_diagnostic_annotation(diag))

    # 2. Baseline regression diffs
    if report.baseline and not report.baseline.matches:
        for diff in report.baseline.diff_entries:
            props = {"title": f"Regression: {diff.category}.{diff.name}"}
            msg = diff.message or f"Baseline diff in {diff.category}.{diff.name} ({diff.kind})"
            add_command("error", props, msg)
        for reason in report.baseline.reasons:
            props = {"title": "Baseline Regression"}
            add_command("error", props, reason)

    # 3. Fallback overall error annotation if report failed but no annotations were added
    if not report.success and not annotations:
        props = {"title": report.status.value}
        msg = (
            f"Verification failed for workflow '{report.workflow.display_name}' "
            f"with fixture '{report.fixture.display_name}' ({report.status.value})"
        )
        add_command("error", props, msg)

    return annotations
