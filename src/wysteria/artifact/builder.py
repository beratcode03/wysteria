"""Deterministic builder for CI Artifacts reusing existing reporting and provenance models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wysteria.artifact.models import CURRENT_ARTIFACT_VERSION, CIArtifact
from wysteria.provenance.builder import build_provenance
from wysteria.reporting.builder import build_developer_report
from wysteria.reporting.gate import evaluate_gate
from wysteria.reporting.models import (
    DeveloperReport,
    FixtureIdentity,
    GateDecision,
    WorkflowIdentity,
)

if TYPE_CHECKING:
    from wysteria.baselines.models import BaselineComparison
    from wysteria.diff.models import WorkflowDiff
    from wysteria.fixtures.models import Fixture
    from wysteria.fixtures.parser import ParsedFixture
    from wysteria.ir.models import Workflow
    from wysteria.ir.parser import ParsedWorkflow
    from wysteria.policy.models import PolicyResult
    from wysteria.verification.models import VerificationResult


from pathlib import Path


def _clean_path(path_str: str | None) -> str:
    if not path_str:
        return ""
    p_str = path_str.replace("\\", "/")
    try:
        p = Path(path_str)
        if p.is_absolute():
            cwd = Path.cwd()
            if p.is_relative_to(cwd):
                return p.relative_to(cwd).as_posix()
    except Exception:
        pass
    return p_str


def build_ci_artifact(
    report: DeveloperReport | None = None,
    *,
    result: VerificationResult | None = None,
    workflow: Workflow | ParsedWorkflow | None = None,
    fixture: Fixture | ParsedFixture | None = None,
    workflow_display: str | None = None,
    fixture_display: str | None = None,
    baseline_comparison: BaselineComparison | None = None,
    workflow_diff: WorkflowDiff | None = None,
    policy_result: PolicyResult | None = None,
) -> CIArtifact:
    """Build a versioned, machine-readable CI artifact representing the complete verification decision."""
    cleaned_wf_disp = _clean_path(workflow_display) if workflow_display else None
    cleaned_fix_disp = _clean_path(fixture_display) if fixture_display else None

    if report is None:
        if result is None:
            raise ValueError("either 'report' or 'result' must be provided to build_ci_artifact")
        report = build_developer_report(
            result,
            workflow=workflow,
            fixture=fixture,
            workflow_display=cleaned_wf_disp,
            fixture_display=cleaned_fix_disp,
            baseline_comparison=baseline_comparison,
            workflow_diff=workflow_diff,
            policy_result=policy_result,
        )

    # Normalize paths on workflow and fixture identity
    norm_wf = WorkflowIdentity(
        name=report.workflow.name,
        fingerprint=report.workflow.fingerprint,
        display_name=_clean_path(report.workflow.display_name),
    )
    norm_fix = FixtureIdentity(
        id=report.fixture.id,
        name=report.fixture.name,
        display_name=_clean_path(report.fixture.display_name),
    )

    prov = report.provenance
    if prov is None:
        gate_sum = report.gate or evaluate_gate(
            report.status,
            workflow_diff=report.workflow_diff,
            policy_result=report.policy,
        )
        prov = build_provenance(
            workflow_id=norm_wf,
            fixture_id=norm_fix,
            status=report.status,
            workflow_fingerprint=report.workflow_fingerprint,
            diagnostics=report.diagnostics,
            outputs=report.outputs,
            assertions=report.assertions,
            baseline_summary=report.baseline,
            workflow_diff=report.workflow_diff,
            policy_result=report.policy,
            gate_summary=gate_sum,
        )

    gate_dec = (
        report.gate.decision
        if report.gate is not None
        else (prov.gate_decision if prov is not None else GateDecision.FAIL)
    )

    reasons = list(report.reasons or (prov.reasons if prov is not None else []))
    expl = report.explanation or (prov.explanation if prov is not None else None)

    # Reconstruct developer_report with normalized identities and provenance
    norm_report = report.model_copy(
        update={
            "workflow": norm_wf,
            "fixture": norm_fix,
            "provenance": prov,
        }
    )

    return CIArtifact(
        artifact_version=CURRENT_ARTIFACT_VERSION,
        schema_version=CURRENT_ARTIFACT_VERSION,
        gate_decision=gate_dec,
        workflow_fingerprint=report.workflow_fingerprint,
        workflow=norm_wf,
        fixture=norm_fix,
        developer_report=norm_report,
        provenance=prov,
        baseline=report.baseline,
        semantic_diff=report.workflow_diff,
        policy=report.policy,
        explanation=expl,
        reasons=reasons,
    )
