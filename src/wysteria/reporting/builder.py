"""Deterministic builder and formatters for DeveloperReport presentation model."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from wysteria.diff import WorkflowDiff, format_workflow_diff
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.reporting.gate import evaluate_gate
from wysteria.reporting.models import (
    AssertionReportItem,
    BaselineDiffEntry,
    BaselineSummary,
    DeveloperReport,
    DiagnosticCategory,
    ExecutionSummary,
    FixtureIdentity,
    GateDecision,
    MatchState,
    NormalizedDiagnostic,
    OutputReportItem,
    ReportStatus,
    StatusBadge,
    StatusPresentation,
    ValidationSummary,
    WorkflowIdentity,
)
from wysteria.verification.evaluator import strict_equals
from wysteria.verification.models import NodeExecutionTrace, VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from wysteria.baselines.models import BaselineComparison
    from wysteria.fixtures.models import Fixture
    from wysteria.fixtures.parser import ParsedFixture
    from wysteria.ir.models import Workflow
    from wysteria.ir.parser import ParsedWorkflow
    from wysteria.policy.models import PolicyResult


def _format_value(val: Any) -> str:
    """Format a JSON-compatible value deterministically."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return json.dumps(val)
    if isinstance(val, (dict, list)):
        return json.dumps(val, separators=(",", ":"), sort_keys=True)
    return repr(val)


def categorize_diagnostic_code(code: str) -> DiagnosticCategory:
    """Classify a Wysteria diagnostic code into a presentation-neutral category."""
    if code.startswith("WYS"):
        num_str = code[3:]
        if num_str.isdigit():
            num = int(num_str)
            if 100 <= num < 200:
                return DiagnosticCategory.SCHEMA
            if 200 <= num < 300:
                return DiagnosticCategory.REFERENCE
            if 300 <= num < 400:
                return DiagnosticCategory.GRAPH
            if 400 <= num < 450:
                return DiagnosticCategory.CAPABILITY
            if 450 <= num < 500:
                return DiagnosticCategory.POLICY
            if 500 <= num < 600:
                return DiagnosticCategory.SEMANTIC
            if 600 <= num < 700:
                return DiagnosticCategory.BASELINE
            if 700 <= num < 800:
                return DiagnosticCategory.FIXTURE
            if 800 <= num < 850:
                return DiagnosticCategory.RUNTIME
            if num in {850, 851}:
                return DiagnosticCategory.ASSERTION
            if num == 852:
                return DiagnosticCategory.OUTPUT
            if num == 853:
                return DiagnosticCategory.LIMIT
            if 854 <= num < 900:
                return DiagnosticCategory.RUNTIME
            if 900 <= num < 1000:
                return DiagnosticCategory.SYSTEM
    return DiagnosticCategory.GENERAL


