"""Validation for all input, node, and output references."""

from wysteria.ir.models import Reference, Workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic


def _check_reference(
    reference: Reference,
    workflow: Workflow,
    node_ids: set[str],
    path: str,
    parsed: ParsedWorkflow | None,
) -> list[Diagnostic]:
    if reference.input is not None and reference.input not in workflow.inputs:
        return [
            diagnostic(
                "WYS300",
                f"input reference '{reference.input}' is not declared",
                path,
                parsed=parsed,
                hint="Declare the input or reference an existing input.",
            )
        ]
    if reference.node is not None and reference.node not in node_ids:
        return [
            diagnostic(
                "WYS301",
                f"node reference '{reference.node}' does not exist",
                path,
                parsed=parsed,
                hint="Reference an existing node ID.",
            )
        ]
    return []


def validate_references(
    workflow: Workflow, parsed: ParsedWorkflow | None = None
) -> list[Diagnostic]:
    """Validate references independently of graph shape and type compatibility."""

    diagnostics: list[Diagnostic] = []
    node_ids = {node.id for node in workflow.nodes}
    for index, node in enumerate(workflow.nodes):
        for input_name, reference in node.inputs.items():
            diagnostics.extend(
                _check_reference(
                    reference, workflow, node_ids, f"/nodes/{index}/inputs/{input_name}", parsed
                )
            )
    for index, edge in enumerate(workflow.edges):
        diagnostics.extend(
            _check_reference(edge.source, workflow, node_ids, f"/edges/{index}/source", parsed)
        )
        if edge.target_node not in node_ids:
            diagnostics.append(
                diagnostic(
                    "WYS302",
                    f"edge target node '{edge.target_node}' does not exist",
                    f"/edges/{index}/target_node",
                    parsed=parsed,
                )
            )
    for name, output in workflow.outputs.items():
        diagnostics.extend(
            _check_reference(output.source, workflow, node_ids, f"/outputs/{name}/source", parsed)
        )
    for index, assertion in enumerate(workflow.assertions):
        diagnostics.extend(
            _check_reference(
                assertion.source, workflow, node_ids, f"/assertions/{index}/source", parsed
            )
        )
    return diagnostics
