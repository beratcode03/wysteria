"""Deterministic verification engine connecting workflows, fixtures, and execution."""

from typing import Any

from wysteria.fixtures.models import Fixture
from wysteria.fixtures.parser import ParsedFixture, validate_fixture_structure
from wysteria.fixtures.validation import validate_fixture_compatibility
from wysteria.ir.models import AssertPredicate, Workflow
from wysteria.ir.normalize import fingerprint_workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.validation.capabilities import CapabilityPolicy, validate_capabilities
from wysteria.validation.common import has_errors
from wysteria.validation.semantic import _value_type
from wysteria.verification.evaluator import evaluate_workflow, strict_equals
from wysteria.verification.models import VerificationResult, VerificationStatus


def evaluate_assertion_predicate(
    predicate: AssertPredicate,
    value: Any,
    expected: Any | None,
) -> bool:
    """Evaluate an assertion predicate using strict type-safe equality."""

    if predicate == AssertPredicate.EXISTS:
        return value is not None
    if predicate == AssertPredicate.EQUALS:
        return strict_equals(value, expected)
    if predicate == AssertPredicate.TYPE_IS:
        return _value_type(value).value == expected
    return False


def verify_fixture(
    workflow: Workflow | ParsedWorkflow,
    fixture: Fixture | ParsedFixture,
    *,
    policy: CapabilityPolicy | None = None,
    complete_outputs: bool | None = None,
) -> VerificationResult:
    """Verify a workflow proposal deterministically against one fixture."""

    workflow_fingerprint: str | None = None

    # 1. Validate Workflow
    if isinstance(workflow, ParsedWorkflow):
        from wysteria.api import validate_workflow

        wf_result = validate_workflow(workflow, policy=policy)
        if not wf_result.valid:
            fixture_id = (
                fixture.id
                if isinstance(fixture, Fixture)
                else fixture.data.get("id", "<unknown>")
                if isinstance(getattr(fixture, "data", None), dict)
                else "<unknown>"
            )
            return VerificationResult(
                status=VerificationStatus.INVALID_WORKFLOW,
                success=False,
                fixture_id=fixture_id,
                workflow_fingerprint=None,
                diagnostics=wf_result.diagnostics,
            )
        actual_workflow: Workflow = wf_result.workflow  # type: ignore[assignment]
    elif isinstance(workflow, Workflow):
        actual_workflow = workflow
        if policy is not None and actual_workflow.capabilities:
            cap_diags = validate_capabilities(actual_workflow, policy)
            if has_errors(cap_diags):
                return VerificationResult(
                    status=VerificationStatus.INVALID_WORKFLOW,
                    success=False,
                    fixture_id=fixture.id if isinstance(fixture, Fixture) else "<unknown>",
                    workflow_fingerprint=fingerprint_workflow(actual_workflow),
                    diagnostics=cap_diags,
                )
    else:
        raise TypeError(f"expected Workflow or ParsedWorkflow, got {type(workflow).__name__}")

    workflow_fingerprint = fingerprint_workflow(actual_workflow)

    # 2. Validate Fixture
    if isinstance(fixture, ParsedFixture):
        fix_model, fix_diags = validate_fixture_structure(fixture)
        if fix_model is None or has_errors(fix_diags):
            fixture_id = (
                fixture.data.get("id", "<unknown>")
                if isinstance(getattr(fixture, "data", None), dict)
                else "<unknown>"
            )
            return VerificationResult(
                status=VerificationStatus.INVALID_FIXTURE,
                success=False,
                fixture_id=fixture_id,
                workflow_fingerprint=workflow_fingerprint,
                diagnostics=fix_diags,
            )
        actual_fixture: Fixture = fix_model
    elif isinstance(fixture, Fixture):
        actual_fixture = fixture
    else:
        raise TypeError(f"expected Fixture or ParsedFixture, got {type(fixture).__name__}")

    # 3. Validate Fixture Compatibility with Workflow
    compat_diags = validate_fixture_compatibility(actual_fixture, actual_workflow)
    if has_errors(compat_diags):
        return VerificationResult(
            status=VerificationStatus.INVALID_FIXTURE,
            success=False,
            fixture_id=actual_fixture.id,
            workflow_fingerprint=workflow_fingerprint,
            diagnostics=compat_diags,
        )

    # 4. Evaluate Workflow
    exec_result = evaluate_workflow(actual_workflow, actual_fixture.inputs)
    node_values = exec_result.node_values
    traces = exec_result.traces

    # 5. Runtime Error vs Expected Error Verification
    expected_err_code = actual_fixture.expected.expected_error_code
    runtime_errors = [
        d
        for d in exec_result.diagnostics
        if d.code in {"WYS800", "WYS801", "WYS802", "WYS803", "WYS853"}
    ]

    if expected_err_code is not None:
        if runtime_errors:
            actual_code = runtime_errors[0].code
            if actual_code == expected_err_code:
                # Expected runtime failure occurred as specified
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    success=True,
                    fixture_id=actual_fixture.id,
                    workflow_fingerprint=workflow_fingerprint,
                    diagnostics=[],
                    actual_outputs={},
                    actual_assertions={},
                    traces=traces,
                )
            else:
                diff_diag = Diagnostic(
                    code="WYS800",
                    severity=Severity.ERROR,
                    message=f"expected runtime error '{expected_err_code}', got '{actual_code}'",
                    path="/expected/error",
                )
                return VerificationResult(
                    status=VerificationStatus.RUNTIME_ERROR,
                    success=False,
                    fixture_id=actual_fixture.id,
                    workflow_fingerprint=workflow_fingerprint,
                    diagnostics=[diff_diag, runtime_errors[0]],
                    actual_outputs={},
                    actual_assertions={},
                    traces=traces,
                )
        else:
            # Succeeded when an error was expected
            err_diag = Diagnostic(
                code="WYS800",
                severity=Severity.ERROR,
                message=f"expected runtime error '{expected_err_code}', but workflow evaluated successfully",
                path="/expected/error",
            )
            return VerificationResult(
                status=VerificationStatus.RUNTIME_ERROR,
                success=False,
                fixture_id=actual_fixture.id,
                workflow_fingerprint=workflow_fingerprint,
                diagnostics=[err_diag],
                actual_outputs={},
                actual_assertions={},
                traces=traces,
            )

    # If no error was expected, any runtime failure fails verification
    if runtime_errors:
        err = runtime_errors[0]
        status = (
            VerificationStatus.LIMIT_EXCEEDED
            if err.code == "WYS853"
            else VerificationStatus.RUNTIME_ERROR
        )
        return VerificationResult(
            status=status,
            success=False,
            fixture_id=actual_fixture.id,
            workflow_fingerprint=workflow_fingerprint,
            diagnostics=runtime_errors,
            actual_outputs={},
            actual_assertions={},
            traces=traces,
        )

    # 6. Actual Outputs Collection
    actual_outputs: dict[str, Any] = {}
    for name in sorted(actual_workflow.outputs.keys()):
        spec = actual_workflow.outputs[name]
        if spec.source.node is not None:
            if spec.source.node in node_values:
                actual_outputs[name] = node_values[spec.source.node]
        elif spec.source.input is not None:
            if spec.source.input in actual_fixture.inputs:
                actual_outputs[name] = actual_fixture.inputs[spec.source.input]

    # 7. Actual Assertions Collection
    actual_assertions: dict[str, bool] = {}

    # Node-level AssertNodes
    for node in actual_workflow.nodes:
        if node.kind == "assert":
            actual_assertions[node.id] = bool(node_values.get(node.id, False))

    # Workflow-level assertions
    for a in actual_workflow.assertions:
        val = None
        if a.source.node is not None:
            val = node_values.get(a.source.node)
        elif a.source.input is not None:
            val = actual_fixture.inputs.get(a.source.input)
        actual_assertions[a.id] = evaluate_assertion_predicate(a.predicate, val, a.expected)

    # 8. Assertions Comparison
    assertion_diagnostics: list[Diagnostic] = []
    expected_assertions = actual_fixture.expected.assertions

    if expected_assertions is not None:
        for target_id in sorted(expected_assertions.keys()):
            expected_bool = expected_assertions[target_id]
            actual_bool = actual_assertions.get(target_id)
            if actual_bool is None:
                assertion_diagnostics.append(
                    Diagnostic(
                        code="WYS703",
                        severity=Severity.ERROR,
                        message=f"expected assertion target '{target_id}' not found in workflow",
                        path=f"/expected/assertions/{target_id}",
                    )
                )
            elif actual_bool != expected_bool:
                is_assert_node = any(
                    n.id == target_id and n.kind == "assert" for n in actual_workflow.nodes
                )
                code = "WYS850" if is_assert_node else "WYS851"
                assertion_diagnostics.append(
                    Diagnostic(
                        code=code,
                        severity=Severity.ERROR,
                        message=f"assertion '{target_id}' expected {expected_bool}, got {actual_bool}",
                        path=f"/expected/assertions/{target_id}",
                    )
                )

        # Assertions not mentioned in expected.assertions default to expecting True
        for target_id in sorted(actual_assertions.keys()):
            if target_id not in expected_assertions:
                if not actual_assertions[target_id]:
                    is_assert_node = any(
                        n.id == target_id and n.kind == "assert" for n in actual_workflow.nodes
                    )
                    code = "WYS850" if is_assert_node else "WYS851"
                    assertion_diagnostics.append(
                        Diagnostic(
                            code=code,
                            severity=Severity.ERROR,
                            message=f"assertion '{target_id}' evaluated to false",
                            path=f"/assertions/{target_id}",
                        )
                    )
    else:
        # If no expected.assertions declared, all assertions are required to evaluate to True
        for target_id in sorted(actual_assertions.keys()):
            if not actual_assertions[target_id]:
                is_assert_node = any(
                    n.id == target_id and n.kind == "assert" for n in actual_workflow.nodes
                )
                code = "WYS850" if is_assert_node else "WYS851"
                assertion_diagnostics.append(
                    Diagnostic(
                        code=code,
                        severity=Severity.ERROR,
                        message=f"assertion '{target_id}' evaluated to false",
                        path=f"/assertions/{target_id}",
                    )
                )

    # 9. Output Comparison
    output_diagnostics: list[Diagnostic] = []
    expected_outputs = actual_fixture.expected.outputs

    if expected_outputs is not None:
        for name in sorted(expected_outputs.keys()):
            expected_val = expected_outputs[name]
            if name not in actual_outputs:
                output_diagnostics.append(
                    Diagnostic(
                        code="WYS852",
                        severity=Severity.ERROR,
                        message=f"missing actual output '{name}'",
                        path=f"/outputs/{name}",
                    )
                )
            else:
                actual_val = actual_outputs[name]
                if not strict_equals(actual_val, expected_val):
                    output_diagnostics.append(
                        Diagnostic(
                            code="WYS852",
                            severity=Severity.ERROR,
                            message=f"output mismatch for '{name}': expected {expected_val!r}, got {actual_val!r}",
                            path=f"/outputs/{name}",
                        )
                    )

        check_complete = (
            complete_outputs
            if complete_outputs is not None
            else actual_fixture.expected.complete_outputs
        )
        if check_complete:
            for name in sorted(actual_outputs.keys()):
                if name not in expected_outputs:
                    output_diagnostics.append(
                        Diagnostic(
                            code="WYS852",
                            severity=Severity.ERROR,
                            message=f"unexpected actual output '{name}'",
                            path=f"/outputs/{name}",
                        )
                    )

    # 10. Final Verification Outcome
    comparison_diagnostics = assertion_diagnostics + output_diagnostics
    if has_errors(comparison_diagnostics):
        if assertion_diagnostics:
            final_status = VerificationStatus.ASSERTION_FAILED
        else:
            final_status = VerificationStatus.OUTPUT_MISMATCH

        return VerificationResult(
            status=final_status,
            success=False,
            fixture_id=actual_fixture.id,
            workflow_fingerprint=workflow_fingerprint,
            diagnostics=comparison_diagnostics,
            actual_outputs=actual_outputs,
            actual_assertions=actual_assertions,
            traces=traces,
        )

    return VerificationResult(
        status=VerificationStatus.PASSED,
        success=True,
        fixture_id=actual_fixture.id,
        workflow_fingerprint=workflow_fingerprint,
        diagnostics=[],
        actual_outputs=actual_outputs,
        actual_assertions=actual_assertions,
        traces=traces,
    )
