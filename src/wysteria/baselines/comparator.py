"""Deterministic baseline comparison and structured diff reporting."""

from wysteria.baselines.models import (
    AssertionDiff,
    Baseline,
    BaselineComparison,
    BaselineComparisonStatus,
    DiffKind,
    OutputDiff,
)
from wysteria.reporting.verification import _format_value
from wysteria.verification.evaluator import strict_equals
from wysteria.verification.models import VerificationResult


def compare_baseline(
    result: VerificationResult,
    baseline: Baseline | None,
) -> BaselineComparison:
    """Deterministically compare a verification result against a saved baseline."""
    if baseline is None:
        return BaselineComparison(
            status=BaselineComparisonStatus.NO_BASELINE,
            matches=False,
            workflow_actual=result.workflow_fingerprint,
            fixture_actual=result.fixture_id,
            status_actual=result.status,
            expected_error_actual=result.expected_error_code,
            reasons=["No baseline exists"],
        )

    reasons: list[str] = []

    # 1. Workflow Fingerprint
    workflow_changed = result.workflow_fingerprint != baseline.workflow_fingerprint
    if workflow_changed:
        reasons.append("Workflow fingerprint changed")

    # 2. Fixture ID
    fixture_changed = result.fixture_id != baseline.fixture_id
    if fixture_changed:
        reasons.append(
            f"Fixture ID changed: expected '{baseline.fixture_id}', got '{result.fixture_id}'"
        )

    # 3. Verification Status
    status_changed = result.status != baseline.result.status
    if status_changed:
        reasons.append(
            f"Verification status changed: expected {baseline.result.status.value}, got {result.status.value}"
        )

    # 4. Expected Error Code
    expected_error_changed = result.expected_error_code != baseline.result.expected_error_code
    if expected_error_changed:
        reasons.append(
            f"Expected runtime-error behavior changed: expected {baseline.result.expected_error_code!r}, got {result.expected_error_code!r}"
        )

    # 5. Actual Outputs
    output_diffs: list[OutputDiff] = []
    outputs_changed = False
    all_output_keys = sorted(
        set(baseline.result.actual_outputs.keys()) | set(result.actual_outputs.keys())
    )
    for key in all_output_keys:
        in_base = key in baseline.result.actual_outputs
        in_curr = key in result.actual_outputs
        if in_base and in_curr:
            exp_val = baseline.result.actual_outputs[key]
            act_val = result.actual_outputs[key]
            if strict_equals(exp_val, act_val):
                output_diffs.append(
                    OutputDiff(name=key, kind=DiffKind.MATCH, expected=exp_val, actual=act_val)
                )
            else:
                outputs_changed = True
                output_diffs.append(
                    OutputDiff(name=key, kind=DiffKind.CHANGED, expected=exp_val, actual=act_val)
                )
                reasons.append(f"Output '{key}' changed")
        elif in_base and not in_curr:
            outputs_changed = True
            exp_val = baseline.result.actual_outputs[key]
            output_diffs.append(
                OutputDiff(name=key, kind=DiffKind.MISSING, expected=exp_val, actual=None)
            )
            reasons.append(f"Output '{key}' missing")
        elif not in_base and in_curr:
            outputs_changed = True
            act_val = result.actual_outputs[key]
            output_diffs.append(
                OutputDiff(name=key, kind=DiffKind.UNEXPECTED, expected=None, actual=act_val)
            )
            reasons.append(f"Output '{key}' unexpected")

    # 6. Actual Assertions
    assertion_diffs: list[AssertionDiff] = []
    assertions_changed = False
    all_assertion_keys = sorted(
        set(baseline.result.actual_assertions.keys()) | set(result.actual_assertions.keys())
    )
    for key in all_assertion_keys:
        in_base = key in baseline.result.actual_assertions
        in_curr = key in result.actual_assertions
        if in_base and in_curr:
            exp_bool = baseline.result.actual_assertions[key]
            act_bool = result.actual_assertions[key]
            if exp_bool == act_bool:
                assertion_diffs.append(
                    AssertionDiff(name=key, kind=DiffKind.MATCH, expected=exp_bool, actual=act_bool)
                )
            else:
                assertions_changed = True
                assertion_diffs.append(
                    AssertionDiff(
                        name=key, kind=DiffKind.CHANGED, expected=exp_bool, actual=act_bool
                    )
                )
                reasons.append(f"Assertion '{key}' changed")
        elif in_base and not in_curr:
            assertions_changed = True
            exp_bool = baseline.result.actual_assertions[key]
            assertion_diffs.append(
                AssertionDiff(name=key, kind=DiffKind.MISSING, expected=exp_bool, actual=None)
            )
            reasons.append(f"Assertion '{key}' missing")
        elif not in_base and in_curr:
            assertions_changed = True
            act_bool = result.actual_assertions[key]
            assertion_diffs.append(
                AssertionDiff(name=key, kind=DiffKind.UNEXPECTED, expected=None, actual=act_bool)
            )
            reasons.append(f"Assertion '{key}' unexpected")

    matches = not (
        workflow_changed
        or fixture_changed
        or status_changed
        or expected_error_changed
        or outputs_changed
        or assertions_changed
    )

    return BaselineComparison(
        status=BaselineComparisonStatus.MATCH if matches else BaselineComparisonStatus.REGRESSION,
        matches=matches,
        workflow_changed=workflow_changed,
        workflow_expected=baseline.workflow_fingerprint,
        workflow_actual=result.workflow_fingerprint,
        fixture_changed=fixture_changed,
        fixture_expected=baseline.fixture_id,
        fixture_actual=result.fixture_id,
        status_changed=status_changed,
        status_expected=baseline.result.status,
        status_actual=result.status,
        expected_error_changed=expected_error_changed,
        expected_error_expected=baseline.result.expected_error_code,
        expected_error_actual=result.expected_error_code,
        outputs_changed=outputs_changed,
        output_diffs=output_diffs,
        assertions_changed=assertions_changed,
        assertion_diffs=assertion_diffs,
        reasons=reasons,
    )


