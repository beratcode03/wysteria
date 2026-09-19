from wysteria.diff.models import (
    ChangeCategory,
    DiffSeverity,
    DiffSummary,
    SemanticChange,
    WorkflowDiff,
)
from wysteria.evidence.models import EvidenceResult, EvidenceStatus
from wysteria.policy.models import Policy
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


def test_change_policy_allowed():
    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.CLAIM_ADDED,
                change_type="ADDED",
                severity=DiffSeverity.INFO,
                explanation="claim added",
            )
        ],
        summary=DiffSummary(total_changes=1, info_count=1),
    )
    policy = Policy(allowed_change_categories=[ChangeCategory.CLAIM_ADDED])
    gate = evaluate_gate(ReportStatus.PASS, diff, policy=policy)
    assert gate.decision == GateDecision.PASS


def test_change_policy_forbidden():
    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.NODE_ADDED,
                change_type="ADDED",
                severity=DiffSeverity.INFO,
                explanation="node added",
            )
        ],
        summary=DiffSummary(total_changes=1, info_count=1),
    )
    policy = Policy(forbidden_change_categories=[ChangeCategory.NODE_ADDED])
    gate = evaluate_gate(ReportStatus.PASS, diff, policy=policy)
    assert gate.decision == GateDecision.FAIL
    assert "change category 'NODE_ADDED' is explicitly forbidden by policy" in gate.reasons


def test_change_policy_not_allowed():
    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.CLAIM_CHANGED,
                change_type="CHANGED",
                severity=DiffSeverity.INFO,
                explanation="claim changed",
            )
        ],
        summary=DiffSummary(total_changes=1, info_count=1),
    )
    policy = Policy(allowed_change_categories=[ChangeCategory.NODE_ADDED])
    gate = evaluate_gate(ReportStatus.PASS, diff, policy=policy)
    assert gate.decision == GateDecision.FAIL
    assert "change category 'CLAIM_CHANGED' is not explicitly allowed by policy" in gate.reasons


def test_evidence_results_in_gate():
    diff = WorkflowDiff(identical=True)
    ev_verified = EvidenceResult(claim_id="c1", status=EvidenceStatus.VERIFIED)
    ev_failed = EvidenceResult(claim_id="c2", status=EvidenceStatus.FAILED)
    ev_blocked = EvidenceResult(claim_id="c3", status=EvidenceStatus.BLOCKED)
    ev_needs = EvidenceResult(claim_id="c4", status=EvidenceStatus.NEEDS_EVIDENCE)
    ev_unv = EvidenceResult(claim_id="c5", status=EvidenceStatus.UNVERIFIABLE)

    gate = evaluate_gate(ReportStatus.PASS, diff, evidence_results=[ev_verified])
    assert gate.decision == GateDecision.PASS

    gate_failed = evaluate_gate(ReportStatus.PASS, diff, evidence_results=[ev_failed])
    assert gate_failed.decision == GateDecision.FAIL
    assert "evidence claim 'c2' is failed" in gate_failed.reasons

    gate_blocked = evaluate_gate(ReportStatus.PASS, diff, evidence_results=[ev_blocked])
    assert gate_blocked.decision == GateDecision.BLOCK
    assert "evidence claim 'c3' blocked by policy" in gate_blocked.reasons

    gate_needs = evaluate_gate(ReportStatus.PASS, diff, evidence_results=[ev_needs])
    assert gate_needs.decision == GateDecision.FAIL

    gate_unv = evaluate_gate(ReportStatus.PASS, diff, evidence_results=[ev_unv])
    assert gate_unv.decision == GateDecision.FAIL
