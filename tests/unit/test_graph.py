from types import SimpleNamespace

import pytest

from wysteria.api import GraphCycleError, topological_sort
from wysteria.ir.models import Edge, NodeBase, Reference, Workflow


def _create_node(node_id: str, inputs: dict[str, Reference] | None = None) -> NodeBase:
    return NodeBase.model_construct(
        id=node_id,
        inputs=inputs or {},
        output_type="string",
    )


def test_topological_sort_deterministic_order():
    nodes = [
        _create_node("z"),
        _create_node("m", inputs={"value": Reference(node="a")}),
        _create_node("a"),
    ]
    edges = [
        Edge(source=Reference(node="a"), target_node="m", target_input="value"),
    ]
    wf = Workflow.model_construct(nodes=nodes, edges=edges)

    order = topological_sort(wf)
    assert order == ["a", "m", "z"]


def test_topological_sort_detects_simple_cycle():
    nodes = [
        _create_node("first", inputs={"value": Reference(node="second")}),
        _create_node("second", inputs={"value": Reference(node="first")}),
    ]
    edges = [
        Edge(source=Reference(node="second"), target_node="first", target_input="value"),
        Edge(source=Reference(node="first"), target_node="second", target_input="value"),
    ]
    wf = Workflow.model_construct(nodes=nodes, edges=edges)

    with pytest.raises(GraphCycleError, match="cycle"):
        topological_sort(wf)


def test_topological_sort_detects_self_loop():
    nodes = [
        _create_node("self_node", inputs={"value": Reference(node="self_node")}),
    ]
    edges = [
        Edge(source=Reference(node="self_node"), target_node="self_node", target_input="value"),
    ]
    wf = Workflow.model_construct(nodes=nodes, edges=edges)

    with pytest.raises(GraphCycleError, match="cycle"):
        topological_sort(wf)


def test_topological_sort_deep_linear_graph_no_recursion_error():
    n = 1200
    nodes = [
        SimpleNamespace(
            id=f"node_{i:04d}",
            inputs={"val": Reference(node=f"node_{i - 1:04d}")} if i > 0 else {},
            output_type="string",
        )
        for i in range(n)
    ]
    edges = [
        Edge(
            source=Reference(node=f"node_{i - 1:04d}"),
            target_node=f"node_{i:04d}",
            target_input="val",
        )
        for i in range(1, n)
    ]
    dummy_wf = SimpleNamespace(nodes=nodes, edges=edges)

    order = topological_sort(dummy_wf)  # type: ignore[arg-type]
    assert len(order) == n
    assert order[0] == "node_0000"
    assert order[-1] == f"node_{n - 1:04d}"


def test_topological_sort_multigraph_dependencies():
    nodes = [
        _create_node("nodeA"),
        _create_node(
            "nodeB",
            inputs={"in1": Reference(node="nodeA"), "in2": Reference(node="nodeA")},
        ),
    ]
    edges = [
        Edge(source=Reference(node="nodeA"), target_node="nodeB", target_input="in1"),
        Edge(source=Reference(node="nodeA"), target_node="nodeB", target_input="in2"),
    ]
    wf = Workflow.model_construct(nodes=nodes, edges=edges)

    order = topological_sort(wf)
    assert order == ["nodeA", "nodeB"]


def test_topological_sort_rejects_duplicate_node_ids():
    nodes = [
        _create_node("dup"),
        _create_node("dup"),
    ]
    wf = Workflow.model_construct(nodes=nodes, edges=[])
    with pytest.raises(ValueError, match="duplicate node IDs"):
        topological_sort(wf)
