"""Comprehensive tests for Wysteria's deterministic verification engine."""

import json

import pytest

from wysteria.api import (
    Fixture,
    FixtureExpected,
    ParsedFixture,
    ParsedWorkflow,
    VerificationStatus,
    parse_fixture,
    parse_workflow,
    verify_fixture,
)
from wysteria.fixtures.models import ExpectedError


@pytest.fixture
def base_workflow_data():
    return {
        "ir_version": 1,
        "name": "calc_workflow",
        "inputs": {
            "val_a": {"type": "integer", "required": True},
            "val_b": {"type": "integer", "required": False},
        },
        "nodes": [
            {
                "id": "to_str",
                "kind": "transform",
                "inputs": {"value": {"input": "val_a"}},
                "config": {"operation": "to_string"},
                "output_type": "string",
            },
            {
                "id": "check_positive",
                "kind": "assert",
                "inputs": {"value": {"input": "val_a"}},
                "config": {"predicate": "type_is", "expected": "integer"},
                "output_type": "boolean",
            },
            {
                "id": "pack",
                "kind": "construct",
                "inputs": {
                    "num_str": {"node": "to_str"},
                    "is_int": {"node": "check_positive"},
                },
                "config": {
                    "template": {
                        "str_rep": "${num_str}",
                        "verified": "${is_int}",
                    }
                },
                "output_type": "object",
            },
        ],
        "edges": [
            {"source": {"input": "val_a"}, "target_node": "to_str", "target_input": "value"},
            {
                "source": {"input": "val_a"},
                "target_node": "check_positive",
                "target_input": "value",
            },
            {"source": {"node": "to_str"}, "target_node": "pack", "target_input": "num_str"},
            {"source": {"node": "check_positive"}, "target_node": "pack", "target_input": "is_int"},
        ],
        "capabilities": [],
        "assertions": [
            {
                "id": "check_str_len",
                "source": {"node": "to_str"},
                "predicate": "type_is",
                "expected": "string",
            }
        ],
        "outputs": {
            "result": {"source": {"node": "pack"}, "type": "object"},
            "raw_str": {"source": {"node": "to_str"}, "type": "string"},
        },
    }


@pytest.fixture
def valid_workflow(base_workflow_data):
    return parse_workflow(json.dumps(base_workflow_data), filename="wf.json")


# --- 1. Successful Verification Tests ---


def test_verify_successful_workflow_matching_outputs(valid_workflow):
    fixture_yaml = """
fixture_version: 1
id: pass_case
inputs:
  val_a: 42
expected:
  outputs:
    result:
      str_rep: "42"
      verified: true
    raw_str: "42"
  assertions:
    check_positive: true
    check_str_len: true
"""
    fixture = parse_fixture(fixture_yaml, format="yaml")
    result = verify_fixture(valid_workflow, fixture)

    assert result.success
    assert result.status == VerificationStatus.PASSED
    assert result.fixture_id == "pass_case"
    assert result.workflow_fingerprint is not None
    assert len(result.diagnostics) == 0
    assert result.actual_outputs["raw_str"] == "42"
    assert result.actual_outputs["result"] == {"str_rep": "42", "verified": True}
    assert result.actual_assertions["check_positive"] is True
    assert result.actual_assertions["check_str_len"] is True
    assert len(result.traces) == 3


def test_verify_successful_subset_outputs(valid_workflow):
    # Only asserting raw_str, not result
    fixture = Fixture(
        fixture_version=1,
        id="subset_case",
        inputs={"val_a": 10},
        expected=FixtureExpected(
            outputs={"raw_str": "10"},
        ),
    )
    result = verify_fixture(valid_workflow, fixture)
    assert result.success
    assert result.status == VerificationStatus.PASSED


# --- 2. Output Mismatch Tests ---


