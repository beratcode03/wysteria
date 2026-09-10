"""Comprehensive unit tests for regression baselines."""

import json

import pytest

from wysteria.api import (
    CURRENT_BASELINE_VERSION,
    Baseline,
    BaselineComparisonStatus,
    BaselineCreationError,
    BaselineLoadError,
    BaselineParseError,
    BaselineResult,
    DiffKind,
    VerificationResult,
    VerificationStatus,
    compare_baseline,
    create_baseline,
    format_baseline_report,
    load_baseline,
    parse_fixture,
    parse_workflow,
    serialize_baseline,
    verify_fixture,
)

SAMPLE_WORKFLOW = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: n1
    kind: transform
    inputs:
      value:
        input: name
    config:
      operation: uppercase
    output_type: string
  - id: a1
    kind: assert
    inputs:
      value:
        input: name
    config:
      predicate: exists
    output_type: boolean
edges:
  - source: {input: name}
    target_node: n1
    target_input: value
  - source: {input: name}
    target_node: a1
    target_input: value
capabilities: []
assertions:
  - id: name_is_valid
    source: {node: a1}
    predicate: equals
    expected: true
outputs:
  greeting:
    source: {node: n1}
    type: string
"""

HAPPY_FIXTURE = """fixture_version: 1
id: happy-path
inputs:
  name: "berat"
expected:
  outputs:
    greeting: "BERAT"
  assertions:
    a1: true
    name_is_valid: true
"""

EXPECTED_ERR_WORKFLOW = """ir_version: 1
name: select_err
inputs:
  data:
    type: object
nodes:
  - id: s1
    kind: select
    inputs:
      value:
        input: data
    config:
      path: "/missing/key"
    output_type: string
edges:
  - source: {input: data}
    target_node: s1
    target_input: value
capabilities: []
assertions: []
outputs:
  val:
    source: {node: s1}
    type: string
"""

EXPECTED_ERR_FIXTURE = """fixture_version: 1
id: exp-err
inputs:
  data: {}
expected:
  error: "WYS801"
"""


@pytest.fixture
def passing_verification():
    wf = parse_workflow(SAMPLE_WORKFLOW, format="yaml")
    fix = parse_fixture(HAPPY_FIXTURE, format="yaml")
    result = verify_fixture(wf, fix)
    assert result.status == VerificationStatus.PASSED
    assert result.success is True
    return result


# 1. create baseline from passing verification
def test_create_baseline_from_passing_verification(tmp_path, passing_verification):
    baseline_path = tmp_path / "baseline.json"
    baseline = create_baseline(passing_verification, baseline_path)

    assert baseline.baseline_version == CURRENT_BASELINE_VERSION
    assert baseline.fixture_id == "happy-path"
    assert baseline.workflow_fingerprint == passing_verification.workflow_fingerprint
    assert baseline.result.status == VerificationStatus.PASSED
    assert baseline.result.success is True
    assert baseline.result.actual_outputs == {"greeting": "BERAT"}
    assert baseline.result.actual_assertions == {"a1": True, "name_is_valid": True}
    assert baseline_path.is_file()


# 2. create baseline from failing verification rejected
def test_create_baseline_from_failing_verification_rejected(tmp_path):
    failing_result = VerificationResult(
        status=VerificationStatus.OUTPUT_MISMATCH,
        success=False,
        fixture_id="happy-path",
        workflow_fingerprint="a" * 64,
        actual_outputs={"greeting": "WRONG"},
    )
    target = tmp_path / "baseline.json"
    with pytest.raises(BaselineCreationError, match="cannot create baseline from OUTPUT_MISMATCH"):
        create_baseline(failing_result, target)
    assert not target.exists()


# 3. baseline serialization deterministic
def test_baseline_serialization_deterministic(passing_verification):
    b1 = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs=passing_verification.actual_outputs,
            actual_assertions=passing_verification.actual_assertions,
        ),
    )
    b2 = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs=dict(reversed(list(passing_verification.actual_outputs.items()))),
            actual_assertions=dict(reversed(list(passing_verification.actual_assertions.items()))),
        ),
    )
    s1 = serialize_baseline(b1)
    s2 = serialize_baseline(b2)
    assert s1 == s2
    assert s1.endswith("\n")
    # Deterministic keys in JSON
    parsed = json.loads(s1)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


# 4. loading valid baseline
def test_load_valid_baseline(tmp_path, passing_verification):
    path = tmp_path / "baseline.json"
    created = create_baseline(passing_verification, path)
    loaded = load_baseline(path)
    assert loaded == created
    assert loaded.workflow_fingerprint == passing_verification.workflow_fingerprint
    assert loaded.fixture_id == "happy-path"


# 4b. loading valid YAML baseline
def test_load_valid_yaml_baseline(tmp_path, passing_verification):
    path = tmp_path / "baseline.yaml"
    path.write_text(
        f"""baseline_version: 1
