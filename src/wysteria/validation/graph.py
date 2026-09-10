"""Explicit edge and acyclic graph validation."""

from collections import defaultdict

from wysteria.ir.models import Workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic


def validate_graph(workflow: Workflow, parsed: ParsedWorkflow | None = None) -> list[Diagnostic]:
    """Validate IDs, edge/input agreement, and directed acyclicity."""

    diagnostics: list[Diagnostic] = []
    ids = [node.id for node in workflow.nodes]
    seen: set[str] = set()
    for index, node_id in enumerate(ids):
        if node_id in seen:
            diagnostics.append(
                diagnostic(
                    "WYS200", f"duplicate node ID '{node_id}'", f"/nodes/{index}/id", parsed=parsed
                )
            )
        seen.add(node_id)

    by_target = {(edge.target_node, edge.target_input): edge.source for edge in workflow.edges}
    if len(by_target) != len(workflow.edges):
        encountered: set[tuple[str, str]] = set()
        for index, edge in enumerate(workflow.edges):
            target = (edge.target_node, edge.target_input)
            if target in encountered:
                diagnostics.append(
                    diagnostic(
                        "WYS201",
                        "multiple edges target the same node input",
                        f"/edges/{index}",
                        parsed=parsed,
                    )
                )
            encountered.add(target)

    node_by_id = {node.id: node for node in workflow.nodes}
    for node_index, node in enumerate(workflow.nodes):
        for input_name, reference in node.inputs.items():
            edge_ref = by_target.get((node.id, input_name))
            if edge_ref is None:
                diagnostics.append(
                    diagnostic(
                        "WYS202",
                        f"node input '{input_name}' has no explicit edge",
                        f"/nodes/{node_index}/inputs/{input_name}",
                        parsed=parsed,
                        hint="Add one matching edge for every node input.",
                    )
                )
            elif edge_ref != reference:
                diagnostics.append(
                    diagnostic(
                        "WYS203",
                        f"edge source does not match node input '{input_name}'",
                        f"/nodes/{node_index}/inputs/{input_name}",
                        parsed=parsed,
                    )
                )
    for edge_index, edge in enumerate(workflow.edges):
        target = node_by_id.get(edge.target_node)
        if target is not None and edge.target_input not in target.inputs:
            diagnostics.append(
                diagnostic(
                    "WYS204",
                    f"edge targets undeclared input '{edge.target_input}'",
                    f"/edges/{edge_index}/target_input",
                    parsed=parsed,
                )
            )

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in workflow.edges:
        if edge.source.node and edge.source.node in node_by_id and edge.target_node in node_by_id:
            adjacency[edge.source.node].add(edge.target_node)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(child) for child in adjacency[node_id]):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(visit(node_id) for node_id in node_by_id):
        diagnostics.append(
            diagnostic("WYS205", "workflow graph contains a cycle", "/edges", parsed=parsed)
        )
    return diagnostics
