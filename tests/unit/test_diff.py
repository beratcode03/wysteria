"""Unit tests for deterministic semantic workflow diffing."""

from __future__ import annotations

import json

from wysteria.api import (
    ChangeCategory,
    DeveloperReport,
    DiffSeverity,
    ParsedWorkflow,
    Workflow,
    build_developer_report,
    diff_workflows,
    format_workflow_diff,
    parse_workflow,
    validate_workflow,
    verify_fixture,
)
from wysteria.fixtures.parser import parse_fixture
from wysteria.ir.models import Capability
from wysteria.validation.capabilities import CapabilityPolicy

BASE_WORKFLOW_YAML = """ir_version: 1
name: user_processor
metadata:
  description: Process and transform user greeting
  labels: [user, greeting]
inputs:
  username:
    type: string
    required: true
nodes:
  - id: trim_step
    kind: transform
    inputs:
      value:
        input: username
    config:
      operation: trim
    output_type: string
  - id: format_step
    kind: transform
    inputs:
      value:
        node: trim_step
    config:
      operation: uppercase
    output_type: string
  - id: check_step
    kind: assert
    inputs:
      value:
        node: format_step
    config:
      predicate: type_is
      expected: string
    output_type: boolean
  - id: package_step
    kind: construct
    inputs:
      name:
        node: format_step
    config:
      template:
        greeting: "Hello, ${name}!"
    output_type: object
edges:
  - source: {input: username}
    target_node: trim_step
    target_input: value
  - source: {node: trim_step}
    target_node: format_step
    target_input: value
  - source: {node: format_step}
    target_node: check_step
    target_input: value
  - source: {node: format_step}
    target_node: package_step
    target_input: name
capabilities: []
assertions:
  - id: name_valid
    source: {node: check_step}
    predicate: equals
    expected: true
outputs:
  result:
    source: {node: package_step}
    type: object
"""


def _get_wf(yaml_text: str, policy: CapabilityPolicy | None = None) -> Workflow:
    parsed: ParsedWorkflow = parse_workflow(yaml_text, filename="workflow.yaml")
    res = validate_workflow(parsed, policy=policy)
    assert res.valid and res.workflow is not None, f"Validation failed: {res.diagnostics}"
    return res.workflow


def test_identical_workflows_produce_no_diff():
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(BASE_WORKFLOW_YAML)

    diff = diff_workflows(wf1, wf2)
    assert diff.identical is True
    assert len(diff.changes) == 0
    assert diff.summary.total_changes == 0
    assert diff.summary.has_breaking is False
    assert "No semantic changes." in format_workflow_diff(diff)


def test_formatting_and_key_order_only_changes_produce_no_diff():
    # Different whitespace, comment, and key order
    reordered_yaml = """# Comment line
name: user_processor
ir_version: 1
inputs:
  username:
    required: true
    type: string
capabilities: []
metadata:
  labels:
    - user
    - greeting
  description: Process and transform user greeting
outputs:
  result:
    type: object
    source:
      node: package_step
nodes:
  - id: trim_step
    kind: transform
    config:
      operation: trim
    output_type: string
    inputs:
      value:
        input: username
  - id: format_step
    kind: transform
    output_type: string
    inputs:
      value:
        node: trim_step
    config:
      operation: uppercase
  - id: check_step
    kind: assert
    inputs:
      value:
        node: format_step
    config:
      expected: string
      predicate: type_is
    output_type: boolean
  - id: package_step
    kind: construct
    inputs:
      name:
        node: format_step
    output_type: object
    config:
      template:
        greeting: "Hello, ${name}!"
assertions:
  - id: name_valid
    predicate: equals
    expected: true
    source:
      node: check_step
edges:
  - source:
      input: username
    target_node: trim_step
    target_input: value
  - target_node: format_step
    target_input: value
    source:
      node: trim_step
  - source:
      node: format_step
    target_node: check_step
    target_input: value
  - source:
      node: format_step
    target_node: package_step
    target_input: name
"""
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(reordered_yaml)

    diff = diff_workflows(wf1, wf2)
    assert diff.identical is True
    assert len(diff.changes) == 0
    assert diff.summary.total_changes == 0


