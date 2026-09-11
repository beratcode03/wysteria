"""Deterministic, in-process workflow node evaluator."""

import json
import math
import re
from copy import deepcopy
from typing import Any

from wysteria.ir.models import (
    AssertNode,
    AssertPredicate,
    ConstantNode,
    ConstructNode,
    HttpNode,
    Node,
    OutputNode,
    SelectNode,
    TransformNode,
    TransformOperation,
    Workflow,
)
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.validation.common import has_errors
from wysteria.validation.graph import topological_sort
from wysteria.validation.semantic import _compatible, _value_type
from wysteria.verification.errors import RuntimeEvaluationError
from wysteria.verification.models import NodeExecutionTrace, WorkflowExecutionResult

MAX_DOCUMENT_DEPTH = 64
MAX_VALUE_BYTES = 1_000_000

_EXACT_PLACEHOLDER_REGEX = re.compile(r"^(?:\$)?\{([A-Za-z][A-Za-z0-9_-]*)\}$")
_ANY_PLACEHOLDER_REGEX = re.compile(r"(?:\$)?\{([A-Za-z][A-Za-z0-9_-]*)\}")
_INT_REGEX = re.compile(r"^-?(0|[1-9][0-9]*)$")
_ARRAY_INDEX_REGEX = re.compile(r"^(0|[1-9][0-9]*)$")


def strict_equals(a: Any, b: Any) -> bool:
    """Evaluate strict, type-safe equality without Python bool/int coercion."""

    # Explicit bool separation: bool is a subclass of int in Python
    if isinstance(a, bool) or isinstance(b, bool):
        if not (isinstance(a, bool) and isinstance(b, bool)):
            return False
        return a is b

    # Numeric equivalence: allow int == float only if numeric values are identical
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b

    if type(a) is not type(b):
        return False

    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(strict_equals(a[k], b[k]) for k in a)

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(strict_equals(x, y) for x, y in zip(a, b, strict=True))

    return a == b


def _to_deterministic_string(val: Any) -> str:
    """Format scalar or JSON values into deterministic string representations."""

    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, (dict, list)):
        return json.dumps(val, separators=(",", ":"), sort_keys=True)
    raise ValueError(f"unsupported type for string conversion: {type(val).__name__}")


def _check_value_size(val: Any, node_id: str) -> None:
    """Guard against memory amplification via oversized values."""

    if isinstance(val, str):
        if len(val.encode("utf-8")) > MAX_VALUE_BYTES:
            raise RuntimeEvaluationError(
                f"node '{node_id}' output string exceeds size limit of {MAX_VALUE_BYTES} bytes",
                code="WYS853",
                node_id=node_id,
            )
    elif isinstance(val, (dict, list)):
        try:
            serialized = json.dumps(val)
            if len(serialized.encode("utf-8")) > MAX_VALUE_BYTES:
                raise RuntimeEvaluationError(
                    f"node '{node_id}' output collection exceeds size limit of {MAX_VALUE_BYTES} bytes",
                    code="WYS853",
                    node_id=node_id,
                )
        except (TypeError, ValueError):
            pass


