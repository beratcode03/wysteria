"""Strict, versioned CI Artifact models for reliable CI consumption."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from wysteria.diff.models import WorkflowDiff
from wysteria.ir.models import StrictModel
from wysteria.policy.models import PolicyResult
from wysteria.provenance.models import (
    Explanation,
    ExplanationItem,
    FixtureIdentity,
    GateDecision,
    Provenance,
    WorkflowIdentity,
)
from wysteria.reporting.models import BaselineSummary, DeveloperReport

CURRENT_ARTIFACT_VERSION = 1
SUPPORTED_ARTIFACT_VERSIONS = frozenset({CURRENT_ARTIFACT_VERSION})


class CIArtifact(StrictModel):
    """Strict, versioned machine-readable artifact representing the complete verification decision."""

    artifact_version: Literal[CURRENT_ARTIFACT_VERSION] = CURRENT_ARTIFACT_VERSION
    schema_version: int = CURRENT_ARTIFACT_VERSION
    gate_decision: GateDecision
    workflow_fingerprint: str | None = None
    workflow: WorkflowIdentity
    fixture: FixtureIdentity
    developer_report: DeveloperReport
    provenance: Provenance
    baseline: BaselineSummary | None = None
    semantic_diff: WorkflowDiff | None = None
    policy: PolicyResult | None = None
    explanation: Explanation | None = None
    reasons: list[ExplanationItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "report" in d and "developer_report" not in d:
            d["developer_report"] = d["report"]
        if "workflow_diff" in d and "semantic_diff" not in d:
            d["semantic_diff"] = d["workflow_diff"]
        if "policy_result" in d and "policy" not in d:
            d["policy"] = d["policy_result"]
        if "baseline_result" in d and "baseline" not in d:
            d["baseline"] = d["baseline_result"]
        if "decision" in d and "gate_decision" not in d:
            d["gate_decision"] = d["decision"]
        if "schema_version" not in d and "artifact_version" in d:
            d["schema_version"] = d["artifact_version"]
        elif "artifact_version" not in d and "schema_version" in d:
            d["artifact_version"] = d["schema_version"]
        return d

    @property
    def report(self) -> DeveloperReport:
        """Alias for developer_report."""
        return self.developer_report

    @property
    def decision(self) -> GateDecision:
        """Alias for gate_decision."""
        return self.gate_decision

    @property
    def fixture_id(self) -> str:
        """Fixture identifier string."""
        return self.fixture.id

    @property
    def baseline_result(self) -> BaselineSummary | None:
        """Alias for baseline."""
        return self.baseline

    @property
    def workflow_diff(self) -> WorkflowDiff | None:
        """Alias for semantic_diff."""
        return self.semantic_diff

    @property
    def policy_result(self) -> PolicyResult | None:
        """Alias for policy."""
        return self.policy

    @property
    def passed(self) -> bool:
        """True if gate decision is PASS."""
        return self.gate_decision == GateDecision.PASS

    @property
    def blocked(self) -> bool:
        """True if gate decision is BLOCK."""
        return self.gate_decision == GateDecision.BLOCK

    @property
    def failed(self) -> bool:
        """True if gate decision is FAIL."""
        return self.gate_decision == GateDecision.FAIL

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize CIArtifact deterministically to canonical formatted JSON."""
        from wysteria.artifact.storage import serialize_ci_artifact

        return serialize_ci_artifact(self, indent=indent)


VerificationArtifact = CIArtifact
