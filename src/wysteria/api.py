"""Small stable public API for loading and verifying Workflow IR."""

from pathlib import Path
from typing import Any

from wysteria.baselines.comparator import (
    compare_baseline as _compare_baseline,
)
from wysteria.baselines.comparator import (
    format_baseline_report as _format_baseline_report,
)
from wysteria.baselines.models import (
    CURRENT_BASELINE_VERSION,
    AssertionDiff,
    Baseline,
    BaselineComparison,
    BaselineComparisonStatus,
    BaselineResult,
    DiffKind,
    OutputDiff,
)
from wysteria.baselines.storage import (
    create_baseline as _create_baseline,
)
from wysteria.baselines.storage import (
    load_baseline as _load_baseline,
)
from wysteria.baselines.storage import (
    parse_baseline as _parse_baseline,
)
from wysteria.baselines.storage import (
    serialize_baseline as _serialize_baseline,
)
from wysteria.errors import (
    BaselineCreationError,
    BaselineError,
    BaselineLoadError,
    BaselineParseError,
    FixtureLoadError,
    FixtureParseError,
    WorkflowParseError,
)
from wysteria.fixtures.models import (
    CURRENT_FIXTURE_VERSION,
    Fixture,
    FixtureExpected,
)
from wysteria.fixtures.parser import (
    ParsedFixture,
)
from wysteria.fixtures.parser import (
    load_fixture as _load_fixture,
)
from wysteria.fixtures.parser import (
    load_fixture_document as _load_fixture_document,
)
from wysteria.fixtures.parser import (
    parse_fixture as _parse_fixture,
)
from wysteria.fixtures.parser import (
    parse_fixture_document as _parse_fixture_document,
)
from wysteria.fixtures.parser import (
    validate_fixture_structure as _validate_fixture_structure,
)
from wysteria.fixtures.validation import (
    FixtureValidationResult,
)
from wysteria.fixtures.validation import (
    validate_fixture as _validate_fixture,
)
from wysteria.fixtures.validation import (
    validate_fixture_compatibility as _validate_fixture_compatibility,
)
from wysteria.ir.models import Workflow
from wysteria.ir.normalize import fingerprint_workflow as _fingerprint_workflow
from wysteria.ir.normalize import normalize_workflow as _normalize_workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.ir.parser import load_workflow as _load_workflow
from wysteria.ir.parser import parse_workflow as _parse_workflow
from wysteria.reporting.diagnostics import Diagnostic, ValidationResult
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
from wysteria.verification.engine import (
    verify_fixture as _verify_fixture,
)
from wysteria.verification.errors import RuntimeEvaluationError
from wysteria.verification.evaluator import (
    evaluate_node as _evaluate_node,
)
from wysteria.verification.evaluator import (
    evaluate_workflow as _evaluate_workflow,
)
from wysteria.verification.evaluator import (
    strict_equals as _strict_equals,
)
from wysteria.verification.models import (
    NodeExecutionTrace,
    VerificationResult,
    VerificationStatus,
    WorkflowExecutionResult,
)


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


def parse_fixture(text: str, *, filename: str = "<memory>", format: str | None = None) -> Fixture:
    """Safely parse and structurally validate YAML/JSON fixture text; raises ``FixtureParseError`` on error."""

    return _parse_fixture(text, filename=filename, format=format)


def load_fixture(path: str | Path) -> Fixture:
    """Read and safely parse a YAML or JSON fixture file."""

    return _load_fixture(path)


def parse_fixture_document(
    text: str, *, filename: str = "<memory>", format: str | None = None
) -> ParsedFixture:
    """Safely parse YAML or JSON fixture text into a document with source locations."""

    return _parse_fixture_document(text, filename=filename, format=format)


def load_fixture_document(path: str | Path) -> ParsedFixture:
    """Read and safely parse a fixture file into a document with source locations."""

    return _load_fixture_document(path)


def validate_fixture_structure(parsed: ParsedFixture) -> tuple[Fixture | None, list[Diagnostic]]:
    """Validate parsed fixture document against strict Pydantic models."""

    return _validate_fixture_structure(parsed)


def validate_fixture_compatibility(
    fixture: Fixture,
    workflow: Workflow,
    parsed: ParsedFixture | None = None,
) -> list[Diagnostic]:
    """Validate fixture compatibility against a workflow contract and return diagnostics."""

    return _validate_fixture_compatibility(fixture, workflow, parsed=parsed)


