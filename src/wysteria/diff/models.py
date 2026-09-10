"""Strict models for deterministic semantic workflow diffing."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator

from wysteria.ir.models import StrictModel, _json_value


class DiffSeverity(StrEnum):
    """Classification of semantic impact for a workflow change."""

    INFO = "INFO"
    WARNING = "WARNING"
    BREAKING = "BREAKING"


class ChangeCategory(StrEnum):
    """High-level category of a semantic change."""

    NODE_ADDED = "NODE_ADDED"
    NODE_REMOVED = "NODE_REMOVED"
    NODE_CHANGED = "NODE_CHANGED"
    EDGE_ADDED = "EDGE_ADDED"
    EDGE_REMOVED = "EDGE_REMOVED"
    EDGE_CHANGED = "EDGE_CHANGED"
    INPUT_CHANGED = "INPUT_CHANGED"
    OUTPUT_CHANGED = "OUTPUT_CHANGED"
    CONFIG_CHANGED = "CONFIG_CHANGED"
    ASSERTION_CHANGED = "ASSERTION_CHANGED"
    CAPABILITY_CHANGED = "CAPABILITY_CHANGED"
    METADATA_CHANGED = "METADATA_CHANGED"


class SemanticChange(StrictModel):
    """A single deterministic semantic change between two workflow contracts."""

    category: ChangeCategory
    change_type: str
    severity: DiffSeverity
    target_id: str | None = None
    node_id: str | None = None
    edge_id: str | None = None
    path: str = ""
    before: Any = None
    after: Any = None
    explanation: str

    @field_validator("before", "after")
    @classmethod
    def _validate_change_values(cls, value: Any) -> Any:
        return _json_value(value)

    @property
    def before_value(self) -> Any:
        return self.before

    @property
    def after_value(self) -> Any:
        return self.after

    @property
    def message(self) -> str:
        return self.explanation


class DiffSummary(StrictModel):
    """Statistical summary of semantic changes by severity."""

    total_changes: int = 0
    breaking_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    has_breaking: bool = False


class WorkflowDiff(StrictModel):
    """Complete deterministic diff between two workflow contracts."""

    old_workflow: str | None = None
    new_workflow: str | None = None
    old_fingerprint: str | None = None
    new_fingerprint: str | None = None
    identical: bool = True
    changes: list[SemanticChange] = Field(default_factory=list)
    summary: DiffSummary = Field(default_factory=DiffSummary)

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize WorkflowDiff deterministically to formatted JSON."""
        data = self.model_dump(mode="json")
        return json.dumps(data, indent=indent, sort_keys=True)
