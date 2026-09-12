"""Unit tests for Phase 2.4a: Developer Report Contract."""

import json
from copy import deepcopy

from wysteria.api import (
    AssertionReportItem,
    DeveloperReport,
    DiagnosticCategory,
    ExecutionSummary,
    FixtureIdentity,
    MatchState,
    NormalizedDiagnostic,
    OutputReportItem,
    ReportStatus,
    StatusBadge,
    ValidationSummary,
    VerificationResult,
    VerificationStatus,
    WorkflowIdentity,
    build_developer_report,
    build_report,
    compare_baseline,
    create_baseline,
    fingerprint_workflow,
    format_developer_report,
    format_report_json,
    parse_fixture,
    parse_workflow,
    verify_fixture,
)
from wysteria.baselines.models import (
    BaselineComparisonStatus,
)
from wysteria.reporting.builder import (
    categorize_diagnostic_code,
    diagnostic_sort_key,
    make_status_presentation,
    normalize_diagnostic,
)
from wysteria.reporting.diagnostics import Diagnostic, Severity, SourceLocation


def _parse_wf(text: str):
    return parse_workflow(text, filename="workflow.yaml")


def _parse_fix(text: str):
    return parse_fixture(text, filename="fixture.yaml")


SAMPLE_WORKFLOW_TEXT = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: msg
    kind: construct
    inputs:
      who:
        input: name
    config:
      template:
        greeting: "Hello, ${who}!"
    output_type: object
  - id: check_name
    kind: assert
    inputs:
      value:
        input: name
    config:
      predicate: type_is
      expected: string
    output_type: boolean
edges:
  - source: {input: name}
    target_node: msg
    target_input: who
  - source: {input: name}
    target_node: check_name
    target_input: value
capabilities: []
assertions:
  - id: name_is_valid
    source: {node: check_name}
    predicate: equals
    expected: true
outputs:
  output:
    source: {node: msg}
    type: object
"""

HAPPY_FIXTURE_TEXT = """fixture_version: 1
id: happy-path
name: Happy Path Fixture
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, BERAT!"
  assertions:
    check_name: true
    name_is_valid: true
"""

MISMATCH_FIXTURE_TEXT = """fixture_version: 1
id: mismatch-path
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, WORLD!"
"""

ASSERTION_FAIL_FIXTURE_TEXT = """fixture_version: 1
id: assert-fail
inputs:
  name: "BERAT"
expected:
  assertions:
    check_name: false
"""

SELECT_ERROR_WORKFLOW = """ir_version: 1
name: select_wf
inputs:
  user:
    type: object
nodes:
  - id: select_name
    kind: select
    inputs:
      value:
        input: user
    config:
      path: "/user/name"
    output_type: string
edges:
  - source: {input: user}
    target_node: select_name
    target_input: value
capabilities: []
assertions: []
outputs:
  name:
    source: {node: select_name}
    type: string
"""

SELECT_ERROR_FIXTURE_TEXT = """fixture_version: 1
id: select-fix
inputs:
  user: {}
"""

MODIFIED_WORKFLOW_TEXT = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: msg
    kind: construct
    inputs:
      who:
        input: name
    config:
      template:
        greeting: "Hi, ${who}!"
    output_type: object
  - id: check_name
    kind: assert
    inputs:
      value:
        input: name
    config:
      predicate: type_is
      expected: string
    output_type: boolean
edges:
  - source: {input: name}
    target_node: msg
    target_input: who
  - source: {input: name}
    target_node: check_name
    target_input: value
capabilities: []
assertions:
  - id: name_is_valid
    source: {node: check_name}
    predicate: equals
    expected: true
outputs:
  output:
    source: {node: msg}
    type: object
"""


