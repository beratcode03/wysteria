"""Deterministic verification report formatting for CLI and CI."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from wysteria.reporting.builder import (
    build_developer_report,
    format_developer_report,
)
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.reporting.models import DeveloperReport
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
    match = re.search(r"(?:node|AssertNode)\s+'([^']+)'", diag.message, re.IGNORECASE)
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


def format_verification_json(result: VerificationResult | DeveloperReport) -> str:
    """Serialize VerificationResult or DeveloperReport to deterministic formatted JSON."""
    if isinstance(result, DeveloperReport):
        return result.to_json()
    report = build_developer_report(result)
    return report.to_json()


def format_verification_report(
    result: VerificationResult | DeveloperReport,
    workflow_display: str = "",
    fixture_display: str = "",
    parsed_fixture: ParsedFixture | None = None,
) -> str:
    """Format a VerificationResult or DeveloperReport into a concise, deterministic human-readable report."""
    if isinstance(result, DeveloperReport):
        return format_developer_report(result)
    report = build_developer_report(
        result,
        fixture=parsed_fixture,
        workflow_display=workflow_display,
        fixture_display=fixture_display,
    )
    return format_developer_report(report)
