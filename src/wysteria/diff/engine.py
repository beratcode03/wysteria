"""Deterministic semantic workflow diff engine."""

from __future__ import annotations

from collections import deque

from wysteria.diff.models import (
    ChangeCategory,
    DiffSeverity,
    DiffSummary,
    SemanticChange,
    WorkflowDiff,
)
from wysteria.ir.models import Edge, Reference, Workflow
from wysteria.ir.normalize import fingerprint_workflow


def change_sort_key(change: SemanticChange) -> tuple[str, str, str, str]:
    """Stable, deterministic sort key for semantic changes."""
    return (
        change.category.value,
        change.target_id or change.node_id or change.edge_id or "",
        change.path,
        change.change_type,
    )


def _ref_str(ref: Reference) -> str:
    """Format reference as stable readable string."""
    if ref.input is not None:
        return f"input.{ref.input}"
    return f"node.{ref.node}"


def _edge_identity(edge: Edge) -> str:
    """Format edge identity as stable readable string."""
    return f"{_ref_str(edge.source)} -> {edge.target_node}:{edge.target_input}"


def _is_node_reachable_to_terminal(workflow: Workflow, start_node_id: str) -> bool:
    """Determine if start_node_id reaches any output or assertion in workflow DAG."""
    terminal_nodes: set[str] = set()
    for output in workflow.outputs.values():
        if output.source.node:
            terminal_nodes.add(output.source.node)
    for assertion in workflow.assertions:
        if assertion.source.node:
            terminal_nodes.add(assertion.source.node)

    if start_node_id in terminal_nodes:
        return True

    adjacency: dict[str, list[str]] = {node.id: [] for node in workflow.nodes}
    for edge in workflow.edges:
        if edge.source.node and edge.source.node in adjacency:
            adjacency[edge.source.node].append(edge.target_node)

    visited: set[str] = set()
    queue = deque([start_node_id])
    while queue:
        current = queue.popleft()
        if current in terminal_nodes:
            return True
        if current not in visited:
            visited.add(current)
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    queue.append(neighbor)
    return False


def _is_edge_reachable_to_terminal(workflow: Workflow, edge: Edge) -> bool:
    """Determine if an edge's target node reaches any output or assertion."""
    return _is_node_reachable_to_terminal(workflow, edge.target_node)