# 1. Successful report
def test_successful_report():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)
    assert result.status == VerificationStatus.PASSED

    report = build_developer_report(result, workflow=wf, fixture=fix)

    assert isinstance(report, DeveloperReport)
    assert report.success is True
    assert report.passed is True
    assert report.failed is False
    assert report.status == ReportStatus.PASSED
    assert report.overall_status == ReportStatus.PASS

    # Presentation
    assert report.status_presentation.status == ReportStatus.PASS
    assert report.status_presentation.label == "PASS"
    assert report.status_presentation.badge == StatusBadge.SUCCESS
    assert report.status_presentation.passed is True

    # Identity
    assert report.workflow.name == "greeter"
    assert report.workflow.fingerprint == result.workflow_fingerprint
    assert report.fixture.id == "happy-path"
    assert report.fixture.name == "Happy Path Fixture"
    assert report.fixture_id == "happy-path"

    # Validation summary
    assert report.validation.workflow_valid is True
    assert report.validation.fixture_valid is True
    assert report.validation.error_count == 0
    assert report.validation.warning_count == 0

    # Execution summary
    assert report.execution.total_nodes_executed == 2
    assert report.execution.success is True
    assert report.execution.expected_error_occurred is False
    assert report.execution.actual_error_code is None

    # Outputs
    assert len(report.outputs) == 1
    assert report.outputs[0].id == "output"
    assert report.outputs[0].name == "output"
    assert report.outputs[0].actual == {"greeting": "Hello, BERAT!"}
    assert report.outputs[0].expected == {"greeting": "Hello, BERAT!"}
    assert report.outputs[0].match_state == MatchState.MATCH

    # Assertions
    assert len(report.assertions) == 2
    assert [a.id for a in report.assertions] == ["check_name", "name_is_valid"]
    assert all(a.match_state == MatchState.MATCH for a in report.assertions)
    assert all(a.actual is True for a in report.assertions)

    # Traces & Diagnostics
    assert len(report.traces) == 2
    assert len(report.diagnostics) == 0

    # Human format test
    formatted = format_developer_report(report)
    assert "WYSTERIA" in formatted
    assert "Workflow: greeter" in formatted
    assert "Fixture:  Happy Path Fixture" in formatted
    assert "PASS" in formatted


# 2. Failed output report
def test_failed_output_report():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(MISMATCH_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)
    assert result.status == VerificationStatus.OUTPUT_MISMATCH

    report = build_developer_report(result, workflow=wf, fixture=fix)

    assert report.success is False
    assert report.passed is False
    assert report.failed is True
    assert report.status == ReportStatus.OUTPUT_MISMATCH
    assert report.overall_status == ReportStatus.FAIL
    assert report.status_presentation.label == "OUTPUT MISMATCH"
    assert report.status_presentation.badge == StatusBadge.FAILURE

    # Output items
    assert len(report.outputs) == 1
    out = report.outputs[0]
    assert out.id == "output"
    assert out.actual == {"greeting": "Hello, BERAT!"}
    assert out.expected == {"greeting": "Hello, WORLD!"}
    assert out.match_state == MatchState.MISMATCH

    # Diagnostics
    assert len(report.diagnostics) >= 1
    diag = report.diagnostics[0]
    assert diag.code == "WYS852"
    assert diag.category == DiagnosticCategory.OUTPUT

    formatted = format_developer_report(report)
    assert "OUTPUT_MISMATCH" in formatted
    assert "FAIL" in formatted


# 3. Failed assertion report
def test_failed_assertion_report():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(ASSERTION_FAIL_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)
    assert result.status == VerificationStatus.ASSERTION_FAILED

    report = build_developer_report(result, workflow=wf, fixture=fix)

    assert report.success is False
    assert report.status == ReportStatus.ASSERTION_FAILED
    assert report.overall_status == ReportStatus.FAIL
    assert report.status_presentation.label == "ASSERTION FAILED"
    assert report.status_presentation.badge == StatusBadge.FAILURE

    # Assertions
    mismatched = [a for a in report.assertions if a.match_state == MatchState.MISMATCH]
    assert len(mismatched) >= 1
    item = mismatched[0]
    assert item.id == "check_name"
    assert item.expected is False
    assert item.actual is True

    # Diagnostics
    assert any(d.category == DiagnosticCategory.ASSERTION for d in report.diagnostics)


# 4. Invalid workflow report
def test_invalid_workflow_report():
    raw_wf = _parse_wf("ir_version: 1\nname: broken\ninputs: {}\n")  # missing required 'nodes'
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(raw_wf, fix)
    assert result.status == VerificationStatus.INVALID_WORKFLOW

    report = build_developer_report(result, fixture=fix)

    assert report.success is False
    assert report.status == ReportStatus.INVALID_WORKFLOW
    assert report.overall_status == ReportStatus.FAIL
    assert report.status_presentation.label == "INVALID WORKFLOW"
    assert report.status_presentation.badge == StatusBadge.ERROR
    assert report.validation.workflow_valid is False
    assert report.validation.error_count > 0
    assert any(d.category == DiagnosticCategory.SCHEMA for d in report.diagnostics)