workflow_fingerprint: "{passing_verification.workflow_fingerprint}"
fixture_id: "happy-path"
result:
  status: PASSED
  success: true
  actual_outputs:
    greeting: "BERAT"
  actual_assertions:
    a1: true
    name_is_valid: true
""",
        encoding="utf-8",
    )
    loaded = load_baseline(path)
    assert loaded.baseline_version == 1
    assert loaded.fixture_id == "happy-path"
    assert loaded.result.actual_outputs["greeting"] == "BERAT"


# 5. invalid baseline syntax
def test_invalid_baseline_syntax_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{ unclosed json", encoding="utf-8")
    with pytest.raises(BaselineParseError, match="invalid JSON"):
        load_baseline(path)


def test_invalid_baseline_syntax_duplicate_keys(tmp_path):
    path = tmp_path / "dup.json"
    path.write_text('{"baseline_version": 1, "baseline_version": 1}', encoding="utf-8")
    with pytest.raises(BaselineParseError, match="duplicate JSON object key"):
        load_baseline(path)


def test_invalid_baseline_syntax_non_finite_number(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text('{"baseline_version": 1, "val": NaN}', encoding="utf-8")
    with pytest.raises(BaselineParseError, match="non-finite JSON number"):
        load_baseline(path)


def test_invalid_baseline_syntax_yaml_anchor(tmp_path):
    path = tmp_path / "anchor.yaml"
    path.write_text("baseline_version: &anchor 1\n", encoding="utf-8")
    with pytest.raises(BaselineParseError, match="YAML aliases, anchors, and explicit tags"):
        load_baseline(path)


# 6. invalid baseline schema
def test_invalid_baseline_schema_missing_fields(tmp_path):
    path = tmp_path / "missing_fp.json"
    path.write_text(
        json.dumps(
            {
                "baseline_version": 1,
                "fixture_id": "test",
                "result": {"status": "PASSED", "success": True},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineParseError, match="baseline schema validation error"):
        load_baseline(path)


def test_invalid_baseline_schema_extra_fields(tmp_path):
    path = tmp_path / "extra.json"
    path.write_text(
        json.dumps(
            {
                "baseline_version": 1,
                "workflow_fingerprint": "a" * 64,
                "fixture_id": "test",
                "unknown_extra_field": 123,
                "result": {"status": "PASSED", "success": True},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineParseError, match="Extra inputs are not permitted"):
        load_baseline(path)


def test_invalid_baseline_schema_invalid_fingerprint(tmp_path):
    path = tmp_path / "bad_fp.json"
    path.write_text(
        json.dumps(
            {
                "baseline_version": 1,
                "workflow_fingerprint": "g" * 64,
                "fixture_id": "test",
                "result": {"status": "PASSED", "success": True},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineParseError, match="String should match pattern"):
        load_baseline(path)


# 7. unsupported baseline version
def test_unsupported_baseline_version(tmp_path):
    path = tmp_path / "v999.json"
    path.write_text(
        json.dumps(
            {
                "baseline_version": 999,
                "workflow_fingerprint": "a" * 64,
                "fixture_id": "test",
                "result": {"status": "PASSED", "success": True},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineParseError, match="unsupported baseline version 999"):
        load_baseline(path)


# 8. matching baseline
def test_matching_baseline(passing_verification):
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs=passing_verification.actual_outputs,
            actual_assertions=passing_verification.actual_assertions,
            expected_error_code=passing_verification.expected_error_code,
        ),
    )
    comparison = compare_baseline(passing_verification, baseline)
    assert comparison.matches is True
    assert comparison.status == BaselineComparisonStatus.MATCH
    assert not comparison.workflow_changed
    assert not comparison.fixture_changed
    assert not comparison.status_changed
    assert not comparison.outputs_changed
    assert not comparison.assertions_changed
    assert not comparison.expected_error_changed
    assert comparison.reasons == []

    report = format_baseline_report(comparison)
    assert "MATCH" in report
    assert "✓ fingerprint matches" in report
    assert "Result: MATCH" in report


# 9. output regression
def test_output_regression(passing_verification):
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs={"greeting": "BERATCAN", "extra_expected": "old"},
            actual_assertions=passing_verification.actual_assertions,
        ),
    )
    comparison = compare_baseline(passing_verification, baseline)
    assert comparison.matches is False
    assert comparison.status == BaselineComparisonStatus.REGRESSION
    assert comparison.outputs_changed is True
    assert any(d.name == "greeting" and d.kind == DiffKind.CHANGED for d in comparison.output_diffs)
    assert any(
        d.name == "extra_expected" and d.kind == DiffKind.MISSING for d in comparison.output_diffs
    )

    report = format_baseline_report(comparison)
    assert "REGRESSION" in report
    assert "Outputs" in report
    assert 'expected: "BERATCAN"' in report
    assert 'actual:   "BERAT"' in report
    assert "Result: REGRESSION" in report


# 10. assertion regression
def test_assertion_regression(passing_verification):
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs=passing_verification.actual_outputs,
            actual_assertions={"a1": False, "name_is_valid": True},
        ),
    )
    comparison = compare_baseline(passing_verification, baseline)
    assert comparison.matches is False
    assert comparison.status == BaselineComparisonStatus.REGRESSION
    assert comparison.assertions_changed is True
    assert any(d.name == "a1" and d.kind == DiffKind.CHANGED for d in comparison.assertion_diffs)
    assert any(
        d.name == "name_is_valid" and d.kind == DiffKind.MATCH for d in comparison.assertion_diffs
    )

    report = format_baseline_report(comparison)
    assert "REGRESSION" in report
    assert "Assertions" in report
    assert "a1" in report
    assert "expected: false" in report
    assert "actual:   true" in report
    assert "✓ name_is_valid" in report
    assert "Result: REGRESSION" in report


# 11. status regression
def test_status_regression(passing_verification):
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=VerificationStatus.PASSED,
            success=True,
            actual_outputs=passing_verification.actual_outputs,
            actual_assertions=passing_verification.actual_assertions,
        ),
    )
    failing_curr = VerificationResult(
        status=VerificationStatus.RUNTIME_ERROR,
        success=False,
        fixture_id=passing_verification.fixture_id,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        actual_outputs=passing_verification.actual_outputs,
        actual_assertions=passing_verification.actual_assertions,
    )
    comparison = compare_baseline(failing_curr, baseline)
    assert comparison.matches is False
    assert comparison.status_changed is True
    assert comparison.status == BaselineComparisonStatus.REGRESSION
    assert comparison.status_expected == VerificationStatus.PASSED
    assert comparison.status_actual == VerificationStatus.RUNTIME_ERROR

    report = format_baseline_report(comparison)
    assert "Status" in report
    assert "expected: PASSED" in report
    assert "actual:   RUNTIME_ERROR" in report


# 12. workflow fingerprint change
def test_workflow_fingerprint_change(passing_verification):
    different_fp = "f" * 64
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=different_fp,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs=passing_verification.actual_outputs,
            actual_assertions=passing_verification.actual_assertions,
        ),
    )
    comparison = compare_baseline(passing_verification, baseline)
    assert comparison.matches is False
    assert comparison.workflow_changed is True
    assert comparison.workflow_expected == different_fp
    assert comparison.workflow_actual == passing_verification.workflow_fingerprint

    report = format_baseline_report(comparison)
    assert "Workflow fingerprint changed" in report
    assert f"expected: {different_fp}" in report


# 13. expected-error behavior regression
def test_expected_error_behavior_regression():
    wf = parse_workflow(EXPECTED_ERR_WORKFLOW, format="yaml")
    fix = parse_fixture(EXPECTED_ERR_FIXTURE, format="yaml")
    result = verify_fixture(wf, fix)
    assert result.status == VerificationStatus.PASSED
    assert result.expected_error_code == "WYS801"

    baseline_without_err = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=result.workflow_fingerprint,
        fixture_id=result.fixture_id,
        result=BaselineResult(
            status=VerificationStatus.PASSED,
            success=True,
            actual_outputs={},
            actual_assertions={},
            expected_error_code=None,
        ),
    )
    comparison = compare_baseline(result, baseline_without_err)
    assert comparison.matches is False
    assert comparison.expected_error_changed is True
    assert comparison.expected_error_expected is None
    assert comparison.expected_error_actual == "WYS801"

    report = format_baseline_report(comparison)
    assert "Expected Error" in report
    assert 'actual:   "WYS801"' in report


# 14. missing baseline
def test_missing_baseline(passing_verification, tmp_path):
    comparison = compare_baseline(passing_verification, None)
    assert comparison.matches is False
    assert comparison.status == BaselineComparisonStatus.NO_BASELINE
    assert "No baseline exists" in comparison.reasons

    missing_file = tmp_path / "nonexistent.json"
    with pytest.raises(BaselineLoadError, match="not a readable regular file"):
        load_baseline(missing_file)


# 15. existing baseline without --force
def test_existing_baseline_without_force(tmp_path, passing_verification):
    path = tmp_path / "baseline.json"
    create_baseline(passing_verification, path)
    assert path.is_file()

    with pytest.raises(BaselineCreationError, match="already exists"):
        create_baseline(passing_verification, path, force=False)


# 16. --force overwrite if implemented
def test_force_overwrite(tmp_path, passing_verification):
    path = tmp_path / "baseline.json"
    create_baseline(passing_verification, path)
    assert path.is_file()

    # Overwrite with force=True succeeds
    b2 = create_baseline(passing_verification, path, force=True)
    assert b2.workflow_fingerprint == passing_verification.workflow_fingerprint


# 17. deterministic comparison ordering
def test_deterministic_comparison_ordering(passing_verification):
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs={"z_out": 1, "a_out": 2, "m_out": 3},
            actual_assertions={"z_assert": True, "a_assert": False},
        ),
    )
    curr = VerificationResult(
        status=passing_verification.status,
        success=passing_verification.success,
        fixture_id=passing_verification.fixture_id,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        actual_outputs={"m_out": 3, "z_out": 99, "a_out": 2},
        actual_assertions={"a_assert": True, "z_assert": True},
    )
    comp1 = compare_baseline(curr, baseline)
    comp2 = compare_baseline(curr, baseline)

    assert [d.name for d in comp1.output_diffs] == ["a_out", "m_out", "z_out"]
    assert [d.name for d in comp1.assertion_diffs] == ["a_assert", "z_assert"]
    assert comp1.output_diffs == comp2.output_diffs
    assert comp1.assertion_diffs == comp2.assertion_diffs


# 20. repeated comparison produces equivalent results
def test_repeated_comparison_equivalent_results(passing_verification):
    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=passing_verification.workflow_fingerprint,
        fixture_id=passing_verification.fixture_id,
        result=BaselineResult(
            status=passing_verification.status,
            success=passing_verification.success,
            actual_outputs={"greeting": "DIFFERENT"},
            actual_assertions=passing_verification.actual_assertions,
        ),
    )
    comp1 = compare_baseline(passing_verification, baseline)
    comp2 = compare_baseline(passing_verification, baseline)
    assert comp1.model_dump(mode="json") == comp2.model_dump(mode="json")
    assert format_baseline_report(comp1) == format_baseline_report(comp2)


# Bounded document tests
def test_baseline_size_limit(tmp_path):
    path = tmp_path / "huge.json"
    # Create file > 1,000,000 bytes
    path.write_text(" " * 1_000_001, encoding="utf-8")
    with pytest.raises(BaselineParseError, match="exceeds the 1000000 byte limit"):
        load_baseline(path)


def test_baseline_depth_limit(tmp_path):
    path = tmp_path / "deep.json"
    # Create JSON nesting > 64
    nested = '{"a": ' * 65 + "1" + "}" * 65
    path.write_text(nested, encoding="utf-8")
    with pytest.raises(BaselineParseError, match="maximum nesting depth"):
        load_baseline(path)
