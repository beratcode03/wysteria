"""Workflow-dependent compatibility validation for fixtures."""

from pydantic import BaseModel, ConfigDict, Field

from wysteria.fixtures.models import Fixture
from wysteria.fixtures.parser import ParsedFixture
from wysteria.ir.models import Workflow
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.validation.common import diagnostic, has_errors
from wysteria.validation.semantic import _compatible, _value_type


class FixtureValidationResult(BaseModel):
    """Result of validating one fixture against a workflow contract."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    fixture: Fixture | None = Field(default=None, exclude=True)


def validate_fixture_compatibility(
    fixture: Fixture,
    workflow: Workflow,
    parsed: ParsedFixture | None = None,
) -> list[Diagnostic]:
    """Validate a fixture's inputs, outputs, and assertions against a workflow contract."""

    diagnostics: list[Diagnostic] = []

    # 1. Inputs validation
    for name in sorted(fixture.inputs):
        if name not in workflow.inputs:
            diagnostics.append(
                diagnostic(
                    "WYS702",
                    f"undeclared fixture input '{name}'",
                    f"/inputs/{name}",
                    parsed=parsed,
                    severity=Severity.ERROR,
                    hint="Declare the input in the workflow or remove it from the fixture.",
                )
            )

    for name in sorted(workflow.inputs):
        spec = workflow.inputs[name]
        if spec.required and name not in fixture.inputs:
            diagnostics.append(
                diagnostic(
                    "WYS702",
                    f"missing required workflow input '{name}'",
                    f"/inputs/{name}",
                    parsed=parsed,
                    severity=Severity.ERROR,
                    hint=f"Provide a value of type '{spec.type.value}' for '{name}'.",
                )
            )

    for name in sorted(fixture.inputs):
        if name in workflow.inputs:
            spec = workflow.inputs[name]
            val = fixture.inputs[name]
            actual = _value_type(val)
            if not _compatible(actual, spec.type):
                diagnostics.append(
                    diagnostic(
                        "WYS702",
                        f"fixture input '{name}' has type '{actual.value}', expected '{spec.type.value}'",
                        f"/inputs/{name}",
                        parsed=parsed,
                        severity=Severity.ERROR,
                        hint=f"Provide an input value compatible with type '{spec.type.value}'.",
                    )
                )

    # 2. Expected outputs validation
    if fixture.expected.outputs is not None:
        for name in sorted(fixture.expected.outputs):
            val = fixture.expected.outputs[name]
            if name not in workflow.outputs:
                diagnostics.append(
                    diagnostic(
                        "WYS703",
                        f"expected output '{name}' is not declared in workflow outputs",
                        f"/expected/outputs/{name}",
                        parsed=parsed,
                        severity=Severity.ERROR,
                        hint="Declare the output in the workflow or remove it from expected.outputs.",
                    )
                )
            else:
                out_spec = workflow.outputs[name]
                actual = _value_type(val)
                if not _compatible(actual, out_spec.type):
                    diagnostics.append(
                        diagnostic(
                            "WYS703",
                            f"expected output '{name}' has type '{actual.value}', expected '{out_spec.type.value}'",
                            f"/expected/outputs/{name}",
                            parsed=parsed,
                            severity=Severity.ERROR,
                            hint=f"Provide an expected output compatible with type '{out_spec.type.value}'.",
                        )
                    )

    # 3. Expected assertions validation
    if fixture.expected.assertions is not None:
        workflow_assertion_ids = {a.id for a in workflow.assertions}
        assert_node_ids = {node.id for node in workflow.nodes if node.kind == "assert"}
        valid_assertion_targets = workflow_assertion_ids | assert_node_ids
        for assertion_id in sorted(fixture.expected.assertions):
            if assertion_id not in valid_assertion_targets:
                diagnostics.append(
                    diagnostic(
                        "WYS703",
                        f"expected assertion '{assertion_id}' does not match any workflow assertion or assert node ID",
                        f"/expected/assertions/{assertion_id}",
                        parsed=parsed,
                        severity=Severity.ERROR,
                        hint="Reference a valid workflow assertion ID or assert node ID.",
                    )
                )

    return diagnostics


def validate_fixture(
    fixture: Fixture,
    workflow: Workflow,
    parsed: ParsedFixture | None = None,
) -> FixtureValidationResult:
    """Validate a fixture against a workflow and return a structured result."""

    diagnostics = validate_fixture_compatibility(fixture, workflow, parsed=parsed)
    return FixtureValidationResult(
        valid=not has_errors(diagnostics),
        diagnostics=diagnostics,
        fixture=fixture,
    )
