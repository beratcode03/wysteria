"""Small semantic validation for the fixed deterministic node vocabulary."""

import re
from typing import Any

from wysteria.ir.models import (
    AssertNode,
    AssertPredicate,
    Capability,
    ConstantNode,
    ConstructNode,
    FileReadNode,
    HttpNode,
    OutputNode,
    Reference,
    SelectNode,
    TransformNode,
    TransformOperation,
    ValueType,
    Workflow,
)
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic

_JSON_POINTER_REGEX = re.compile(r"^(/([^/~]|~[01])*)*$")
_PLACEHOLDER_REGEX = re.compile(r"(?:\$)?\{([A-Za-z][A-Za-z0-9_-]*)\}")


def _extract_placeholders(value: Any) -> set[str]:
    """Recursively find all {var} or ${var} placeholders in a template."""
    placeholders: set[str] = set()
    if isinstance(value, str):
        placeholders.update(_PLACEHOLDER_REGEX.findall(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            placeholders.update(_extract_placeholders(k))
            placeholders.update(_extract_placeholders(v))
    elif isinstance(value, list):
        for item in value:
            placeholders.update(_extract_placeholders(item))
    return placeholders


def _value_type(value: Any) -> ValueType:
    if value is None:
        return ValueType.NULL
    if isinstance(value, bool):
        return ValueType.BOOLEAN
    if isinstance(value, int):
        return ValueType.INTEGER
    if isinstance(value, float):
        return ValueType.NUMBER
    if isinstance(value, str):
        return ValueType.STRING
    if isinstance(value, list):
        return ValueType.ARRAY
    return ValueType.OBJECT


def _compatible(source: ValueType, expected: ValueType) -> bool:
    return (
        expected == ValueType.ANY
        or source == expected
        or (source == ValueType.INTEGER and expected == ValueType.NUMBER)
    )


def validate_semantics(
    workflow: Workflow, parsed: ParsedWorkflow | None = None
) -> list[Diagnostic]:
    """Validate node-specific deterministic constraints and reference types."""

    diagnostics: list[Diagnostic] = []
    input_types = {name: spec.type for name, spec in workflow.inputs.items()}
    node_types = {node.id: node.output_type for node in workflow.nodes}

    def get_source_type(ref: Reference | None) -> ValueType:
        if ref is None:
            return ValueType.ANY
        if ref.input is not None:
            return input_types.get(ref.input, ValueType.ANY)
        if ref.node is not None:
            return node_types.get(ref.node, ValueType.ANY)
        return ValueType.ANY

    for index, node in enumerate(workflow.nodes):
        path = f"/nodes/{index}"
        if isinstance(node, ConstantNode):
            actual = _value_type(node.config.value)
            if not _compatible(actual, node.output_type):
                diagnostics.append(
                    diagnostic(
                        "WYS500",
                        "constant value does not match output_type",
                        f"{path}/output_type",
                        parsed=parsed,
                    )
                )
            if node.inputs:
                diagnostics.append(
                    diagnostic(
                        "WYS501",
                        "constant nodes cannot declare inputs",
                        f"{path}/inputs",
                        parsed=parsed,
                    )
                )
        elif (
            isinstance(node, (SelectNode, TransformNode, AssertNode, OutputNode))
            and "value" not in node.inputs
        ):
            diagnostics.append(
                diagnostic(
                    "WYS502",
                    f"{node.kind} nodes require a 'value' input",
                    f"{path}/inputs",
                    parsed=parsed,
                )
            )

        if isinstance(node, SelectNode):
            if any(name != "value" for name in node.inputs):
                diagnostics.append(
                    diagnostic(
                        "WYS507",
                        "select nodes cannot declare inputs other than 'value'",
                        f"{path}/inputs",
                        parsed=parsed,
                    )
                )
            if not _JSON_POINTER_REGEX.fullmatch(node.config.path):
                diagnostics.append(
                    diagnostic(
                        "WYS506",
                        f"invalid JSON pointer '{node.config.path}': must follow RFC 6901",
                        f"{path}/config/path",
                        parsed=parsed,
                        hint="Use empty string or start with '/' and escape '~' as '~0' and '/' as '~1'.",
                    )
                )
            elif node.config.path != "":
                ref = node.inputs.get("value")
                if ref:
                    source_type = get_source_type(ref)
                    if source_type not in {ValueType.OBJECT, ValueType.ARRAY, ValueType.ANY}:
                        diagnostics.append(
                            diagnostic(
                                "WYS507",
                                f"select node input must be object, array, or any, got '{source_type.value}'",
                                f"{path}/inputs/value",
                                parsed=parsed,
                            )
                        )

        elif isinstance(node, ConstructNode):
            if isinstance(node.config.template, dict) and node.output_type not in {
                ValueType.OBJECT,
                ValueType.ANY,
            }:
                diagnostics.append(
                    diagnostic(
                        "WYS503",
                        f"construct node with object template must output object or any, got '{node.output_type.value}'",
                        f"{path}/output_type",
                        parsed=parsed,
                    )
                )
            elif isinstance(node.config.template, list) and node.output_type not in {
                ValueType.ARRAY,
                ValueType.ANY,
            }:
                diagnostics.append(
                    diagnostic(
                        "WYS503",
                        f"construct node with array template must output array or any, got '{node.output_type.value}'",
                        f"{path}/output_type",
                        parsed=parsed,
                    )
                )
            placeholders = _extract_placeholders(node.config.template)
            for placeholder in sorted(placeholders):
                if placeholder not in node.inputs:
                    diagnostics.append(
                        diagnostic(
                            "WYS509",
                            f"construct template references undeclared input '{placeholder}'",
                            f"{path}/config/template",
                            parsed=parsed,
                            hint="Declare the input in the node's 'inputs' mapping.",
                        )
                    )

        elif isinstance(node, TransformNode):
            if any(name != "value" for name in node.inputs):
                diagnostics.append(
                    diagnostic(
                        "WYS504",
                        "transform nodes cannot declare inputs other than 'value'",
                        f"{path}/inputs",
                        parsed=parsed,
                    )
                )
            ref = node.inputs.get("value")
            source_type = get_source_type(ref)
            op = node.config.operation
            if op in {
                TransformOperation.LOWERCASE,
                TransformOperation.UPPERCASE,
                TransformOperation.TRIM,
            }:
                if source_type not in {ValueType.STRING, ValueType.ANY}:
                    diagnostics.append(
                        diagnostic(
                            "WYS504",
                            "string transform requires a string input",
                            f"{path}/inputs/value",
                            parsed=parsed,
                        )
                    )
                if node.output_type not in {ValueType.STRING, ValueType.ANY}:
                    diagnostics.append(
                        diagnostic(
                            "WYS508",
                            f"transform '{op.value}' must produce string or any output, got '{node.output_type.value}'",
                            f"{path}/output_type",
                            parsed=parsed,
                        )
                    )
            elif op == TransformOperation.TO_STRING:
                if node.output_type not in {ValueType.STRING, ValueType.ANY}:
                    diagnostics.append(
                        diagnostic(
                            "WYS508",
                            f"transform 'to_string' must produce string or any output, got '{node.output_type.value}'",
                            f"{path}/output_type",
                            parsed=parsed,
                        )
                    )
            elif op == TransformOperation.TO_INTEGER:
                if source_type not in {
                    ValueType.STRING,
                    ValueType.INTEGER,
                    ValueType.NUMBER,
                    ValueType.BOOLEAN,
                    ValueType.ANY,
                }:
                    diagnostics.append(
                        diagnostic(
                            "WYS504",
                            f"transform 'to_integer' input cannot be converted from '{source_type.value}'",
                            f"{path}/inputs/value",
                            parsed=parsed,
                        )
                    )
                if node.output_type not in {
                    ValueType.INTEGER,
                    ValueType.NUMBER,
                    ValueType.ANY,
                }:
                    diagnostics.append(
                        diagnostic(
                            "WYS508",
                            f"transform 'to_integer' must produce integer, number, or any output, got '{node.output_type.value}'",
                            f"{path}/output_type",
                            parsed=parsed,
                        )
                    )
            elif op == TransformOperation.IDENTITY:
                if not _compatible(source_type, node.output_type):
                    diagnostics.append(
                        diagnostic(
                            "WYS508",
                            f"identity transform output_type '{node.output_type.value}' does not match input source type '{source_type.value}'",
                            f"{path}/output_type",
                            parsed=parsed,
                        )
                    )

        elif isinstance(node, AssertNode):
            if any(name != "value" for name in node.inputs):
                diagnostics.append(
                    diagnostic(
                        "WYS510",
                        "assert nodes cannot declare inputs other than 'value'",
                        f"{path}/inputs",
                        parsed=parsed,
                    )
                )
            if node.output_type not in {ValueType.BOOLEAN, ValueType.ANY}:
                diagnostics.append(
                    diagnostic(
                        "WYS510",
                        f"assert nodes must produce boolean or any output, got '{node.output_type.value}'",
                        f"{path}/output_type",
                        parsed=parsed,
                    )
                )
            pred = node.config.predicate
            if pred == AssertPredicate.EXISTS:
                if node.config.expected is not None:
                    diagnostics.append(
                        diagnostic(
                            "WYS510",
                            "assert predicate 'exists' must not specify an expected value",
                            f"{path}/config/expected",
                            parsed=parsed,
                            hint="Set expected to null or omit it.",
                        )
                    )
            elif pred == AssertPredicate.TYPE_IS:
                valid_types = {v.value for v in ValueType}
                if (
                    not isinstance(node.config.expected, str)
                    or node.config.expected not in valid_types
                ):
                    diagnostics.append(
                        diagnostic(
                            "WYS510",
                            f"assert predicate 'type_is' requires expected to be a valid type name (one of: {', '.join(sorted(valid_types))})",
                            f"{path}/config/expected",
                            parsed=parsed,
                        )
                    )

        elif isinstance(node, OutputNode):
            if any(name != "value" for name in node.inputs):
                diagnostics.append(
                    diagnostic(
                        "WYS511",
                        "output nodes cannot declare inputs other than 'value'",
                        f"{path}/inputs",
                        parsed=parsed,
                    )
                )
            ref = node.inputs.get("value")
            if ref:
                source_type = get_source_type(ref)
                if not _compatible(source_type, node.output_type):
                    diagnostics.append(
                        diagnostic(
                            "WYS511",
                            f"output node output_type '{node.output_type.value}' does not match input source type '{source_type.value}'",
                            f"{path}/output_type",
                            parsed=parsed,
                        )
                    )

        elif isinstance(node, HttpNode):
            if Capability.NETWORK_HTTP not in workflow.capabilities:
                diagnostics.append(
                    diagnostic(
                        "WYS514",
                        f"node '{node.id}' requires capability '{Capability.NETWORK_HTTP.value}' but it is not declared in workflow capabilities",
                        f"{path}",
                        parsed=parsed,
                    )
                )

        elif isinstance(node, FileReadNode):
            if Capability.FILE_READ not in workflow.capabilities:
                diagnostics.append(
                    diagnostic(
                        "WYS514",
                        f"node '{node.id}' requires capability '{Capability.FILE_READ.value}' but it is not declared in workflow capabilities",
                        f"{path}",
                        parsed=parsed,
                    )
                )

    for name, output in workflow.outputs.items():
        source_type = get_source_type(output.source)
        if not _compatible(source_type, output.type):
            diagnostics.append(
                diagnostic(
                    "WYS505",
                    f"output '{name}' type does not match its source",
                    f"/outputs/{name}/type",
                    parsed=parsed,
                )
            )

    seen_assertion_ids: set[str] = set()
    for index, assertion in enumerate(workflow.assertions):
        path = f"/assertions/{index}"
        if assertion.id in seen_assertion_ids:
            diagnostics.append(
                diagnostic(
                    "WYS512",
                    f"duplicate assertion ID '{assertion.id}'",
                    f"{path}/id",
                    parsed=parsed,
                )
            )
        seen_assertion_ids.add(assertion.id)

        if assertion.predicate == AssertPredicate.EXISTS:
            if assertion.expected is not None:
                diagnostics.append(
                    diagnostic(
                        "WYS513",
                        "assertion predicate 'exists' must not specify an expected value",
                        f"{path}/expected",
                        parsed=parsed,
                        hint="Set expected to null or omit it.",
                    )
                )
        elif assertion.predicate == AssertPredicate.TYPE_IS:
            valid_types = {v.value for v in ValueType}
            if not isinstance(assertion.expected, str) or assertion.expected not in valid_types:
                diagnostics.append(
                    diagnostic(
                        "WYS513",
                        f"assertion predicate 'type_is' requires expected to be a valid type name (one of: {', '.join(sorted(valid_types))})",
                        f"{path}/expected",
                        parsed=parsed,
                    )
                )

    return diagnostics