def _eval_construct_template(
    template: Any,
    resolved_inputs: dict[str, Any],
    node: ConstructNode,
    depth: int = 0,
) -> Any:
    """Recursively evaluate construct template with type preservation and scalar interpolation."""

    if depth > MAX_DOCUMENT_DEPTH:
        raise RuntimeEvaluationError(
            f"construct node '{node.id}' template nesting depth exceeds limit of {MAX_DOCUMENT_DEPTH}",
            code="WYS803",
            node_id=node.id,
        )

    if isinstance(template, str):
        # 1. Exact single placeholder: preserves raw value and type
        exact_match = _EXACT_PLACEHOLDER_REGEX.fullmatch(template)
        if exact_match:
            var_name = exact_match.group(1)
            if var_name not in resolved_inputs:
                raise RuntimeEvaluationError(
                    f"unresolved construct placeholder '{var_name}' in node '{node.id}'",
                    code="WYS803",
                    node_id=node.id,
                )
            return deepcopy(resolved_inputs[var_name])

        # 2. String interpolation: only scalars permitted
        if _ANY_PLACEHOLDER_REGEX.search(template):

            def replace_var(match: re.Match) -> str:
                var_name = match.group(1)
                if var_name not in resolved_inputs:
                    raise RuntimeEvaluationError(
                        f"unresolved construct placeholder '{var_name}' in node '{node.id}'",
                        code="WYS803",
                        node_id=node.id,
                    )
                val = resolved_inputs[var_name]
                if isinstance(val, (dict, list)):
                    raise RuntimeEvaluationError(
                        f"cannot interpolate complex value of type '{type(val).__name__}' "
                        f"for placeholder '{var_name}' into string in node '{node.id}'",
                        code="WYS803",
                        node_id=node.id,
                    )
                return _to_deterministic_string(val)

            res = _ANY_PLACEHOLDER_REGEX.sub(replace_var, template)
            _check_value_size(res, node.id)
            return res

        return template

    if isinstance(template, dict):
        new_dict: dict[str, Any] = {}
        for k, v in template.items():
            # Interpolate dictionary key if needed
            if _ANY_PLACEHOLDER_REGEX.search(k):

                def replace_key(match: re.Match) -> str:
                    var_name = match.group(1)
                    if var_name not in resolved_inputs:
                        raise RuntimeEvaluationError(
                            f"unresolved construct placeholder '{var_name}' in key of node '{node.id}'",
                            code="WYS803",
                            node_id=node.id,
                        )
                    val = resolved_inputs[var_name]
                    if isinstance(val, (dict, list)):
                        raise RuntimeEvaluationError(
                            f"cannot interpolate complex value of type '{type(val).__name__}' "
                            f"for key placeholder '{var_name}' in node '{node.id}'",
                            code="WYS803",
                            node_id=node.id,
                        )
                    return _to_deterministic_string(val)

                new_k = _ANY_PLACEHOLDER_REGEX.sub(replace_key, k)
            else:
                new_k = k

            if new_k in new_dict:
                raise RuntimeEvaluationError(
                    f"substituted dictionary key collision: '{new_k}' in node '{node.id}'",
                    code="WYS803",
                    node_id=node.id,
                )

            new_dict[new_k] = _eval_construct_template(v, resolved_inputs, node, depth + 1)
        return new_dict

    if isinstance(template, list):
        return [
            _eval_construct_template(item, resolved_inputs, node, depth + 1) for item in template
        ]

    return template


def _eval_select(node: SelectNode, resolved_inputs: dict[str, Any]) -> Any:
    """Traverse value using RFC 6901 JSON Pointer."""

    root = resolved_inputs.get("value")
    path = node.config.path

    if path == "":
        return deepcopy(root)

    # Path must start with /
    segments = path[1:].split("/")
    current = root

    for seg in segments:
        # RFC 6901 unescaping: replace ~1 with /, then ~0 with ~
        token = seg.replace("~1", "/").replace("~0", "~")

        if isinstance(current, dict):
            if token not in current:
                raise RuntimeEvaluationError(
                    f"JSON Pointer segment '{token}' not found in object (path: '{path}') in node '{node.id}'",
                    code="WYS801",
                    node_id=node.id,
                )
            current = current[token]
        elif isinstance(current, list):
            if not _ARRAY_INDEX_REGEX.fullmatch(token):
                raise RuntimeEvaluationError(
                    f"invalid JSON Pointer array index '{token}' (path: '{path}') in node '{node.id}'",
                    code="WYS801",
                    node_id=node.id,
                )
            idx = int(token)
            if idx < 0 or idx >= len(current):
                raise RuntimeEvaluationError(
                    f"JSON Pointer array index '{token}' out of range [0, {len(current)}) (path: '{path}') in node '{node.id}'",
                    code="WYS801",
                    node_id=node.id,
                )
            current = current[idx]
        else:
            raise RuntimeEvaluationError(
                f"cannot traverse JSON Pointer segment '{token}' on scalar value of type '{type(current).__name__}' "
                f"(path: '{path}') in node '{node.id}'",
                code="WYS801",
                node_id=node.id,
            )

    return deepcopy(current)


