"""Comprehensive unit tests for Phase 7: Workflow Provenance & Explainability."""

import json

from wysteria.api import (
    CURRENT_PROVENANCE_VERSION,
    ChangeCategory,
    DeveloperReport,
    DiagnosticCategory,
    ExplanationItem,
    ExplanationSeverity,
    GateDecision,
    MatchState,
    NormalizedDiagnostic,
    OutputReportItem,
    Policy,
    PolicyResult,
    PolicyRule,
    PolicyStatus,
    PolicyViolation,
    Provenance,
    ReportStatus,
    Severity,
    WorkflowDiff,
    WorkflowIdentity,
    WorkflowProvenance,
    build_developer_report,
    build_provenance,
    evaluate_policy,
    explanation_item_sort_key,
    format_explanation_human,
    format_github_annotations,
    format_provenance_json,
    parse_fixture,
    parse_workflow,
    validate_workflow,
    verify_fixture,
)
from wysteria.diff.models import DiffSeverity, DiffSummary, SemanticChange
from wysteria.ir.models import Capability
from wysteria.reporting.models import FixtureIdentity
from wysteria.validation.capabilities import CapabilityPolicy

SAMPLE_PASS_WF = """ir_version: 1
name: test_pass
inputs:
  val:
    type: string
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config:
      value: "hello"
    output_type: string
edges: []
capabilities: []
assertions: []
outputs:
  out:
    source: {node: n1}
    type: string
"""

SAMPLE_PASS_FIXTURE = """fixture_version: 1
id: fix_pass
inputs:
  val: "any"
expected:
  outputs:
    out: "hello"
"""

SAMPLE_FAIL_FIXTURE = """fixture_version: 1
id: fix_fail
inputs:
  val: "any"
expected:
  outputs:
    out: "world"
"""

SAMPLE_POLICY_FORBIDDEN = """policy_version: 1
name: block_policy
forbidden_capabilities:
  - network.http
"""

SAMPLE_CAPABILITY_WF = """ir_version: 1
name: test_cap
inputs: {}
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config:
      value: 1
    output_type: integer
edges: []
capabilities:
  - network.http
assertions: []
outputs: {}
"""


def test_provenance_model_basics():
    """Verify strict, versioned Provenance and WorkflowProvenance model properties."""
    wf_id = WorkflowIdentity(name="test_flow", fingerprint="abcd1234", display_name="test_flow")
    fix_id = FixtureIdentity(id="fix_1", name="fixture 1", display_name="fix_1")

    prov = Provenance(
        workflow=wf_id,
        workflow_fingerprint="abcd1234",
        fixture=fix_id,
        verification_outcome="PASS",
        gate_decision=GateDecision.PASS,
        decision=GateDecision.PASS,
    )

    assert prov.provenance_version == CURRENT_PROVENANCE_VERSION
    assert prov.workflow.name == "test_flow"
    assert prov.workflow_fingerprint == "abcd1234"
    assert prov.fixture.id == "fix_1"
    assert prov.verification_outcome == "PASS"
    assert prov.regression_outcome is None
    assert prov.semantic_changes == []
    assert prov.policy_violations == []
    assert prov.gate_decision == GateDecision.PASS
    assert prov.decision == GateDecision.PASS
    assert prov.reasons == []
    assert prov.explanations == []
    assert WorkflowProvenance is Provenance


def test_explanation_item_sort_key():
    """Verify deterministic ordering: BLOCK, BREAKING, FAIL, WARNING, INFO, PASS."""
    item_pass = ExplanationItem(
        severity=ExplanationSeverity.PASS,
        category="gate",
        source="gate",
        message="passing verification",
    )
    item_info = ExplanationItem(
        severity=ExplanationSeverity.INFO,
        category="semantic",
        source="semantic",
        message="description updated",
    )
    item_warning = ExplanationItem(
        severity=ExplanationSeverity.WARNING,
        category="semantic",
        source="semantic",
        message="node config modified",
    )
    item_fail = ExplanationItem(
        severity=ExplanationSeverity.FAIL,
        category="output",
        source="output",
        code="WYS852",
        message="output mismatch",
        target="result",
    )
    item_breaking = ExplanationItem(
        severity=ExplanationSeverity.BREAKING,
        category="semantic",
        source="semantic",
        message="output type changed",
        target="result",
    )
    item_block = ExplanationItem(
        severity=ExplanationSeverity.BLOCK,
        category="policy",
        source="policy",
        code="WYS453",
        message='forbidden capability "network"',
        node_id="fetch_data",
    )

    items = [item_pass, item_info, item_warning, item_fail, item_breaking, item_block]
    items.sort(key=explanation_item_sort_key)

    assert items[0].severity == ExplanationSeverity.BLOCK
    assert items[1].severity == ExplanationSeverity.BREAKING
    assert items[2].severity == ExplanationSeverity.FAIL
    assert items[3].severity == ExplanationSeverity.WARNING
    assert items[4].severity == ExplanationSeverity.INFO
    assert items[5].severity == ExplanationSeverity.PASS