def test_node_added():
    yaml_with_node = BASE_WORKFLOW_YAML.replace(
        "capabilities: []",
        """capabilities: []
""",
    )
    # Add a standalone constant node
    yaml_with_node = yaml_with_node.replace(
        "  - id: package_step",
        """  - id: extra_constant
    kind: constant
    inputs: {}
    config:
      value: "extra"
    output_type: string
  - id: package_step""",
    )
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(yaml_with_node)

    diff = diff_workflows(wf1, wf2)
    assert diff.identical is False
    assert len(diff.changes) == 1

    change = diff.changes[0]
    assert change.category == ChangeCategory.NODE_ADDED
    assert change.change_type == "node_added"
    assert change.severity == DiffSeverity.INFO
    assert change.node_id == "extra_constant"
    assert change.before is None
    assert change.after["id"] == "extra_constant"
    assert diff.summary.info_count == 1
    assert diff.summary.breaking_count == 0


def test_node_removed():
    # Remove trim_step by routing username directly to format_step
    modified_yaml = BASE_WORKFLOW_YAML.replace(
        """  - id: trim_step
    kind: transform
    inputs:
      value:
        input: username
    config:
      operation: trim
    output_type: string
  - id: format_step
    kind: transform
    inputs:
      value:
        node: trim_step
    config:
      operation: uppercase
    output_type: string""",
        """  - id: format_step
    kind: transform
    inputs:
      value:
        input: username
    config:
      operation: uppercase
    output_type: string""",
    ).replace(
        """  - source: {input: username}
    target_node: trim_step
    target_input: value
  - source: {node: trim_step}
    target_node: format_step
    target_input: value""",
        """  - source: {input: username}
    target_node: format_step
    target_input: value""",
    )

    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    assert diff.identical is False

    node_removals = [c for c in diff.changes if c.category == ChangeCategory.NODE_REMOVED]
    assert len(node_removals) == 1
    rem = node_removals[0]
    assert rem.node_id == "trim_step"
    assert rem.severity == DiffSeverity.BREAKING
    assert rem.after is None
    assert rem.before["id"] == "trim_step"


def test_node_kind_and_output_type_changed():
    # Change format_step from transform (string) to constant (integer)
    modified_yaml = BASE_WORKFLOW_YAML.replace(
        """  - id: format_step
    kind: transform
    inputs:
      value:
        node: trim_step
    config:
      operation: uppercase
    output_type: string""",
        """  - id: format_step
    kind: constant
    inputs: {}
    config:
      value: 42
    output_type: integer""",
    ).replace(
        """  - source: {node: trim_step}
    target_node: format_step
    target_input: value\n""",
        "",
    )

    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    changes_by_type = {c.change_type: c for c in diff.changes}

    assert "node_kind_changed" in changes_by_type
    assert changes_by_type["node_kind_changed"].before == "transform"
    assert changes_by_type["node_kind_changed"].after == "constant"
    assert changes_by_type["node_kind_changed"].severity == DiffSeverity.BREAKING

    assert "node_output_type_changed" in changes_by_type
    assert changes_by_type["node_output_type_changed"].before == "string"
    assert changes_by_type["node_output_type_changed"].after == "integer"
    assert changes_by_type["node_output_type_changed"].severity == DiffSeverity.BREAKING


def test_transform_operation_changed():
    modified_yaml = BASE_WORKFLOW_YAML.replace("operation: uppercase", "operation: lowercase")
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    assert len(diff.changes) == 1
    change = diff.changes[0]
    assert change.category == ChangeCategory.CONFIG_CHANGED
    assert change.change_type == "transform_operation_changed"
    assert change.severity == DiffSeverity.BREAKING
    assert change.node_id == "format_step"
    assert change.before == "uppercase"
    assert change.after == "lowercase"
    assert diff.summary.breaking_count == 1


def test_assert_config_changed():
    modified_yaml = BASE_WORKFLOW_YAML.replace("predicate: type_is", "predicate: equals").replace(
        "expected: string", "expected: true"
    )
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    changes_by_type = {c.change_type: c for c in diff.changes}

    assert "assert_predicate_changed" in changes_by_type
    assert changes_by_type["assert_predicate_changed"].before == "type_is"
    assert changes_by_type["assert_predicate_changed"].after == "equals"
    assert changes_by_type["assert_predicate_changed"].severity == DiffSeverity.BREAKING

    assert "assert_expected_changed" in changes_by_type
    assert changes_by_type["assert_expected_changed"].before == "string"
    assert changes_by_type["assert_expected_changed"].after is True