def _eval_transform(node: TransformNode, resolved_inputs: dict[str, Any]) -> Any:
    """Execute one pure TransformOperation."""

    val = resolved_inputs.get("value")
    op = node.config.operation

    if op == TransformOperation.IDENTITY:
        return deepcopy(val)

    if op == TransformOperation.LOWERCASE:
        if not isinstance(val, str):
            raise RuntimeEvaluationError(
                f"transform 'lowercase' requires string input, got '{type(val).__name__}' in node '{node.id}'",
                code="WYS802",
                node_id=node.id,
            )
        return val.lower()

    if op == TransformOperation.UPPERCASE:
        if not isinstance(val, str):
            raise RuntimeEvaluationError(
                f"transform 'uppercase' requires string input, got '{type(val).__name__}' in node '{node.id}'",
                code="WYS802",
                node_id=node.id,
            )
        return val.upper()

    if op == TransformOperation.TRIM:
        if not isinstance(val, str):
            raise RuntimeEvaluationError(
                f"transform 'trim' requires string input, got '{type(val).__name__}' in node '{node.id}'",
                code="WYS802",
                node_id=node.id,
            )
        return val.strip()

    if op == TransformOperation.TO_STRING:
        return _to_deterministic_string(val)

    if op == TransformOperation.TO_INTEGER:
        if isinstance(val, bool):
            return 1 if val else 0
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            if not math.isfinite(val) or not val.is_integer():
                raise RuntimeEvaluationError(
                    f"transform 'to_integer' cannot convert non-integral float {val} to integer in node '{node.id}'",
                    code="WYS802",
                    node_id=node.id,
                )
            return int(val)
        if isinstance(val, str):
            if not _INT_REGEX.fullmatch(val):
                raise RuntimeEvaluationError(
                    f"transform 'to_integer' cannot convert invalid integer string '{val}' in node '{node.id}'",
                    code="WYS802",
                    node_id=node.id,
                )
            return int(val)
        raise RuntimeEvaluationError(
            f"transform 'to_integer' cannot convert value of type '{type(val).__name__}' in node '{node.id}'",
            code="WYS802",
            node_id=node.id,
        )

    raise RuntimeEvaluationError(
        f"unsupported transform operation '{op}' in node '{node.id}'",
        code="WYS802",
        node_id=node.id,
    )


def _eval_assert(
    node: AssertNode, resolved_inputs: dict[str, Any]
) -> tuple[bool, list[Diagnostic]]:
    """Evaluate AssertNode predicate and return (boolean_result, diagnostics)."""

    val = resolved_inputs.get("value")
    pred = node.config.predicate
    expected = node.config.expected

    if pred == AssertPredicate.EXISTS:
        res = val is not None
    elif pred == AssertPredicate.EQUALS:
        res = strict_equals(val, expected)
    elif pred == AssertPredicate.TYPE_IS:
        actual_type = _value_type(val).value
        res = actual_type == expected
    else:
        raise RuntimeEvaluationError(
            f"unsupported assert predicate '{pred}' in node '{node.id}'",
            code="WYS800",
            node_id=node.id,
        )

    diagnostics: list[Diagnostic] = []
    if not res:
        diagnostics.append(
            Diagnostic(
                code="WYS850",
                severity=Severity.ERROR,
                message=f"AssertNode '{node.id}' evaluated to false",
                path=f"/nodes/{node.id}",
                hint=f"Predicate '{pred.value}' failed on input value.",
            )
        )

    return res, diagnostics


