"""Strict, versioned Workflow Provenance and Explanation models."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import Field

from wysteria.diff.models import SemanticChange
from wysteria.ir.models import StrictModel
from wysteria.policy.models import PolicyViolation

CURRENT_PROVENANCE_VERSION = 1
SUPPORTED_PROVENANCE_VERSIONS = frozenset({CURRENT_PROVENANCE_VERSION})


class GateDecision(StrEnum):
    """Deterministic PASS/FAIL/BLOCK decision for a changed workflow."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCK = "BLOCK"


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


class ExplanationSeverity(StrEnum):
    """Deterministic severity rating for an explanation item."""

    BLOCK = "BLOCK"
    BREAKING = "BREAKING"
    FAIL = "FAIL"
    WARNING = "WARNING"
    INFO = "INFO"
    PASS = "PASS"


class ExplanationCategory(StrEnum):
    """Classification category for explanation findings."""

    POLICY = "policy"
    SEMANTIC = "semantic"
    OUTPUT = "output"
    ASSERTION = "assertion"
    RUNTIME = "runtime"
    VALIDATION = "validation"
    REGRESSION = "regression"
    GATE = "gate"


class ExplanationItem(StrictModel):
    """Structured, deterministic explanation reason item."""

    severity: ExplanationSeverity
    category: str
    source: str
    code: str | None = None
    message: str
    node_id: str | None = None
    target: str | None = None
    path: str | None = None


class Explanation(StrictModel):
    """Deterministic explainability container summarizing why a workflow PASS/FAIL/BLOCKed."""

    decision: GateDecision
    reasons: list[ExplanationItem] = Field(default_factory=list)
    fingerprint: str | None = None
    summary: str = ""

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize Explanation deterministically to formatted JSON."""
        data = self.model_dump(mode="json")
        return json.dumps(data, indent=indent, sort_keys=True)


class Provenance(StrictModel):
    """Strict, versioned provenance model capturing full workflow lineage and gating decision."""

    provenance_version: Literal[CURRENT_PROVENANCE_VERSION] = CURRENT_PROVENANCE_VERSION
    proposal_source: str | None = None
    proposal_fingerprint: str | None = None
    compiler_version: str | None = None
    workflow: WorkflowIdentity
    workflow_fingerprint: str | None = None
    fixture: FixtureIdentity
    verification_outcome: str
    regression_outcome: str | None = None
    semantic_changes: list[SemanticChange] = Field(default_factory=list)
    policy_violations: list[PolicyViolation] = Field(default_factory=list)
    gate_decision: GateDecision
    decision: GateDecision
    reasons: list[ExplanationItem] = Field(default_factory=list)
    explanation: Explanation | None = None

    @property
    def explanations(self) -> list[ExplanationItem]:
        """Alias for reasons."""
        return self.reasons

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize Provenance deterministically to formatted JSON."""
        data = self.model_dump(mode="json")
        return json.dumps(data, indent=indent, sort_keys=True)


WorkflowProvenance = Provenance
