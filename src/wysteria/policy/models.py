"""Strict, deterministic policy models and schemas."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator

from wysteria.ir.models import (
    CapabilityField,
    StrictModel,
)
from wysteria.reporting.diagnostics import Severity

CURRENT_POLICY_VERSION = 1
SUPPORTED_POLICY_VERSIONS = frozenset({CURRENT_POLICY_VERSION})


class PolicyStatus(StrEnum):
    """Deterministic status of a policy evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCK = "BLOCK"


class PolicyRule(StrEnum):
    """Supported deterministic policy rule identifiers."""

    MAX_NODES = "max_nodes"
    MAX_EDGES = "max_edges"
    FORBIDDEN_CAPABILITIES = "forbidden_capabilities"
    REQUIRED_CAPABILITIES = "required_capabilities"
    REQUIRE_ASSERTIONS = "require_assertions"
    REQUIRE_OUTPUTS = "require_outputs"
    FORBID_UNREACHABLE_NODES = "forbid_unreachable_nodes"
    ALLOWED_HTTP_HOSTS = "allowed_http_hosts"
    FORBIDDEN_HTTP_HOSTS = "forbidden_http_hosts"
    ALLOWED_HTTP_METHODS = "allowed_http_methods"


class PolicyViolation(StrictModel):
    """A structured, deterministic policy violation finding."""

    code: str
    policy: str
    severity: Severity = Severity.ERROR
    message: str
    node_id: str | None = None
    capability: str | None = None
    path: str = ""


class Policy(StrictModel):
    """The stable v1 governance and security policy model."""

    policy_version: Literal[CURRENT_POLICY_VERSION] = CURRENT_POLICY_VERSION
    id: str | None = None
    name: str | None = None
    description: str | None = None
    max_nodes: int | None = Field(default=None, ge=0)
    max_edges: int | None = Field(default=None, ge=0)
    forbidden_capabilities: list[CapabilityField] = Field(default_factory=list)
    required_capabilities: list[CapabilityField] = Field(default_factory=list)
    require_assertions: bool = False
    require_outputs: bool = False
    forbid_unreachable_nodes: bool = False
    allowed_http_hosts: list[str] | None = None
    forbidden_http_hosts: list[str] | None = None
    allowed_http_methods: list[str] | None = None
    allowed_evidence_hosts: list[str] | None = None
    forbidden_evidence_hosts: list[str] | None = None
    evidence_host_trust_tiers: dict[str, int] = Field(default_factory=dict)
    max_evidence_trust_tier: int | None = Field(default=None, ge=1, le=4)

    @field_validator("forbidden_capabilities", "required_capabilities", mode="before")
    @classmethod
    def _normalize_cap_list(cls, value: Any) -> Any:
        if value is None:
            return []
        return value

    @field_validator(
        "require_assertions", "require_outputs", "forbid_unreachable_nodes", mode="before"
    )
    @classmethod
    def _normalize_bool(cls, value: Any) -> Any:
        if value is None:
            return False
        return value


class PolicyResult(StrictModel):
    """Deterministic result of evaluating a workflow against a policy."""

    status: PolicyStatus
    passed: bool
    blocked: bool = False
    policy_name: str | None = None
    violations: list[PolicyViolation] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize PolicyResult deterministically to formatted JSON."""
        data = self.model_dump(mode="json")
        return json.dumps(data, indent=indent, sort_keys=True)
