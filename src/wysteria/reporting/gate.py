"""Deterministic change gating logic."""

from __future__ import annotations

from wysteria.diff.models import DiffSeverity, WorkflowDiff
from wysteria.reporting.models import GateDecision, GateSummary, ReportStatus


def evaluate_gate(status: ReportStatus, workflow_diff: WorkflowDiff | None) -> GateSummary:
    """
    Evaluate whether a changed workflow is safe to accept based on its verification report.
    Returns a deterministic PASS/FAIL decision with sorted reasons.
    """
    reasons: list[str] = []

    # Check verification status first
    if status == ReportStatus.INVALID_WORKFLOW:
        reasons.append("invalid workflow")
    elif status == ReportStatus.INVALID_FIXTURE:
        reasons.append("invalid fixture")
    elif status == ReportStatus.ASSERTION_FAILED:
        reasons.append("assertion failure")
    elif status == ReportStatus.OUTPUT_MISMATCH:
        reasons.append("output mismatch")
    elif status == ReportStatus.REGRESSION:
        reasons.append("regression")
    elif status != ReportStatus.PASS and status != ReportStatus.PASSED:
        # Catch any other failures
        reasons.append("verification failed")

    # Check semantic diff
    if workflow_diff is not None:
        if workflow_diff.summary.has_breaking:
            reasons.append("breaking semantic workflow changes")
        elif not workflow_diff.identical:
            # Check if there are changes other than INFO
            # "informational-only workflow changes + passing verification => PASS"
            has_non_info = False
            for change in workflow_diff.changes:
                if change.severity not in (DiffSeverity.INFO, DiffSeverity.BREAKING):
                    has_non_info = True
                    break
            if has_non_info:
                reasons.append("non-informational workflow changes")

    if reasons:
        return GateSummary(decision=GateDecision.FAIL, reasons=sorted(reasons))

    return GateSummary(decision=GateDecision.PASS, reasons=["passing verification"])