def test_pass_explanation_and_human_formatting():
    """Verify explanation generation and human formatting for a passing workflow."""
    wf = parse_workflow(SAMPLE_PASS_WF, filename="workflow.yaml")
    fix = parse_fixture(SAMPLE_PASS_FIXTURE, filename="fixture.yaml")
    res = verify_fixture(wf, fix)
    report = build_developer_report(res, workflow=wf, fixture=fix)

    prov = report.provenance
    assert prov is not None
    assert prov.gate_decision == GateDecision.PASS
    assert len(prov.reasons) == 1
    assert prov.reasons[0].severity == ExplanationSeverity.PASS
    assert prov.reasons[0].message == "passing verification"

    human_txt = format_explanation_human(prov)
    assert "DECISION: PASS" in human_txt
    assert "Reasons:" in human_txt
    assert "PASS: passing verification" in human_txt
    assert f"Fingerprint:\n  {res.workflow_fingerprint}" in human_txt


def test_fail_explanation_output_mismatch():
    """Verify explanation generation and human formatting for an output mismatch failure."""
    wf = parse_workflow(SAMPLE_PASS_WF, filename="workflow.yaml")
    fix = parse_fixture(SAMPLE_FAIL_FIXTURE, filename="fixture.yaml")
    res = verify_fixture(wf, fix)
    report = build_developer_report(res, workflow=wf, fixture=fix)

    prov = report.provenance
    assert prov is not None
    assert prov.gate_decision == GateDecision.FAIL
    assert len(prov.reasons) >= 1

    out_reason = next(r for r in prov.reasons if r.code == "WYS852")
    assert out_reason.severity == ExplanationSeverity.FAIL
    assert out_reason.category == "output"
    assert out_reason.target == "out"

    human_txt = format_explanation_human(prov)
    assert "DECISION: FAIL" in human_txt
    assert "FAIL WYS852: output mismatch" in human_txt
    assert "output: out" in human_txt


def test_block_explanation_policy_violation():
    """Verify explanation generation and human formatting for policy violation BLOCK."""
    parsed_wf = parse_workflow(SAMPLE_CAPABILITY_WF, filename="workflow.yaml")
    val_res = validate_workflow(parsed_wf, policy=CapabilityPolicy(allowed=frozenset(Capability)))
    wf = val_res.workflow
    assert wf is not None
    fix = parse_fixture(
        """fixture_version: 1
id: dummy
inputs: {}
expected: {}
""",
        filename="fixture.yaml",
    )
    pol = Policy.model_validate(
        {
            "policy_version": 1,
            "forbidden_capabilities": ["network.http"],
        }
    )

    res = verify_fixture(parsed_wf, fix)
    pol_res = evaluate_policy(wf, pol)
    assert not pol_res.passed

    report = build_developer_report(res, workflow=wf, fixture=fix, policy_result=pol_res)
    prov = report.provenance
    assert prov is not None
    assert prov.gate_decision == GateDecision.BLOCK

    viol_reason = next(r for r in prov.reasons if r.code == "WYS453")
    assert viol_reason.severity == ExplanationSeverity.BLOCK
    assert viol_reason.category == "policy"
    assert "network.http" in viol_reason.message

    human_txt = format_explanation_human(prov)
    assert "DECISION: BLOCK" in human_txt
    assert "BLOCK WYS453:" in human_txt


def test_multiple_simultaneous_reasons():
    """Verify explanation handling when policy, verification, and semantic diff all flag issues."""
    wf_id = WorkflowIdentity(name="multi_test", fingerprint="hash123", display_name="multi_test")
    fix_id = FixtureIdentity(id="fix_multi", display_name="fix_multi")

    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.OUTPUT_CHANGED,
                change_type="TYPE_CHANGED",
                severity=DiffSeverity.BREAKING,
                target_id="final_result",
                path="/outputs/final_result",
                explanation="output type changed",
            )
        ],
        summary=DiffSummary(total_changes=1, breaking_count=1, has_breaking=True),
    )

    pol_result = PolicyResult(
        status=PolicyStatus.BLOCK,
        passed=False,
        blocked=True,
        violations=[
            PolicyViolation(
                code="WYS453",
                policy=PolicyRule.FORBIDDEN_CAPABILITIES.value,
                severity=Severity.ERROR,
                message='forbidden capability "network"',
                node_id="fetch_data",
                capability="network",
                path="/capabilities/0",
            )
        ],
    )

    diag_mismatch = NormalizedDiagnostic(
        code="WYS852",
        severity=Severity.ERROR,
        message="output mismatch for 'final_result': expected 1, got 2",
        category=DiagnosticCategory.OUTPUT,
        path="/outputs/final_result",
    )

    prov = build_provenance(
        workflow_id=wf_id,
        fixture_id=fix_id,
        status=ReportStatus.OUTPUT_MISMATCH,
        workflow_fingerprint="2c441b8a9f00",
        diagnostics=[diag_mismatch],
        outputs=[
            OutputReportItem(
                id="final_result", actual=2, expected=1, match_state=MatchState.MISMATCH
            )
        ],
        workflow_diff=diff,
        policy_result=pol_result,
    )

    assert prov.gate_decision == GateDecision.BLOCK
    assert len(prov.reasons) == 3

    # Ordering check: BLOCK before BREAKING before FAIL
    assert prov.reasons[0].severity == ExplanationSeverity.BLOCK
    assert prov.reasons[0].code == "WYS453"
    assert prov.reasons[0].node_id == "fetch_data"

    assert prov.reasons[1].severity == ExplanationSeverity.BREAKING
    assert prov.reasons[1].target == "final_result"

    assert prov.reasons[2].severity == ExplanationSeverity.FAIL
    assert prov.reasons[2].code == "WYS852"
    assert prov.reasons[2].target == "final_result"

    human_txt = format_explanation_human(prov)
    expected_output = """DECISION: BLOCK

Reasons:
  BLOCK WYS453: forbidden capability "network"
    node: fetch_data

  BREAKING: output type changed
    output: final_result

  FAIL WYS852: output mismatch
    output: final_result

Fingerprint:
  2c441b8a9f00"""
    assert human_txt == expected_output


