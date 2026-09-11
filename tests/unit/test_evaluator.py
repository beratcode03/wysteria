"""Comprehensive tests for deterministic workflow node evaluation and runtime execution."""

import json

import pytest

from wysteria.api import (
    RuntimeEvaluationError,
    evaluate_node,
    evaluate_workflow,
    parse_workflow,
    strict_equals,
    validate_workflow,
)
from wysteria.ir.models import (
    AssertConfig,
    AssertNode,
    AssertPredicate,
    ConstantConfig,
    ConstantNode,
    ConstructConfig,
    ConstructNode,
    HttpNode,
    HttpConfig,
    OutputNode,
    Reference,
    SelectConfig,
    SelectNode,
    TransformConfig,
    TransformNode,
    TransformOperation,
    ValueType,
    Workflow,
)


def _valid_workflow(wf_data: dict) -> Workflow:
    result = validate_workflow(parse_workflow(json.dumps(wf_data), filename="wf.json"))
    assert result.valid
    assert result.workflow is not None
    return result.workflow


# --- strict_equals Tests ---


def test_strict_equals_primitives():
    assert strict_equals(1, 1)
    assert strict_equals("a", "a")
    assert strict_equals(None, None)
    assert strict_equals(True, True)
    assert strict_equals(False, False)
    assert not strict_equals(True, False)
    assert not strict_equals(1, 2)
    assert not strict_equals("a", "b")


def test_strict_equals_bool_vs_int():
    # Python quirk: True == 1 and False == 0 is True in normal Python ==
    # In Wysteria strict_equals, they MUST be False!
    assert not strict_equals(True, 1)
    assert not strict_equals(1, True)
    assert not strict_equals(False, 0)
    assert not strict_equals(0, False)


def test_strict_equals_numeric_int_and_float():
    # Integral floats and ints are mathematically equivalent
    assert strict_equals(42, 42.0)
    assert strict_equals(42.0, 42)
    assert not strict_equals(42, 42.1)


def test_strict_equals_collections():
    assert strict_equals({"a": 1, "b": [2, 3]}, {"b": [2, 3], "a": 1.0})
    assert not strict_equals({"a": True}, {"a": 1})
    assert not strict_equals([1, 2], [1, 2, 3])


# --- 1. ConstantNode Tests ---


def test_constant_node_evaluates_value_unchanged():
    node = ConstantNode(
        id="c1",
        kind="constant",
        inputs={},
        config=ConstantConfig(value={"msg": "hello", "count": 5}),
        output_type=ValueType.OBJECT,
    )
    output, diagnostics = evaluate_node(node, {})
    assert diagnostics == []
    assert output == {"msg": "hello", "count": 5}


def test_constant_node_scalar():
    node = ConstantNode(
        id="c2",
        kind="constant",
        inputs={},
        config=ConstantConfig(value=100),
        output_type=ValueType.INTEGER,
    )
    output, diagnostics = evaluate_node(node, {})
    assert diagnostics == []
    assert output == 100


# --- 2. ConstructNode Tests ---


def test_construct_node_exact_placeholder_type_preservation():
    # Exact placeholder "${data}" must preserve integer, list, dict, bool types
    node = ConstructNode(
        id="b1",
        kind="construct",
        inputs={"num": Reference(input="in_num"), "flag": Reference(input="in_flag")},
        config=ConstructConfig(
            template={
                "exact_num": "${num}",
                "exact_flag": "{flag}",
                "nested": ["${num}", "{flag}"],
            }
        ),
        output_type=ValueType.OBJECT,
    )
    resolved = {"num": 42, "flag": True}
    output, diagnostics = evaluate_node(node, resolved)
    assert diagnostics == []
    assert output["exact_num"] == 42
    assert type(output["exact_num"]) is int
    assert output["exact_flag"] is True
    assert type(output["exact_flag"]) is bool
    assert output["nested"] == [42, True]


