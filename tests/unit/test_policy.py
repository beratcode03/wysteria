"""Comprehensive unit tests for the deterministic Policy Engine."""

import json
from pathlib import Path

import pytest

from wysteria.api import (
    CURRENT_POLICY_VERSION,
    GateDecision,
    Policy,
    PolicyLoadError,
    PolicyParseError,
    PolicyResult,
    PolicyRule,
    PolicyStatus,
    PolicyViolation,
    ReportStatus,
    Severity,
    build_developer_report,
    evaluate_gate,
    evaluate_policy,
    format_developer_report,
    format_policy_report,
    load_policy,
    parse_policy,
    parse_workflow,
    validate_workflow,
    verify_fixture,
    violation_sort_key,
)
from wysteria.diff import (
    ChangeCategory,
    DiffSeverity,
    DiffSummary,
    SemanticChange,
    WorkflowDiff,
)
from wysteria.fixtures.parser import parse_fixture
from wysteria.ir.models import Capability
from wysteria.validation.capabilities import CapabilityPolicy

# --- Fixtures / Sample Workflows ---

VALID_WORKFLOW_TEXT = """
ir_version: 1
name: test_flow
inputs:
  name:
    type: string
nodes:
  - id: greeting
    kind: constant
    inputs: {}
    config:
      value: hello
    output_type: string
edges: []
capabilities: []
assertions:
  - id: check_greeting
    source:
      node: greeting
    predicate: exists
outputs:
  result:
    source:
      node: greeting
    type: string
"""

WORKFLOW_WITH_CAPABILITIES_TEXT = """
ir_version: 1
name: cap_flow
inputs: {}
nodes:
  - id: greeting
    kind: constant
    inputs: {}
    config:
      value: hello
    output_type: string
edges: []
capabilities:
  - network.http
  - file.read
assertions: []
outputs:
  result:
    source:
      node: greeting
    type: string
"""

WORKFLOW_NO_OUTPUTS_TEXT = """
ir_version: 1
name: no_outputs
inputs: {}
nodes:
  - id: greeting
    kind: constant
    inputs: {}
    config:
      value: hello
    output_type: string
edges: []
capabilities: []
assertions:
  - id: check_val
    source:
      node: greeting
    predicate: exists
outputs: {}
"""

WORKFLOW_NO_ASSERTIONS_TEXT = """
ir_version: 1
name: no_assertions
inputs: {}
nodes:
  - id: greeting
    kind: constant
    inputs: {}
    config:
      value: hello
    output_type: string
edges: []
capabilities: []
assertions: []
outputs:
  result:
    source:
      node: greeting
    type: string
"""

WORKFLOW_WITH_ASSERT_NODE_TEXT = """
ir_version: 1
name: assert_node_flow
inputs: {}
nodes:
  - id: greeting
    kind: constant
    inputs: {}
    config:
      value: hello
    output_type: string
  - id: assert_step
    kind: assert
    inputs:
      value:
        node: greeting
    config:
      predicate: exists
    output_type: boolean
edges:
  - source:
      node: greeting
    target_node: assert_step
    target_input: value
capabilities: []
assertions: []
outputs:
  result:
    source:
      node: greeting
    type: string
"""

WORKFLOW_WITH_UNREACHABLE_NODES_TEXT = """
ir_version: 1
name: unreachable_flow
inputs: {}
nodes:
  - id: active_node
    kind: constant
    inputs: {}
    config:
      value: used
    output_type: string
  - id: orphan_node
    kind: constant
    inputs: {}
    config:
      value: unused
    output_type: string
  - id: orphan_child
    kind: transform
    inputs:
      value:
        node: orphan_node
    config:
      operation: uppercase
    output_type: string
edges:
  - source:
      node: orphan_node
    target_node: orphan_child
    target_input: value
capabilities: []
assertions: []
outputs:
  result:
    source:
      node: active_node
    type: string
"""


def _get_wf(text: str):
    parsed = parse_workflow(text, filename="workflow.yaml")
    res = validate_workflow(parsed, policy=CapabilityPolicy(allowed=frozenset(Capability)))
    assert res.valid
    return res.workflow


# --- 1. Valid Policy Parsing ---