def extract_node_id(diag: Diagnostic) -> str | None:
    """Extract node ID from diagnostic path or message."""
    if diag.path:
        parts = diag.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "nodes" and not parts[1].isdigit():
            return parts[1]
    match = re.search(r"(?:node|AssertNode)\s+'([^']+)'", diag.message, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def normalize_diagnostic(diag: Diagnostic) -> NormalizedDiagnostic:
    """Normalize a diagnostic finding into a structured record."""
    node_id = extract_node_id(diag)
    category = categorize_diagnostic_code(diag.code)
    return NormalizedDiagnostic(
        code=diag.code,
        severity=diag.severity,
        message=diag.message,
        category=category,
        node_id=node_id,
        path=diag.path,
        location=diag.location,
        hint=diag.hint,
    )


def diagnostic_sort_key(d: NormalizedDiagnostic) -> tuple:
    """Stable, deterministic sort key for normalized diagnostics."""
    loc_file = d.location.file if d.location else ""
    loc_line = d.location.line if d.location else 0
    loc_col = d.location.column if d.location else 0
    return (
        0 if d.severity == Severity.ERROR else 1,
        d.code,
        loc_file,
        loc_line,
        loc_col,
        d.node_id or "",
        d.path,
        d.message,
    )


def make_status_presentation(status: ReportStatus, passed: bool) -> StatusPresentation:
    """Create a presentation-neutral visual representation for any report status."""
    if passed or status in {ReportStatus.PASS, ReportStatus.PASSED}:
        return StatusPresentation(
            status=ReportStatus.PASS,
            label="PASS",
            badge=StatusBadge.SUCCESS,
            passed=True,
        )

    labels: dict[ReportStatus, tuple[str, StatusBadge]] = {
        ReportStatus.OUTPUT_MISMATCH: ("OUTPUT MISMATCH", StatusBadge.FAILURE),
        ReportStatus.ASSERTION_FAILED: ("ASSERTION FAILED", StatusBadge.FAILURE),
        ReportStatus.REGRESSION: ("REGRESSION", StatusBadge.FAILURE),
        ReportStatus.INVALID_WORKFLOW: ("INVALID WORKFLOW", StatusBadge.ERROR),
        ReportStatus.INVALID_FIXTURE: ("INVALID FIXTURE", StatusBadge.ERROR),
        ReportStatus.RUNTIME_ERROR: ("RUNTIME ERROR", StatusBadge.ERROR),
        ReportStatus.LIMIT_EXCEEDED: ("LIMIT EXCEEDED", StatusBadge.ERROR),
        ReportStatus.FAIL: ("FAIL", StatusBadge.FAILURE),
    }

    label, badge = labels.get(status, (status.value.replace("_", " "), StatusBadge.FAILURE))
    return StatusPresentation(
        status=status,
        label=label,
        badge=badge,
        passed=False,
    )


def _build_baseline_summary(comparison: BaselineComparison) -> BaselineSummary:
    """Convert BaselineComparison into structured BaselineSummary with stable ordering."""
    diff_entries: list[BaselineDiffEntry] = []
    output_diffs: list[BaselineDiffEntry] = []
    assertion_diffs: list[BaselineDiffEntry] = []

    if comparison.workflow_changed:
        diff_entries.append(
            BaselineDiffEntry(
                category="workflow",
                name="workflow_fingerprint",
                kind="CHANGED",
                expected=comparison.workflow_expected,
                actual=comparison.workflow_actual,
                message="Workflow fingerprint changed",
            )
        )

    if comparison.fixture_changed:
        diff_entries.append(
            BaselineDiffEntry(
                category="fixture",
                name="fixture_id",
                kind="CHANGED",
                expected=comparison.fixture_expected,
                actual=comparison.fixture_actual,
                message=f"Fixture ID changed: expected '{comparison.fixture_expected}', got '{comparison.fixture_actual}'",
            )
        )

    if comparison.status_changed:
        diff_entries.append(
            BaselineDiffEntry(
                category="status",
                name="status",
                kind="CHANGED",
                expected=comparison.status_expected.value if comparison.status_expected else None,
                actual=comparison.status_actual.value if comparison.status_actual else None,
                message="Verification status changed",
            )
        )

    if comparison.expected_error_changed:
        diff_entries.append(
            BaselineDiffEntry(
                category="expected_error",
                name="expected_error_code",
                kind="CHANGED",
                expected=comparison.expected_error_expected,
                actual=comparison.expected_error_actual,
                message="Expected runtime-error behavior changed",
            )
        )

    sorted_out_diffs = sorted(comparison.output_diffs, key=lambda d: d.name)
    for diff in sorted_out_diffs:
        entry = BaselineDiffEntry(
            category="output",
            name=diff.name,
            kind=diff.kind.value if hasattr(diff.kind, "value") else str(diff.kind),
            expected=diff.expected,
            actual=diff.actual,
            message=f"Output '{diff.name}' {str(diff.kind).lower()}",
        )
        output_diffs.append(entry)
        kind_str = diff.kind.value if hasattr(diff.kind, "value") else str(diff.kind)
        if kind_str != "MATCH":
            diff_entries.append(entry)

    sorted_assert_diffs = sorted(comparison.assertion_diffs, key=lambda d: d.name)
    for diff in sorted_assert_diffs:
        entry = BaselineDiffEntry(
            category="assertion",
            name=diff.name,
            kind=diff.kind.value if hasattr(diff.kind, "value") else str(diff.kind),
            expected=diff.expected,
            actual=diff.actual,
            message=f"Assertion '{diff.name}' {str(diff.kind).lower()}",
        )
        assertion_diffs.append(entry)
        kind_str = diff.kind.value if hasattr(diff.kind, "value") else str(diff.kind)
        if kind_str != "MATCH":
            diff_entries.append(entry)

    # Deterministic ordering for diff entries
    diff_entries.sort(key=lambda e: (e.category, e.name))

    st_exp = comparison.status_expected.value if comparison.status_expected else None
    st_act = comparison.status_actual.value if comparison.status_actual else None
    status_str = (
        comparison.status.value if hasattr(comparison.status, "value") else str(comparison.status)
    )

    return BaselineSummary(
        status=status_str,
        matches=comparison.matches,
        workflow_changed=comparison.workflow_changed,
        workflow_expected=comparison.workflow_expected,
        workflow_actual=comparison.workflow_actual,
        fixture_changed=comparison.fixture_changed,
        fixture_expected=comparison.fixture_expected,
        fixture_actual=comparison.fixture_actual,
        status_changed=comparison.status_changed,
        status_expected=st_exp,
        status_actual=st_act,
        expected_error_changed=comparison.expected_error_changed,
        expected_error_expected=comparison.expected_error_expected,
        expected_error_actual=comparison.expected_error_actual,
        outputs_changed=comparison.outputs_changed,
        output_diffs=output_diffs,
        assertions_changed=comparison.assertions_changed,
        assertion_diffs=assertion_diffs,
        diff_entries=diff_entries,
        reasons=list(comparison.reasons),
    )


def build_developer_report(
    result: VerificationResult,
    *,
    workflow: Workflow | ParsedWorkflow | None = None,
    fixture: Fixture | ParsedFixture | None = None,
    workflow_display: str | None = None,
    fixture_display: str | None = None,
    baseline_comparison: BaselineComparison | None = None,
    workflow_diff: WorkflowDiff | None = None,
    policy_result: PolicyResult | None = None,
) -> DeveloperReport:
    """Build a stable, presentation-independent DeveloperReport from a VerificationResult."""
    # 1. Workflow identity
    wf_name: str | None = None
    if workflow is not None:
        name_val = getattr(workflow, "name", None)
        if name_val is not None:
            wf_name = name_val
        elif hasattr(workflow, "data") and isinstance(workflow.data, dict):
            wf_name = workflow.data.get("name")

    wf_disp = (
        workflow_display
        or wf_name
        or (result.workflow_fingerprint[:8] if result.workflow_fingerprint else "<unknown>")
    )
    workflow_id = WorkflowIdentity(
        name=wf_name,
        fingerprint=result.workflow_fingerprint,
        display_name=wf_disp,
    )

    # 2. Fixture identity
    fix_id = result.fixture_id
    fix_name: str | None = None
    if fixture is not None:
        fix_id = getattr(fixture, "id", result.fixture_id)
        fix_name = getattr(fixture, "name", None)
        if hasattr(fixture, "data") and isinstance(fixture.data, dict):
            fix_id = fixture.data.get("id", fix_id)
            if fix_name is None:
                fix_name = fixture.data.get("name")

    fix_disp = fixture_display or fix_name or fix_id or "<unknown>"
    fixture_id_model = FixtureIdentity(
        id=fix_id,
        name=fix_name,
        display_name=fix_disp,
    )

    # 3. Overall status and baseline handling
    is_regression = False
    if baseline_comparison is not None:
        status_val = (
            baseline_comparison.status.value
            if hasattr(baseline_comparison.status, "value")
            else str(baseline_comparison.status)
        )
        if status_val == "REGRESSION":
            is_regression = True

    if is_regression:
        status = ReportStatus.REGRESSION
        overall_status = ReportStatus.FAIL
        success = False
    else:
        status = ReportStatus(result.status.value)
        success = result.success
        overall_status = ReportStatus.PASS if success else ReportStatus.FAIL

    status_presentation = make_status_presentation(status, success)

    # 4. Diagnostics normalization & deterministic sorting
    norm_diags = [normalize_diagnostic(d) for d in result.diagnostics]
    norm_diags.sort(key=diagnostic_sort_key)

    # 5. Validation summary
    wf_valid = result.status != VerificationStatus.INVALID_WORKFLOW
    fix_valid = result.status != VerificationStatus.INVALID_FIXTURE
    err_count = sum(1 for d in norm_diags if d.severity == Severity.ERROR)
    warn_count = sum(1 for d in norm_diags if d.severity == Severity.WARNING)
    validation = ValidationSummary(
        workflow_valid=wf_valid,
        fixture_valid=fix_valid,
        error_count=err_count,
        warning_count=warn_count,
    )

    # 6. Execution summary
    exp_occurred = bool(
        result.expected_error_code is not None and result.status == VerificationStatus.PASSED
    )
    actual_err: str | None = None
    for d in norm_diags:
        if d.code in {"WYS800", "WYS801", "WYS802", "WYS803", "WYS853"}:
            actual_err = d.code
            break

    execution = ExecutionSummary(
        total_nodes_executed=len(result.traces),
        success=result.success,
        expected_error_occurred=exp_occurred,
        expected_error_code=result.expected_error_code,
        actual_error_code=actual_err,
    )

    # 7. Outputs collection
    expected_outputs: dict[str, Any] | None = None
    complete_outputs = False
    if fixture is not None:
        exp = getattr(fixture, "expected", None)
        if exp is not None and hasattr(exp, "outputs") and exp.outputs is not None:
            expected_outputs = exp.outputs
            complete_outputs = bool(getattr(exp, "complete_outputs", False))
        elif hasattr(fixture, "data") and isinstance(fixture.data, dict):
            raw_exp = fixture.data.get("expected")
            if isinstance(raw_exp, dict):
                if isinstance(raw_exp.get("outputs"), dict):
                    expected_outputs = raw_exp["outputs"]
                complete_outputs = bool(raw_exp.get("complete_outputs", False))

    outputs: list[OutputReportItem] = []
    if expected_outputs is not None:
        all_out_keys = sorted(set(expected_outputs.keys()) | set(result.actual_outputs.keys()))
        for key in all_out_keys:
            in_expected = key in expected_outputs
            in_actual = key in result.actual_outputs
            if in_expected and in_actual:
                exp_val = expected_outputs[key]
                act_val = result.actual_outputs[key]
                match_st = (
                    MatchState.MATCH if strict_equals(exp_val, act_val) else MatchState.MISMATCH
                )
                outputs.append(
                    OutputReportItem(id=key, actual=act_val, expected=exp_val, match_state=match_st)
                )
            elif in_expected and not in_actual:
                outputs.append(
                    OutputReportItem(
                        id=key,
                        actual=None,
                        expected=expected_outputs[key],
                        match_state=MatchState.MISSING,
                    )
                )
            elif not in_expected and in_actual:
                act_val = result.actual_outputs[key]
                unexpected = complete_outputs or any(
                    f"unexpected actual output '{key}'" in d.message for d in norm_diags
                )
                outputs.append(
                    OutputReportItem(
                        id=key,
                        actual=act_val,
                        expected=None,
                        match_state=MatchState.UNEXPECTED if unexpected else MatchState.UNCHECKED,
                    )
                )
    else:
        mismatch_keys: set[str] = set()
        for d in norm_diags:
            if d.code == "WYS852":
                m = re.search(r"output mismatch for '([^']+)'", d.message)
                if m:
                    mismatch_keys.add(m.group(1))

        for key in sorted(result.actual_outputs.keys()):
            act_val = result.actual_outputs[key]
            match_st = (
                MatchState.MISMATCH
                if key in mismatch_keys
                else (MatchState.MATCH if result.success else MatchState.UNCHECKED)
            )
            outputs.append(
                OutputReportItem(id=key, actual=act_val, expected=None, match_state=match_st)
            )

    outputs.sort(key=lambda o: o.id)

    # 8. Assertions collection
    expected_assertions: dict[str, bool] | None = None
    if fixture is not None:
        exp = getattr(fixture, "expected", None)
        if exp is not None and hasattr(exp, "assertions") and exp.assertions is not None:
            expected_assertions = exp.assertions
        elif hasattr(fixture, "data") and isinstance(fixture.data, dict):
            raw_exp = fixture.data.get("expected")
            if isinstance(raw_exp, dict) and isinstance(raw_exp.get("assertions"), dict):
                expected_assertions = raw_exp["assertions"]

    assertions: list[AssertionReportItem] = []
    if expected_assertions is not None:
        all_assert_keys = sorted(
            set(expected_assertions.keys()) | set(result.actual_assertions.keys())
        )
        for key in all_assert_keys:
            exp_val = expected_assertions.get(key, True)
            if key in result.actual_assertions:
                act_val = result.actual_assertions[key]
                match_st = MatchState.MATCH if act_val == exp_val else MatchState.MISMATCH
                assertions.append(
                    AssertionReportItem(
                        id=key, actual=act_val, expected=exp_val, match_state=match_st
                    )
                )
            else:
                assertions.append(
                    AssertionReportItem(
                        id=key, actual=None, expected=exp_val, match_state=MatchState.MISSING
                    )
                )
    else:
        for key in sorted(result.actual_assertions.keys()):
            act_val = result.actual_assertions[key]
            match_st = MatchState.MATCH if act_val is True else MatchState.MISMATCH
            assertions.append(
                AssertionReportItem(id=key, actual=act_val, expected=True, match_state=match_st)
            )

    assertions.sort(key=lambda a: a.id)

    # 9. Traces
    traces: list[NodeExecutionTrace] = sorted(result.traces, key=lambda t: t.step)

    # 10. Baseline summary
    baseline = (
        _build_baseline_summary(baseline_comparison) if baseline_comparison is not None else None
    )

    if workflow_diff is None and baseline_comparison is not None:
        workflow_diff = getattr(baseline_comparison, "workflow_diff", None)

    # 11. Backwards compatibility copies
    actual_outputs = {k: result.actual_outputs[k] for k in sorted(result.actual_outputs.keys())}
    actual_assertions = {
        k: result.actual_assertions[k] for k in sorted(result.actual_assertions.keys())
    }

    return DeveloperReport(
        status=status,
        overall_status=overall_status,
        status_presentation=status_presentation,
        success=success,
        workflow=workflow_id,
        fixture=fixture_id_model,
        fixture_id=fix_id,
        workflow_fingerprint=result.workflow_fingerprint,
        validation=validation,
        execution=execution,
        outputs=outputs,
        assertions=assertions,
        diagnostics=norm_diags,
        traces=traces,
        actual_outputs=actual_outputs,
        actual_assertions=actual_assertions,
        baseline=baseline,
        workflow_diff=workflow_diff,
        policy=policy_result,
        gate=evaluate_gate(status, workflow_diff, policy_result=policy_result),
    )


build_report = build_developer_report


def _format_diagnostic_block(diag: NormalizedDiagnostic | Diagnostic) -> list[str]:
    """Format a single diagnostic as a concise, structured block."""
    lines = [f"✗ {diag.code}"]
    node_id = diag.node_id if isinstance(diag, NormalizedDiagnostic) else extract_node_id(diag)
    if node_id:
        lines.append(f"Node: {node_id}")
    if diag.location:
        lines.append(f"Location: {diag.location.file}:{diag.location.line}:{diag.location.column}")
    msg = diag.message
    if node_id:
        msg = re.sub(rf"\s+in node '{re.escape(node_id)}'", "", msg)
    lines.append(msg)
    if diag.hint:
        lines.append(f"  hint: {diag.hint}")
    return lines


def format_developer_report(report: DeveloperReport) -> str:
    """Format a DeveloperReport into a concise, deterministic human-readable report."""
    sections: list[str] = []

    # Header
    header_lines = [
        "WYSTERIA",
        "",
        f"Workflow: {report.workflow.display_name}",
        f"Fixture:  {report.fixture.display_name}",
    ]
    if report.workflow_fingerprint:
        header_lines.append(f"Fingerprint: {report.workflow_fingerprint}")
    sections.append("\n".join(header_lines))

    if report.status in {ReportStatus.PASSED, ReportStatus.PASS}:
        # Validation
        val_lines = [
            "Validation",
            "  ✓ Workflow valid",
            "  ✓ Fixture valid",
        ]
        sections.append("\n".join(val_lines))

        # Execution
        exec_lines = ["Execution"]
        if report.execution.expected_error_occurred and report.execution.expected_error_code:
            exec_lines.append(f"  ✓ Expected error {report.execution.expected_error_code} occurred")
        else:
            count = report.execution.total_nodes_executed
            unit = "node" if count == 1 else "nodes"
            exec_lines.append(f"  ✓ {count} {unit} evaluated")
        sections.append("\n".join(exec_lines))

        # Outputs
        if report.actual_outputs:
            out_lines = ["Outputs"]
            for key in sorted(report.actual_outputs.keys()):
                out_lines.append(f"  ✓ {key} = {_format_value(report.actual_outputs[key])}")
            sections.append("\n".join(out_lines))

        # Assertions
        if report.actual_assertions:
            assert_lines = ["Assertions"]
            for key in sorted(report.actual_assertions.keys()):
                assert_lines.append(f"  ✓ {key}")
            sections.append("\n".join(assert_lines))

        # Result
        sections.append("Result\n  ✓ PASS")

    elif report.status == ReportStatus.OUTPUT_MISMATCH:
        sections.append("Result\n  ✗ FAIL")
        mismatch_lines = ["OUTPUT_MISMATCH", ""]

        diff_found = False
        for item in report.outputs:
            if item.match_state == MatchState.MISMATCH:
                diff_found = True
                mismatch_lines.append(f"  {item.id}")
                mismatch_lines.append(f"    expected: {_format_value(item.expected)}")
                mismatch_lines.append(f"    actual:   {_format_value(item.actual)}")
            elif item.match_state == MatchState.MISSING:
                diff_found = True
                mismatch_lines.append(f"  {item.id}")
                mismatch_lines.append(f"    expected: {_format_value(item.expected)}")
                mismatch_lines.append("    actual:   <missing>")
            elif item.match_state == MatchState.UNEXPECTED:
                diff_found = True
                mismatch_lines.append(f"  {item.id}")
                mismatch_lines.append("    expected: <none>")
                mismatch_lines.append(f"    actual:   {_format_value(item.actual)}")

        if not diff_found and report.diagnostics:
            for diag in report.diagnostics:
                mismatch_lines.extend(_format_diagnostic_block(diag))

        sections.append("\n".join(mismatch_lines))

    elif report.status == ReportStatus.ASSERTION_FAILED:
        sections.append("Result\n  ✗ FAIL")
        assert_lines = ["ASSERTION_FAILED", ""]

        diff_found = False
        for item in report.assertions:
            if item.match_state == MatchState.MISMATCH:
                diff_found = True
                assert_lines.append(f"  {item.id}")
                assert_lines.append(f"    expected: {str(item.expected).lower()}")
                assert_lines.append(f"    actual:   {str(item.actual).lower()}")
            elif item.match_state == MatchState.MISSING:
                diff_found = True
                assert_lines.append(f"  {item.id}")
                assert_lines.append(f"    expected: {str(item.expected).lower()}")
                assert_lines.append("    actual:   <not found>")

        if not diff_found and report.diagnostics:
            for diag in report.diagnostics:
                assert_lines.extend(_format_diagnostic_block(diag))

        sections.append("\n".join(assert_lines))

    elif report.status == ReportStatus.REGRESSION:
        sections.append("Result\n  ✗ FAIL")
        reg_lines = ["REGRESSION", ""]
        if report.baseline:
            for entry in report.baseline.diff_entries:
                reg_lines.append(f"  {entry.category}: {entry.name} ({entry.kind})")
                if entry.message:
                    reg_lines.append(f"    {entry.message}")
            for reason in report.baseline.reasons:
                reg_lines.append(f"  reason: {reason}")
        sections.append("\n".join(reg_lines))

    else:
        # RUNTIME_ERROR, LIMIT_EXCEEDED, INVALID_WORKFLOW, INVALID_FIXTURE
        sections.append("Result\n  ✗ FAIL")
        cat_lines = [report.status.value, ""]
        if report.diagnostics:
            diag_blocks = []
            for diag in report.diagnostics:
                diag_blocks.append("\n".join(_format_diagnostic_block(diag)))
            cat_lines.append("\n\n".join(diag_blocks))
        sections.append("\n".join(cat_lines))

    if report.workflow_diff is not None and not report.workflow_diff.identical:
        sections.append(format_workflow_diff(report.workflow_diff))

    if report.policy is not None:
        policy_lines = ["Policy Evaluation"]
        if report.policy.passed:
            policy_lines.append("  ✓ PASS")
            if report.policy.policy_name:
                policy_lines.append(f"  Policy: {report.policy.policy_name}")
        else:
            policy_lines.append(f"  ✗ {report.policy.status.value}")
            if report.policy.policy_name:
                policy_lines.append(f"  Policy: {report.policy.policy_name}")
            for violation in report.policy.violations:
                node_part = f" [node: {violation.node_id}]" if violation.node_id else ""
                cap_part = f" [capability: {violation.capability}]" if violation.capability else ""
                policy_lines.append(
                    f"  ✗ {violation.code} ({violation.policy}){node_part}{cap_part}: {violation.message}"
                )
        sections.append("\n".join(policy_lines))

    if report.gate is not None:
        gate_lines = ["Gate Decision"]
        if report.gate.decision == GateDecision.PASS:
            gate_lines.append(f"  ✓ {report.gate.decision.value}")
        else:
            gate_lines.append(f"  ✗ {report.gate.decision.value}")
        for reason in report.gate.reasons:
            gate_lines.append(f"    - {reason}")
        sections.append("\n".join(gate_lines))

    return "\n\n".join(sections)


def format_policy_report(
    result: PolicyResult,
    *,
    workflow_display: str | None = None,
    policy_display: str | None = None,
) -> str:
    """Format a standalone PolicyResult into a deterministic human-readable string."""
    sections: list[str] = ["Wysteria Policy Check"]
    meta_lines: list[str] = []
    if workflow_display:
        meta_lines.append(f"Workflow: {workflow_display}")
    if policy_display:
        meta_lines.append(f"Policy: {policy_display}")
    elif result.policy_name:
        meta_lines.append(f"Policy: {result.policy_name}")
    if meta_lines:
        sections.append("\n".join(meta_lines))

    res_lines = ["Result"]
    if result.passed:
        res_lines.append("  ✓ PASS")
        res_lines.append("  All policy checks passed.")
    else:
        res_lines.append(f"  ✗ {result.status.value}")
    sections.append("\n".join(res_lines))

    if result.violations:
        viol_lines = ["Violations"]
        for v in result.violations:
            viol_lines.append(f"  ✗ {v.code} ({v.policy})")
            if v.node_id:
                viol_lines.append(f"    Node: {v.node_id}")
            if v.capability:
                viol_lines.append(f"    Capability: {v.capability}")
            if v.path:
                viol_lines.append(f"    Path: [{v.path}]")
            viol_lines.append(f"    {v.message}")
        sections.append("\n".join(viol_lines))

    return "\n\n".join(sections)


def format_report_json(report: DeveloperReport, *, indent: int = 2) -> str:
    """Serialize DeveloperReport to deterministic formatted JSON."""
    return report.to_json(indent=indent)