def test_construct_node_string_interpolation():
    node = ConstructNode(
        id="b2",
        kind="construct",
        inputs={"first": Reference(input="f"), "last": Reference(input="l")},
        config=ConstructConfig(
            template={
                "greeting": "Hello, {first} ${last}!",
                "count_msg": "Found {first} items.",
            }
        ),
        output_type=ValueType.OBJECT,
    )
    resolved = {"first": 5, "last": "Smith"}
    output, diagnostics = evaluate_node(node, resolved)
    assert diagnostics == []
    assert output["greeting"] == "Hello, 5 Smith!"
    assert output["count_msg"] == "Found 5 items."


def test_construct_node_rejection_of_complex_interpolation():
    # Attempting to interpolate a dict or list into a string must raise WYS803
    node = ConstructNode(
        id="b3",
        kind="construct",
        inputs={"items": Reference(input="it")},
        config=ConstructConfig(template={"message": "Your items: {items}"}),
        output_type=ValueType.OBJECT,
    )
    resolved = {"items": [1, 2, 3]}
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, resolved)
    assert exc_info.value.code == "WYS803"
    assert "cannot interpolate complex value" in str(exc_info.value)


def test_construct_node_key_collision():
    # Substituted keys colliding must fail with WYS803
    node = ConstructNode(
        id="b4",
        kind="construct",
        inputs={"k1": Reference(input="k1"), "k2": Reference(input="k2")},
        config=ConstructConfig(
            template={
                "{k1}": "val1",
                "{k2}": "val2",
            }
        ),
        output_type=ValueType.OBJECT,
    )
    resolved = {"k1": "same_key", "k2": "same_key"}
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, resolved)
    assert exc_info.value.code == "WYS803"
    assert "collision" in str(exc_info.value)


def test_construct_node_unresolved_placeholder():
    node = ConstructNode(
        id="b5",
        kind="construct",
        inputs={"k1": Reference(input="k1")},
        config=ConstructConfig(template={"msg": "{missing_placeholder}"}),
        output_type=ValueType.OBJECT,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"k1": "foo"})
    assert exc_info.value.code == "WYS803"
    assert "unresolved construct placeholder" in str(exc_info.value)


# --- 3. SelectNode Tests ---


def test_select_node_root_selection():
    node = SelectNode(
        id="s1",
        kind="select",
        inputs={"value": Reference(input="payload")},
        config=SelectConfig(path=""),
        output_type=ValueType.ANY,
    )
    data = {"a": 1, "b": 2}
    output, diagnostics = evaluate_node(node, {"value": data})
    assert diagnostics == []
    assert output == data


def test_select_node_nested_object_and_array():
    node = SelectNode(
        id="s2",
        kind="select",
        inputs={"value": Reference(input="payload")},
        config=SelectConfig(path="/users/1/name"),
        output_type=ValueType.STRING,
    )
    data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
    output, diagnostics = evaluate_node(node, {"value": data})
    assert diagnostics == []
    assert output == "Bob"


def test_select_node_rfc6901_escaping():
    node = SelectNode(
        id="s3",
        kind="select",
        inputs={"value": Reference(input="payload")},
        config=SelectConfig(path="/a~1b/c~0d"),
        output_type=ValueType.INTEGER,
    )
    data = {"a/b": {"c~d": 42}}
    output, diagnostics = evaluate_node(node, {"value": data})
    assert diagnostics == []
    assert output == 42


def test_select_node_missing_key_raises_wys801():
    node = SelectNode(
        id="s4",
        kind="select",
        inputs={"value": Reference(input="payload")},
        config=SelectConfig(path="/missing/key"),
        output_type=ValueType.ANY,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"value": {"other": 1}})
    assert exc_info.value.code == "WYS801"
    assert "not found" in str(exc_info.value)


def test_select_node_out_of_range_index_raises_wys801():
    node = SelectNode(
        id="s5",
        kind="select",
        inputs={"value": Reference(input="payload")},
        config=SelectConfig(path="/items/5"),
        output_type=ValueType.ANY,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"value": {"items": [1, 2]}})
    assert exc_info.value.code == "WYS801"
    assert "out of range" in str(exc_info.value)