def test_valid_policy_yaml():
    text = """
policy_version: 1
name: security-baseline
description: Standard enterprise policy
max_nodes: 50
max_edges: 100
forbidden_capabilities:
  - network.http
  - process.execute
required_capabilities:
  - file.read
require_assertions: true
require_outputs: true
forbid_unreachable_nodes: true
"""
    p = parse_policy(text)
    assert p.policy_version == CURRENT_POLICY_VERSION
    assert p.name == "security-baseline"
    assert p.description == "Standard enterprise policy"
    assert p.max_nodes == 50
    assert p.max_edges == 100
    assert len(p.forbidden_capabilities) == 2
    assert len(p.required_capabilities) == 1
    assert p.require_assertions is True
    assert p.require_outputs is True
    assert p.forbid_unreachable_nodes is True


def test_valid_policy_json():
    data = {
        "policy_version": 1,
        "name": "json-policy",
        "max_nodes": 10,
        "max_edges": 20,
        "require_assertions": False,
        "require_outputs": True,
        "forbid_unreachable_nodes": False,
    }
    p = parse_policy(json.dumps(data), filename="policy.json")
    assert p.name == "json-policy"
    assert p.max_nodes == 10
    assert p.max_edges == 20
    assert p.require_assertions is False
    assert p.require_outputs is True


def test_valid_minimal_policy():
    text = "policy_version: 1\n"
    p = parse_policy(text)
    assert p.policy_version == 1
    assert p.max_nodes is None
    assert p.max_edges is None
    assert p.forbidden_capabilities == []
    assert p.required_capabilities == []
    assert p.require_assertions is False
    assert p.require_outputs is False
    assert p.forbid_unreachable_nodes is False


def test_valid_policy_null_fields():
    text = """
policy_version: 1
forbidden_capabilities: null
required_capabilities: null
require_assertions: null
require_outputs: null
forbid_unreachable_nodes: null
"""
    p = parse_policy(text)
    assert p.forbidden_capabilities == []
    assert p.required_capabilities == []
    assert p.require_assertions is False
    assert p.require_outputs is False
    assert p.forbid_unreachable_nodes is False


# --- 2. Invalid Policy Parsing ---


def test_invalid_policy_unknown_field():
    text = "policy_version: 1\nunknown_rule: 42\n"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"
    assert "extra_forbidden" in str(exc_info.value) or "unknown_rule" in str(exc_info.value)


def test_invalid_policy_version():
    text = "policy_version: 99\n"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"
    assert "unsupported policy version" in str(exc_info.value)


def test_invalid_policy_negative_limits():
    text = "policy_version: 1\nmax_nodes: -5\n"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"


def test_invalid_policy_malformed_yaml():
    text = "policy_version: 1\n  invalid: [unclosed"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"


def test_invalid_policy_empty():
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy("")
    assert exc_info.value.code == "WYS450"
    assert "empty" in str(exc_info.value)


def test_invalid_policy_non_mapping():
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy("- item1\n- item2\n")
    assert exc_info.value.code == "WYS450"


def test_invalid_policy_duplicate_keys():
    text = "policy_version: 1\nmax_nodes: 5\nmax_nodes: 10\n"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"
    assert "duplicate key" in str(exc_info.value)


def test_invalid_policy_yaml_anchors_forbidden():
    text = "policy_version: 1\ndefs: &anchor 5\nmax_nodes: *anchor\n"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"
    assert "anchors and aliases are forbidden" in str(exc_info.value)


def test_invalid_policy_custom_yaml_tag_forbidden():
    text = "policy_version: 1\nmax_nodes: !custom 5\n"
    with pytest.raises(PolicyParseError) as exc_info:
        parse_policy(text)
    assert exc_info.value.code == "WYS450"
    assert "custom YAML tags" in str(exc_info.value)


def test_policy_load_nonexistent_file(tmp_path: Path):
    nonexistent = tmp_path / "missing.yaml"
    with pytest.raises(PolicyLoadError):
        load_policy(nonexistent)


def test_policy_load_valid_file(tmp_path: Path):
    valid_file = tmp_path / "policy.yaml"
    valid_file.write_text("policy_version: 1\nmax_nodes: 10\n", encoding="utf-8")
    loaded = load_policy(valid_file)
    assert loaded.max_nodes == 10


# --- 3. max_nodes Policy ---