def test_select_and_construct_and_constant_config_changed():
    # Construct template changed
    modified_yaml = BASE_WORKFLOW_YAML.replace(
        'greeting: "Hello, ${name}!"', 'greeting: "Hi, ${name}!"'
    )
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    assert len(diff.changes) == 1
    change = diff.changes[0]
    assert change.change_type == "construct_template_changed"
    assert change.severity == DiffSeverity.BREAKING
    assert change.before == {"greeting": "Hello, ${name}!"}
    assert change.after == {"greeting": "Hi, ${name}!"}


def test_edge_added_and_removed_with_reachability():
    # Add a dead/unreachable node and edge in wf1
    dead_node_yaml = BASE_WORKFLOW_YAML.replace(
        "  - id: package_step",
        """  - id: dead_node
    kind: constant
    inputs: {}
    config:
      value: "dead"
    output_type: string
  - id: dead_consumer
    kind: transform
    inputs:
      value:
        node: dead_node
    config:
      operation: uppercase
    output_type: string
  - id: package_step""",
    ).replace(
        "edges:\n",
        """edges:
  - source: {node: dead_node}
    target_node: dead_consumer
    target_input: value
""",
    )

    wf1 = _get_wf(dead_node_yaml)
    wf2 = _get_wf(BASE_WORKFLOW_YAML)

    diff = diff_workflows(wf1, wf2)

    # The edge from dead_node to dead_consumer was removed and was unreachable to outputs
    edge_removals = [
        c
        for c in diff.changes
        if c.category == ChangeCategory.EDGE_REMOVED and "dead_node" in (c.edge_id or "")
    ]
    assert len(edge_removals) == 1
    assert edge_removals[0].severity == DiffSeverity.WARNING

    # Now test edge removal that is REACHABLE (e.g. format_step -> package_step)
    # in reverse diff:
    diff_rev = diff_workflows(wf2, wf1)
    edge_adds = [
        c
        for c in diff_rev.changes
        if c.category == ChangeCategory.EDGE_ADDED and "dead_node" in (c.edge_id or "")
    ]
    assert len(edge_adds) == 1
    assert edge_adds[0].severity == DiffSeverity.INFO


def test_edge_source_changed():
    # Change package_step input 'name' to come from trim_step instead of format_step
    modified_yaml = BASE_WORKFLOW_YAML.replace(
        """  - id: package_step
    kind: construct
    inputs:
      name:
        node: format_step""",
        """  - id: package_step
    kind: construct
    inputs:
      name:
        node: trim_step""",
    ).replace(
        """  - source: {node: format_step}
    target_node: package_step
    target_input: name""",
        """  - source: {node: trim_step}
    target_node: package_step
    target_input: name""",
    )

    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    edge_changes = [c for c in diff.changes if c.change_type == "edge_source_changed"]
    assert len(edge_changes) == 1
    ch = edge_changes[0]
    assert ch.category == ChangeCategory.EDGE_CHANGED
    assert ch.severity == DiffSeverity.BREAKING
    assert ch.before["node"] == "format_step"
    assert ch.after["node"] == "trim_step"


def test_edge_target_changed():
    # Divert edge from one target to another
    yaml1 = """ir_version: 1
name: test_flow
inputs:
  x: {type: string}
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config: {value: "hi"}
    output_type: string
  - id: n2
    kind: construct
    inputs:
      v: {node: n1}
    config: {template: {greeting: "hi"}}
    output_type: object
  - id: n3
    kind: construct
    inputs: {}
    config: {template: {greeting: "bye"}}
    output_type: object
edges:
  - source: {node: n1}
    target_node: n2
    target_input: v
outputs:
  out: {source: {node: n2}, type: object}
"""

    yaml2 = """ir_version: 1
name: test_flow
inputs:
  x: {type: string}
nodes:
  - id: n1
    kind: constant
    inputs: {}
    config: {value: "hi"}
    output_type: string
  - id: n2
    kind: construct
    inputs: {}
    config: {template: {greeting: "hi"}}
    output_type: object
  - id: n3
    kind: construct
    inputs:
      v: {node: n1}
    config: {template: {greeting: "bye"}}
    output_type: object
edges:
  - source: {node: n1}
    target_node: n3
    target_input: v
outputs:
  out: {source: {node: n3}, type: object}
"""

    wf1 = _get_wf(yaml1)
    wf2 = _get_wf(yaml2)

    diff = diff_workflows(wf1, wf2)
    target_changes = [c for c in diff.changes if c.change_type == "edge_target_changed"]
    assert len(target_changes) == 1
    assert target_changes[0].severity == DiffSeverity.BREAKING
    assert target_changes[0].before == {"target_node": "n2", "target_input": "v"}
    assert target_changes[0].after == {"target_node": "n3", "target_input": "v"}