def test_select_node_scalar_traversal_raises_wys801():
    node = SelectNode(
        id="s6",
        kind="select",
        inputs={"value": Reference(input="payload")},
        config=SelectConfig(path="/count/sub"),
        output_type=ValueType.ANY,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"value": {"count": 10}})
    assert exc_info.value.code == "WYS801"
    assert "cannot traverse" in str(exc_info.value)


# --- 4. TransformNode Tests ---


@pytest.mark.parametrize(
    ("op", "val", "expected", "out_type"),
    [
        (TransformOperation.IDENTITY, "hello", "hello", ValueType.STRING),
        (TransformOperation.LOWERCASE, "HeLLo WoRLD", "hello world", ValueType.STRING),
        (TransformOperation.UPPERCASE, "hello world", "HELLO WORLD", ValueType.STRING),
        (TransformOperation.TRIM, "  whitespace  \n", "whitespace", ValueType.STRING),
        (TransformOperation.TO_STRING, 123, "123", ValueType.STRING),
        (TransformOperation.TO_STRING, True, "true", ValueType.STRING),
        (TransformOperation.TO_STRING, False, "false", ValueType.STRING),
        (TransformOperation.TO_STRING, None, "null", ValueType.STRING),
        (TransformOperation.TO_INTEGER, "42", 42, ValueType.INTEGER),
        (TransformOperation.TO_INTEGER, "-10", -10, ValueType.INTEGER),
        (TransformOperation.TO_INTEGER, True, 1, ValueType.INTEGER),
        (TransformOperation.TO_INTEGER, False, 0, ValueType.INTEGER),
        (TransformOperation.TO_INTEGER, 99.0, 99, ValueType.INTEGER),
    ],
)
def test_transform_node_operations(op, val, expected, out_type):
    node = TransformNode(
        id="t1",
        kind="transform",
        inputs={"value": Reference(input="v")},
        config=TransformConfig(operation=op),
        output_type=out_type,
    )
    output, diagnostics = evaluate_node(node, {"value": val})
    assert diagnostics == []
    assert output == expected
    assert type(output) is type(expected)


def test_transform_to_integer_rejects_non_integral_float():
    node = TransformNode(
        id="t2",
        kind="transform",
        inputs={"value": Reference(input="v")},
        config=TransformConfig(operation=TransformOperation.TO_INTEGER),
        output_type=ValueType.INTEGER,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"value": 3.14})
    assert exc_info.value.code == "WYS802"
    assert "non-integral float" in str(exc_info.value)


def test_transform_to_integer_rejects_invalid_string():
    node = TransformNode(
        id="t3",
        kind="transform",
        inputs={"value": Reference(input="v")},
        config=TransformConfig(operation=TransformOperation.TO_INTEGER),
        output_type=ValueType.INTEGER,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"value": "42.0"})
    assert exc_info.value.code == "WYS802"
    assert "invalid integer string" in str(exc_info.value)


# --- 5. AssertNode Tests ---


def test_assert_node_exists():
    node = AssertNode(
        id="a1",
        kind="assert",
        inputs={"value": Reference(input="v")},
        config=AssertConfig(predicate=AssertPredicate.EXISTS),
        output_type=ValueType.BOOLEAN,
    )
    # Exists true
    out_true, diag_true = evaluate_node(node, {"value": "something"})
    assert out_true is True
    assert diag_true == []

    # Exists false (null)
    out_false, diag_false = evaluate_node(node, {"value": None})
    assert out_false is False
    assert len(diag_false) == 1
    assert diag_false[0].code == "WYS850"


def test_assert_node_equals_strict():
    node = AssertNode(
        id="a2",
        kind="assert",
        inputs={"value": Reference(input="v")},
        config=AssertConfig(predicate=AssertPredicate.EQUALS, expected=True),
        output_type=ValueType.BOOLEAN,
    )
    # Strict boolean true matches
    out, diag = evaluate_node(node, {"value": True})
    assert out is True
    assert diag == []

    # Integer 1 must NOT match True under strict equality!
    out_int, diag_int = evaluate_node(node, {"value": 1})
    assert out_int is False
    assert len(diag_int) == 1
    assert diag_int[0].code == "WYS850"


