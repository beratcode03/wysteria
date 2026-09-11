"""Strict, presentation-independent DeveloperReport models and schemas."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from wysteria.diff.models import SemanticChange, WorkflowDiff
from wysteria.ir.models import StrictModel, _json_value
from wysteria.reporting.diagnostics import Severity, SourceLocation
from wysteria.verification.models import NodeExecutionTrace


class ReportStatus(StrEnum):
    """Presentation-neutral status code for verification and baseline reporting."""

    PASS = "PASS"
    PASSED = "PASSED"
    FAIL = "FAIL"
    INVALID_WORKFLOW = "INVALID_WORKFLOW"
    INVALID_FIXTURE = "INVALID_FIXTURE"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    ASSERTION_FAILED = "ASSERTION_FAILED"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    REGRESSION = "REGRESSION"


class StatusBadge(StrEnum):
    """Semantic status category without presentation-specific styling or colors."""

    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class StatusPresentation(StrictModel):
    """Presentation-neutral visual representation of verification outcome."""

    status: ReportStatus
    label: str
    badge: StatusBadge
    passed: bool


class DiagnosticCategory(StrEnum):
    """Semantic category for normalized diagnostics."""

    SCHEMA = "schema"
    REFERENCE = "reference"
    GRAPH = "graph"
    CAPABILITY = "capability"
    SEMANTIC = "semantic"
    BASELINE = "baseline"
    FIXTURE = "fixture"
    RUNTIME = "runtime"
    ASSERTION = "assertion"
    OUTPUT = "output"
    LIMIT = "limit"
    SYSTEM = "system"
    GENERAL = "general"


class NormalizedDiagnostic(StrictModel):
    """Normalized diagnostic finding suitable for UI, CLI, and CI consumers."""

    code: str
    severity: Severity
    message: str
    category: DiagnosticCategory
    node_id: str | None = None
    path: str = ""
    location: SourceLocation | None = None
    hint: str | None = None

    @property
    def source_location(self) -> SourceLocation | None:
        """Alias for location."""
        return self.location


class MatchState(StrEnum):
    """Deterministic match state of an output or assertion evaluation."""

    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    MISSING = "MISSING"
    UNEXPECTED = "UNEXPECTED"
    UNCHECKED = "UNCHECKED"


class OutputReportItem(StrictModel):
    """Structured representation of a single workflow output."""

    id: str
    actual: Any = None
    expected: Any = None
    match_state: MatchState

    @property
    def name(self) -> str:
        """Alias for id."""
        return self.id

    @field_validator("actual", "expected")
    @classmethod
    def _validate_values(cls, value: Any) -> Any:
        return _json_value(value)


class AssertionReportItem(StrictModel):
    """Structured representation of a single workflow or node assertion."""

    id: str
    actual: bool | None = None
    expected: bool | None = None
    match_state: MatchState

    @property
    def name(self) -> str:
        """Alias for id."""
        return self.id


class ValidationSummary(StrictModel):
    """Summary of workflow and fixture validation state."""

    workflow_valid: bool
    fixture_valid: bool
    error_count: int = 0
    warning_count: int = 0


class ExecutionSummary(StrictModel):
    """Summary of deterministic execution state."""

    total_nodes_executed: int = 0
    success: bool
    expected_error_occurred: bool = False
    expected_error_code: str | None = None
    actual_error_code: str | None = None


class WorkflowIdentity(StrictModel):
    """Identity metadata for a verified workflow."""

    name: str | None = None
    fingerprint: str | None = None
    display_name: str = ""


class FixtureIdentity(StrictModel):
    """Identity metadata for a test fixture."""

    id: str
    name: str | None = None
    display_name: str = ""


class BaselineDiffEntry(StrictModel):
    """Structured diff item comparing against a regression baseline."""

    category: str
    name: str
    kind: str
    expected: Any = None
    actual: Any = None
    message: str = ""

    @field_validator("expected", "actual")
    @classmethod
    def _validate_values(cls, value: Any) -> Any:
        return _json_value(value)


class BaselineSummary(StrictModel):
    """Structured regression baseline comparison summary."""

    status: str
    matches: bool
    workflow_changed: bool = False
    workflow_expected: str | None = None
    workflow_actual: str | None = None
    fixture_changed: bool = False
    fixture_expected: str | None = None
    fixture_actual: str | None = None
    status_changed: bool = False
    status_expected: str | None = None
    status_actual: str | None = None
    expected_error_changed: bool = False
    expected_error_expected: str | None = None
    expected_error_actual: str | None = None
    outputs_changed: bool = False
    output_diffs: list[BaselineDiffEntry] = Field(default_factory=list)
    assertions_changed: bool = False
    assertion_diffs: list[BaselineDiffEntry] = Field(default_factory=list)
    diff_entries: list[BaselineDiffEntry] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class GateDecision(StrEnum):
    """Deterministic PASS/FAIL decision for a changed workflow."""

    PASS = "PASS"
    FAIL = "FAIL"


class GateSummary(StrictModel):
    """Result of evaluating a workflow change against verification rules."""

    decision: GateDecision
    reasons: list[str] = Field(default_factory=list)


class DeveloperReport(StrictModel):
    """Stable, presentation-independent developer report contract."""

    # Overall outcome
    status: ReportStatus
    overall_status: ReportStatus
    status_presentation: StatusPresentation
    success: bool

    # Identities
    workflow: WorkflowIdentity
    fixture: FixtureIdentity
    fixture_id: str
    workflow_fingerprint: str | None = None

    # Summaries
    validation: ValidationSummary
    execution: ExecutionSummary

    # Detail collections (deterministically sorted)
    outputs: list[OutputReportItem] = Field(default_factory=list)
    assertions: list[AssertionReportItem] = Field(default_factory=list)
    diagnostics: list[NormalizedDiagnostic] = Field(default_factory=list)
    traces: list[NodeExecutionTrace] = Field(default_factory=list)

    # Backwards compatibility collections
    actual_outputs: dict[str, Any] = Field(default_factory=dict)
    actual_assertions: dict[str, bool] = Field(default_factory=dict)

    # Optional baseline comparison
    baseline: BaselineSummary | None = None

    # Optional semantic workflow diff
    workflow_diff: WorkflowDiff | None = None

    # Optional change gate decision
    gate: GateSummary | None = None

    @property
    def semantic_changes(self) -> list[SemanticChange] | None:
        """Alias for workflow_diff changes where available."""
        return self.workflow_diff.changes if self.workflow_diff is not None else None

    @property
    def passed(self) -> bool:
        """True if the verification succeeded."""
        return self.success

    @property
    def failed(self) -> bool:
        """True if the verification failed."""
        return not self.success

    @field_validator("actual_outputs")
    @classmethod
    def _validate_outputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {k: _json_value(v) for k, v in value.items()}

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize DeveloperReport deterministically to formatted JSON."""
        data = self.model_dump(mode="json")
        return json.dumps(data, indent=indent, sort_keys=True)