def test_input_added_and_removed():
    # Add optional and required inputs
    yaml_with_inputs = BASE_WORKFLOW_YAML.replace(
        "inputs:\n  username:\n    type: string\n    required: true",
        """inputs:
  username:
    type: string
    required: true
  opt_tag:
    type: string
    required: false
  req_token:
    type: string
    required: true""",
    )

    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(yaml_with_inputs)

    diff = diff_workflows(wf1, wf2)
    input_adds = {c.target_id: c for c in diff.changes if c.change_type == "input_added"}
    assert "opt_tag" in input_adds
    assert input_adds["opt_tag"].severity == DiffSeverity.INFO

    assert "req_token" in input_adds
    assert input_adds["req_token"].severity == DiffSeverity.BREAKING

    # Test reverse: removal of inputs
    diff_rev = diff_workflows(wf2, wf1)
    input_rems = {c.target_id: c for c in diff_rev.changes if c.change_type == "input_removed"}
    assert "opt_tag" in input_rems
    assert input_rems["opt_tag"].severity == DiffSeverity.BREAKING
    assert "req_token" in input_rems
    assert input_rems["req_token"].severity == DiffSeverity.BREAKING


def test_input_type_and_required_changed():
    modified_yaml = BASE_WORKFLOW_YAML.replace(
        "inputs:\n  username:\n    type: string\n    required: true",
        "inputs:\n  username:\n    type: any\n    required: false",
    )
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    changes = {c.change_type: c for c in diff.changes}

    assert "input_type_changed" in changes
    assert changes["input_type_changed"].severity == DiffSeverity.BREAKING
    assert changes["input_type_changed"].before == "string"
    assert changes["input_type_changed"].after == "any"

    assert "input_required_changed" in changes
    assert changes["input_required_changed"].severity == DiffSeverity.INFO


def test_output_added_and_removed_and_changed():
    yaml_with_two_outputs = BASE_WORKFLOW_YAML.replace(
        "outputs:\n  result:\n    source: {node: package_step}\n    type: object",
        """outputs:
  result:
    source: {node: package_step}
    type: object
  secondary:
    source: {node: format_step}
    type: string""",
    )

    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(yaml_with_two_outputs)

    # Added output: INFO
    diff = diff_workflows(wf1, wf2)
    out_adds = [c for c in diff.changes if c.change_type == "output_added"]
    assert len(out_adds) == 1
    assert out_adds[0].target_id == "secondary"
    assert out_adds[0].severity == DiffSeverity.INFO

    # Removed output: BREAKING
    diff_rev = diff_workflows(wf2, wf1)
    out_rems = [c for c in diff_rev.changes if c.change_type == "output_removed"]
    assert len(out_rems) == 1
    assert out_rems[0].target_id == "secondary"
    assert out_rems[0].severity == DiffSeverity.BREAKING

    # Output source changed
    yaml_src_changed = BASE_WORKFLOW_YAML.replace(
        "    source: {node: package_step}\n    type: object",
        "    source: {node: format_step}\n    type: string",
    )
    wf3 = _get_wf(yaml_src_changed)
    diff3 = diff_workflows(wf1, wf3)
    c_types = {c.change_type: c for c in diff3.changes}
    assert "output_source_changed" in c_types
    assert c_types["output_source_changed"].severity == DiffSeverity.BREAKING
    assert "output_type_changed" in c_types
    assert c_types["output_type_changed"].severity == DiffSeverity.BREAKING


def test_assertion_added_removed_and_modified():
    yaml_no_assertions = BASE_WORKFLOW_YAML.replace(
        """assertions:
  - id: name_valid
    source: {node: check_step}
    predicate: equals
    expected: true""",
        "assertions: []",
    )

    wf_orig = _get_wf(BASE_WORKFLOW_YAML)
    wf_no_a = _get_wf(yaml_no_assertions)

    # Removal -> BREAKING
    diff_rem = diff_workflows(wf_orig, wf_no_a)
    assert any(
        c.change_type == "assertion_removed" and c.severity == DiffSeverity.BREAKING
        for c in diff_rem.changes
    )

    # Addition -> BREAKING
    diff_add = diff_workflows(wf_no_a, wf_orig)
    assert any(
        c.change_type == "assertion_added" and c.severity == DiffSeverity.BREAKING
        for c in diff_add.changes
    )

    # Modified assertion predicate & expected
    yaml_modified_a = BASE_WORKFLOW_YAML.replace("predicate: equals", "predicate: type_is").replace(
        "expected: true", "expected: boolean"
    )
    wf_mod = _get_wf(yaml_modified_a)
    diff_mod = diff_workflows(wf_orig, wf_mod)
    mod_types = {c.change_type: c for c in diff_mod.changes}
    assert "assertion_predicate_changed" in mod_types
    assert mod_types["assertion_predicate_changed"].severity == DiffSeverity.BREAKING
    assert "assertion_expected_changed" in mod_types
    assert mod_types["assertion_expected_changed"].severity == DiffSeverity.BREAKING


