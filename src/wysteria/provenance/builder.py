"""Deterministic builder for Workflow Provenance and Explanations."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from wysteria.diff.models import DiffSeverity, WorkflowDiff
from wysteria.policy.models import PolicyResult
from wysteria.provenance.models import (
    CURRENT_PROVENANCE_VERSION,
    Explanation,
    ExplanationCategory,
    ExplanationItem,
    ExplanationSeverity,
    Provenance,
)
from wysteria.reporting.diagnostics import Severity
from wysteria.reporting.models import (
    AssertionReportItem,
    BaselineSummary,
    FixtureIdentity,
    GateDecision,
    GateSummary,
    MatchState,
    NormalizedDiagnostic,
    OutputReportItem,
    ReportStatus,
    WorkflowIdentity,
)

if TYPE_CHECKING:
    pass


_SEVERITY_ORDER: dict[ExplanationSeverity, int] = {
    ExplanationSeverity.BLOCK: 0,
    ExplanationSeverity.BREAKING: 1,
    ExplanationSeverity.FAIL: 2,
    ExplanationSeverity.WARNING: 3,
    ExplanationSeverity.INFO: 4,
    ExplanationSeverity.PASS: 5,
}


def explanation_item_sort_key(item: ExplanationItem) -> tuple:
    """Stable, deterministic sort key for explanation items."""
    sev_rank = _SEVERITY_ORDER.get(item.severity, 99)
    return (
        sev_rank,
        item.code or "",
        item.category,
        item.node_id or "",
        item.target or "",
        item.path or "",
        item.message,
    )


def _extract_output_target_and_message(diag: NormalizedDiagnostic) -> tuple[str | None, str]:
    """Extract clean target output name and concise message from an output diagnostic."""
    m_mismatch = re.search(r"output mismatch for '([^']+)'", diag.message)
    if m_mismatch:
        return m_mismatch.group(1), "output mismatch"
    m_missing = re.search(r"missing actual output '([^']+)'", diag.message)
    if m_missing:
        return m_missing.group(1), "missing actual output"
    m_unexpected = re.search(r"unexpected actual output '([^']+)'", diag.message)
    if m_unexpected:
        return m_unexpected.group(1), "unexpected actual output"

    target = None
    if diag.path and diag.path.startswith(("/outputs/", "/expected/outputs/")):
        target = diag.path.strip("/").split("/")[-1]
    return target, diag.message


def _extract_assertion_target(diag: NormalizedDiagnostic) -> str | None:
    """Extract target assertion name from an assertion diagnostic."""
    m = re.search(r"assertion '([^']+)'", diag.message)
    if m:
        return m.group(1)
    if diag.path and diag.path.startswith(("/assertions/", "/expected/assertions/")):
        return diag.path.strip("/").split("/")[-1]
    return None


def generate_explanations(
    *,
    gate_decision: GateDecision,
    status: ReportStatus,
    diagnostics: list[NormalizedDiagnostic] | None = None,
    outputs: list[OutputReportItem] | None = None,
    assertions: list[AssertionReportItem] | None = None,
    baseline_summary: BaselineSummary | None = None,
    workflow_diff: WorkflowDiff | None = None,
    policy_result: PolicyResult | None = None,
) -> list[ExplanationItem]:
    """Generate deterministic, structured explanation items from verification and governance artifacts."""
    reasons: list[ExplanationItem] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_item(item: ExplanationItem) -> None:
        key = (
            item.severity.value,
            item.code or "",
            item.node_id or item.target or "",
            item.message,
        )
        if key not in seen:
            seen.add(key)
            reasons.append(item)

    # 1. Policy Violations -> BLOCK
    if policy_result is not None and not policy_result.passed:
        for v in policy_result.violations:
            add_item(
                ExplanationItem(
                    severity=ExplanationSeverity.BLOCK,
                    category=ExplanationCategory.POLICY.value,
                    source=ExplanationCategory.POLICY.value,
                    code=v.code,
                    message=v.message,
                    node_id=v.node_id,
                    target=v.capability or v.node_id,
                    path=v.path,
                )
            )

    # 2. Semantic Workflow Changes -> BREAKING / WARNING
    if workflow_diff is not None and not workflow_diff.identical:
        for change in workflow_diff.changes:
            if change.severity == DiffSeverity.BREAKING:
                add_item(
                    ExplanationItem(
                        severity=ExplanationSeverity.BREAKING,
                        category=ExplanationCategory.SEMANTIC.value,
                        source=ExplanationCategory.SEMANTIC.value,
                        code=None,
                        message=change.explanation,
                        node_id=change.node_id,
                        target=change.target_id,
                        path=change.path,
                    )
                )
            elif change.severity == DiffSeverity.WARNING and gate_decision != GateDecision.PASS:
                add_item(
                    ExplanationItem(
                        severity=ExplanationSeverity.WARNING,
                        category=ExplanationCategory.SEMANTIC.value,
                        source=ExplanationCategory.SEMANTIC.value,
                        code=None,
                        message=change.explanation,
                        node_id=change.node_id,
                        target=change.target_id,
                        path=change.path,
                    )
                )

    # 3. Output Mismatches -> FAIL
    diags = diagnostics or []
    output_diags = [d for d in diags if d.code == "WYS852"]
    reported_output_targets: set[str] = set()

    for d in output_diags:
        target, msg = _extract_output_target_and_message(d)
        if target:
            reported_output_targets.add(target)
        add_item(
            ExplanationItem(
                severity=ExplanationSeverity.FAIL,
                category=ExplanationCategory.OUTPUT.value,
                source=ExplanationCategory.OUTPUT.value,
                code=d.code,
                message=msg,
                node_id=d.node_id,
                target=target,
                path=d.path,
            )
        )

    if outputs is not None:
        for out in outputs:
            if out.match_state in {MatchState.MISMATCH, MatchState.MISSING, MatchState.UNEXPECTED}:
                if out.id not in reported_output_targets:
                    msg = "output mismatch"
                    if out.match_state == MatchState.MISSING:
                        msg = "missing actual output"
                    elif out.match_state == MatchState.UNEXPECTED:
                        msg = "unexpected actual output"
                    add_item(
                        ExplanationItem(
                            severity=ExplanationSeverity.FAIL,
                            category=ExplanationCategory.OUTPUT.value,
                            source=ExplanationCategory.OUTPUT.value,
                            code="WYS852",
                            message=msg,
                            target=out.id,
                            path=f"/outputs/{out.id}",
                        )
                    )

    # 4. Assertion Failures -> FAIL
    assertion_diags = [d for d in diags if d.code in {"WYS850", "WYS851"}]
    reported_assert_targets: set[str] = set()

    for d in assertion_diags:
        target = _extract_assertion_target(d)
        if target:
            reported_assert_targets.add(target)
        add_item(
            ExplanationItem(
                severity=ExplanationSeverity.FAIL,
                category=ExplanationCategory.ASSERTION.value,
                source=ExplanationCategory.ASSERTION.value,
                code=d.code,
                message=d.message,
                node_id=d.node_id,
                target=target,
                path=d.path,
            )
        )

    if assertions is not None:
        for a in assertions:
            if a.match_state in {MatchState.MISMATCH, MatchState.MISSING}:
                if a.id not in reported_assert_targets:
                    add_item(
                        ExplanationItem(
                            severity=ExplanationSeverity.FAIL,
                            category=ExplanationCategory.ASSERTION.value,
                            source=ExplanationCategory.ASSERTION.value,
                            code="WYS850",
                            message=f"assertion '{a.id}' failed",
                            target=a.id,
                            path=f"/assertions/{a.id}",
                        )
                    )

    # 5. Runtime Failures -> FAIL
    runtime_diags = [
        d
        for d in diags
        if d.code in {"WYS800", "WYS801", "WYS802", "WYS803", "WYS853"}
        or (d.code.startswith("WYS8") and d.code not in {"WYS850", "WYS851", "WYS852"})
    ]
    for d in runtime_diags:
        add_item(
            ExplanationItem(
                severity=ExplanationSeverity.FAIL,
                category=ExplanationCategory.RUNTIME.value,
                source=ExplanationCategory.RUNTIME.value,
                code=d.code,
                message=d.message,
                node_id=d.node_id,
                path=d.path,
            )
        )

    # 6. Validation Failures -> FAIL
    val_codes = {"WYS1", "WYS2", "WYS3", "WYS4", "WYS5", "WYS7"}
    val_diags = [
        d
        for d in diags
        if any(d.code.startswith(prefix) for prefix in val_codes)
        and not (450 <= int(d.code[3:]) <= 460 if d.code[3:].isdigit() else False)
        and d.severity == Severity.ERROR
    ]
    for d in val_diags:
        add_item(
            ExplanationItem(
                severity=ExplanationSeverity.FAIL,
                category=ExplanationCategory.VALIDATION.value,
                source=ExplanationCategory.VALIDATION.value,
                code=d.code,
                message=d.message,
                node_id=d.node_id,
                path=d.path,
            )
        )

    # 7. Regression Mismatches -> FAIL
    if baseline_summary is not None and not baseline_summary.matches:
        for entry in baseline_summary.diff_entries:
            msg = entry.message or f"diff in {entry.category}.{entry.name}"
            if not msg.lower().startswith("baseline"):
                msg = f"baseline regression: {msg}"
            add_item(
                ExplanationItem(
                    severity=ExplanationSeverity.FAIL,
                    category=ExplanationCategory.REGRESSION.value,
                    source=ExplanationCategory.REGRESSION.value,
                    code=None,
                    message=msg,
                    target=entry.name,
                    path=f"/{entry.category}/{entry.name}",
                )
            )
        if not baseline_summary.diff_entries and baseline_summary.reasons:
            for r in baseline_summary.reasons:
                add_item(
                    ExplanationItem(
                        severity=ExplanationSeverity.FAIL,
                        category=ExplanationCategory.REGRESSION.value,
                        source=ExplanationCategory.REGRESSION.value,
                        code=None,
                        message=r,
                    )
                )

    # 8. Fallback / Gate-Level Explanations
    if not reasons:
        if gate_decision == GateDecision.PASS:
            add_item(
                ExplanationItem(
                    severity=ExplanationSeverity.PASS,
                    category=ExplanationCategory.GATE.value,
                    source=ExplanationCategory.GATE.value,
                    code=None,
                    message="passing verification",
                )
            )
        elif gate_decision == GateDecision.BLOCK:
            add_item(
                ExplanationItem(
                    severity=ExplanationSeverity.BLOCK,
                    category=ExplanationCategory.GATE.value,
                    source=ExplanationCategory.GATE.value,
                    code=None,
                    message="workflow blocked by policy",
                )
            )
        else:
            add_item(
                ExplanationItem(
                    severity=ExplanationSeverity.FAIL,
                    category=ExplanationCategory.GATE.value,
                    source=ExplanationCategory.GATE.value,
                    code=None,
                    message="verification failed",
                )
            )

    reasons.sort(key=explanation_item_sort_key)
    return reasons


def build_provenance(
    *,
    workflow_id: WorkflowIdentity,
    fixture_id: FixtureIdentity,
    status: ReportStatus,
    workflow_fingerprint: str | None = None,
    diagnostics: list[NormalizedDiagnostic] | None = None,
    outputs: list[OutputReportItem] | None = None,
    assertions: list[AssertionReportItem] | None = None,
    baseline_summary: BaselineSummary | None = None,
    workflow_diff: WorkflowDiff | None = None,
    policy_result: PolicyResult | None = None,
    gate_summary: GateSummary | None = None,
) -> Provenance:
    """Build a deterministic, versioned Provenance model capturing full verification lineage."""
    if gate_summary is None:
        from wysteria.reporting.gate import evaluate_gate

        gate_summary = evaluate_gate(
            status, workflow_diff=workflow_diff, policy_result=policy_result
        )

    decision = gate_summary.decision

    reasons = generate_explanations(
        gate_decision=decision,
        status=status,
        diagnostics=diagnostics,
        outputs=outputs,
        assertions=assertions,
        baseline_summary=baseline_summary,
        workflow_diff=workflow_diff,
        policy_result=policy_result,
    )

    explanation = Explanation(
        decision=decision,
        reasons=reasons,
        fingerprint=workflow_fingerprint,
        summary=f"Decision: {decision.value}",
    )

    semantic_changes = workflow_diff.changes if workflow_diff is not None else []
    policy_violations = policy_result.violations if policy_result is not None else []

    reg_outcome: str | None = None
    if baseline_summary is not None:
        reg_outcome = baseline_summary.status

    return Provenance(
        provenance_version=CURRENT_PROVENANCE_VERSION,
        workflow=workflow_id,
        workflow_fingerprint=workflow_fingerprint,
        fixture=fixture_id,
        verification_outcome=status.value,
        regression_outcome=reg_outcome,
        semantic_changes=list(semantic_changes),
        policy_violations=list(policy_violations),
        gate_decision=decision,
        decision=decision,
        reasons=reasons,
        explanation=explanation,
    )