def format_baseline_report(comparison: BaselineComparison) -> str:
    """Format a deterministic structured human-readable report of baseline comparison."""
    header = [
        comparison.status.value,
        "────────────────────────────",
    ]
    sections: list[str] = ["\n".join(header)]

    if comparison.status == BaselineComparisonStatus.NO_BASELINE:
        sections.append("No baseline exists\n\nResult: NO_BASELINE")
        return "\n\n".join(sections)

    if comparison.status == BaselineComparisonStatus.REGRESSION:
        # 1. Workflow
        if comparison.workflow_changed:
            wf_lines = [
                "Workflow fingerprint changed",
                f"  expected: {comparison.workflow_expected}",
                f"  actual:   {comparison.workflow_actual}",
            ]
            sections.append("\n".join(wf_lines))

        # 2. Fixture ID
        if comparison.fixture_changed:
            fix_lines = [
                "Fixture ID changed",
                f"  expected: {comparison.fixture_expected}",
                f"  actual:   {comparison.fixture_actual}",
            ]
            sections.append("\n".join(fix_lines))

        # 3. Outputs
        if comparison.output_diffs:
            out_lines = ["Outputs"]
            for diff in comparison.output_diffs:
                if diff.kind == DiffKind.MATCH:
                    out_lines.append(f"  ✓ {diff.name}")
                elif diff.kind == DiffKind.CHANGED:
                    out_lines.append(f"  {diff.name}")
                    out_lines.append(f"    expected: {_format_value(diff.expected)}")
                    out_lines.append(f"    actual:   {_format_value(diff.actual)}")
                elif diff.kind == DiffKind.MISSING:
                    out_lines.append(f"  {diff.name}")
                    out_lines.append(f"    expected: {_format_value(diff.expected)}")
                    out_lines.append("    actual:   <missing>")
                elif diff.kind == DiffKind.UNEXPECTED:
                    out_lines.append(f"  {diff.name}")
                    out_lines.append("    expected: <none>")
                    out_lines.append(f"    actual:   {_format_value(diff.actual)}")
            sections.append("\n".join(out_lines))

        # 4. Assertions
        if comparison.assertion_diffs:
            assert_lines = ["Assertions"]
            for diff in comparison.assertion_diffs:
                if diff.kind == DiffKind.MATCH:
                    assert_lines.append(f"  ✓ {diff.name}")
                elif diff.kind == DiffKind.CHANGED:
                    assert_lines.append(f"  {diff.name}")
                    assert_lines.append(f"    expected: {str(diff.expected).lower()}")
                    assert_lines.append(f"    actual:   {str(diff.actual).lower()}")
                elif diff.kind == DiffKind.MISSING:
                    assert_lines.append(f"  {diff.name}")
                    assert_lines.append(f"    expected: {str(diff.expected).lower()}")
                    assert_lines.append("    actual:   <missing>")
                elif diff.kind == DiffKind.UNEXPECTED:
                    assert_lines.append(f"  {diff.name}")
                    assert_lines.append("    expected: <none>")
                    assert_lines.append(f"    actual:   {str(diff.actual).lower()}")
            sections.append("\n".join(assert_lines))

        # 5. Status
        st_lines = ["Status"]
        exp_st = comparison.status_expected.value if comparison.status_expected else "none"
        act_st = comparison.status_actual.value if comparison.status_actual else "none"
        st_lines.append(f"  expected: {exp_st}")
        st_lines.append(f"  actual:   {act_st}")
        sections.append("\n".join(st_lines))

        # 6. Expected Error
        if comparison.expected_error_changed:
            err_lines = ["Expected Error"]
            exp_err = _format_value(comparison.expected_error_expected)
            act_err = _format_value(comparison.expected_error_actual)
            err_lines.append(f"  expected: {exp_err}")
            err_lines.append(f"  actual:   {act_err}")
            sections.append("\n".join(err_lines))

        sections.append("Result: REGRESSION")

    else:
        # MATCH
        # Workflow
        sections.append("Workflow\n  ✓ fingerprint matches")

        # Outputs
        if comparison.output_diffs:
            out_lines = ["Outputs"]
            for diff in comparison.output_diffs:
                out_lines.append(f"  ✓ {diff.name} = {_format_value(diff.actual)}")
            sections.append("\n".join(out_lines))

        # Assertions
        if comparison.assertion_diffs:
            assert_lines = ["Assertions"]
            for diff in comparison.assertion_diffs:
                assert_lines.append(f"  ✓ {diff.name}")
            sections.append("\n".join(assert_lines))

        # Status
        act_st = comparison.status_actual.value if comparison.status_actual else "PASSED"
        sections.append(f"Status\n  ✓ {act_st}")

        sections.append("Result: MATCH")

    return "\n\n".join(sections)