def test_assert_node_type_is():
    node = AssertNode(
        id="a3",
        kind="assert",
        inputs={"value": Reference(input="v")},
        config=AssertConfig(predicate=AssertPredicate.TYPE_IS, expected="integer"),
        output_type=ValueType.BOOLEAN,
    )
    # Integer value
    out_int, diag_int = evaluate_node(node, {"value": 42})
    assert out_int is True
    assert diag_int == []

    # Float value is number, not integer
    out_flt, diag_flt = evaluate_node(node, {"value": 42.5})
    assert out_flt is False
    assert len(diag_flt) == 1
    assert diag_flt[0].code == "WYS850"


# --- 6. OutputNode Tests ---


def test_output_node_passthrough():
    node = OutputNode(
        id="out1",
        kind="output",
        inputs={"value": Reference(input="v")},
        config={},
        output_type=ValueType.STRING,
    )
    output, diagnostics = evaluate_node(node, {"value": "passed through"})
    assert diagnostics == []
    assert output == "passed through"


def test_output_node_type_mismatch_raises_wys800():
    node = OutputNode(
        id="out2",
        kind="output",
        inputs={"value": Reference(input="v")},
        config={},
        output_type=ValueType.INTEGER,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {"value": "not an int"})
    assert exc_info.value.code == "WYS800"
    assert "type mismatch" in str(exc_info.value)


# --- Multi-node DAG & Workflow Evaluation Tests ---


def test_multi_node_dag_execution():
    # DAG:
    # 1. const1 ("  HELLO WORLD  ")
    # 2. trim_node (trim const1) -> "HELLO WORLD"
    # 3. lower_node (lowercase trim_node) -> "hello world"
    # 4. assert_node (equals "hello world") -> True
    # 5. construct_node (template with lower_node and assert_node)
    # 6. output_node (pass construct_node)
    wf_data = {
        "ir_version": 1,
        "name": "dag_workflow",
        "inputs": {},
        "nodes": [
            {
                "id": "const1",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "  HELLO WORLD  "},
                "output_type": "string",
            },
            {
                "id": "trim_node",
                "kind": "transform",
                "inputs": {"value": {"node": "const1"}},
                "config": {"operation": "trim"},
                "output_type": "string",
            },
            {
                "id": "lower_node",
                "kind": "transform",
                "inputs": {"value": {"node": "trim_node"}},
                "config": {"operation": "lowercase"},
                "output_type": "string",
            },
            {
                "id": "assert_node",
                "kind": "assert",
                "inputs": {"value": {"node": "lower_node"}},
                "config": {"predicate": "equals", "expected": "hello world"},
                "output_type": "boolean",
            },
            {
                "id": "builder",
                "kind": "construct",
                "inputs": {
                    "text": {"node": "lower_node"},
                    "verified": {"node": "assert_node"},
                },
                "config": {
                    "template": {
                        "result_text": "${text}",
                        "is_valid": "${verified}",
                    }
                },
                "output_type": "object",
            },
            {
                "id": "out_node",
                "kind": "output",
                "inputs": {"value": {"node": "builder"}},
                "config": {},
                "output_type": "object",
            },
        ],
        "edges": [
            {"source": {"node": "const1"}, "target_node": "trim_node", "target_input": "value"},
            {"source": {"node": "trim_node"}, "target_node": "lower_node", "target_input": "value"},
            {
                "source": {"node": "lower_node"},
                "target_node": "assert_node",
                "target_input": "value",
            },
            {"source": {"node": "lower_node"}, "target_node": "builder", "target_input": "text"},
            {
                "source": {"node": "assert_node"},
                "target_node": "builder",
                "target_input": "verified",
            },
            {"source": {"node": "builder"}, "target_node": "out_node", "target_input": "value"},
        ],
        "capabilities": [],
        "assertions": [],
        "outputs": {"final": {"source": {"node": "out_node"}, "type": "object"}},
    }
    wf = _valid_workflow(wf_data)
    result = evaluate_workflow(wf, {})

    assert result.success
    assert len(result.diagnostics) == 0
    assert result.node_values["const1"] == "  HELLO WORLD  "
    assert result.node_values["trim_node"] == "HELLO WORLD"
    assert result.node_values["lower_node"] == "hello world"
    assert result.node_values["assert_node"] is True
    assert result.node_values["builder"] == {
        "result_text": "hello world",
        "is_valid": True,
    }
    assert result.node_values["out_node"] == {
        "result_text": "hello world",
        "is_valid": True,
    }

    # Trace assertions
    assert len(result.traces) == 6
    assert result.traces[0].step == 0
    assert result.traces[0].node_id == "const1"
    assert result.traces[5].step == 5
    assert result.traces[5].node_id == "out_node"