def test_verify_output_mismatch_fails(valid_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="mismatch_case",
        inputs={"val_a": 42},
        expected=FixtureExpected(
            outputs={"raw_str": "WRONG_VALUE"},
        ),
    )
    result = verify_fixture(valid_workflow, fixture)

    assert not result.success
    assert result.status == VerificationStatus.OUTPUT_MISMATCH
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "WYS852"
    assert "output mismatch for 'raw_str'" in result.diagnostics[0].message
    assert result.diagnostics[0].path == "/outputs/raw_str"


def test_verify_strict_equals_prevents_bool_int_output_coercion():
    wf_data = {
        "ir_version": 1,
        "name": "bool_int_wf",
        "inputs": {},
        "nodes": [
            {
                "id": "c_num",
                "kind": "constant",
                "inputs": {},
                "config": {"value": 1},
                "output_type": "any",
            }
        ],
        "edges": [],
        "capabilities": [],
        "assertions": [],
        "outputs": {"num": {"source": {"node": "c_num"}, "type": "any"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")
    # Expected output is boolean True, but actual is int 1
    fixture = Fixture(
        fixture_version=1,
        id="type_mismatch_case",
        inputs={},
        expected=FixtureExpected(outputs={"num": True}),
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.OUTPUT_MISMATCH
    assert result.diagnostics[0].code == "WYS852"


def test_verify_unexpected_actual_output_when_complete_outputs_declared(valid_workflow):
    # Fixture declares complete_outputs: true, but only provides 'raw_str' in expected.outputs
    # 'result' output produced by workflow is unexpected!
    fixture = Fixture(
        fixture_version=1,
        id="unexpected_output_case",
        inputs={"val_a": 5},
        expected=FixtureExpected(
            complete_outputs=True,
            outputs={"raw_str": "5"},
        ),
    )
    result = verify_fixture(valid_workflow, fixture)
    assert not result.success
    assert result.status == VerificationStatus.OUTPUT_MISMATCH
    assert any("unexpected actual output 'result'" in d.message for d in result.diagnostics)


# --- 3. Assertion Semantics Tests ---


def test_verify_assertion_mismatch_expected_true_actual_false(base_workflow_data):
    # Modify workflow so check_positive asserts equals 999
    base_workflow_data["nodes"][1]["config"] = {"predicate": "equals", "expected": 999}
    wf = parse_workflow(json.dumps(base_workflow_data), filename="wf.json")

    # Fixture expects check_positive to be true
    fixture = Fixture(
        fixture_version=1,
        id="assert_fail_case",
        inputs={"val_a": 42},  # 42 != 999 -> check_positive is False!
        expected=FixtureExpected(
            assertions={"check_positive": True},
        ),
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.ASSERTION_FAILED
    assert result.actual_assertions["check_positive"] is False
    assert any(d.code == "WYS850" for d in result.diagnostics)


def test_verify_expected_false_assertion_passes(base_workflow_data):
    # Workflow check_positive asserts equals 999
    base_workflow_data["nodes"][1]["config"] = {"predicate": "equals", "expected": 999}
    wf = parse_workflow(json.dumps(base_workflow_data), filename="wf.json")

    # Fixture EXPLICITLY EXPECTS check_positive to be false!
    fixture = Fixture(
        fixture_version=1,
        id="expected_false_case",
        inputs={"val_a": 42},  # 42 != 999 -> check_positive is False
        expected=FixtureExpected(
            assertions={"check_positive": False, "check_str_len": True},
            outputs={"raw_str": "42"},
        ),
    )
    result = verify_fixture(wf, fixture)
    assert result.success
    assert result.status == VerificationStatus.PASSED
    assert result.actual_assertions["check_positive"] is False
    assert len(result.diagnostics) == 0


def test_verify_workflow_level_assertion_failure(base_workflow_data):
    # Workflow-level assertion expects constant "hello", but to_str produces "42"
    base_workflow_data["assertions"] = [
        {
            "id": "strict_check",
            "source": {"node": "to_str"},
            "predicate": "equals",
            "expected": "hello",
        }
    ]
    wf = parse_workflow(json.dumps(base_workflow_data), filename="wf.json")
    fixture = Fixture(
        fixture_version=1,
        id="wf_assert_fail",
        inputs={"val_a": 42},
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.ASSERTION_FAILED
    assert any(d.code == "WYS851" for d in result.diagnostics)


# --- 4. Expected Runtime Error Tests ---


def test_verify_expected_runtime_error_matching_passes():
    # Workflow with SelectNode that references non-existent path -> raises WYS801
    wf_data = {
        "ir_version": 1,
        "name": "err_wf",
        "inputs": {"payload": {"type": "object"}},
        "nodes": [
            {
                "id": "sel",
                "kind": "select",
                "inputs": {"value": {"input": "payload"}},
                "config": {"path": "/missing/key"},
                "output_type": "any",
            }
        ],
        "edges": [{"source": {"input": "payload"}, "target_node": "sel", "target_input": "value"}],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "sel"}, "type": "any"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")

    # Fixture declares expected error WYS801
    fixture_yaml = """
fixture_version: 1
id: expected_error_case
inputs:
  payload: {"valid": true}
expected:
  error: "WYS801"
"""
    fixture = parse_fixture(fixture_yaml, format="yaml")
    result = verify_fixture(wf, fixture)

    assert result.success
    assert result.status == VerificationStatus.PASSED
    assert len(result.diagnostics) == 0


def test_verify_expected_runtime_error_structured_code_passes():
    # Using expected.error.code syntax
    wf_data = {
        "ir_version": 1,
        "name": "err_wf",
        "inputs": {"payload": {"type": "object"}},
        "nodes": [
            {
                "id": "sel",
                "kind": "select",
                "inputs": {"value": {"input": "payload"}},
                "config": {"path": "/missing/key"},
                "output_type": "any",
            }
        ],
        "edges": [{"source": {"input": "payload"}, "target_node": "sel", "target_input": "value"}],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "sel"}, "type": "any"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")
    fixture = Fixture(
        fixture_version=1,
        id="code_struct_case",
        inputs={"payload": {}},
        expected=FixtureExpected(error=ExpectedError(code="WYS801")),
    )
    result = verify_fixture(wf, fixture)
    assert result.success
    assert result.status == VerificationStatus.PASSED


def test_verify_expected_runtime_error_mismatch_fails():
    # Workflow raises WYS801, but fixture expects WYS802
    wf_data = {
        "ir_version": 1,
        "name": "err_wf",
        "inputs": {"payload": {"type": "object"}},
        "nodes": [
            {
                "id": "sel",
                "kind": "select",
                "inputs": {"value": {"input": "payload"}},
                "config": {"path": "/missing/key"},
                "output_type": "any",
            }
        ],
        "edges": [{"source": {"input": "payload"}, "target_node": "sel", "target_input": "value"}],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "sel"}, "type": "any"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")
    fixture = Fixture(
        fixture_version=1,
        id="wrong_err_code",
        inputs={"payload": {}},
        expected=FixtureExpected(error="WYS802"),  # Expects WYS802, but gets WYS801
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.RUNTIME_ERROR
    assert any(
        "expected runtime error 'WYS802', got 'WYS801'" in d.message for d in result.diagnostics
    )


def test_verify_expected_error_but_successful_execution_fails(valid_workflow):
    # Workflow evaluates successfully, but fixture expected WYS801
    fixture = Fixture(
        fixture_version=1,
        id="unexpected_success",
        inputs={"val_a": 10},
        expected=FixtureExpected(error="WYS801"),
    )
    result = verify_fixture(valid_workflow, fixture)
    assert not result.success
    assert result.status == VerificationStatus.RUNTIME_ERROR
    assert any(
        "expected runtime error 'WYS801', but workflow evaluated successfully" in d.message
        for d in result.diagnostics
    )


def test_verify_unhandled_runtime_error_fails(valid_workflow):
    # Transform to_integer receives invalid string if we pass invalid node input
    wf_data = {
        "ir_version": 1,
        "name": "transform_err_wf",
        "inputs": {"str_val": {"type": "string"}},
        "nodes": [
            {
                "id": "tr",
                "kind": "transform",
                "inputs": {"value": {"input": "str_val"}},
                "config": {"operation": "to_integer"},
                "output_type": "integer",
            }
        ],
        "edges": [{"source": {"input": "str_val"}, "target_node": "tr", "target_input": "value"}],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "tr"}, "type": "integer"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")
    fixture = Fixture(
        fixture_version=1,
        id="unhandled_err",
        inputs={"str_val": "not_an_int"},
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.RUNTIME_ERROR
    assert any(d.code == "WYS802" for d in result.diagnostics)


# --- 5. Invalid Workflow and Invalid Fixture Tests ---


def test_verify_invalid_workflow_status():
    # Missing required field in workflow
    invalid_parsed_wf = ParsedWorkflow(
        data={"ir_version": 1, "name": "bad"},
        filename="bad.yaml",
        locations={},
    )
    fixture = Fixture(fixture_version=1, id="f1", inputs={})
    result = verify_fixture(invalid_parsed_wf, fixture)

    assert not result.success
    assert result.status == VerificationStatus.INVALID_WORKFLOW
    assert len(result.diagnostics) > 0


def test_verify_invalid_fixture_structure(valid_workflow):
    # Fixture missing required 'id'
    invalid_parsed_fixture = ParsedFixture(
        data={"fixture_version": 1, "inputs": {}},
        filename="bad_fix.yaml",
        locations={},
    )
    result = verify_fixture(valid_workflow, invalid_parsed_fixture)

    assert not result.success
    assert result.status == VerificationStatus.INVALID_FIXTURE
    assert any(d.code == "WYS701" for d in result.diagnostics)


def test_verify_fixture_workflow_input_mismatch(valid_workflow):
    # Fixture provides string for integer input
    fixture = Fixture(
        fixture_version=1,
        id="type_mismatch",
        inputs={"val_a": "forty_two"},  # val_a is integer!
    )
    result = verify_fixture(valid_workflow, fixture)

    assert not result.success
    assert result.status == VerificationStatus.INVALID_FIXTURE
    assert any(d.code == "WYS702" for d in result.diagnostics)


# --- 6. Determinism & Integrity Tests ---


def test_verify_repeated_execution_identical_result(valid_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="repeat_case",
        inputs={"val_a": 100},
        expected=FixtureExpected(
            outputs={"raw_str": "100"},
            assertions={"check_positive": True, "check_str_len": True},
        ),
    )
    first_res = verify_fixture(valid_workflow, fixture)
    assert first_res.success

    for _ in range(50):
        subsequent = verify_fixture(valid_workflow, fixture)
        assert subsequent.model_dump() == first_res.model_dump()


def test_verify_result_contains_traces_and_metadata(valid_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="trace_metadata_case",
        inputs={"val_a": 7},
    )
    result = verify_fixture(valid_workflow, fixture)
    assert result.success
    assert result.fixture_id == "trace_metadata_case"
    assert result.workflow_fingerprint is not None
    assert len(result.workflow_fingerprint) == 64  # SHA-256 hex
    assert len(result.traces) == 3
    assert result.traces[0].step == 0
    assert result.traces[1].step == 1
    assert result.traces[2].step == 2


def test_verify_workflow_assertion_expected_false_but_actual_true(base_workflow_data):
    # Workflow assertion passes (type_is string for to_str), but fixture expects False
    wf = parse_workflow(json.dumps(base_workflow_data), filename="wf.json")
    fixture = Fixture(
        fixture_version=1,
        id="assert_mismatch_false_true",
        inputs={"val_a": 10},
        expected=FixtureExpected(assertions={"check_str_len": False}),
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.ASSERTION_FAILED
    assert any(d.code == "WYS851" for d in result.diagnostics)


def test_verify_capability_policy_denial():
    wf_data = {
        "ir_version": 1,
        "name": "cap_wf",
        "inputs": {},
        "nodes": [
            {
                "id": "c",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "hi"},
                "output_type": "string",
            }
        ],
        "edges": [],
        "capabilities": ["network.http"],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "c"}, "type": "string"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")
    fixture = Fixture(fixture_version=1, id="f_cap", inputs={})
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.INVALID_WORKFLOW
    assert any(d.code == "WYS400" for d in result.diagnostics)


def test_verify_limit_exceeded():
    wf_data = {
        "ir_version": 1,
        "name": "limit_wf",
        "inputs": {
            "base_str": {"type": "string", "required": True},
        },
        "nodes": [
            {
                "id": "expander",
                "kind": "construct",
                "inputs": {"b": {"input": "base_str"}},
                "config": {"template": {"val": "{b}{b}{b}{b}{b}{b}{b}{b}{b}{b}{b}"}},
                "output_type": "object",
            }
        ],
        "edges": [
            {"source": {"input": "base_str"}, "target_node": "expander", "target_input": "b"}
        ],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "expander"}, "type": "object"}},
    }
    wf = parse_workflow(json.dumps(wf_data), filename="wf.json")
    fixture = Fixture(
        fixture_version=1,
        id="f_limit",
        inputs={"base_str": "x" * 100_000},
    )
    result = verify_fixture(wf, fixture)
    assert not result.success
    assert result.status == VerificationStatus.LIMIT_EXCEEDED
    assert any(d.code == "WYS853" for d in result.diagnostics)


def test_verify_diagnostic_ordering_deterministic(valid_workflow):
    # Multiple mismatched outputs should be sorted deterministically by path
    fixture = Fixture(
        fixture_version=1,
        id="multi_mismatch",
        inputs={"val_a": 42},
        expected=FixtureExpected(
            outputs={"raw_str": "wrong1", "result": {"bad": True}},
        ),
    )
    result = verify_fixture(valid_workflow, fixture)
    assert not result.success
    paths = [d.path for d in result.diagnostics]
    assert paths == sorted(paths)


def test_engine_passes_mocks_to_evaluator():
    wf_data = {
        "ir_version": 1,
        "name": "engine_mock_test",
        "inputs": {},
        "nodes": [
            {
                "id": "h1",
                "kind": "http",
                "inputs": {},
                "config": {"method": "GET", "url": "https://api.example.com"},
                "output_type": "string",
            },
            {
                "id": "out1",
                "kind": "output",
                "inputs": {"value": {"node": "h1"}},
                "config": {},
                "output_type": "string",
            },
        ],
        "edges": [
            {"source": {"node": "h1"}, "target_node": "out1", "target_input": "value"},
        ],
        "capabilities": ["network.http"],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "out1"}, "type": "string"}},
    }
    from pydantic import TypeAdapter

    from wysteria.ir.models import Workflow

    wf = TypeAdapter(Workflow).validate_python(wf_data)

    fix = Fixture(
        fixture_version=1,
        id="f1",
        inputs={},
        mocks={"h1": "mocked string"},
        expected={"outputs": {"res": "mocked string"}},
    )

    result = verify_fixture(wf, fix)
    assert result.success
    assert result.actual_outputs["res"] == "mocked string"


def test_engine_missing_mock_fails_verification():
    wf_data = {
        "ir_version": 1,
        "name": "engine_mock_test",
        "inputs": {},
        "nodes": [
            {
                "id": "h1",
                "kind": "http",
                "inputs": {},
                "config": {"method": "GET", "url": "https://api.example.com"},
                "output_type": "string",
            }
        ],
        "edges": [],
        "capabilities": ["network.http"],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "h1"}, "type": "string"}},
    }
    from pydantic import TypeAdapter

    from wysteria.ir.models import Workflow

    wf = TypeAdapter(Workflow).validate_python(wf_data)

    fix = Fixture(
        fixture_version=1,
        id="f1",
        inputs={},
        mocks={},  # Missing h1
        expected={},
    )

    result = verify_fixture(wf, fix)
    assert not result.success
    assert result.status == VerificationStatus.RUNTIME_ERROR
    assert len(result.diagnostics) > 0
    assert result.diagnostics[0].code == "WYS800"
    assert "missing mock" in result.diagnostics[0].message
