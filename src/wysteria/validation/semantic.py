"""Small semantic validation for the fixed deterministic node vocabulary."""

from typing import Any

from wysteria.ir.models import (
    AssertNode,
    ConstantNode,
    ConstructNode,
    SelectNode,
    TransformNode,
    ValueType,
    Workflow,
)
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic


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
    types = {name: spec.type for name, spec in workflow.inputs.items()}
    types.update({node.id: node.output_type for node in workflow.nodes})
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
            isinstance(node, (SelectNode, TransformNode, AssertNode)) and "value" not in node.inputs
        ):
            diagnostics.append(
                diagnostic(
                    "WYS502",
                    f"{node.kind} nodes require a 'value' input",
                    f"{path}/inputs",
                    parsed=parsed,
                )
            )
        elif isinstance(node, ConstructNode) and node.output_type not in {
            ValueType.OBJECT,
            ValueType.ARRAY,
            ValueType.ANY,
        }:
            diagnostics.append(
                diagnostic(
                    "WYS503",
                    "construct nodes must output object, array, or any",
                    f"{path}/output_type",
                    parsed=parsed,
                )
            )
        if isinstance(node, TransformNode) and node.config.operation.value in {
            "lowercase",
            "uppercase",
            "trim",
        }:
            reference = node.inputs.get("value")
            if reference is not None:
                source_type = types.get(reference.input or reference.node or "", ValueType.ANY)
                if source_type not in {ValueType.STRING, ValueType.ANY}:
                    diagnostics.append(
                        diagnostic(
                            "WYS504",
                            "string transform requires a string input",
                            f"{path}/inputs/value",
                            parsed=parsed,
                        )
                    )
    for name, output in workflow.outputs.items():
        source_type = types.get(output.source.input or output.source.node or "", ValueType.ANY)
        if not _compatible(source_type, output.type):
            diagnostics.append(
                diagnostic(
                    "WYS505",
                    f"output '{name}' type does not match its source",
                    f"/outputs/{name}/type",
                    parsed=parsed,
                )
            )
    return diagnostics