def test_topological_execution_order_deterministic():
    # Tie-breaking with lexicographical node IDs:
    # Nodes 'z_const' and 'a_const' have in-degree 0.
    # Topological sort MUST evaluate 'a_const' before 'z_const'.
    wf_data = {
        "ir_version": 1,
        "name": "topo_workflow",
        "inputs": {},
        "nodes": [
            {
                "id": "z_const",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "z"},
                "output_type": "string",
            },
            {
                "id": "a_const",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "a"},
                "output_type": "string",
            },
            {
                "id": "collector",
                "kind": "construct",
                "inputs": {
                    "first": {"node": "a_const"},
                    "second": {"node": "z_const"},
                },
                "config": {"template": ["${first}", "${second}"]},
                "output_type": "array",
            },
        ],
        "edges": [
            {"source": {"node": "a_const"}, "target_node": "collector", "target_input": "first"},
            {"source": {"node": "z_const"}, "target_node": "collector", "target_input": "second"},
        ],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "collector"}, "type": "array"}},
    }
    wf = _valid_workflow(wf_data)
    result = evaluate_workflow(wf, {})
    assert result.success
    executed_ids = [t.node_id for t in result.traces]
    assert executed_ids == ["a_const", "z_const", "collector"]


def test_assert_node_false_records_wys850_without_corrupting_node_values():
    wf_data = {
        "ir_version": 1,
        "name": "assert_false_wf",
        "inputs": {"val": {"type": "integer"}},
        "nodes": [
            {
                "id": "check_val",
                "kind": "assert",
                "inputs": {"value": {"input": "val"}},
                "config": {"predicate": "equals", "expected": 100},
                "output_type": "boolean",
            },
            {
                "id": "construct_downstream",
                "kind": "construct",
                "inputs": {"status": {"node": "check_val"}},
                "config": {"template": {"status": "${status}"}},
                "output_type": "object",
            },
        ],
        "edges": [
            {"source": {"input": "val"}, "target_node": "check_val", "target_input": "value"},
            {
                "source": {"node": "check_val"},
                "target_node": "construct_downstream",
                "target_input": "status",
            },
        ],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "construct_downstream"}, "type": "object"}},
    }
    wf = _valid_workflow(wf_data)
    # val is 99 != 100
    result = evaluate_workflow(wf, {"val": 99})

    # Evaluator completed all nodes
    assert result.node_values["check_val"] is False
    assert result.node_values["construct_downstream"] == {"status": False}
    # Success is False because WYS850 diagnostic was recorded
    assert not result.success
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "WYS850"
    assert "check_val" in result.diagnostics[0].message


