"""Wysteria init templates."""

WORKFLOW_YAML = """ir_version: 1
name: quickstart
metadata:
  description: A minimal Wysteria quickstart workflow
inputs:
  username:
    type: string
nodes:
  - id: format_name
    kind: transform
    inputs:
      value:
        input: username
    config:
      operation: uppercase
    output_type: string
  - id: make_greeting
    kind: construct
    inputs:
      name:
        node: format_name
    config:
      template:
        greeting: "Hello, {name}!"
        valid: true
    output_type: object
edges:
  - source: {input: username}
    target_node: format_name
    target_input: value
  - source: {node: format_name}
    target_node: make_greeting
    target_input: name
capabilities: []
assertions:
  - id: check_input_exists
    source: {input: username}
    predicate: exists
  - id: check_greeting_type
    source: {node: make_greeting}
    predicate: type_is
    expected: object
  - id: check_name_type
    source: {node: format_name}
    predicate: type_is
    expected: string
outputs:
  result:
    source: {node: make_greeting}
    type: object
  formatted_name:
    source: {node: format_name}
    type: string
"""

FIXTURE_YAML = """fixture_version: 1
id: fixture-quickstart
name: Quickstart Fixture
inputs:
  username: "alice"
expected:
  outputs:
    result:
      greeting: "Hello, ALICE!"
      valid: true
    formatted_name: "ALICE"
  assertions:
    check_input_exists: true
    check_greeting_type: true
    check_name_type: true
"""

POLICY_YAML = """policy_version: 1
name: quickstart-policy
description: Basic policy for quickstart demo.
max_nodes: 10
max_edges: 10
forbidden_capabilities:
  - network.http
  - process.execute
  - file.read
required_capabilities: []
require_assertions: true
require_outputs: true
forbid_unreachable_nodes: true
"""

GITHUB_WORKFLOW_YAML = """name: Wysteria CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    name: Verify Contract
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v5

      - name: Install Wysteria
        run: uv tool install wysteria

      - name: Wysteria contract verification
        run: |
          wysteria verify workflow.yaml \\
            --fixture fixture.yaml \\
            --policy policy.yaml \\
            --github-annotations
"""