def validate_fixture(
    fixture: Fixture,
    workflow: Workflow,
    parsed: ParsedFixture | None = None,
) -> FixtureValidationResult:
    """Validate a fixture against a workflow contract and return a structured result."""

    return _validate_fixture(fixture, workflow, parsed=parsed)


def evaluate_node(node, resolved_inputs: dict[str, Any]) -> tuple[Any, list[Diagnostic]]:
    """Evaluate a single node deterministically against resolved inputs."""

    return _evaluate_node(node, resolved_inputs)


def evaluate_workflow(workflow: Workflow, inputs: dict[str, Any]) -> WorkflowExecutionResult:
    """Evaluate a workflow DAG in deterministic topological order against inputs."""

    return _evaluate_workflow(workflow, inputs)


def strict_equals(a: Any, b: Any) -> bool:
    """Compare two values for strict deterministic equality."""

    return _strict_equals(a, b)


def verify_fixture(
    workflow: Workflow | ParsedWorkflow | str | Path,
    fixture: Fixture | ParsedFixture | str | Path,
    *,
    policy: CapabilityPolicy | None = None,
    complete_outputs: bool | None = None,
) -> VerificationResult:
    """Verify a workflow proposal deterministically against a fixture."""

    if isinstance(workflow, (str, Path)):
        workflow = _load_workflow(workflow)
    if isinstance(fixture, (str, Path)):
        fixture = _load_fixture_document(fixture)

    return _verify_fixture(
        workflow,
        fixture,
        policy=policy,
        complete_outputs=complete_outputs,
    )


def create_baseline(
    result: VerificationResult,
    path: str | Path,
    *,
    force: bool = False,
) -> Baseline:
    """Create and safely persist a regression baseline from a successful verification result."""

    return _create_baseline(result, path, force=force)


def load_baseline(path: str | Path) -> Baseline:
    """Read, safely parse, and validate a baseline file."""

    return _load_baseline(path)


def compare_baseline(
    result: VerificationResult,
    baseline: Baseline | None,
) -> BaselineComparison:
    """Deterministically compare a verification result against a saved baseline."""

    return _compare_baseline(result, baseline)


def parse_baseline(text: str, *, filename: str = "<memory>", format: str | None = None) -> Baseline:
    """Safely parse and validate baseline text into a Baseline model."""

    return _parse_baseline(text, filename=filename, format=format)


def serialize_baseline(baseline: Baseline) -> str:
    """Deterministically serialize a Baseline model to canonical formatted JSON."""

    return _serialize_baseline(baseline)


def format_baseline_report(comparison: BaselineComparison) -> str:
    """Format a deterministic structured human-readable report of baseline comparison."""

    return _format_baseline_report(comparison)


__all__ = [
    "CURRENT_BASELINE_VERSION",
    "CURRENT_FIXTURE_VERSION",
    "AssertionDiff",
    "Baseline",
    "BaselineComparison",
    "BaselineComparisonStatus",
    "BaselineCreationError",
    "BaselineError",
    "BaselineLoadError",
    "BaselineParseError",
    "BaselineResult",
    "DiffKind",
    "Fixture",
    "FixtureExpected",
    "FixtureLoadError",
    "FixtureParseError",
    "FixtureValidationResult",
    "GraphCycleError",
    "NodeExecutionTrace",
    "OutputDiff",
    "ParsedFixture",
    "ParsedWorkflow",
    "RuntimeEvaluationError",
    "VerificationResult",
    "VerificationStatus",
    "WorkflowExecutionResult",
    "WorkflowParseError",
    "compare_baseline",
    "create_baseline",
    "evaluate_node",
    "evaluate_workflow",
    "fingerprint_workflow",
    "format_baseline_report",
    "load_baseline",
    "load_fixture",
    "load_fixture_document",
    "load_workflow",
    "normalize_workflow",
    "parse_baseline",
    "parse_fixture",
    "parse_fixture_document",
    "parse_workflow",
    "serialize_baseline",
    "strict_equals",
    "topological_sort",
    "validate_fixture",
    "validate_fixture_compatibility",
    "validate_fixture_structure",
    "validate_workflow",
    "verify_fixture",
]
