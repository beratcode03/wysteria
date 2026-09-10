"""Shared validation helpers."""

from collections.abc import Iterable
from typing import Protocol

from wysteria.reporting.diagnostics import Diagnostic, Severity, SourceLocation


class HasLocations(Protocol):
    locations: dict[str, SourceLocation]


def location_for(parsed: HasLocations | None, path: str):
    """Find the closest known source location for a diagnostic path."""

    if parsed is None:
        return None
    candidate = path
    while candidate not in parsed.locations and candidate:
        candidate = candidate.rsplit("/", 1)[0]
    return parsed.locations.get(candidate)


def diagnostic(
    code: str,
    message: str,
    path: str = "",
    *,
    parsed: HasLocations | None = None,
    severity: Severity = Severity.ERROR,
    hint: str | None = None,
) -> Diagnostic:
    """Build one source-aware diagnostic."""

    return Diagnostic(
        code=code,
        severity=severity,
        message=message,
        path=path,
        location=location_for(parsed, path),
        hint=hint,
    )


def has_errors(diagnostics: Iterable[Diagnostic]) -> bool:
    """Return whether diagnostics contain errors."""

    return any(item.severity == Severity.ERROR for item in diagnostics)
