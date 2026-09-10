"""Stable, machine-readable validation diagnostics."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """Diagnostic severity."""

    ERROR = "error"
    WARNING = "warning"


class SourceLocation(BaseModel):
    """A one-based location in a source document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str
    line: int = Field(ge=1)
    column: int = Field(ge=1)


class Diagnostic(BaseModel):
    """A stable validation finding suitable for people and automation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Severity
    message: str
    path: str = ""
    location: SourceLocation | None = None
    hint: str | None = None


class ValidationResult(BaseModel):
    """Result of validating one workflow document."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    blocked: bool = False
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    workflow: object | None = Field(default=None, exclude=True)