# 5. Runtime error report
def test_runtime_error_report():
    wf = _parse_wf(SELECT_ERROR_WORKFLOW)
    fix = _parse_fix(SELECT_ERROR_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)
    assert result.status == VerificationStatus.RUNTIME_ERROR

    report = build_developer_report(result, workflow=wf, fixture=fix)

    assert report.success is False
    assert report.status == ReportStatus.RUNTIME_ERROR
    assert report.overall_status == ReportStatus.FAIL
    assert report.status_presentation.label == "RUNTIME ERROR"
    assert report.status_presentation.badge == StatusBadge.ERROR
    assert report.execution.actual_error_code == "WYS801"
    assert len(report.diagnostics) >= 1
    diag = report.diagnostics[0]
    assert diag.code == "WYS801"
    assert diag.category == DiagnosticCategory.RUNTIME
    assert diag.node_id == "select_name"


def test_limit_exceeded_report():
    # Construct a manual VerificationResult representing LIMIT_EXCEEDED
    diag = Diagnostic(
        code="WYS853",
        severity=Severity.ERROR,
        message="runtime limit exceeded: value exceeds maximum allowed size",
        path="/nodes/n1",
    )
    result = VerificationResult(
        status=VerificationStatus.LIMIT_EXCEEDED,
        success=False,
        fixture_id="fix-1",
        diagnostics=[diag],
    )
    report = build_developer_report(result)
    assert report.status == ReportStatus.LIMIT_EXCEEDED
    assert report.status_presentation.label == "LIMIT EXCEEDED"
    assert report.status_presentation.badge == StatusBadge.ERROR
    assert report.diagnostics[0].category == DiagnosticCategory.LIMIT


