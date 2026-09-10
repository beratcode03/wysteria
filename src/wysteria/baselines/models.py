"""Strict, deterministic regression baseline and comparison models."""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, Field, field_validator

from wysteria.ir.models import StrictModel, _enum_value, _json_value
from wysteria.verification.models import VerificationStatus

CURRENT_BASELINE_VERSION = 1
SUPPORTED_BASELINE_VERSIONS = frozenset({CURRENT_BASELINE_VERSION})

VerificationStatusField = Annotated[
    VerificationStatus, BeforeValidator(_enum_value(VerificationStatus))
]


class DiffKind(StrEnum):
    """Classification of difference between baseline expectation and actual verification."""

    MATCH = "MATCH"
    CHANGED = "CHANGED"
    MISSING = "MISSING"
    UNEXPECTED = "UNEXPECTED"


class OutputDiff(StrictModel):
    """Detailed diff for a single output."""

    name: str
    kind: DiffKind
    expected: Any = None
    actual: Any = None

    @field_validator("expected", "actual")
    @classmethod
    def _validate_diff_values(cls, value: Any) -> Any:
        return _json_value(value)


class AssertionDiff(StrictModel):
    """Detailed diff for a single assertion."""

    name: str
    kind: DiffKind
    expected: bool | None = None
    actual: bool | None = None


class BaselineResult(StrictModel):
    """Contractual subset of verification results recorded in a regression baseline."""

    status: VerificationStatusField
    success: bool
    actual_outputs: dict[str, Any] = Field(default_factory=dict)
    actual_assertions: dict[str, bool] = Field(default_factory=dict)
    expected_error_code: str | None = None

    @field_validator("actual_outputs")
    @classmethod
    def _validate_outputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {k: _json_value(v) for k, v in value.items()}


class Baseline(StrictModel):
    """The stable v1 regression baseline contract."""

    baseline_version: Literal[CURRENT_BASELINE_VERSION]
    workflow_fingerprint: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    fixture_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    result: BaselineResult


class BaselineComparisonStatus(StrEnum):
    """Deterministic machine-readable status of a baseline comparison."""

    MATCH = "MATCH"
    REGRESSION = "REGRESSION"
    NO_BASELINE = "NO_BASELINE"


class BaselineComparison(StrictModel):
    """Structured deterministic result of comparing a verification run against a baseline."""

    status: BaselineComparisonStatus
    matches: bool
    workflow_changed: bool = False
    workflow_expected: str | None = None
    workflow_actual: str | None = None
    fixture_changed: bool = False
    fixture_expected: str | None = None
    fixture_actual: str | None = None
    status_changed: bool = False
    status_expected: VerificationStatus | None = None
    status_actual: VerificationStatus | None = None
    expected_error_changed: bool = False
    expected_error_expected: str | None = None
    expected_error_actual: str | None = None
    outputs_changed: bool = False
    output_diffs: list[OutputDiff] = Field(default_factory=list)
    assertions_changed: bool = False
    assertion_diffs: list[AssertionDiff] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