def evaluate_node(
    node: Node,
    resolved_inputs: dict[str, Any],
    mocks: dict[str, Any] | None = None,
) -> tuple[Any, list[Diagnostic]]:
    """Evaluate one node against resolved inputs, returning (output, diagnostics)."""

    diagnostics: list[Diagnostic] = []

    if isinstance(node, ConstantNode):
        output = deepcopy(node.config.value)

    elif isinstance(node, ConstructNode):
        output = _eval_construct_template(node.config.template, resolved_inputs, node)

    elif isinstance(node, SelectNode):
        output = _eval_select(node, resolved_inputs)

    elif isinstance(node, TransformNode):
        output = _eval_transform(node, resolved_inputs)

    elif isinstance(node, AssertNode):
        output, assert_diagnostics = _eval_assert(node, resolved_inputs)
        diagnostics.extend(assert_diagnostics)

    elif isinstance(node, OutputNode):
        val = resolved_inputs.get("value")
        actual_type = _value_type(val)
        if not _compatible(actual_type, node.output_type):
            raise RuntimeEvaluationError(
                f"output node '{node.id}' type mismatch: expected '{node.output_type.value}', got '{actual_type.value}'",
                code="WYS800",
                node_id=node.id,
            )
        output = deepcopy(val)

    elif isinstance(node, HttpNode):
        if mocks is None or node.id not in mocks:
            raise RuntimeEvaluationError(
                f"missing mock for HTTP node '{node.id}'",
                code="WYS800",
                node_id=node.id,
            )
        output = deepcopy(mocks[node.id])

    else:
        raise RuntimeEvaluationError(
            f"unsupported node kind '{type(node).__name__}' in node '{node.id}'",
            code="WYS800",
            node_id=node.id,
        )

    # Guard output size
    _check_value_size(output, node.id)

    # Runtime output type compatibility check (except AssertNode which is always bool)
    if not isinstance(node, AssertNode):
        actual_type = _value_type(output)
        if not _compatible(actual_type, node.output_type):
            raise RuntimeEvaluationError(
                f"node '{node.id}' evaluated to type '{actual_type.value}', which is incompatible with output_type '{node.output_type.value}'",
                code="WYS800",
                node_id=node.id,
            )

    return output, diagnostics


def evaluate_workflow(
    workflow: Workflow,
    inputs: dict[str, Any],
    mocks: dict[str, Any] | None = None,
) -> WorkflowExecutionResult:
    """Evaluate a workflow DAG in deterministic topological order against inputs."""

    context_inputs = deepcopy(inputs)
    node_values: dict[str, Any] = {}
    traces: list[NodeExecutionTrace] = []
    diagnostics: list[Diagnostic] = []

    node_map = {node.id: node for node in workflow.nodes}
    order = topological_sort(workflow)

    for step, node_id in enumerate(order):
        node = node_map[node_id]
        resolved_inputs: dict[str, Any] = {}

        try:
            for input_name, ref in node.inputs.items():
                if ref.input is not None:
                    if ref.input in context_inputs:
                        resolved_inputs[input_name] = context_inputs[ref.input]
                    else:
                        raise RuntimeEvaluationError(
                            f"unresolved input reference '{ref.input}' in node '{node.id}'",
                            code="WYS800",
                            node_id=node.id,
                            path=f"/nodes/{node.id}/inputs/{input_name}",
                        )
                elif ref.node is not None:
                    if ref.node in node_values:
                        resolved_inputs[input_name] = node_values[ref.node]
                    else:
                        raise RuntimeEvaluationError(
                            f"unresolved node reference '{ref.node}' in node '{node.id}'",
                            code="WYS800",
                            node_id=node.id,
                            path=f"/nodes/{node.id}/inputs/{input_name}",
                        )

            output, node_diagnostics = evaluate_node(node, resolved_inputs, mocks)
            diagnostics.extend(node_diagnostics)
            node_values[node.id] = output

            traces.append(
                NodeExecutionTrace(
                    step=step,
                    node_id=node.id,
                    kind=node.kind,
                    resolved_inputs=deepcopy(resolved_inputs),
                    output=deepcopy(output),
                )
            )

        except RuntimeEvaluationError as err:
            diagnostics.append(
                Diagnostic(
                    code=err.code,
                    severity=Severity.ERROR,
                    message=err.message,
                    path=err.path or f"/nodes/{err.node_id or node.id}",
                )
            )
            return WorkflowExecutionResult(
                success=False,
                node_values=node_values,
                traces=traces,
                diagnostics=diagnostics,
            )

    return WorkflowExecutionResult(
        success=not has_errors(diagnostics),
        node_values=node_values,
        traces=traces,
        diagnostics=diagnostics,
    )