# 6. Regression report
def test_regression_report(tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(SAMPLE_WORKFLOW_TEXT, encoding="utf-8")
    fix_file = tmp_path / "fix.yaml"
    fix_file.write_text(HAPPY_FIXTURE_TEXT, encoding="utf-8")
    base_file = tmp_path / "base.json"

    # 1. Baseline creation
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    res1 = verify_fixture(wf, fix)
    base = create_baseline(res1, base_file)

    # 2. Comparison with regression (modified workflow produces different output)
    wf_mod = _parse_wf(MODIFIED_WORKFLOW_TEXT)
    res2 = verify_fixture(wf_mod, fix)
    comparison = compare_baseline(res2, base)
    assert comparison.status == BaselineComparisonStatus.REGRESSION

    # 3. Report construction
    report = build_developer_report(
        res2, workflow=wf_mod, fixture=fix, baseline_comparison=comparison
    )

    assert report.status == ReportStatus.REGRESSION
    assert report.overall_status == ReportStatus.FAIL
    assert report.status_presentation.label == "REGRESSION"
    assert report.status_presentation.badge == StatusBadge.FAILURE
    assert report.success is False
    assert report.baseline is not None
    assert report.baseline.matches is False
    assert report.baseline.workflow_changed is True
    assert report.baseline.outputs_changed is True
    assert len(report.baseline.diff_entries) >= 1
    assert len(report.baseline.reasons) >= 1

    formatted = format_developer_report(report)
    assert "REGRESSION" in formatted
    assert "FAIL" in formatted


# 7. Output expected/actual representation
def test_output_expected_actual_representation():
    item_match = OutputReportItem(
        id="result",
        actual={"val": 42},
        expected={"val": 42},
        match_state=MatchState.MATCH,
    )
    assert item_match.id == "result"
    assert item_match.name == "result"
    assert item_match.actual == {"val": 42}
    assert item_match.expected == {"val": 42}
    assert item_match.match_state == MatchState.MATCH

    item_missing = OutputReportItem(
        id="missing_out",
        actual=None,
        expected="expected_str",
        match_state=MatchState.MISSING,
    )
    assert item_missing.actual is None
    assert item_missing.expected == "expected_str"
    assert item_missing.match_state == MatchState.MISSING

    item_unexpected = OutputReportItem(
        id="unexp_out",
        actual=123,
        expected=None,
        match_state=MatchState.UNEXPECTED,
    )
    assert item_unexpected.match_state == MatchState.UNEXPECTED


# 8. Assertion expected/actual representation
def test_assertion_expected_actual_representation():
    item = AssertionReportItem(
        id="check_valid",
        actual=True,
        expected=True,
        match_state=MatchState.MATCH,
    )
    assert item.id == "check_valid"
    assert item.name == "check_valid"
    assert item.actual is True
    assert item.expected is True
    assert item.match_state == MatchState.MATCH

    item_fail = AssertionReportItem(
        id="check_zero",
        actual=False,
        expected=True,
        match_state=MatchState.MISMATCH,
    )
    assert item_fail.match_state == MatchState.MISMATCH


# 9. Diagnostic normalization
def test_diagnostic_normalization():
    codes_to_expected = {
        "WYS102": DiagnosticCategory.SCHEMA,
        "WYS201": DiagnosticCategory.REFERENCE,
        "WYS301": DiagnosticCategory.GRAPH,
        "WYS401": DiagnosticCategory.CAPABILITY,
        "WYS501": DiagnosticCategory.SEMANTIC,
        "WYS600": DiagnosticCategory.BASELINE,
        "WYS700": DiagnosticCategory.FIXTURE,
        "WYS702": DiagnosticCategory.FIXTURE,
        "WYS801": DiagnosticCategory.RUNTIME,
        "WYS802": DiagnosticCategory.RUNTIME,
        "WYS850": DiagnosticCategory.ASSERTION,
        "WYS851": DiagnosticCategory.ASSERTION,
        "WYS852": DiagnosticCategory.OUTPUT,
        "WYS853": DiagnosticCategory.LIMIT,
        "WYS900": DiagnosticCategory.SYSTEM,
        "OTHER": DiagnosticCategory.GENERAL,
    }

    for code, expected_cat in codes_to_expected.items():
        assert categorize_diagnostic_code(code) == expected_cat

    diag = Diagnostic(
        code="WYS801",
        severity=Severity.ERROR,
        message="error in node 'select_target': key missing",
        path="/nodes/select_target/config/path",
        location=SourceLocation(file="wf.yaml", line=12, column=5),
        hint="check key in input object",
    )
    norm = normalize_diagnostic(diag)
    assert norm.code == "WYS801"
    assert norm.severity == Severity.ERROR
    assert norm.category == DiagnosticCategory.RUNTIME
    assert norm.node_id == "select_target"
    assert norm.location == SourceLocation(file="wf.yaml", line=12, column=5)
    assert norm.source_location == norm.location
    assert norm.hint == "check key in input object"


# 10. Deterministic ordering
def test_deterministic_ordering():
    # Diagnostics sorting test
    d1 = NormalizedDiagnostic(
        code="WYS852",
        severity=Severity.ERROR,
        message="b mismatch",
        category=DiagnosticCategory.OUTPUT,
        node_id="b",
    )
    d2 = NormalizedDiagnostic(
        code="WYS102",
        severity=Severity.ERROR,
        message="a schema error",
        category=DiagnosticCategory.SCHEMA,
        node_id="a",
    )
    d3 = NormalizedDiagnostic(
        code="WYS500",
        severity=Severity.WARNING,
        message="warn",
        category=DiagnosticCategory.SEMANTIC,
    )
    sorted_diags = sorted([d1, d3, d2], key=diagnostic_sort_key)
    # Errors before warnings, then by code
    assert sorted_diags[0].code == "WYS102"
    assert sorted_diags[1].code == "WYS852"
    assert sorted_diags[2].code == "WYS500"

    # Outputs sorting by ID
    outputs = [
        OutputReportItem(id="z", match_state=MatchState.MATCH),
        OutputReportItem(id="a", match_state=MatchState.MATCH),
        OutputReportItem(id="m", match_state=MatchState.MATCH),
    ]
    report = DeveloperReport(
        status=ReportStatus.PASS,
        overall_status=ReportStatus.PASS,
        status_presentation=make_status_presentation(ReportStatus.PASS, True),
        success=True,
        workflow=WorkflowIdentity(display_name="test"),
        fixture=FixtureIdentity(id="fix", display_name="fix"),
        fixture_id="fix",
        validation=ValidationSummary(workflow_valid=True, fixture_valid=True),
        execution=ExecutionSummary(success=True),
        outputs=sorted(outputs, key=lambda o: o.id),
    )
    assert [o.id for o in report.outputs] == ["a", "m", "z"]


# 11. Deterministic JSON serialization
def test_deterministic_json_serialization():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)

    report1 = build_developer_report(result, workflow=wf, fixture=fix)
    report2 = build_developer_report(result, workflow=wf, fixture=fix)

    json1 = report1.to_json()
    json2 = report2.to_json()
    json3 = format_report_json(report1)

    assert json1 == json2
    assert json1 == json3
    assert "\x1b" not in json1  # No ANSI escape codes

    data = json.loads(json1)
    assert data["status"] == "PASSED"
    assert data["overall_status"] == "PASS"
    assert data["success"] is True
    assert "workflow" in data
    assert "fixture" in data
    assert "validation" in data
    assert "execution" in data
    assert "outputs" in data
    assert "assertions" in data
    assert "diagnostics" in data
    assert "traces" in data


