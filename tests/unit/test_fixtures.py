"""Comprehensive tests for deterministic fixture models, safe parsing, and compatibility validation."""

import json

import pytest

from wysteria.api import (
    CURRENT_FIXTURE_VERSION,
    Fixture,
    FixtureExpected,
    FixtureLoadError,
    FixtureParseError,
    load_fixture,
    parse_fixture,
    parse_workflow,
    validate_fixture,
    validate_fixture_compatibility,
    validate_fixture_structure,
    validate_workflow,
)
from wysteria.fixtures.parser import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_DEPTH,
    load_fixture_document,
    parse_fixture_document,
)
from wysteria.validation.capabilities import CapabilityPolicy


@pytest.fixture
def minimal_workflow():
    wf_data = {
        "ir_version": 1,
        "name": "sample_workflow",
        "inputs": {
            "name": {"type": "string", "required": True},
            "age": {"type": "integer", "required": False},
            "ratio": {"type": "number", "required": False},
        },
        "nodes": [
            {
                "id": "constant_node",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "hello"},
                "output_type": "string",
            },
            {
                "id": "check_name",
                "kind": "assert",
                "inputs": {"value": {"input": "name"}},
                "config": {"predicate": "exists"},
                "output_type": "boolean",
            },
        ],
        "edges": [
            {"source": {"input": "name"}, "target_node": "check_name", "target_input": "value"},
        ],
        "capabilities": [],
        "assertions": [
            {
                "id": "top_check",
                "source": {"node": "constant_node"},
                "predicate": "equals",
                "expected": "hello",
            }
        ],
        "outputs": {
            "greeting": {"source": {"node": "constant_node"}, "type": "string"},
            "is_valid": {"source": {"node": "check_name"}, "type": "boolean"},
        },
    }
    result = validate_workflow(parse_workflow(json.dumps(wf_data), filename="wf.json"))
    assert result.valid
    return result.workflow


@pytest.fixture
def http_workflow():
    wf_data = {
        "ir_version": 1,
        "name": "http_workflow",
        "inputs": {},
        "nodes": [
            {
                "id": "fetch_data",
                "kind": "http",
                "inputs": {},
                "config": {"method": "GET", "url": "https://api.example.com/data"},
                "output_type": "object",
            },
            {
                "id": "const_node",
                "kind": "constant",
                "inputs": {},
                "config": {"value": 123},
                "output_type": "integer",
            },
        ],
        "edges": [],
        "capabilities": ["network.http"],
        "assertions": [],
        "outputs": {"result": {"source": {"node": "fetch_data"}, "type": "object"}},
    }
    from wysteria.ir.models import Capability

    policy = CapabilityPolicy(allowed=frozenset({Capability.NETWORK_HTTP}))
    result = validate_workflow(
        parse_workflow(json.dumps(wf_data), filename="http_wf.json"), policy=policy
    )
    if not result.valid:
        print(result.diagnostics)
    assert result.valid
    return result.workflow


# --- Valid Fixture Parsing Tests ---


def test_valid_yaml_fixture():
    yaml_text = """
fixture_version: 1
id: basic_case
name: Basic Test Case
description: Tests valid greeting workflow
inputs:
  name: "Alice"
  age: 30
expected:
  outputs:
    greeting: "hello"
  assertions:
    top_check: true
    check_name: true
  error: null
"""
    fixture = parse_fixture(yaml_text, format="yaml")
    assert fixture.fixture_version == 1
    assert fixture.id == "basic_case"
    assert fixture.name == "Basic Test Case"
    assert fixture.description == "Tests valid greeting workflow"
    assert fixture.inputs == {"name": "Alice", "age": 30}
    assert fixture.expected.outputs == {"greeting": "hello"}
    assert fixture.expected.assertions == {"top_check": True, "check_name": True}
    assert fixture.expected.error is None


def test_valid_json_fixture():
    json_text = json.dumps(
        {
            "fixture_version": 1,
            "id": "json_case",
            "inputs": {"name": "Bob"},
            "expected": {
                "outputs": {"greeting": "hello"},
                "assertions": {"top_check": True},
                "error": None,
            },
        }
    )
    fixture = parse_fixture(json_text, format="json")
    assert fixture.id == "json_case"
    assert fixture.inputs == {"name": "Bob"}
    assert fixture.expected.outputs == {"greeting": "hello"}
    assert fixture.expected.assertions == {"top_check": True}


