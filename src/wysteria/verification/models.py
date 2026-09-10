"""Strict models for node execution traces and evaluation results."""

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from wysteria.ir.models import StrictModel, _json_value
from wysteria.reporting.diagnostics import Diagnostic


class NodeExecutionTrace(StrictModel):
    """Deterministic execution trace of a single node evaluation."""

    step: int = Field(ge=0)
    node_id: str
    kind: str
    resolved_inputs: dict[str, Any]
    output: Any

    @field_validator("output")
    @classmethod
    def _validate_output(cls, value: Any) -> Any:
        return _json_value(value)

    @field_validator("resolved_inputs")
    @classmethod
    def _validate_inputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {k: _json_value(v) for k, v in value.items()}


class WorkflowExecutionResult(StrictModel):
    """Result of evaluating all nodes in a workflow DAG."""

    success: bool
    node_values: dict[str, Any] = Field(default_factory=dict)
    traces: list[NodeExecutionTrace] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @field_validator("node_values")
    @classmethod
    def _validate_node_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {k: _json_value(v) for k, v in value.items()}


class VerificationStatus(StrEnum):
    """Deterministic machine-readable status of a verification run."""

    PASSED = "PASSED"
    INVALID_WORKFLOW = "INVALID_WORKFLOW"
    INVALID_FIXTURE = "INVALID_FIXTURE"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    ASSERTION_FAILED = "ASSERTION_FAILED"
    OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


class VerificationResult(StrictModel):
    """Final deterministic result of verifying a workflow against a fixture."""

    status: VerificationStatus
    success: bool
    fixture_id: str
    workflow_fingerprint: str | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    actual_outputs: dict[str, Any] = Field(default_factory=dict)
    actual_assertions: dict[str, bool] = Field(default_factory=dict)
    traces: list[NodeExecutionTrace] = Field(default_factory=list)
    expected_error_code: str | None = None

    @field_validator("actual_outputs")
    @classmethod
    def _validate_outputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {k: _json_value(v) for k, v in value.items()}