def test_policy_max_nodes_pass():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # 1 node
    p = Policy(max_nodes=1)
    res = evaluate_policy(wf, p)
    assert res.passed
    assert res.status == PolicyStatus.PASS
    assert len(res.violations) == 0


def test_policy_max_nodes_fail():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # 1 node
    p = Policy(max_nodes=0)
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert res.status == PolicyStatus.BLOCK
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.code == "WYS451"
    assert v.policy == PolicyRule.MAX_NODES.value
    assert v.severity == Severity.ERROR
    assert "1 > 0" in v.message


# --- 4. max_edges Policy ---


def test_policy_max_edges_pass():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # 0 edges
    p = Policy(max_edges=0)
    res = evaluate_policy(wf, p)
    assert res.passed
    assert len(res.violations) == 0


def test_policy_max_edges_fail():
    wf = _get_wf(WORKFLOW_WITH_UNREACHABLE_NODES_TEXT)  # 1 edge
    p = Policy(max_edges=0)
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.code == "WYS452"
    assert v.policy == PolicyRule.MAX_EDGES.value
    assert "1 > 0" in v.message


# --- 5. forbidden_capabilities Policy ---


def test_policy_forbidden_capabilities_pass():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # no capabilities
    p = Policy(forbidden_capabilities=["network.http"])
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_forbidden_capabilities_fail():
    wf = _get_wf(WORKFLOW_WITH_CAPABILITIES_TEXT)  # network.http, file.read
    p = Policy(forbidden_capabilities=["network.http"])
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.code == "WYS453"
    assert v.policy == PolicyRule.FORBIDDEN_CAPABILITIES.value
    assert v.capability == "network.http"
    assert "network.http" in v.message


# --- 6. required_capabilities Policy ---


def test_policy_required_capabilities_pass():
    wf = _get_wf(WORKFLOW_WITH_CAPABILITIES_TEXT)  # network.http, file.read
    p = Policy(required_capabilities=["file.read"])
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_required_capabilities_fail():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # no capabilities
    p = Policy(required_capabilities=["file.read"])
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.code == "WYS454"
    assert v.policy == PolicyRule.REQUIRED_CAPABILITIES.value
    assert v.capability == "file.read"
    assert "file.read" in v.message


# --- 7. require_assertions Policy ---


def test_policy_require_assertions_pass_with_workflow_assertion():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # has check_greeting assertion
    p = Policy(require_assertions=True)
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_require_assertions_pass_with_assert_node():
    wf = _get_wf(WORKFLOW_WITH_ASSERT_NODE_TEXT)  # has AssertNode
    p = Policy(require_assertions=True)
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_require_assertions_fail():
    wf = _get_wf(WORKFLOW_NO_ASSERTIONS_TEXT)  # no assertions
    p = Policy(require_assertions=True)
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.code == "WYS455"
    assert v.policy == PolicyRule.REQUIRE_ASSERTIONS.value


# --- 8. require_outputs Policy ---


def test_policy_require_outputs_pass():
    wf = _get_wf(VALID_WORKFLOW_TEXT)  # has result output
    p = Policy(require_outputs=True)
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_require_outputs_fail():
    wf = _get_wf(WORKFLOW_NO_OUTPUTS_TEXT)  # outputs: {}
    p = Policy(require_outputs=True)
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert len(res.violations) == 1
    v = res.violations[0]
    assert v.code == "WYS456"
    assert v.policy == PolicyRule.REQUIRE_OUTPUTS.value


# --- 9. forbid_unreachable_nodes Policy ---


def test_policy_forbid_unreachable_nodes_pass_when_all_contribute_to_output():
    wf = _get_wf(VALID_WORKFLOW_TEXT)
    p = Policy(forbid_unreachable_nodes=True)
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_forbid_unreachable_nodes_pass_when_contribute_to_assertion():
    text = """
ir_version: 1
name: assert_flow
inputs: {}
nodes:
  - id: input_const
    kind: constant
    inputs: {}
    config:
      value: 123
    output_type: integer
edges: []
capabilities: []
assertions:
  - id: check_exists
    source:
      node: input_const
    predicate: exists
outputs: {}
"""
    wf = _get_wf(text)
    p = Policy(forbid_unreachable_nodes=True)
    res = evaluate_policy(wf, p)
    assert res.passed