# 12. Report contains workflow fingerprint
def test_report_contains_workflow_fingerprint():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)

    report = build_developer_report(result, workflow=wf, fixture=fix)

    assert report.workflow_fingerprint is not None
    assert len(report.workflow_fingerprint) == 64
    from wysteria.api import validate_workflow

    val_res = validate_workflow(wf)
    assert val_res.valid is True
    expected_fp = fingerprint_workflow(val_res.workflow)
    assert report.workflow_fingerprint == expected_fp


# 13. Report contains trace information
def test_report_contains_trace_information():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)

    report = build_developer_report(result, workflow=wf, fixture=fix)

    assert len(report.traces) == 2
    assert report.traces[0].step == 0
    assert report.traces[1].step == 1
    trace_ids = {t.node_id for t in report.traces}
    assert trace_ids == {"msg", "check_name"}
    for t in report.traces:
        assert isinstance(t.resolved_inputs, dict)
        assert t.kind in {"construct", "assert"}


# 14. Report conversion does not mutate VerificationResult
def test_report_conversion_does_not_mutate_verification_result():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)

    snapshot_before = deepcopy(result.model_dump(mode="json"))

    # Build report multiple times with various parameters
    r1 = build_developer_report(result)
    r2 = build_developer_report(result, workflow=wf, fixture=fix)
    r3 = build_report(result)

    snapshot_after = result.model_dump(mode="json")
    assert snapshot_before == snapshot_after
    assert r1.success == result.success
    assert r2.success == result.success
    assert r3.success == result.success


# 15. Clean Public API aliases
def test_public_api_report_exports():
    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)

    report = build_report(result)
    assert isinstance(report, DeveloperReport)
    assert report.status == ReportStatus.PASSED

    json_str = format_report_json(report)
    assert isinstance(json_str, str)
    assert "PASSED" in json_str


def test_evidence_verification_reporting():
    from wysteria.evidence.models import ClaimType, EvidenceResult, EvidenceStatus

    wf = _parse_wf(SAMPLE_WORKFLOW_TEXT)
    fix = _parse_fix(HAPPY_FIXTURE_TEXT)
    result = verify_fixture(wf, fix)

    evidence_results = [
        EvidenceResult(
            claim_id="claim-1",
            claim_type=ClaimType.API_ENDPOINT,
            status=EvidenceStatus.VERIFIED,
            source="https://docs.api.com",
            trust_tier=1,
            reason="All good.",
            evidence_text="Endpoint GET /api exists. \x1b[31mDangerous ansi here\x1b[0m",
        ),
        EvidenceResult(
            claim_id="claim-2",
            claim_type=ClaimType.FACTUAL,
            status=EvidenceStatus.UNVERIFIABLE,
        ),
    ]

    report = build_developer_report(result, evidence_results=evidence_results)

    # JSON output check
    json_str = format_report_json(report)
    data = json.loads(json_str)
    assert "evidence_results" in data
    assert len(data["evidence_results"]) == 2
    assert data["evidence_results"][0]["claim_id"] == "claim-1"
    assert data["evidence_results"][0]["claim_type"] == "api_endpoint"
    assert data["evidence_results"][0]["status"] == "verified"
    assert data["evidence_results"][0]["source"] == "https://docs.api.com"
    assert data["evidence_results"][0]["trust_tier"] == 1
    assert data["evidence_results"][0]["reason"] == "All good."

    # CLI output check
    cli_str = format_developer_report(report)
    assert "Evidence Verification" in cli_str
    assert "✓ claim-1 [api_endpoint]: VERIFIED" in cli_str
    assert "source: https://docs.api.com" in cli_str
    assert "trust tier: 1" in cli_str
    assert "reason: All good." in cli_str
    assert "! claim-2 [factual]: UNVERIFIABLE" in cli_str

    # Safe rendering check (no ANSI escape)
    assert "\x1b[31m" not in cli_str
    assert (
        "Endpoint GET /api exists. [31mDangerous ansi here[0m" in cli_str
        or "Endpoint GET /api exists." in cli_str
    )