def test_capability_added_and_removed():
    yaml_cap = BASE_WORKFLOW_YAML.replace("capabilities: []", "capabilities: ['file.read']")

    policy = CapabilityPolicy(allowed=frozenset({Capability.FILE_READ}))
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(yaml_cap, policy=policy)

    # Added capability -> BREAKING
    diff_add = diff_workflows(wf1, wf2)
    assert any(
        c.change_type == "capability_added" and c.severity == DiffSeverity.BREAKING
        for c in diff_add.changes
    )

    # Removed capability -> INFO
    diff_rem = diff_workflows(wf2, wf1)
    assert any(
        c.change_type == "capability_removed" and c.severity == DiffSeverity.INFO
        for c in diff_rem.changes
    )


def test_metadata_changes():
    modified_yaml = BASE_WORKFLOW_YAML.replace(
        "name: user_processor", "name: user_greeter"
    ).replace("description: Process and transform user greeting", "description: New description")

    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    wf2 = _get_wf(modified_yaml)

    diff = diff_workflows(wf1, wf2)
    types = {c.change_type: c for c in diff.changes}

    assert "workflow_name_changed" in types
    assert types["workflow_name_changed"].severity == DiffSeverity.INFO

    assert "metadata_description_changed" in types
    assert types["metadata_description_changed"].severity == DiffSeverity.INFO
    assert diff.summary.breaking_count == 0
    assert diff.summary.info_count == 2


def test_deterministic_repeated_diff():
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    mod_yaml = BASE_WORKFLOW_YAML.replace("operation: uppercase", "operation: lowercase")
    wf2 = _get_wf(mod_yaml)

    diff1 = diff_workflows(wf1, wf2, old_display="old.yaml", new_display="new.yaml")
    diff2 = diff_workflows(wf1, wf2, old_display="old.yaml", new_display="new.yaml")

    json1 = diff1.to_json()
    json2 = diff2.to_json()

    assert json1 == json2
    assert format_workflow_diff(diff1) == format_workflow_diff(diff2)


def test_json_serialization_determinism():
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    mod_yaml = BASE_WORKFLOW_YAML.replace("operation: uppercase", "operation: lowercase")
    wf2 = _get_wf(mod_yaml)

    diff = diff_workflows(wf1, wf2)
    json_text = diff.to_json()

    parsed = json.loads(json_text)
    assert parsed["identical"] is False
    assert parsed["summary"]["breaking_count"] == 1
    assert len(parsed["changes"]) == 1
    change = parsed["changes"][0]
    assert change["category"] == "CONFIG_CHANGED"
    assert change["change_type"] == "transform_operation_changed"
    assert change["severity"] == "BREAKING"
    assert change["node_id"] == "format_step"
    assert change["before"] == "uppercase"
    assert change["after"] == "lowercase"


def test_developer_report_workflow_diff_integration():
    wf1 = _get_wf(BASE_WORKFLOW_YAML)
    mod_yaml = BASE_WORKFLOW_YAML.replace("operation: uppercase", "operation: lowercase")
    wf2 = _get_wf(mod_yaml)

    diff = diff_workflows(wf1, wf2)

    fix_text = """fixture_version: 1
id: test-fix
inputs:
  username: "alice"
"""
    parsed_fix = parse_fixture(fix_text, format="yaml")
    res = verify_fixture(wf1, parsed_fix)

    report = build_developer_report(
        res,
        workflow=wf1,
        fixture=parsed_fix,
        workflow_diff=diff,
    )

    assert isinstance(report, DeveloperReport)
    assert report.workflow_diff is not None
    assert report.workflow_diff.identical is False
    assert len(report.workflow_diff.changes) == 1
    assert report.semantic_changes is not None
    assert len(report.semantic_changes) == 1

    report_json = report.to_json()
    parsed_report = json.loads(report_json)
    assert "workflow_diff" in parsed_report
    assert parsed_report["workflow_diff"]["summary"]["breaking_count"] == 1