def test_policy_forbid_unreachable_nodes_fail_orphan_nodes():
    wf = _get_wf(WORKFLOW_WITH_UNREACHABLE_NODES_TEXT)
    # active_node contributes to output.
    # orphan_node -> orphan_child do not contribute to output or assertion!
    p = Policy(forbid_unreachable_nodes=True)
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert len(res.violations) == 2
    node_ids = {v.node_id for v in res.violations}
    assert node_ids == {"orphan_node", "orphan_child"}
    for v in res.violations:
        assert v.code == "WYS457"
        assert v.policy == PolicyRule.FORBID_UNREACHABLE_NODES.value


# --- 10. Multiple Simultaneous Violations ---


def test_multiple_simultaneous_violations():
    # Workflow with 3 nodes, 1 edge, and unreachable nodes:
    wf = _get_wf(WORKFLOW_WITH_UNREACHABLE_NODES_TEXT)
    p = Policy(
        max_nodes=1,
        max_edges=0,
        require_assertions=True,
        forbid_unreachable_nodes=True,
    )
    res = evaluate_policy(wf, p)
    assert not res.passed
    assert res.blocked
    assert res.status == PolicyStatus.BLOCK
    # Should violate:
    # 1. max_nodes (3 > 1)
    # 2. max_edges (1 > 0)
    # 3. require_assertions
    # 4. forbid_unreachable_nodes (orphan_child, orphan_node)
    codes = [v.code for v in res.violations]
    assert "WYS451" in codes
    assert "WYS452" in codes
    assert "WYS455" in codes
    assert "WYS457" in codes
    assert len(res.violations) == 5  # 2 unreachable nodes


# --- 11. Deterministic Violation Ordering ---


def test_deterministic_violation_ordering():
    wf = _get_wf(WORKFLOW_WITH_UNREACHABLE_NODES_TEXT)
    p = Policy(
        max_nodes=1,
        max_edges=0,
        require_assertions=True,
        forbid_unreachable_nodes=True,
    )
    res1 = evaluate_policy(wf, p)
    res2 = evaluate_policy(wf, p)

    assert len(res1.violations) == len(res2.violations)
    for v1, v2 in zip(res1.violations, res2.violations, strict=True):
        assert v1.model_dump() == v2.model_dump()

    # Verify sort key directly
    sort_keys = [violation_sort_key(v) for v in res1.violations]
    assert sort_keys == sorted(sort_keys)


# --- 12. JSON Serialization & Reporting ---


def test_policy_result_json_serialization():
    wf = _get_wf(WORKFLOW_WITH_UNREACHABLE_NODES_TEXT)
    p = Policy(name="audit-policy", max_nodes=1)
    res = evaluate_policy(wf, p)
    json_str = res.to_json()

    assert "\x1b" not in json_str
    data = json.loads(json_str)
    assert data["status"] == "BLOCK"
    assert data["passed"] is False
    assert data["blocked"] is True
    assert data["policy_name"] == "audit-policy"
    assert len(data["violations"]) == 1
    assert data["violations"][0]["code"] == "WYS451"
    assert data["violations"][0]["policy"] == "max_nodes"


def test_format_policy_report_human():
    wf = _get_wf(VALID_WORKFLOW_TEXT)
    p = Policy(name="sample-policy")
    res = evaluate_policy(wf, p)
    rep = format_policy_report(res, workflow_display="test.yaml", policy_display="sample.yaml")
    assert "Wysteria Policy Check" in rep
    assert "✓ PASS" in rep
    assert "Workflow: test.yaml" in rep
    assert "Policy: sample.yaml" in rep


def test_format_policy_report_human_blocked():
    wf = _get_wf(VALID_WORKFLOW_TEXT)
    p = Policy(name="strict-policy", max_nodes=0)
    res = evaluate_policy(wf, p)
    rep = format_policy_report(res, workflow_display="test.yaml", policy_display="strict.yaml")
    assert "✗ BLOCK" in rep
    assert "WYS451" in rep
    assert "max_nodes" in rep


# --- 13. Gate Integration ---


def test_gate_with_passing_policy():
    gate = evaluate_gate(
        ReportStatus.PASS, None, policy_result=PolicyResult(status=PolicyStatus.PASS, passed=True)
    )
    assert gate.decision == GateDecision.PASS
    assert gate.reasons == ["passing verification"]