def test_unresolved_reference_handling():
    # If inputs dictionary is missing a required input
    wf_data = {
        "ir_version": 1,
        "name": "missing_ref_wf",
        "inputs": {"needed": {"type": "string"}},
        "nodes": [
            {
                "id": "out",
                "kind": "output",
                "inputs": {"value": {"input": "needed"}},
                "config": {},
                "output_type": "string",
            }
        ],
        "edges": [
            {"source": {"input": "needed"}, "target_node": "out", "target_input": "value"},
        ],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "out"}, "type": "string"}},
    }
    wf = _valid_workflow(wf_data)
    # Provide empty inputs
    result = evaluate_workflow(wf, {})
    assert not result.success
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "WYS800"
    assert "unresolved input reference" in result.diagnostics[0].message


def test_repeated_execution_deterministic_traces_and_values():
    wf_data = {
        "ir_version": 1,
        "name": "repeat_wf",
        "inputs": {"num": {"type": "integer"}},
        "nodes": [
            {
                "id": "b",
                "kind": "transform",
                "inputs": {"value": {"input": "num"}},
                "config": {"operation": "to_string"},
                "output_type": "string",
            },
            {
                "id": "a",
                "kind": "constant",
                "inputs": {},
                "config": {"value": "prefix_"},
                "output_type": "string",
            },
            {
                "id": "c",
                "kind": "construct",
                "inputs": {"pre": {"node": "a"}, "num_str": {"node": "b"}},
                "config": {"template": {"result": "{pre}{num_str}"}},
                "output_type": "object",
            },
        ],
        "edges": [
            {"source": {"input": "num"}, "target_node": "b", "target_input": "value"},
            {"source": {"node": "a"}, "target_node": "c", "target_input": "pre"},
            {"source": {"node": "b"}, "target_node": "c", "target_input": "num_str"},
        ],
        "capabilities": [],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "c"}, "type": "object"}},
    }
    wf = _valid_workflow(wf_data)
    inputs = {"num": 42}

    first_result = evaluate_workflow(wf, inputs)
    for _ in range(50):
        subsequent = evaluate_workflow(wf, inputs)
        assert subsequent.model_dump() == first_result.model_dump()


def test_max_value_size_limit_rejection():
    # String exceeding 1MB produces WYS853
    node = ConstantNode(
        id="huge_const",
        kind="constant",
        inputs={},
        config=ConstantConfig(value="x" * 1_000_001),
        output_type=ValueType.STRING,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {})
    assert exc_info.value.code == "WYS853"
    assert "exceeds size limit" in str(exc_info.value)


# --- 7. HttpNode Mock Tests ---


def test_http_node_object_mock_success():
    node = HttpNode(
        id="h1",
        kind="http",
        inputs={},
        config=HttpConfig(method="GET", url="https://api.example.com/data"),
        output_type=ValueType.OBJECT,
    )
    mocks = {"h1": {"status": 200, "body": {"hello": "world"}}}
    output, diagnostics = evaluate_node(node, {}, mocks=mocks)
    assert diagnostics == []
    assert output == {"status": 200, "body": {"hello": "world"}}


def test_http_node_scalar_array_mock_success():
    node = HttpNode(
        id="h2",
        kind="http",
        inputs={},
        config=HttpConfig(method="GET", url="https://api.example.com/arr"),
        output_type=ValueType.ARRAY,
    )
    mocks = {"h2": [1, 2, 3]}
    output, diagnostics = evaluate_node(node, {}, mocks=mocks)
    assert diagnostics == []
    assert output == [1, 2, 3]


def test_http_node_missing_mock_raises_wys800():
    node = HttpNode(
        id="h3",
        kind="http",
        inputs={},
        config=HttpConfig(method="GET", url="https://api.example.com/data"),
        output_type=ValueType.OBJECT,
    )
    mocks = {"other": {}}
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {}, mocks=mocks)
    assert exc_info.value.code == "WYS800"
    assert "missing mock for HTTP node" in str(exc_info.value)


def test_http_node_mocks_none_raises_wys800():
    node = HttpNode(
        id="h4",
        kind="http",
        inputs={},
        config=HttpConfig(method="GET", url="https://api.example.com/data"),
        output_type=ValueType.OBJECT,
    )
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {}, mocks=None)
    assert exc_info.value.code == "WYS800"
    assert "missing mock for HTTP node" in str(exc_info.value)


