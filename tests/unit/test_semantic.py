import json

import pytest

from wysteria.api import parse_workflow, validate_workflow


def validate(data: dict):
    return validate_workflow(parse_workflow(json.dumps(data), filename="workflow.json"))


def codes(result):
    return {item.code for item in result.diagnostics}


# --- SelectNode and JSON Pointer Tests ---


@pytest.mark.parametrize(
    "valid_path",
    [
        "",
        "/",
        "/key",
        "/users/0/name",
        "/a~1b/c~0d",
        "/nested/array/12/field",
    ],
)
def test_valid_json_pointer_paths(workflow_data, valid_path):
    workflow_data["inputs"]["payload"] = {"type": "object"}
    workflow_data["nodes"] = [
        {
            "id": "selector",
            "kind": "select",
            "inputs": {"value": {"input": "payload"}},
            "config": {"path": valid_path},
            "output_type": "any",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "payload"}, "target_node": "selector", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "selector"}, "type": "any"}
    assert validate(workflow_data).valid


@pytest.mark.parametrize(
    "invalid_path",
    [
        "no_leading_slash",
        "/bad~2escape",
        "/trailing~",
        "/another/~3/bad",
        "relative/path",
    ],
)
def test_invalid_json_pointer_paths(workflow_data, invalid_path):
    workflow_data["inputs"]["payload"] = {"type": "object"}
    workflow_data["nodes"] = [
        {
            "id": "selector",
            "kind": "select",
            "inputs": {"value": {"input": "payload"}},
            "config": {"path": invalid_path},
            "output_type": "any",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "payload"}, "target_node": "selector", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "selector"}, "type": "any"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS506" in codes(result)


def test_select_input_type_must_be_indexable(workflow_data):
    # Input is integer, path is /field -> scalar cannot be selected into
    workflow_data["inputs"]["num"] = {"type": "integer"}
    workflow_data["nodes"] = [
        {
            "id": "selector",
            "kind": "select",
            "inputs": {"value": {"input": "num"}},
            "config": {"path": "/field"},
            "output_type": "any",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "num"}, "target_node": "selector", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "selector"}, "type": "any"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS507" in codes(result)


# --- Transform Node Tests ---