def test_gate_with_violating_policy():
    viol = PolicyViolation(code="WYS451", policy="max_nodes", message="too many nodes")
    policy_res = PolicyResult(
        status=PolicyStatus.BLOCK, passed=False, blocked=True, violations=[viol]
    )
    gate = evaluate_gate(ReportStatus.PASS, None, policy_result=policy_res)
    assert gate.decision == GateDecision.BLOCK
    assert any("policy violation" in r for r in gate.reasons)
    assert any("too many nodes" in r for r in gate.reasons)


def test_gate_with_failing_verification_and_violating_policy():
    viol = PolicyViolation(code="WYS451", policy="max_nodes", message="too many nodes")
    policy_res = PolicyResult(
        status=PolicyStatus.BLOCK, passed=False, blocked=True, violations=[viol]
    )
    gate = evaluate_gate(ReportStatus.OUTPUT_MISMATCH, None, policy_result=policy_res)
    # Policy block takes precedence as BLOCK
    assert gate.decision == GateDecision.BLOCK
    assert "output mismatch" in gate.reasons
    assert any("policy violation" in r for r in gate.reasons)


def test_gate_with_failing_verification_and_passing_policy():
    policy_res = PolicyResult(status=PolicyStatus.PASS, passed=True)
    gate = evaluate_gate(ReportStatus.OUTPUT_MISMATCH, None, policy_result=policy_res)
    assert gate.decision == GateDecision.FAIL
    assert "output mismatch" in gate.reasons


def test_gate_informational_diff_with_passing_policy():
    diff = WorkflowDiff(
        identical=False,
        changes=[
            SemanticChange(
                category=ChangeCategory.NODE_ADDED,
                change_type="ADDED",
                severity=DiffSeverity.INFO,
                explanation="metadata changed",
            )
        ],
        summary=DiffSummary(total_changes=1, info_count=1),
    )
    policy_res = PolicyResult(status=PolicyStatus.PASS, passed=True)
    gate = evaluate_gate(ReportStatus.PASS, diff, policy_result=policy_res)
    assert gate.decision == GateDecision.PASS


# --- 14. DeveloperReport with Policy Integration ---


def test_developer_report_with_policy():
    wf_parsed = parse_workflow(VALID_WORKFLOW_TEXT, filename="workflow.yaml")
    fix_text = """
fixture_version: 1
id: test_fix
inputs:
  name: world
expected:
  outputs:
    result: hello
"""
    fix_parsed = parse_fixture(fix_text, filename="fixture.yaml")
    verif_res = verify_fixture(wf_parsed, fix_parsed)
    assert verif_res.success

    policy_viol = PolicyViolation(
        code="WYS451", policy="max_nodes", message="node count exceeds limit: 1 > 0"
    )
    pol_res = PolicyResult(
        status=PolicyStatus.BLOCK,
        passed=False,
        blocked=True,
        policy_name="node-limit",
        violations=[policy_viol],
    )

    report = build_developer_report(
        verif_res,
        workflow=wf_parsed,
        fixture=fix_parsed,
        policy_result=pol_res,
    )

    assert report.policy is not None
    assert report.policy.blocked is True
    assert report.gate is not None
    assert report.gate.decision == GateDecision.BLOCK

    rep_text = format_developer_report(report)
    assert "Policy Evaluation" in rep_text
    assert "✗ BLOCK" in rep_text
    assert "WYS451" in rep_text
    assert "Gate Decision" in rep_text

    rep_json = json.loads(report.to_json())
    assert "policy" in rep_json
    assert rep_json["policy"]["blocked"] is True
    assert rep_json["gate"]["decision"] == "BLOCK"


# --- HTTP Policy Tests ---

HTTP_WORKFLOW_TEXT = """
ir_version: 1
name: http_flow
inputs: {}
nodes:
  - id: n1
    kind: constant
    config:
      value: "dummy"
    output_type: string
  - id: h1
    kind: http
    config:
      method: GET
      url: https://api.example.com/data
    output_type: string
  - id: h2
    kind: http
    config:
      method: POST
      url: https://internal.corp.com/v1
    output_type: string
  - id: h3
    kind: http
    config:
      method: GET
      url: https://evil.com/exfil
    output_type: string
edges: []
capabilities:
  - network.http
assertions: []
outputs:
  result:
    source:
      node: h1
    type: string
"""