def test_http_node_incompatible_mock_type_rejected_by_existing_validation():
    node = HttpNode(
        id="h5",
        kind="http",
        inputs={},
        config=HttpConfig(method="GET", url="https://api.example.com/data"),
        output_type=ValueType.OBJECT,
    )
    mocks = {"h5": "this is a string, not an object"}
    with pytest.raises(RuntimeEvaluationError) as exc_info:
        evaluate_node(node, {}, mocks=mocks)
    assert exc_info.value.code == "WYS800"
    assert "incompatible with output_type" in str(exc_info.value)


def test_http_node_feeds_downstream_nodes():
    wf_data = {
        "ir_version": 1,
        "name": "mocked_http_wf",
        "inputs": {},
        "nodes": [
            {
                "id": "http1",
                "kind": "http",
                "inputs": {},
                "config": {"method": "GET", "url": "https://api.example.com"},
                "output_type": "object",
            },
            {
                "id": "sel1",
                "kind": "select",
                "inputs": {"value": {"node": "http1"}},
                "config": {"path": "/body/value"},
                "output_type": "integer",
            },
            {
                "id": "trans1",
                "kind": "transform",
                "inputs": {"value": {"node": "sel1"}},
                "config": {"operation": "to_string"},
                "output_type": "string",
            },
            {
                "id": "out1",
                "kind": "output",
                "inputs": {"value": {"node": "trans1"}},
                "config": {},
                "output_type": "string",
            },
        ],
        "edges": [
            {"source": {"node": "http1"}, "target_node": "sel1", "target_input": "value"},
            {"source": {"node": "sel1"}, "target_node": "trans1", "target_input": "value"},
            {"source": {"node": "trans1"}, "target_node": "out1", "target_input": "value"},
        ],
        "capabilities": ["network.http"],
        "assertions": [],
        "outputs": {"res": {"source": {"node": "out1"}, "type": "string"}},
    }
    from pydantic import TypeAdapter
    from wysteria.ir.models import Workflow

    wf = TypeAdapter(Workflow).validate_python(wf_data)
    mocks = {"http1": {"status": 200, "body": {"value": 42}}}
    result = evaluate_workflow(wf, {}, mocks=mocks)

    assert result.success
    assert result.node_values["http1"] == {"status": 200, "body": {"value": 42}}
    assert result.node_values["sel1"] == 42
    assert result.node_values["trans1"] == "42"
    assert result.node_values["out1"] == "42"


def test_multiple_http_nodes_use_own_mocks():
    wf_data = {
        "ir_version": 1,
        "name": "multi_mock",
        "inputs": {},
        "nodes": [
            {
                "id": "h1",
                "kind": "http",
                "inputs": {},
                "config": {"method": "GET", "url": "https://api.example.com/1"},
                "output_type": "string",
            },
            {
                "id": "h2",
                "kind": "http",
                "inputs": {},
                "config": {"method": "GET", "url": "https://api.example.com/2"},
                "output_type": "string",
            },
            {
                "id": "out",
                "kind": "output",
                "inputs": {"value": {"node": "h2"}},
                "config": {},
                "output_type": "string",
            },
        ],
        "edges": [
            {"source": {"node": "h2"}, "target_node": "out", "target_input": "value"},
        ],
        "capabilities": ["network.http"],
        "assertions": [],
        "outputs": {
            "r1": {"source": {"node": "h1"}, "type": "string"},
            "r2": {"source": {"node": "out"}, "type": "string"},
        },
    }
    from pydantic import TypeAdapter
    from wysteria.ir.models import Workflow

    wf = TypeAdapter(Workflow).validate_python(wf_data)
    mocks = {"h1": "response1", "h2": "response2"}
    result = evaluate_workflow(wf, {}, mocks=mocks)
    assert result.success
    assert result.node_values["h1"] == "response1"
    assert result.node_values["h2"] == "response2"