def diff_workflows(
    old_workflow: Workflow,
    new_workflow: Workflow,
    *,
    old_display: str | None = None,
    new_display: str | None = None,
) -> WorkflowDiff:
    """Deterministically diff two typed Workflow IR contracts."""
    old_fp = fingerprint_workflow(old_workflow)
    new_fp = fingerprint_workflow(new_workflow)

    if old_fp == new_fp:
        return WorkflowDiff(
            old_workflow=old_display,
            new_workflow=new_display,
            old_fingerprint=old_fp,
            new_fingerprint=new_fp,
            identical=True,
            changes=[],
            summary=DiffSummary(),
        )

    changes: list[SemanticChange] = []

    # 1. Metadata changes
    if old_workflow.name != new_workflow.name:
        changes.append(
            SemanticChange(
                category=ChangeCategory.METADATA_CHANGED,
                change_type="workflow_name_changed",
                severity=DiffSeverity.INFO,
                target_id="name",
                path="name",
                before=old_workflow.name,
                after=new_workflow.name,
                explanation=f"Workflow name changed from '{old_workflow.name}' to '{new_workflow.name}'",
            )
        )

    if old_workflow.metadata.description != new_workflow.metadata.description:
        changes.append(
            SemanticChange(
                category=ChangeCategory.METADATA_CHANGED,
                change_type="metadata_description_changed",
                severity=DiffSeverity.INFO,
                target_id="description",
                path="metadata/description",
                before=old_workflow.metadata.description,
                after=new_workflow.metadata.description,
                explanation="Workflow metadata description changed",
            )
        )

    if sorted(old_workflow.metadata.labels) != sorted(new_workflow.metadata.labels):
        changes.append(
            SemanticChange(
                category=ChangeCategory.METADATA_CHANGED,
                change_type="metadata_labels_changed",
                severity=DiffSeverity.INFO,
                target_id="labels",
                path="metadata/labels",
                before=sorted(old_workflow.metadata.labels),
                after=sorted(new_workflow.metadata.labels),
                explanation="Workflow metadata labels changed",
            )
        )

    # 2. Capabilities changes
    old_caps = set(old_workflow.capabilities)
    new_caps = set(new_workflow.capabilities)

    for cap in sorted(new_caps - old_caps):
        changes.append(
            SemanticChange(
                category=ChangeCategory.CAPABILITY_CHANGED,
                change_type="capability_added",
                severity=DiffSeverity.BREAKING,
                target_id=str(cap),
                path=f"capabilities/{cap}",
                before=None,
                after=str(cap),
                explanation=f"Capability requirement added: '{cap}'",
            )
        )

    for cap in sorted(old_caps - new_caps):
        changes.append(
            SemanticChange(
                category=ChangeCategory.CAPABILITY_CHANGED,
                change_type="capability_removed",
                severity=DiffSeverity.INFO,
                target_id=str(cap),
                path=f"capabilities/{cap}",
                before=str(cap),
                after=None,
                explanation=f"Capability requirement removed: '{cap}'",
            )
        )

    # 3. Inputs changes
    all_input_names = sorted(set(old_workflow.inputs.keys()) | set(new_workflow.inputs.keys()))
    for name in all_input_names:
        in_old = name in old_workflow.inputs
        in_new = name in new_workflow.inputs

        if in_old and not in_new:
            changes.append(
                SemanticChange(
                    category=ChangeCategory.INPUT_CHANGED,
                    change_type="input_removed",
                    severity=DiffSeverity.BREAKING,
                    target_id=name,
                    path=f"inputs/{name}",
                    before=old_workflow.inputs[name].model_dump(mode="json"),
                    after=None,
                    explanation=f"Workflow input '{name}' removed",
                )
            )
        elif not in_old and in_new:
            new_spec = new_workflow.inputs[name]
            sev = DiffSeverity.BREAKING if new_spec.required else DiffSeverity.INFO
            changes.append(
                SemanticChange(
                    category=ChangeCategory.INPUT_CHANGED,
                    change_type="input_added",
                    severity=sev,
                    target_id=name,
                    path=f"inputs/{name}",
                    before=None,
                    after=new_spec.model_dump(mode="json"),
                    explanation=f"Workflow input '{name}' added (type: {new_spec.type.value}, required: {new_spec.required})",
                )
            )
        else:
            old_spec = old_workflow.inputs[name]
            new_spec = new_workflow.inputs[name]
            if old_spec.type != new_spec.type:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.INPUT_CHANGED,
                        change_type="input_type_changed",
                        severity=DiffSeverity.BREAKING,
                        target_id=name,
                        path=f"inputs/{name}/type",
                        before=old_spec.type.value,
                        after=new_spec.type.value,
                        explanation=f"Workflow input '{name}' type changed from '{old_spec.type.value}' to '{new_spec.type.value}'",
                    )
                )
            if old_spec.required != new_spec.required:
                sev = DiffSeverity.BREAKING if new_spec.required else DiffSeverity.INFO
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.INPUT_CHANGED,
                        change_type="input_required_changed",
                        severity=sev,
                        target_id=name,
                        path=f"inputs/{name}/required",
                        before=old_spec.required,
                        after=new_spec.required,
                        explanation=f"Workflow input '{name}' required changed from {old_spec.required} to {new_spec.required}",
                    )
                )

    # 4. Outputs changes
    all_output_names = sorted(set(old_workflow.outputs.keys()) | set(new_workflow.outputs.keys()))
    for name in all_output_names:
        in_old = name in old_workflow.outputs
        in_new = name in new_workflow.outputs

        if in_old and not in_new:
            changes.append(
                SemanticChange(
                    category=ChangeCategory.OUTPUT_CHANGED,
                    change_type="output_removed",
                    severity=DiffSeverity.BREAKING,
                    target_id=name,
                    path=f"outputs/{name}",
                    before=old_workflow.outputs[name].model_dump(mode="json"),
                    after=None,
                    explanation=f"Workflow output '{name}' removed",
                )
            )
        elif not in_old and in_new:
            new_out = new_workflow.outputs[name]
            changes.append(
                SemanticChange(
                    category=ChangeCategory.OUTPUT_CHANGED,
                    change_type="output_added",
                    severity=DiffSeverity.INFO,
                    target_id=name,
                    path=f"outputs/{name}",
                    before=None,
                    after=new_out.model_dump(mode="json"),
                    explanation=f"Workflow output '{name}' added (type: {new_out.type.value})",
                )
            )
        else:
            old_out = old_workflow.outputs[name]
            new_out = new_workflow.outputs[name]
            if old_out.type != new_out.type:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.OUTPUT_CHANGED,
                        change_type="output_type_changed",
                        severity=DiffSeverity.BREAKING,
                        target_id=name,
                        path=f"outputs/{name}/type",
                        before=old_out.type.value,
                        after=new_out.type.value,
                        explanation=f"Workflow output '{name}' type changed from '{old_out.type.value}' to '{new_out.type.value}'",
                    )
                )
            if old_out.source != new_out.source:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.OUTPUT_CHANGED,
                        change_type="output_source_changed",
                        severity=DiffSeverity.BREAKING,
                        target_id=name,
                        path=f"outputs/{name}/source",
                        before=old_out.source.model_dump(mode="json"),
                        after=new_out.source.model_dump(mode="json"),
                        explanation=f"Workflow output '{name}' source changed from '{_ref_str(old_out.source)}' to '{_ref_str(new_out.source)}'",
                    )
                )

    # 5. Assertions changes
    old_asserts = {a.id: a for a in old_workflow.assertions}
    new_asserts = {a.id: a for a in new_workflow.assertions}
    all_assert_ids = sorted(set(old_asserts.keys()) | set(new_asserts.keys()))
    for aid in all_assert_ids:
        in_old = aid in old_asserts
        in_new = aid in new_asserts

        if in_old and not in_new:
            changes.append(
                SemanticChange(
                    category=ChangeCategory.ASSERTION_CHANGED,
                    change_type="assertion_removed",
                    severity=DiffSeverity.BREAKING,
                    target_id=aid,
                    path=f"assertions/{aid}",
                    before=old_asserts[aid].model_dump(mode="json"),
                    after=None,
                    explanation=f"Workflow assertion '{aid}' removed",
                )
            )
        elif not in_old and in_new:
            changes.append(
                SemanticChange(
                    category=ChangeCategory.ASSERTION_CHANGED,
                    change_type="assertion_added",
                    severity=DiffSeverity.BREAKING,
                    target_id=aid,
                    path=f"assertions/{aid}",
                    before=None,
                    after=new_asserts[aid].model_dump(mode="json"),
                    explanation=f"Workflow assertion '{aid}' added",
                )
            )
        else:
            old_a = old_asserts[aid]
            new_a = new_asserts[aid]
            if old_a.predicate != new_a.predicate:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.ASSERTION_CHANGED,
                        change_type="assertion_predicate_changed",
                        severity=DiffSeverity.BREAKING,
                        target_id=aid,
                        path=f"assertions/{aid}/predicate",
                        before=old_a.predicate.value,
                        after=new_a.predicate.value,
                        explanation=f"Workflow assertion '{aid}' predicate changed from '{old_a.predicate.value}' to '{new_a.predicate.value}'",
                    )
                )
            if old_a.expected != new_a.expected:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.ASSERTION_CHANGED,
                        change_type="assertion_expected_changed",
                        severity=DiffSeverity.BREAKING,
                        target_id=aid,
                        path=f"assertions/{aid}/expected",
                        before=old_a.expected,
                        after=new_a.expected,
                        explanation=f"Workflow assertion '{aid}' expected value changed",
                    )
                )
            if old_a.source != new_a.source:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.ASSERTION_CHANGED,
                        change_type="assertion_source_changed",
                        severity=DiffSeverity.BREAKING,
                        target_id=aid,
                        path=f"assertions/{aid}/source",
                        before=old_a.source.model_dump(mode="json"),
                        after=new_a.source.model_dump(mode="json"),
                        explanation=f"Workflow assertion '{aid}' source changed from '{_ref_str(old_a.source)}' to '{_ref_str(new_a.source)}'",
                    )
                )

    # 6. Nodes changes
    old_nodes = {n.id: n for n in old_workflow.nodes}
    new_nodes = {n.id: n for n in new_workflow.nodes}
    all_node_ids = sorted(set(old_nodes.keys()) | set(new_nodes.keys()))

    for nid in all_node_ids:
        in_old = nid in old_nodes
        in_new = nid in new_nodes

        if in_old and not in_new:
            old_n = old_nodes[nid]
            changes.append(
                SemanticChange(
                    category=ChangeCategory.NODE_REMOVED,
                    change_type="node_removed",
                    severity=DiffSeverity.BREAKING,
                    node_id=nid,
                    target_id=nid,
                    path=f"nodes/{nid}",
                    before=old_n.model_dump(mode="json"),
                    after=None,
                    explanation=f"Node '{nid}' removed (kind: {old_n.kind})",
                )
            )
        elif not in_old and in_new:
            new_n = new_nodes[nid]
            changes.append(
                SemanticChange(
                    category=ChangeCategory.NODE_ADDED,
                    change_type="node_added",
                    severity=DiffSeverity.INFO,
                    node_id=nid,
                    target_id=nid,
                    path=f"nodes/{nid}",
                    before=None,
                    after=new_n.model_dump(mode="json"),
                    explanation=f"Node '{nid}' added (kind: {new_n.kind})",
                )
            )
        else:
            old_n = old_nodes[nid]
            new_n = new_nodes[nid]

            # Kind changed
            if old_n.kind != new_n.kind:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.NODE_CHANGED,
                        change_type="node_kind_changed",
                        severity=DiffSeverity.BREAKING,
                        node_id=nid,
                        target_id=nid,
                        path=f"nodes/{nid}/kind",
                        before=old_n.kind,
                        after=new_n.kind,
                        explanation=f"Node '{nid}' kind changed from '{old_n.kind}' to '{new_n.kind}'",
                    )
                )

            # Output type changed
            if old_n.output_type != new_n.output_type:
                changes.append(
                    SemanticChange(
                        category=ChangeCategory.NODE_CHANGED,
                        change_type="node_output_type_changed",
                        severity=DiffSeverity.BREAKING,
                        node_id=nid,
                        target_id=nid,
                        path=f"nodes/{nid}/output_type",
                        before=old_n.output_type.value,
                        after=new_n.output_type.value,
                        explanation=f"Node '{nid}' output type changed from '{old_n.output_type.value}' to '{new_n.output_type.value}'",
                    )
                )

            # Node inputs changed
            all_inps = sorted(set(old_n.inputs.keys()) | set(new_n.inputs.keys()))
            for inp_k in all_inps:
                if inp_k in old_n.inputs and inp_k in new_n.inputs:
                    if old_n.inputs[inp_k] != new_n.inputs[inp_k]:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.NODE_CHANGED,
                                change_type="node_input_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/inputs/{inp_k}",
                                before=old_n.inputs[inp_k].model_dump(mode="json"),
                                after=new_n.inputs[inp_k].model_dump(mode="json"),
                                explanation=f"Node '{nid}' input '{inp_k}' binding changed from '{_ref_str(old_n.inputs[inp_k])}' to '{_ref_str(new_n.inputs[inp_k])}'",
                            )
                        )
                elif inp_k in old_n.inputs:
                    changes.append(
                        SemanticChange(
                            category=ChangeCategory.NODE_CHANGED,
                            change_type="node_input_removed",
                            severity=DiffSeverity.BREAKING,
                            node_id=nid,
                            target_id=nid,
                            path=f"nodes/{nid}/inputs/{inp_k}",
                            before=old_n.inputs[inp_k].model_dump(mode="json"),
                            after=None,
                            explanation=f"Node '{nid}' input '{inp_k}' removed",
                        )
                    )
                else:
                    changes.append(
                        SemanticChange(
                            category=ChangeCategory.NODE_CHANGED,
                            change_type="node_input_added",
                            severity=DiffSeverity.BREAKING,
                            node_id=nid,
                            target_id=nid,
                            path=f"nodes/{nid}/inputs/{inp_k}",
                            before=None,
                            after=new_n.inputs[inp_k].model_dump(mode="json"),
                            explanation=f"Node '{nid}' input '{inp_k}' added",
                        )
                    )

            # Config changed
            if old_n.kind == new_n.kind:
                if old_n.kind == "transform":
                    if old_n.config.operation != new_n.config.operation:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.CONFIG_CHANGED,
                                change_type="transform_operation_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/config/operation",
                                before=old_n.config.operation.value,
                                after=new_n.config.operation.value,
                                explanation=f"Node '{nid}' transform operation changed from '{old_n.config.operation.value}' to '{new_n.config.operation.value}'",
                            )
                        )
                elif old_n.kind == "assert":
                    if old_n.config.predicate != new_n.config.predicate:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.CONFIG_CHANGED,
                                change_type="assert_predicate_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/config/predicate",
                                before=old_n.config.predicate.value,
                                after=new_n.config.predicate.value,
                                explanation=f"Node '{nid}' assert predicate changed from '{old_n.config.predicate.value}' to '{new_n.config.predicate.value}'",
                            )
                        )
                    if old_n.config.expected != new_n.config.expected:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.CONFIG_CHANGED,
                                change_type="assert_expected_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/config/expected",
                                before=old_n.config.expected,
                                after=new_n.config.expected,
                                explanation=f"Node '{nid}' assert expected value changed",
                            )
                        )
                elif old_n.kind == "select":
                    if old_n.config.path != new_n.config.path:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.CONFIG_CHANGED,
                                change_type="select_path_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/config/path",
                                before=old_n.config.path,
                                after=new_n.config.path,
                                explanation=f"Node '{nid}' select path changed from '{old_n.config.path}' to '{new_n.config.path}'",
                            )
                        )
                elif old_n.kind == "construct":
                    if old_n.config.template != new_n.config.template:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.CONFIG_CHANGED,
                                change_type="construct_template_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/config/template",
                                before=old_n.config.template,
                                after=new_n.config.template,
                                explanation=f"Node '{nid}' construct template changed",
                            )
                        )
                elif old_n.kind == "constant":
                    if old_n.config.value != new_n.config.value:
                        changes.append(
                            SemanticChange(
                                category=ChangeCategory.CONFIG_CHANGED,
                                change_type="constant_value_changed",
                                severity=DiffSeverity.BREAKING,
                                node_id=nid,
                                target_id=nid,
                                path=f"nodes/{nid}/config/value",
                                before=old_n.config.value,
                                after=new_n.config.value,
                                explanation=f"Node '{nid}' constant value changed",
                            )
                        )
                elif old_n.config.model_dump() != new_n.config.model_dump():
                    changes.append(
                        SemanticChange(
                            category=ChangeCategory.CONFIG_CHANGED,
                            change_type="node_config_changed",
                            severity=DiffSeverity.BREAKING,
                            node_id=nid,
                            target_id=nid,
                            path=f"nodes/{nid}/config",
                            before=old_n.config.model_dump(mode="json"),
                            after=new_n.config.model_dump(mode="json"),
                            explanation=f"Node '{nid}' config changed",
                        )
                    )

    # 7. Edges changes
    target_map_old: dict[tuple[str, str], Edge] = {
        (e.target_node, e.target_input): e for e in old_workflow.edges
    }
    target_map_new: dict[tuple[str, str], Edge] = {
        (e.target_node, e.target_input): e for e in new_workflow.edges
    }

    # Same target input, source changed
    common_targets = set(target_map_old.keys()) & set(target_map_new.keys())
    for target in common_targets:
        old_e = target_map_old[target]
        new_e = target_map_new[target]
        if old_e.source != new_e.source:
            edge_id = _edge_identity(old_e)
            changes.append(
                SemanticChange(
                    category=ChangeCategory.EDGE_CHANGED,
                    change_type="edge_source_changed",
                    severity=DiffSeverity.BREAKING,
                    node_id=old_e.target_node,
                    edge_id=edge_id,
                    target_id=edge_id,
                    path=f"edges/{old_e.target_node}/{old_e.target_input}/source",
                    before=old_e.source.model_dump(mode="json"),
                    after=new_e.source.model_dump(mode="json"),
                    explanation=f"Edge targeting '{old_e.target_node}:{old_e.target_input}' source changed from '{_ref_str(old_e.source)}' to '{_ref_str(new_e.source)}'",
                )
            )

    unmapped_old = {k: v for k, v in target_map_old.items() if k not in target_map_new}
    unmapped_new = {k: v for k, v in target_map_new.items() if k not in target_map_old}

    # Detect edge target changed (same source, target changed)
    sources_in_unmapped_old = {_ref_str(e.source) for e in unmapped_old.values()}
    for src_str in sorted(sources_in_unmapped_old):
        old_candidates = sorted(
            [e for e in unmapped_old.values() if _ref_str(e.source) == src_str],
            key=lambda e: (e.target_node, e.target_input),
        )
        new_candidates = sorted(
            [e for e in unmapped_new.values() if _ref_str(e.source) == src_str],
            key=lambda e: (e.target_node, e.target_input),
        )
        pair_count = min(len(old_candidates), len(new_candidates))
        for i in range(pair_count):
            oe = old_candidates[i]
            ne = new_candidates[i]
            del unmapped_old[(oe.target_node, oe.target_input)]
            del unmapped_new[(ne.target_node, ne.target_input)]
            edge_id = _edge_identity(oe)
            changes.append(
                SemanticChange(
                    category=ChangeCategory.EDGE_CHANGED,
                    change_type="edge_target_changed",
                    severity=DiffSeverity.BREAKING,
                    node_id=oe.target_node,
                    edge_id=edge_id,
                    target_id=edge_id,
                    path=f"edges/{oe.target_node}/{oe.target_input}",
                    before={"target_node": oe.target_node, "target_input": oe.target_input},
                    after={"target_node": ne.target_node, "target_input": ne.target_input},
                    explanation=f"Edge from '{src_str}' target changed from '{oe.target_node}:{oe.target_input}' to '{ne.target_node}:{ne.target_input}'",
                )
            )

    # Remaining old edges: removed
    for (tn, ti), oe in sorted(unmapped_old.items(), key=lambda item: (item[0][0], item[0][1])):
        edge_id = _edge_identity(oe)
        reachable = _is_edge_reachable_to_terminal(old_workflow, oe)
        sev = DiffSeverity.BREAKING if reachable else DiffSeverity.WARNING
        changes.append(
            SemanticChange(
                category=ChangeCategory.EDGE_REMOVED,
                change_type="edge_removed",
                severity=sev,
                node_id=tn,
                edge_id=edge_id,
                target_id=edge_id,
                path=f"edges/{tn}/{ti}",
                before=oe.model_dump(mode="json"),
                after=None,
                explanation=f"Edge '{edge_id}' removed"
                + (
                    " (reachable to workflow outputs/assertions)" if reachable else " (unreachable)"
                ),
            )
        )

    # Remaining new edges: added
    for (tn, ti), ne in sorted(unmapped_new.items(), key=lambda item: (item[0][0], item[0][1])):
        edge_id = _edge_identity(ne)
        changes.append(
            SemanticChange(
                category=ChangeCategory.EDGE_ADDED,
                change_type="edge_added",
                severity=DiffSeverity.INFO,
                node_id=tn,
                edge_id=edge_id,
                target_id=edge_id,
                path=f"edges/{tn}/{ti}",
                before=None,
                after=ne.model_dump(mode="json"),
                explanation=f"Edge '{edge_id}' added",
            )
        )

    # Deterministic sorting
    changes.sort(key=change_sort_key)

    # Summary
    breaking_count = sum(1 for c in changes if c.severity == DiffSeverity.BREAKING)
    warning_count = sum(1 for c in changes if c.severity == DiffSeverity.WARNING)
    info_count = sum(1 for c in changes if c.severity == DiffSeverity.INFO)
    summary = DiffSummary(
        total_changes=len(changes),
        breaking_count=breaking_count,
        warning_count=warning_count,
        info_count=info_count,
        has_breaking=(breaking_count > 0),
    )

    return WorkflowDiff(
        old_workflow=old_display,
        new_workflow=new_display,
        old_fingerprint=old_fp,
        new_fingerprint=new_fp,
        identical=(len(changes) == 0),
        changes=changes,
        summary=summary,
    )