def test_transform_output_type_mismatch_for_string_ops(workflow_data):
    # uppercase operation cannot produce integer output
    workflow_data["nodes"] = [
        {
            "id": "tr",
            "kind": "transform",
            "inputs": {"value": {"input": "name"}},
            "config": {"operation": "uppercase"},
            "output_type": "integer",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "tr", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "tr"}, "type": "integer"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS508" in codes(result)


def test_transform_to_string_output_type_mismatch(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "tr",
            "kind": "transform",
            "inputs": {"value": {"input": "name"}},
            "config": {"operation": "to_string"},
            "output_type": "boolean",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "tr", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "tr"}, "type": "boolean"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS508" in codes(result)


def test_transform_to_integer_output_and_input_checks(workflow_data):
    # Output type must be integer/number
    workflow_data["nodes"] = [
        {
            "id": "tr",
            "kind": "transform",
            "inputs": {"value": {"input": "name"}},
            "config": {"operation": "to_integer"},
            "output_type": "string",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "tr", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "tr"}, "type": "string"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS508" in codes(result)

    # Input type cannot be object
    workflow_data["inputs"]["obj"] = {"type": "object"}
    workflow_data["nodes"][0]["inputs"]["value"] = {"input": "obj"}
    workflow_data["nodes"][0]["output_type"] = "integer"
    workflow_data["edges"] = [
        {"source": {"input": "obj"}, "target_node": "tr", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"]["type"] = "integer"
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS504" in codes(result)


# --- Construct Template Placeholder Tests ---


def test_construct_template_with_valid_placeholders(workflow_data):
    workflow_data["inputs"]["greeting"] = {"type": "string"}
    workflow_data["nodes"] = [
        {
            "id": "builder",
            "kind": "construct",
            "inputs": {
                "name": {"input": "name"},
                "greeting": {"input": "greeting"},
            },
            "config": {
                "template": {
                    "message": "{greeting}, {name}!",
                    "alt": "${greeting}",
                    "list": ["item", "{name}"],
                }
            },
            "output_type": "object",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "builder", "target_input": "name"},
        {"source": {"input": "greeting"}, "target_node": "builder", "target_input": "greeting"},
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "builder"}, "type": "object"}
    assert validate(workflow_data).valid


def test_construct_template_with_undeclared_placeholder(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "builder",
            "kind": "construct",
            "inputs": {"name": {"input": "name"}},
            "config": {
                "template": {
                    "message": "{name} and {missing_friend}",
                }
            },
            "output_type": "object",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "builder", "target_input": "name"},
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "builder"}, "type": "object"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS509" in codes(result)
    assert any("missing_friend" in d.message for d in result.diagnostics)


# --- AssertNode Tests ---


def test_assert_node_exists_with_unexpected_expected_value(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "check",
            "kind": "assert",
            "inputs": {"value": {"input": "name"}},
            "config": {"predicate": "exists", "expected": "cannot_be_here"},
            "output_type": "boolean",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "check", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "check"}, "type": "boolean"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS510" in codes(result)


def test_assert_node_type_is_with_invalid_type_name(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "check",
            "kind": "assert",
            "inputs": {"value": {"input": "name"}},
            "config": {"predicate": "type_is", "expected": "invalid_type_123"},
            "output_type": "boolean",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "check", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "check"}, "type": "boolean"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS510" in codes(result)


# --- OutputNode Tests ---


def test_output_node_semantics():
    valid_wf = {
        "ir_version": 1,
        "name": "sample",
        "inputs": {"val": {"type": "string"}},
        "nodes": [
            {
                "id": "out_node",
                "kind": "output",
                "inputs": {"value": {"input": "val"}},
                "config": {},
                "output_type": "string",
            }
        ],
        "edges": [{"source": {"input": "val"}, "target_node": "out_node", "target_input": "value"}],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "out_node"}, "type": "string"}},
    }
    assert validate(valid_wf).valid

    # Missing value input
    invalid_missing = json.loads(json.dumps(valid_wf))
    invalid_missing["nodes"][0]["inputs"] = {}
    invalid_missing["edges"] = []
    assert "WYS502" in codes(validate(invalid_missing))

    # Incompatible output type
    invalid_type = json.loads(json.dumps(valid_wf))
    invalid_type["nodes"][0]["output_type"] = "integer"
    invalid_type["outputs"]["res"]["type"] = "integer"
    assert "WYS511" in codes(validate(invalid_type))

    # Single non-value input is rejected (regression test)
    invalid_non_value = json.loads(json.dumps(valid_wf))
    invalid_non_value["nodes"][0]["inputs"] = {"foo": {"input": "val"}}
    invalid_non_value["edges"] = [
        {"source": {"input": "val"}, "target_node": "out_node", "target_input": "foo"}
    ]
    res_non_value = validate(invalid_non_value)
    assert not res_non_value.valid
    assert "WYS511" in codes(res_non_value)
    assert any("inputs other than 'value'" in d.message for d in res_non_value.diagnostics)


def test_output_node_rejects_single_non_value_input():
    wf = {
        "ir_version": 1,
        "name": "sample",
        "inputs": {"val": {"type": "string"}},
        "nodes": [
            {
                "id": "out_node",
                "kind": "output",
                "inputs": {"foo": {"input": "val"}},
                "config": {},
                "output_type": "string",
            }
        ],
        "edges": [{"source": {"input": "val"}, "target_node": "out_node", "target_input": "foo"}],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "out_node"}, "type": "string"}},
    }
    result = validate(wf)
    assert not result.valid
    assert "WYS511" in codes(result)
    assert any("inputs other than 'value'" in d.message for d in result.diagnostics)


def test_select_node_rejects_forbidden_inputs(workflow_data):
    workflow_data["inputs"]["payload"] = {"type": "object"}
    workflow_data["nodes"] = [
        {
            "id": "selector",
            "kind": "select",
            "inputs": {
                "value": {"input": "payload"},
                "extra": {"input": "payload"},
            },
            "config": {"path": ""},
            "output_type": "any",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "payload"}, "target_node": "selector", "target_input": "value"},
        {"source": {"input": "payload"}, "target_node": "selector", "target_input": "extra"},
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "selector"}, "type": "any"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS507" in codes(result)
    assert any("inputs other than 'value'" in d.message for d in result.diagnostics)


def test_transform_node_rejects_forbidden_inputs(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "tr",
            "kind": "transform",
            "inputs": {
                "value": {"input": "name"},
                "extra": {"input": "name"},
            },
            "config": {"operation": "lowercase"},
            "output_type": "string",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "tr", "target_input": "value"},
        {"source": {"input": "name"}, "target_node": "tr", "target_input": "extra"},
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "tr"}, "type": "string"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS504" in codes(result)
    assert any("inputs other than 'value'" in d.message for d in result.diagnostics)