def test_valid_fixture_with_mocks():
    yaml_text = """
fixture_version: 1
id: mock_case
inputs: {}
mocks:
  fetch_data: {"status": "ok", "items": [1, 2, 3]}
"""
    fixture = parse_fixture(yaml_text, format="yaml")
    assert fixture.id == "mock_case"
    assert fixture.mocks == {"fetch_data": {"status": "ok", "items": [1, 2, 3]}}


def test_yaml_and_json_parsing_consistency():
    data = {
        "fixture_version": CURRENT_FIXTURE_VERSION,
        "id": "consistent_case",
        "name": "Consistency Check",
        "description": "Same data in YAML and JSON",
        "inputs": {"name": "Charlie", "age": 25},
        "expected": {
            "outputs": {"greeting": "hello"},
            "assertions": {"top_check": True},
            "error": None,
        },
    }
    yaml_text = f"""
fixture_version: {data["fixture_version"]}
id: {data["id"]}
name: {data["name"]}
description: {data["description"]}
inputs:
  name: "Charlie"
  age: 25
expected:
  outputs:
    greeting: "hello"
  assertions:
    top_check: true
"""
    json_text = json.dumps(data)

    from_yaml = parse_fixture(yaml_text, format="yaml")
    from_json = parse_fixture(json_text, format="json")

    assert from_yaml.model_dump() == from_json.model_dump()


def test_minimal_fixture_without_expected():
    yaml_text = """
fixture_version: 1
id: minimal_case
inputs:
  name: "Dave"
"""
    fixture = parse_fixture(yaml_text, format="yaml")
    assert fixture.id == "minimal_case"
    assert fixture.inputs == {"name": "Dave"}
    assert fixture.expected.outputs is None
    assert fixture.expected.assertions is None
    assert fixture.expected.error is None


def test_fixture_with_expected_error():
    yaml_text = """
fixture_version: 1
id: error_case
inputs:
  name: "Eve"
expected:
  error: "WYS801"
"""
    fixture = parse_fixture(yaml_text, format="yaml")
    assert fixture.expected.error == "WYS801"


# --- Parser Boundary & Malformed Fixture Tests (WYS700) ---


def test_malformed_yaml_syntax():
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture("fixture_version: [unclosed list", format="yaml")
    assert exc_info.value.code == "WYS700"


def test_malformed_json_syntax():
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture('{"fixture_version": 1, "id": ', format="json")
    assert exc_info.value.code == "WYS700"