def test_http_policy_backward_compatibility():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)
    pol = parse_policy("policy_version: 1\nname: blank")
    res = evaluate_policy(wf, pol)
    assert res.passed
    assert res.status == PolicyStatus.PASS


def test_http_policy_allowed_hosts():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)
    pol1 = parse_policy(
        "policy_version: 1\nallowed_http_hosts: ['api.example.com', 'internal.corp.com', 'evil.com']"
    )
    res1 = evaluate_policy(wf, pol1)
    assert res1.passed

    pol2 = parse_policy("policy_version: 1\nallowed_http_hosts: ['api.example.com']")
    res2 = evaluate_policy(wf, pol2)
    assert not res2.passed
    assert len(res2.violations) == 2
    assert res2.violations[0].code == "WYS458"
    assert res2.violations[0].node_id == "h2"
    assert res2.violations[1].code == "WYS458"
    assert res2.violations[1].node_id == "h3"


def test_http_policy_forbidden_hosts():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)

    pol3 = parse_policy("policy_version: 1\nforbidden_http_hosts: ['evil.com']")
    res3 = evaluate_policy(wf, pol3)
    assert not res3.passed
    assert len(res3.violations) == 1
    assert res3.violations[0].code == "WYS459"
    assert res3.violations[0].node_id == "h3"

    pol4 = parse_policy("policy_version: 1\nforbidden_http_hosts: ['unknown.com']")
    res4 = evaluate_policy(wf, pol4)
    assert res4.passed


def test_http_policy_methods():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)

    pol5 = parse_policy("policy_version: 1\nallowed_http_methods: ['GET', 'POST']")
    res5 = evaluate_policy(wf, pol5)
    assert res5.passed

    pol6 = parse_policy("policy_version: 1\nallowed_http_methods: ['GET']")
    res6 = evaluate_policy(wf, pol6)
    assert not res6.passed
    assert len(res6.violations) == 1
    assert res6.violations[0].code == "WYS460"
    assert res6.violations[0].node_id == "h2"
    assert "POST" in res6.violations[0].message


def test_http_policy_exact_matching():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)
    pol7 = parse_policy(
        "policy_version: 1\nallowed_http_hosts: ['example.com', 'evil-api.example.com', 'api.example.com.evil.com']"
    )
    res7 = evaluate_policy(wf, pol7)
    assert not res7.passed
    assert len(res7.violations) == 3


def test_http_policy_multiple_nodes_and_deterministic_order():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)
    pol = parse_policy("policy_version: 1\nallowed_http_hosts: []")
    res = evaluate_policy(wf, pol)
    assert not res.passed
    assert len(res.violations) == 3
    assert res.violations[0].node_id == "h1"
    assert res.violations[1].node_id == "h2"
    assert res.violations[2].node_id == "h3"


def test_http_policy_both_allowed_and_forbidden():
    wf = _get_wf(HTTP_WORKFLOW_TEXT)
    pol = parse_policy(
        "policy_version: 1\nallowed_http_hosts: ['api.example.com']\nforbidden_http_hosts: ['api.example.com']"
    )
    res = evaluate_policy(wf, pol)
    assert not res.passed
    assert len(res.violations) == 3
    codes = [v.code for v in res.violations]
    assert codes == ["WYS458", "WYS458", "WYS459"]

    v_458 = [v for v in res.violations if v.code == "WYS458"]
    assert v_458[0].node_id == "h2"
    assert v_458[1].node_id == "h3"
    v_459 = [v for v in res.violations if v.code == "WYS459"]
    assert v_459[0].node_id == "h1"


def test_http_policy_non_http_nodes_unaffected():
    wf_text = """
ir_version: 1
name: http_flow
inputs: {}
nodes:
  - id: n1
    kind: constant
    config:
      value: "dummy"
    output_type: string
edges: []
capabilities: []
assertions: []
outputs:
  result:
    source:
      node: n1
    type: string
"""
    wf = _get_wf(wf_text)
    pol = parse_policy(
        "policy_version: 1\nallowed_http_hosts: ['api.example.com']\nforbidden_http_hosts: ['evil.com']\nallowed_http_methods: ['GET']"
    )
    res = evaluate_policy(wf, pol)
    assert res.passed
