"""Deterministic policy evaluator for declarative workflow contracts."""

from __future__ import annotations

from collections import deque
from urllib.parse import urlparse

from wysteria.ir.models import AssertNode, HttpNode, OutputNode, Workflow
from wysteria.policy.models import Policy, PolicyResult, PolicyRule, PolicyStatus, PolicyViolation
from wysteria.reporting.diagnostics import Severity


def violation_sort_key(v: PolicyViolation) -> tuple:
    """Deterministic sort key for policy violations."""
    return (
        0 if v.severity == Severity.ERROR else 1,
        v.code,
        v.policy,
        v.node_id or "",
        v.capability or "",
        v.path,
        v.message,
    )


def evaluate_policy(workflow: Workflow, policy: Policy) -> PolicyResult:
    """
    Deterministically evaluate a validated workflow against an explicit security/governance policy.
    Produces structured violations and PASS/BLOCK semantics.
    """
    violations: list[PolicyViolation] = []

    # 1. max_nodes: fails when node count exceeds limit
    if policy.max_nodes is not None:
        node_count = len(workflow.nodes)
        if node_count > policy.max_nodes:
            violations.append(
                PolicyViolation(
                    code="WYS451",
                    policy=PolicyRule.MAX_NODES.value,
                    severity=Severity.ERROR,
                    message=f"workflow node count exceeds policy limit: {node_count} > {policy.max_nodes}",
                    path="/nodes",
                )
            )

    # 2. max_edges: fails when edge count exceeds limit
    if policy.max_edges is not None:
        edge_count = len(workflow.edges)
        if edge_count > policy.max_edges:
            violations.append(
                PolicyViolation(
                    code="WYS452",
                    policy=PolicyRule.MAX_EDGES.value,
                    severity=Severity.ERROR,
                    message=f"workflow edge count exceeds policy limit: {edge_count} > {policy.max_edges}",
                    path="/edges",
                )
            )

    # 3. forbidden_capabilities: fails if any forbidden capability is requested
    if policy.forbidden_capabilities:
        forbidden_set = {
            c.value if hasattr(c, "value") else str(c) for c in policy.forbidden_capabilities
        }
        for index, cap in enumerate(workflow.capabilities):
            cap_str = cap.value if hasattr(cap, "value") else str(cap)
            if cap_str in forbidden_set:
                violations.append(
                    PolicyViolation(
                        code="WYS453",
                        policy=PolicyRule.FORBIDDEN_CAPABILITIES.value,
                        severity=Severity.ERROR,
                        message=f"forbidden capability requested: '{cap_str}'",
                        capability=cap_str,
                        path=f"/capabilities/{index}",
                    )
                )

    # 4. required_capabilities: fails if a required capability is absent
    if policy.required_capabilities:
        declared_caps = {c.value if hasattr(c, "value") else str(c) for c in workflow.capabilities}
        for req in policy.required_capabilities:
            req_str = req.value if hasattr(req, "value") else str(req)
            if req_str not in declared_caps:
                violations.append(
                    PolicyViolation(
                        code="WYS454",
                        policy=PolicyRule.REQUIRED_CAPABILITIES.value,
                        severity=Severity.ERROR,
                        message=f"required capability is missing: '{req_str}'",
                        capability=req_str,
                        path="/capabilities",
                    )
                )

    # 5. require_assertions: fails when the workflow has no assertions
    if policy.require_assertions:
        has_assertions = bool(workflow.assertions) or any(
            isinstance(n, AssertNode) for n in workflow.nodes
        )
        if not has_assertions:
            violations.append(
                PolicyViolation(
                    code="WYS455",
                    policy=PolicyRule.REQUIRE_ASSERTIONS.value,
                    severity=Severity.ERROR,
                    message="workflow has no assertions, but policy requires assertions",
                    path="/assertions",
                )
            )

    # 6. require_outputs: fails when the workflow has no outputs
    if policy.require_outputs:
        has_outputs = bool(workflow.outputs) or any(
            isinstance(n, OutputNode) for n in workflow.nodes
        )
        if not has_outputs:
            violations.append(
                PolicyViolation(
                    code="WYS456",
                    policy=PolicyRule.REQUIRE_OUTPUTS.value,
                    severity=Severity.ERROR,
                    message="workflow has no outputs, but policy requires outputs",
                    path="/outputs",
                )
            )

    # 7. forbid_unreachable_nodes: fails when nodes cannot contribute to an output/assertion
    if policy.forbid_unreachable_nodes:
        # Sinks are outputs and assertions
        reachable_nodes: set[str] = set()
        queue: deque[str] = deque()

        for out in workflow.outputs.values():
            if out.source.node:
                reachable_nodes.add(out.source.node)
                queue.append(out.source.node)

        for a in workflow.assertions:
            if a.source.node:
                reachable_nodes.add(a.source.node)
                queue.append(a.source.node)

        for n in workflow.nodes:
            if isinstance(n, (OutputNode, AssertNode)):
                reachable_nodes.add(n.id)
                queue.append(n.id)

        # Build reverse dependency graph: node_id -> predecessor node_ids feeding into it
        predecessors: dict[str, set[str]] = {n.id: set() for n in workflow.nodes}
        for edge in workflow.edges:
            if edge.source.node and edge.target_node in predecessors:
                predecessors[edge.target_node].add(edge.source.node)

        for n in workflow.nodes:
            for ref in n.inputs.values():
                if ref.node and n.id in predecessors:
                    predecessors[n.id].add(ref.node)

        while queue:
            curr = queue.popleft()
            for pred in predecessors.get(curr, ()):
                if pred not in reachable_nodes:
                    reachable_nodes.add(pred)
                    queue.append(pred)

        for index, node in enumerate(workflow.nodes):
            if node.id not in reachable_nodes:
                violations.append(
                    PolicyViolation(
                        code="WYS457",
                        policy=PolicyRule.FORBID_UNREACHABLE_NODES.value,
                        severity=Severity.ERROR,
                        message=f"node '{node.id}' cannot contribute to an output or assertion",
                        node_id=node.id,
                        path=f"/nodes/{index}",
                    )
                )

    # 8. HTTP-specific policy gating
    has_allowed_hosts = policy.allowed_http_hosts is not None
    has_forbidden_hosts = policy.forbidden_http_hosts is not None
    has_allowed_methods = policy.allowed_http_methods is not None

    if has_allowed_hosts or has_forbidden_hosts or has_allowed_methods:
        for index, node in enumerate(workflow.nodes):
            if isinstance(node, HttpNode):
                parsed = urlparse(node.config.url)
                hostname = parsed.hostname or ""

                if has_allowed_hosts and hostname not in policy.allowed_http_hosts:
                    violations.append(
                        PolicyViolation(
                            code="WYS458",
                            policy=PolicyRule.ALLOWED_HTTP_HOSTS.value,
                            severity=Severity.ERROR,
                            message=f"HTTP host '{hostname}' is not in the allowed list",
                            node_id=node.id,
                            path=f"/nodes/{index}/config/url",
                        )
                    )

                if has_forbidden_hosts and hostname in policy.forbidden_http_hosts:
                    violations.append(
                        PolicyViolation(
                            code="WYS459",
                            policy=PolicyRule.FORBIDDEN_HTTP_HOSTS.value,
                            severity=Severity.ERROR,
                            message=f"HTTP host '{hostname}' is explicitly forbidden",
                            node_id=node.id,
                            path=f"/nodes/{index}/config/url",
                        )
                    )

                if has_allowed_methods and node.config.method not in policy.allowed_http_methods:
                    violations.append(
                        PolicyViolation(
                            code="WYS460",
                            policy=PolicyRule.ALLOWED_HTTP_METHODS.value,
                            severity=Severity.ERROR,
                            message=f"HTTP method '{node.config.method}' is not in the allowed list",
                            node_id=node.id,
                            path=f"/nodes/{index}/config/method",
                        )
                    )

    # Deterministic violation ordering
    violations.sort(key=violation_sort_key)

    if violations:
        status = PolicyStatus.BLOCK
        passed = False
        blocked = True
        reasons = [f"policy violation ({v.policy}): {v.message}" for v in violations]
    else:
        status = PolicyStatus.PASS
        passed = True
        blocked = False
        reasons = ["policy checks passed"]

    return PolicyResult(
        status=status,
        passed=passed,
        blocked=blocked,
        policy_name=policy.name or policy.id,
        violations=violations,
        reasons=reasons,
    )
