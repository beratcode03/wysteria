"""Deterministic verification report formatting for CLI and CI."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from wysteria.reporting.diagnostics import Diagnostic
from wysteria.verification.evaluator import strict_equals
from wysteria.verification.models import VerificationResult, VerificationStatus

if TYPE_CHECKING:
    from wysteria.fixtures.parser import ParsedFixture


EXIT_CODES: dict[VerificationStatus, int] = {
    VerificationStatus.PASSED: 0,
    VerificationStatus.OUTPUT_MISMATCH: 1,
    VerificationStatus.ASSERTION_FAILED: 1,
    VerificationStatus.INVALID_WORKFLOW: 2,
    VerificationStatus.INVALID_FIXTURE: 3,
    VerificationStatus.RUNTIME_ERROR: 4,
    VerificationStatus.LIMIT_EXCEEDED: 4,
}


def _extract_node_id(diag: Diagnostic) -> str | None:
    """Extract node ID from diagnostic path or message."""
    if diag.path:
        parts = diag.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "nodes" and not parts[1].isdigit():
            return parts[1]
    match = re.search(r"node '([^']+)'", diag.message)
    if match:
        return match.group(1)
    return None


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


def format_verification_json(result: VerificationResult) -> str:
    """Serialize VerificationResult to deterministic formatted JSON."""
    data = result.model_dump(mode="json")
    return json.dumps(data, indent=2, sort_keys=True)


def _format_diagnostic_block(diag: Diagnostic) -> list[str]:
    """Format a single diagnostic as a concise, structured block."""
    lines = [f"✗ {diag.code}"]
    node_id = _extract_node_id(diag)
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


def format_verification_report(
    result: VerificationResult,
    workflow_display: str,
    fixture_display: str,
    parsed_fixture: ParsedFixture | None = None,
) -> str:
    """Format a VerificationResult into a concise, deterministic human-readable report."""
    sections: list[str] = []

    # Header
    header_lines = [
        "WYSTERIA",
        "",
        f"Workflow: {workflow_display}",
        f"Fixture:  {fixture_display}",
    ]
    sections.append("\n".join(header_lines))

    if result.status == VerificationStatus.PASSED:
        # Validation
        val_lines = [
            "Validation",
            "  ✓ Workflow valid",
            "  ✓ Fixture valid",
        ]
        sections.append("\n".join(val_lines))

        # Execution
        exec_lines = ["Execution"]
        expected_err = None
        if parsed_fixture and isinstance(parsed_fixture.data, dict):
            exp = parsed_fixture.data.get("expected")
            if isinstance(exp, dict) and "error" in exp:
                err_val = exp["error"]
                expected_err = err_val.get("code") if isinstance(err_val, dict) else str(err_val)

        if expected_err:
            exec_lines.append(f"  ✓ Expected error {expected_err} occurred")
        else:
            count = len(result.traces)
            unit = "node" if count == 1 else "nodes"
            exec_lines.append(f"  ✓ {count} {unit} evaluated")
        sections.append("\n".join(exec_lines))

        # Outputs
        if result.actual_outputs:
            out_lines = ["Outputs"]
            for key in sorted(result.actual_outputs.keys()):
                out_lines.append(f"  ✓ {key} = {_format_value(result.actual_outputs[key])}")
            sections.append("\n".join(out_lines))

        # Assertions
        if result.actual_assertions:
            assert_lines = ["Assertions"]
            for key in sorted(result.actual_assertions.keys()):
                assert_lines.append(f"  ✓ {key}")
            sections.append("\n".join(assert_lines))

        # Result
        sections.append("Result\n  ✓ PASS")

    elif result.status == VerificationStatus.OUTPUT_MISMATCH:
        sections.append("Result\n  ✗ FAIL")
        mismatch_lines = ["OUTPUT_MISMATCH", ""]

        expected_outputs = {}
        if parsed_fixture and isinstance(parsed_fixture.data, dict):
            exp = parsed_fixture.data.get("expected")
            if isinstance(exp, dict) and isinstance(exp.get("outputs"), dict):
                expected_outputs = exp["outputs"]

        actual_outputs = result.actual_outputs
        all_keys = sorted(set(expected_outputs.keys()) | set(actual_outputs.keys()))
        diff_found = False

        for k in all_keys:
            if k in expected_outputs and k in actual_outputs:
                if not strict_equals(expected_outputs[k], actual_outputs[k]):
                    diff_found = True
                    mismatch_lines.append(f"  {k}")
                    mismatch_lines.append(f"    expected: {_format_value(expected_outputs[k])}")
                    mismatch_lines.append(f"    actual:   {_format_value(actual_outputs[k])}")
            elif k in expected_outputs and k not in actual_outputs:
                diff_found = True
                mismatch_lines.append(f"  {k}")
                mismatch_lines.append(f"    expected: {_format_value(expected_outputs[k])}")
                mismatch_lines.append("    actual:   <missing>")
            elif k not in expected_outputs and k in actual_outputs:
                if any(f"unexpected actual output '{k}'" in d.message for d in result.diagnostics):
                    diff_found = True
                    mismatch_lines.append(f"  {k}")
                    mismatch_lines.append("    expected: <none>")
                    mismatch_lines.append(f"    actual:   {_format_value(actual_outputs[k])}")

        if not diff_found and result.diagnostics:
            for diag in result.diagnostics:
                mismatch_lines.extend(_format_diagnostic_block(diag))

        sections.append("\n".join(mismatch_lines))

    elif result.status == VerificationStatus.ASSERTION_FAILED:
        sections.append("Result\n  ✗ FAIL")
        assert_lines = ["ASSERTION_FAILED", ""]

        expected_assertions = {}
        if parsed_fixture and isinstance(parsed_fixture.data, dict):
            exp = parsed_fixture.data.get("expected")
            if isinstance(exp, dict) and isinstance(exp.get("assertions"), dict):
                expected_assertions = exp["assertions"]

        diff_found = False
        all_targets = sorted(set(expected_assertions.keys()) | set(result.actual_assertions.keys()))
        for target in all_targets:
            exp_val = expected_assertions.get(target, True)
            if target in result.actual_assertions:
                act_val = result.actual_assertions[target]
                if act_val != exp_val:
                    diff_found = True
                    assert_lines.append(f"  {target}")
                    assert_lines.append(f"    expected: {str(exp_val).lower()}")
                    assert_lines.append(f"    actual:   {str(act_val).lower()}")
            else:
                diff_found = True
                assert_lines.append(f"  {target}")
                assert_lines.append(f"    expected: {str(exp_val).lower()}")
                assert_lines.append("    actual:   <not found>")

        if not diff_found and result.diagnostics:
            for diag in result.diagnostics:
                assert_lines.extend(_format_diagnostic_block(diag))

        sections.append("\n".join(assert_lines))

    else:
        # RUNTIME_ERROR, LIMIT_EXCEEDED, INVALID_WORKFLOW, INVALID_FIXTURE
        sections.append("Result\n  ✗ FAIL")
        cat_lines = [result.status.value, ""]
        if result.diagnostics:
            diag_blocks = []
            for diag in result.diagnostics:
                diag_blocks.append("\n".join(_format_diagnostic_block(diag)))
            cat_lines.append("\n\n".join(diag_blocks))
        sections.append("\n".join(cat_lines))

    return "\n\n".join(sections)