def test_yaml_duplicate_keys_rejected():
    yaml_text = """
fixture_version: 1
id: dup1
id: dup2
inputs: {}
"""
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(yaml_text, format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "duplicate key" in str(exc_info.value)


def test_json_duplicate_keys_rejected():
    json_text = '{"fixture_version": 1, "id": "dup1", "id": "dup2", "inputs": {}}'
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(json_text, format="json")
    assert exc_info.value.code == "WYS700"
    assert "duplicate JSON object key" in str(exc_info.value)


def test_fixture_exceeds_size_limit():
    large_text = "fixture_version: 1\nid: large\ninputs:\n" + ("x: " + "a" * 1000 + "\n") * 1100
    assert len(large_text.encode("utf-8")) > MAX_DOCUMENT_BYTES
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(large_text, format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "byte limit" in str(exc_info.value)


def test_fixture_exceeds_depth_limit_yaml():
    deep_yaml = "a:\n" + "  " * 1 + "b:\n"
    for i in range(MAX_DOCUMENT_DEPTH + 5):
        deep_yaml += "  " * (i + 2) + f"k{i}:\n"
    deep_yaml += "  " * (MAX_DOCUMENT_DEPTH + 7) + "val: 1\n"
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(deep_yaml, format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "nesting depth" in str(exc_info.value)


def test_fixture_exceeds_depth_limit_json():
    deep_json = "{" * (MAX_DOCUMENT_DEPTH + 2) + "}" * (MAX_DOCUMENT_DEPTH + 2)
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(deep_json, format="json")
    assert exc_info.value.code == "WYS700"
    assert "nesting depth" in str(exc_info.value)


def test_yaml_aliases_and_anchors_rejected():
    yaml_text = """
fixture_version: 1
id: anchor_test
inputs:
  base: &default "hello"
  derived: *default
"""
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(yaml_text, format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "YAML aliases, anchors, and explicit tags are not permitted" in str(exc_info.value)


def test_yaml_explicit_tags_rejected():
    yaml_text = """
fixture_version: 1
id: tag_test
inputs:
  val: !!str 123
"""
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(yaml_text, format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "YAML aliases, anchors, and explicit tags are not permitted" in str(exc_info.value)


def test_yaml_scalar_outside_json_subset_rejected():
    yaml_text = """
fixture_version: 1
id: scalar_test
inputs:
  date: 2026-09-10
"""
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(yaml_text, format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "not in Wysteria's JSON-compatible scalar subset" in str(exc_info.value)


def test_json_non_finite_constant_rejected():
    json_text = '{"fixture_version": 1, "id": "test", "inputs": {"val": NaN}}'
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(json_text, format="json")
    assert exc_info.value.code == "WYS700"
    assert "non-finite JSON number is not permitted" in str(exc_info.value)


def test_json_unmatched_closing_delimiter():
    json_text = '{"fixture_version": 1, "id": "test", "inputs": {}}}'
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(json_text, format="json")
    assert exc_info.value.code == "WYS700"
    assert "unmatched closing delimiter" in str(exc_info.value)


def test_json_unclosed_string():
    json_text = '{"fixture_version": 1, "id": "test", "inputs": {"key": "unclosed}}'
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(json_text, format="json")
    assert exc_info.value.code == "WYS700"
    assert "unclosed string" in str(exc_info.value)


def test_root_must_be_mapping_yaml():
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture("- item1\n- item2", format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "root must be a mapping" in str(exc_info.value)


def test_root_must_be_object_json():
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture("[1, 2, 3]", format="json")
    assert exc_info.value.code == "WYS700"
    assert "root must be an object" in str(exc_info.value)


def test_empty_fixture_document():
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture("", format="yaml")
    assert exc_info.value.code == "WYS700"
    assert "empty" in str(exc_info.value)


def test_unsupported_format():
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture("fixture_version: 1", format="xml")
    assert exc_info.value.code == "WYS700"


# --- Structural Schema Validation Tests (WYS701) ---


def test_unknown_root_fields_rejected():
    yaml_text = """
fixture_version: 1
id: test_case
inputs: {}
unexpected_field: "bad"
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "WYS701"
    assert "unexpected_field" in diagnostics[0].path
    assert diagnostics[0].hint == "Remove the unsupported field."


def test_unknown_expected_fields_rejected():
    yaml_text = """
fixture_version: 1
id: test_case
inputs: {}
expected:
  bogus_key: 123
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "bogus_key" in d.path for d in diagnostics)


def test_wrong_fixture_version():
    yaml_text = """
fixture_version: 2
id: test_case
inputs: {}
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "WYS701"
    assert "/fixture_version" in diagnostics[0].path


def test_missing_required_fixture_version():
    yaml_text = """
id: test_case
inputs: {}
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "fixture_version" in d.path for d in diagnostics)


def test_missing_required_id():
    yaml_text = """
fixture_version: 1
inputs: {}
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "id" in d.path for d in diagnostics)


def test_invalid_id_pattern():
    yaml_text = """
fixture_version: 1
id: "123-leading-digit"
inputs: {}
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "id" in d.path for d in diagnostics)


def test_missing_required_inputs():
    yaml_text = """
fixture_version: 1
id: test_case
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "inputs" in d.path for d in diagnostics)


def test_expected_assertion_must_be_boolean():
    yaml_text = """
fixture_version: 1
id: test_case
inputs: {}
expected:
  assertions:
    check1: "not_a_boolean"
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "assertions" in d.path for d in diagnostics)


def test_expected_error_must_be_string():
    yaml_text = """
fixture_version: 1
id: test_case
inputs: {}
expected:
  error: 12345
"""
    parsed = parse_fixture_document(yaml_text, format="yaml")
    fixture, diagnostics = validate_fixture_structure(parsed)
    assert fixture is None
    assert any(d.code == "WYS701" and "error" in d.path for d in diagnostics)


def test_parse_fixture_raises_wys701_on_schema_error():
    yaml_text = """
fixture_version: 99
id: bad_ver
inputs: {}
"""
    with pytest.raises(FixtureParseError) as exc_info:
        parse_fixture(yaml_text, format="yaml")
    assert exc_info.value.code == "WYS701"


# --- File Loading Tests ---


def test_load_fixture_success(tmp_path):
    path = tmp_path / "valid.fixture.yaml"
    path.write_text(
        """
fixture_version: 1
id: file_case
inputs:
  name: "FileTest"
""",
        encoding="utf-8",
    )
    fixture = load_fixture(path)
    assert fixture.id == "file_case"
    assert fixture.inputs == {"name": "FileTest"}


def test_load_fixture_document_success(tmp_path):
    path = tmp_path / "valid.fixture.yaml"
    path.write_text(
        """
fixture_version: 1
id: file_case
inputs:
  name: "FileTest"
""",
        encoding="utf-8",
    )
    parsed = load_fixture_document(path)
    assert parsed.filename == str(path)
    assert "/id" in parsed.locations


def test_load_fixture_not_found(tmp_path):
    path = tmp_path / "nonexistent.yaml"
    with pytest.raises(FixtureLoadError, match="not a readable regular file"):
        load_fixture(path)


def test_load_fixture_directory_rejected(tmp_path):
    with pytest.raises(FixtureLoadError, match="not a readable regular file"):
        load_fixture(tmp_path)


# --- Workflow Compatibility Validation Tests (WYS702, WYS703) ---


def test_fixture_compatibility_valid(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case1",
        inputs={"name": "Alice", "age": 25},
        expected=FixtureExpected(
            outputs={"greeting": "hello"},
            assertions={"top_check": True, "check_name": True},
        ),
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert result.valid
    assert len(result.diagnostics) == 0


def test_fixture_compatibility_missing_required_input(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_missing_req",
        inputs={"age": 25},  # 'name' is required!
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS702"
    assert "missing required workflow input 'name'" in d.message
    assert d.path == "/inputs/name"


def test_fixture_compatibility_extra_undeclared_input(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_extra_input",
        inputs={"name": "Alice", "rogue_input": "intruder"},
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS702"
    assert "undeclared fixture input 'rogue_input'" in d.message
    assert d.path == "/inputs/rogue_input"


def test_fixture_compatibility_input_type_mismatch(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_type_mismatch",
        inputs={"name": 12345},  # name should be string!
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS702"
    assert "fixture input 'name' has type 'integer', expected 'string'" in d.message


def test_fixture_compatibility_number_accepts_integer(minimal_workflow):
    # 'ratio' is number; integer 5 should be accepted under Wysteria type compatibility
    fixture = Fixture(
        fixture_version=1,
        id="case_int_for_number",
        inputs={"name": "Alice", "ratio": 5},
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert result.valid


def test_fixture_compatibility_undeclared_expected_output(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_undeclared_output",
        inputs={"name": "Alice"},
        expected=FixtureExpected(outputs={"nonexistent_output": "val"}),
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS703"
    assert "expected output 'nonexistent_output' is not declared" in d.message
    assert d.path == "/expected/outputs/nonexistent_output"


def test_fixture_compatibility_wrong_expected_output_type(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_wrong_output_type",
        inputs={"name": "Alice"},
        expected=FixtureExpected(outputs={"greeting": 999}),  # greeting is string!
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS703"
    assert "expected output 'greeting' has type 'integer', expected 'string'" in d.message


def test_fixture_compatibility_undeclared_assertion(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_undeclared_assertion",
        inputs={"name": "Alice"},
        expected=FixtureExpected(assertions={"bogus_assertion": True}),
    )
    result = validate_fixture(fixture, minimal_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS703"
    assert "expected assertion 'bogus_assertion' does not match" in d.message
    assert d.path == "/expected/assertions/bogus_assertion"


def test_validate_fixture_compatibility_direct_returns_diagnostics(minimal_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_direct",
        inputs={"name": 123},
    )
    diagnostics = validate_fixture_compatibility(fixture, minimal_workflow)
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "WYS702"


def test_fixture_compatibility_mock_valid(http_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_mock_valid",
        inputs={},
        mocks={"fetch_data": {"id": 1, "name": "test"}},
    )
    result = validate_fixture(fixture, http_workflow)
    assert result.valid
    assert len(result.diagnostics) == 0


def test_fixture_compatibility_mock_undeclared_target(http_workflow):
    fixture = Fixture(
        fixture_version=1, id="case_mock_undeclared", inputs={}, mocks={"missing_node": {"id": 1}}
    )
    result = validate_fixture(fixture, http_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS704"
    assert "not declared in workflow nodes" in d.message
    assert d.path == "/mocks/missing_node"


def test_fixture_compatibility_mock_unmockable_node(http_workflow):
    fixture = Fixture(
        fixture_version=1, id="case_mock_unmockable", inputs={}, mocks={"const_node": 123}
    )
    result = validate_fixture(fixture, http_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS704"
    assert "not mockable" in d.message
    assert d.path == "/mocks/const_node"


def test_fixture_compatibility_mock_type_mismatch(http_workflow):
    fixture = Fixture(
        fixture_version=1,
        id="case_mock_type_mismatch",
        inputs={},
        mocks={"fetch_data": "a string instead of object"},
    )
    result = validate_fixture(fixture, http_workflow)
    assert not result.valid
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == "WYS704"
    assert "expected 'object'" in d.message
    assert d.path == "/mocks/fetch_data"