def test_assert_node_rejects_forbidden_inputs(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "check",
            "kind": "assert",
            "inputs": {
                "value": {"input": "name"},
                "extra": {"input": "name"},
            },
            "config": {"predicate": "exists"},
            "output_type": "boolean",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "check", "target_input": "value"},
        {"source": {"input": "name"}, "target_node": "check", "target_input": "extra"},
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "check"}, "type": "boolean"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS510" in codes(result)
    assert any("inputs other than 'value'" in d.message for d in result.diagnostics)


def test_assert_node_output_type_constraints(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "check",
            "kind": "assert",
            "inputs": {"value": {"input": "name"}},
            "config": {"predicate": "exists"},
            "output_type": "string",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "check", "target_input": "value"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "check"}, "type": "string"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS510" in codes(result)
    assert any("boolean or any output" in d.message for d in result.diagnostics)

    # Output type "any" is permitted
    workflow_data["nodes"][0]["output_type"] = "any"
    workflow_data["outputs"]["result"]["type"] = "any"
    assert validate(workflow_data).valid


def test_construct_node_output_type_constraints(workflow_data):
    # Object template with array output_type
    workflow_data["nodes"] = [
        {
            "id": "builder",
            "kind": "construct",
            "inputs": {"name": {"input": "name"}},
            "config": {"template": {"message": "{name}"}},
            "output_type": "array",
        }
    ]
    workflow_data["edges"] = [
        {"source": {"input": "name"}, "target_node": "builder", "target_input": "name"}
    ]
    workflow_data["outputs"]["result"] = {"source": {"node": "builder"}, "type": "array"}
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS503" in codes(result)

    # Array template with object output_type
    workflow_data["nodes"][0]["config"]["template"] = ["{name}"]
    workflow_data["nodes"][0]["output_type"] = "object"
    workflow_data["outputs"]["result"]["type"] = "object"
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS503" in codes(result)

    # Array template with any output_type is valid
    workflow_data["nodes"][0]["output_type"] = "any"
    workflow_data["outputs"]["result"]["type"] = "any"
    assert validate(workflow_data).valid


def test_top_level_output_type_mismatch(workflow_data):
    # Constant node produces string, output declares integer
    workflow_data["outputs"]["result"]["type"] = "integer"
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS505" in codes(result)


# --- Top-level Assertions Tests ---


def test_top_level_assertion_duplicate_ids(workflow_data):
    workflow_data["assertions"] = [
        {
            "id": "same_id",
            "source": {"node": "constant"},
            "predicate": "exists",
            "expected": None,
        },
        {
            "id": "same_id",
            "source": {"node": "constant"},
            "predicate": "exists",
            "expected": None,
        },
    ]
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS512" in codes(result)


def test_top_level_assertion_predicate_mismatch(workflow_data):
    # exists predicate cannot have expected value
    workflow_data["assertions"] = [
        {
            "id": "chk1",
            "source": {"node": "constant"},
            "predicate": "exists",
            "expected": "hello",
        },
    ]
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS513" in codes(result)

    # type_is predicate requires valid type name
    workflow_data["assertions"] = [
        {
            "id": "chk2",
            "source": {"node": "constant"},
            "predicate": "type_is",
            "expected": "bogus",
        },
    ]
    result = validate(workflow_data)
    assert not result.valid
    assert "WYS513" in codes(result)


# --- Capability Enforcement Tests ---


def test_http_node_requires_capability(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "http_fetch",
            "kind": "http",
            "inputs": {},
            "config": {"method": "GET", "url": "https://example.com"},
            "output_type": "any",
        }
    ]
    workflow_data["edges"] = []
    workflow_data["outputs"]["result"] = {"source": {"node": "http_fetch"}, "type": "any"}
    workflow_data["capabilities"] = []

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS514" in codes(result)
    assert any("requires capability 'network.http'" in d.message for d in result.diagnostics)

    workflow_data["capabilities"] = ["network.http"]
    assert "WYS514" not in codes(validate(workflow_data))


def test_file_read_node_requires_capability(workflow_data):
    workflow_data["nodes"] = [
        {
            "id": "read_cfg",
            "kind": "file_read",
            "inputs": {},
            "config": {"path": "/etc/config.json"},
            "output_type": "any",
        }
    ]
    workflow_data["edges"] = []
    workflow_data["outputs"]["result"] = {"source": {"node": "read_cfg"}, "type": "any"}
    workflow_data["capabilities"] = []

    result = validate(workflow_data)
    assert not result.valid
    assert "WYS514" in codes(result)
    assert any("requires capability 'file.read'" in d.message for d in result.diagnostics)

    workflow_data["capabilities"] = ["file.read"]
    assert "WYS514" not in codes(validate(workflow_data))
