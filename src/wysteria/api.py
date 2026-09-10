"""Small stable public API for loading and verifying Workflow IR."""

from pathlib import Path

from wysteria.errors import WorkflowParseError
from wysteria.ir.models import Workflow
from wysteria.ir.normalize import fingerprint_workflow as _fingerprint_workflow
from wysteria.ir.normalize import normalize_workflow as _normalize_workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.ir.parser import load_workflow as _load_workflow
from wysteria.ir.parser import parse_workflow as _parse_workflow
from wysteria.reporting.diagnostics import ValidationResult
from wysteria.validation.capabilities import CapabilityPolicy, validate_capabilities
from wysteria.validation.common import has_errors
from wysteria.validation.graph import (
    GraphCycleError,
    validate_graph,
)
from wysteria.validation.graph import (
    topological_sort as _topological_sort,
)
from wysteria.validation.references import validate_references
from wysteria.validation.schema import validate_structure
from wysteria.validation.semantic import validate_semantics


def parse_workflow(
    text: str, *, filename: str = "<memory>", format: str | None = None
) -> ParsedWorkflow:
    """Safely parse YAML/JSON workflow text; raises ``WorkflowParseError`` on malformed input."""

    return _parse_workflow(text, filename=filename, format=format)


def load_workflow(path: str | Path) -> ParsedWorkflow:
    """Read and safely parse a YAML or JSON workflow file."""

    return _load_workflow(path)


def validate_workflow(
    parsed: ParsedWorkflow,
    *,
    policy: CapabilityPolicy | None = None,
) -> ValidationResult:
    """Run structural, reference, graph, policy, and semantic validation layers."""

    workflow, diagnostics = validate_structure(parsed)
    if workflow is None:
        return ValidationResult(valid=False, diagnostics=diagnostics)
    diagnostics.extend(validate_references(workflow, parsed))
    diagnostics.extend(validate_graph(workflow, parsed))
    capability_diagnostics = validate_capabilities(workflow, policy, parsed)
    diagnostics.extend(capability_diagnostics)
    diagnostics.extend(validate_semantics(workflow, parsed))
    return ValidationResult(
        valid=not has_errors(diagnostics),
        blocked=bool(capability_diagnostics),
        diagnostics=diagnostics,
        workflow=workflow,
    )


def normalize_workflow(workflow: Workflow) -> dict:
    """Return the canonical normalized representation of a validated workflow."""

    return _normalize_workflow(workflow)


def fingerprint_workflow(workflow: Workflow) -> str:
    """Return a SHA-256 fingerprint of canonical normalized workflow JSON."""

    return _fingerprint_workflow(workflow)


def topological_sort(workflow: Workflow) -> list[str]:
    """Return a deterministic topological ordering of node IDs."""

    return _topological_sort(workflow)


__all__ = [
    "GraphCycleError",
    "WorkflowParseError",
    "fingerprint_workflow",
    "load_workflow",
    "normalize_workflow",
    "parse_workflow",
    "topological_sort",
    "validate_workflow",
]
