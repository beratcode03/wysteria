"""Explicit edge and acyclic graph validation."""

import heapq
from collections import defaultdict

from wysteria.ir.models import Workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic


class GraphCycleError(ValueError):
    """Raised when a cycle is detected during topological sort."""


def topological_sort(workflow: Workflow) -> list[str]:
    """Return a deterministic topological ordering of node IDs using Kahn's algorithm.

    Tie-breaks nodes with in-degree 0 in lexicographical order.
    Raises GraphCycleError if the graph contains a cycle.
    Raises ValueError if the workflow has duplicate node IDs.
    """
    node_ids = [node.id for node in workflow.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("workflow contains duplicate node IDs")

    node_by_id = {node.id: node for node in workflow.nodes}
    in_degree: dict[str, int] = {node_id: 0 for node_id in node_by_id}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in workflow.edges:
        if edge.source.node and edge.source.node in node_by_id and edge.target_node in node_by_id:
            adjacency[edge.source.node].append(edge.target_node)
            in_degree[edge.target_node] += 1

    ready = [node_id for node_id, deg in in_degree.items() if deg == 0]
    heapq.heapify(ready)

    order: list[str] = []
    while ready:
        node_id = heapq.heappop(ready)
        order.append(node_id)
        for target in adjacency[node_id]:
            in_degree[target] -= 1
            if in_degree[target] == 0:
                heapq.heappush(ready, target)

    if len(order) < len(node_by_id):
        raise GraphCycleError("workflow graph contains a cycle")

    return order


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

    if len(seen) == len(ids):
        try:
            topological_sort(workflow)
        except GraphCycleError:
            diagnostics.append(
                diagnostic("WYS205", "workflow graph contains a cycle", "/edges", parsed=parsed)
            )

    return diagnostics