def test_deterministic_json_serialization():
    """Verify byte-for-byte canonical JSON equivalence across multiple serializations."""
    wf_id = WorkflowIdentity(name="det_test", fingerprint="1234abcd", display_name="det_test")
    fix_id = FixtureIdentity(id="fix_det", display_name="fix_det")

    prov1 = build_provenance(
        workflow_id=wf_id,
        fixture_id=fix_id,
        status=ReportStatus.PASS,
        workflow_fingerprint="1234abcd",
    )
    prov2 = build_provenance(
        workflow_id=wf_id,
        fixture_id=fix_id,
        status=ReportStatus.PASS,
        workflow_fingerprint="1234abcd",
    )

    json1 = format_provenance_json(prov1)
    json2 = format_provenance_json(prov2)
    assert json1 == json2

    data = json.loads(json1)
    assert data["provenance_version"] == 1
    assert data["gate_decision"] == "PASS"
    assert data["decision"] == "PASS"
    assert data["reasons"][0]["severity"] == "PASS"
    assert data["reasons"][0]["message"] == "passing verification"
    # Ensure no non-deterministic fields exist
    assert "timestamp" not in data
    assert "duration" not in data
    assert "id" not in data or data["fixture"]["id"] == "fix_det"


def test_developer_report_backwards_compatibility():
    """Verify DeveloperReport integration preserves all existing APIs and properties."""
    wf = parse_workflow(SAMPLE_PASS_WF, filename="workflow.yaml")
    fix = parse_fixture(SAMPLE_PASS_FIXTURE, filename="fixture.yaml")
    res = verify_fixture(wf, fix)
    report = build_developer_report(res, workflow=wf, fixture=fix)

    # Existing public properties
    assert isinstance(report, DeveloperReport)
    assert report.status == ReportStatus.PASSED
    assert report.overall_status == ReportStatus.PASS
    assert report.success is True
    assert report.passed is True
    assert report.failed is False
    assert report.workflow.name == "test_pass"
    assert report.fixture.id == "fix_pass"

    # New Phase 7 properties
    assert report.provenance is not None
    assert report.provenance.gate_decision == GateDecision.PASS
    assert report.explanation is not None
    assert report.explanation.decision == GateDecision.PASS
    assert report.reasons is not None
    assert len(report.reasons) == 1

    # Serialization preserves both existing and new fields
    dump = report.model_dump(mode="json")
    assert "provenance" in dump
    assert dump["provenance"]["provenance_version"] == 1
    assert dump["provenance"]["gate_decision"] == "PASS"


def test_github_annotations_policy_block():
    """Verify GitHub annotations formatting emits proper error for policy violations."""
    parsed_wf = parse_workflow(SAMPLE_CAPABILITY_WF, filename="workflow.yaml")
    val_res = validate_workflow(parsed_wf, policy=CapabilityPolicy(allowed=frozenset(Capability)))
    wf = val_res.workflow
    assert wf is not None
    fix = parse_fixture(
        """fixture_version: 1
id: dummy
inputs: {}
expected: {}
""",
        filename="fixture.yaml",
    )
    pol = Policy.model_validate(
        {
            "policy_version": 1,
            "forbidden_capabilities": ["network.http"],
        }
    )

    res = verify_fixture(parsed_wf, fix)
    pol_res = evaluate_policy(wf, pol)
    report = build_developer_report(res, workflow=parsed_wf, fixture=fix, policy_result=pol_res)

    annotations = format_github_annotations(report)
    assert len(annotations) >= 1
    assert any("title=WYS453" in a for a in annotations)
    assert any("forbidden capability requested" in a for a in annotations)
