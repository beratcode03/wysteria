# Wysteria

Wysteria is a local-first, deterministic verifier for declarative workflow contracts. It lets
developers validate a workflow's structure, references, graph, capabilities, and deterministic
representation before handing it to any executor.

It is not a chatbot, LLM provider, workflow scheduler, browser automation tool, general workflow
executor, or autonomous agent. v0.1 executes no code, shell command, SQL, HTTP request, or external
side effect.

## Trust boundary

An LLM, IDE, or person may produce a workflow document. Wysteria treats that document as untrusted
input. Its parser, typed IR, validators, and policy checks form the trusted core and work without an
LLM or network connection.

## Minimal workflow

```yaml
ir_version: 1
name: greeting
metadata:
  description: A deterministic example
inputs:
  who:
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
assertions: []
outputs:
  message:
    source:
      node: greeting
    type: string
```

## Development

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

```text
uv sync --all-groups
uv run wysteria validate examples/valid/minimal.yaml
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## CLI

### Validate a workflow

```text
wysteria validate workflow.yaml
wysteria validate workflow.yaml --format json
```

### Verify a workflow

Verify a workflow contract deterministically against a test fixture:

```text
wysteria verify workflow.yaml --fixture fixture.yaml
wysteria verify workflow.yaml --fixture fixture.yaml --format json
```

#### Exit codes

| Exit Code | Status / Meaning | Description |
|---|---|---|
| `0` | `PASSED` | Verification passed successfully. |
| `1` | `OUTPUT_MISMATCH`, `ASSERTION_FAILED` | Verification failed due to output mismatch or assertion failure. |
| `2` | `INVALID_WORKFLOW` | Workflow is structurally invalid, malformed, or missing. |
| `3` | `INVALID_FIXTURE` | Fixture is structurally invalid, incompatible with workflow, malformed, or missing. |
| `4` | `RUNTIME_ERROR`, `LIMIT_EXCEEDED` | Runtime evaluation error, limit exceeded, or CLI infrastructure failure. |

### Inspect schema & installation

```text
wysteria schema --ir-version 1
wysteria doctor
```


## Current limitations

v0.1 validates contracts only. Runtime execution, fixtures, regression baselines, semantic diffs,
adapters, plugins, LLM integration, and external side effects are intentionally out of scope.

## Roadmap

The next phases add a deterministic fixture-backed test runtime, regression baselines, and semantic
diffing. Any future adapter or executor remains outside the trusted verification core.

