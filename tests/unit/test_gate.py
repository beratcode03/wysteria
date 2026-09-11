from wysteria.diff.models import (
    ChangeCategory,
    DiffSeverity,
    DiffSummary,
    SemanticChange,
    WorkflowDiff,
)
from wysteria.reporting.gate import evaluate_gate
from wysteria.reporting.models import (
    DeveloperReport,
    ExecutionSummary,
    FixtureIdentity,
    GateDecision,
    ReportStatus,
    StatusBadge,
    StatusPresentation,
    ValidationSummary,
    WorkflowIdentity,
)


def make_report(status: ReportStatus, diff: WorkflowDiff | None = None) -> DeveloperReport:
    return DeveloperReport(
        status=status,
        overall_status=status,
        status_presentation=StatusPresentation(
            status=status,
            label=status.value,
            badge=StatusBadge.SUCCESS,
            passed=(status == ReportStatus.PASS),
        ),
        success=(status == ReportStatus.PASS),
        workflow=WorkflowIdentity(name="test"),
        fixture=FixtureIdentity(id="f1"),
        fixture_id="f1",
        validation=ValidationSummary(workflow_valid=True, fixture_valid=True),
        execution=ExecutionSummary(success=True),
        workflow_diff=diff,
    )


def test_unchanged_passing():
    diff = WorkflowDiff(identical=True)
    gate = evaluate_gate(ReportStatus.PASS, diff)
    assert gate.decision == GateDecision.PASS
    assert gate.reasons == ["passing verification"]


def test_informational_passing():
    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.NODE_ADDED,
                change_type="ADDED",
                severity=DiffSeverity.INFO,
                explanation="info",
            )
        ],
        summary=DiffSummary(total_changes=1, info_count=1),
    )
    gate = evaluate_gate(ReportStatus.PASS, diff)
    assert gate.decision == GateDecision.PASS


def test_breaking_passing():
    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.NODE_CHANGED,
                change_type="CHANGED",
                severity=DiffSeverity.BREAKING,
                explanation="breaking",
            )
        ],
        summary=DiffSummary(total_changes=1, breaking_count=1, has_breaking=True),
    )
    gate = evaluate_gate(ReportStatus.PASS, diff)
    assert gate.decision == GateDecision.FAIL
    assert "breaking semantic workflow changes" in gate.reasons


def test_output_mismatch():
    gate = evaluate_gate(ReportStatus.OUTPUT_MISMATCH, None)
    assert gate.decision == GateDecision.FAIL
    assert "output mismatch" in gate.reasons


def test_invalid_workflow():
    gate = evaluate_gate(ReportStatus.INVALID_WORKFLOW, None)
    assert gate.decision == GateDecision.FAIL
    assert "invalid workflow" in gate.reasons
