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

### Regression Baselines

Wysteria provides deterministic regression baselines to record and detect changes in workflow execution contracts across iterations. Baselines are deterministic local artifacts intended for Git version control.

#### Create a baseline

Create a versioned regression baseline from a successful verification run:

```text
wysteria baseline create workflow.yaml --fixture fixture.yaml --output baseline.json
```

Use `--force` to overwrite an existing baseline file.

#### Check against a baseline

Verify the current workflow proposal against the recorded regression baseline:

```text
wysteria baseline check workflow.yaml --fixture fixture.yaml --baseline baseline.json
wysteria baseline check workflow.yaml --fixture fixture.yaml --baseline baseline.json --format json
```

#### Baseline exit codes

| Exit Code | Meaning | Description |
|---|---|---|
| `0` | Baseline matches | Current verification matches the baseline regression contract. |
| `1` | Regression detected | Output, assertion, status, error behavior, or workflow fingerprint mismatch detected. |
| `2` | Invalid workflow | Workflow is structurally invalid, malformed, or missing. |
| `3` | Invalid fixture | Fixture is structurally invalid, incompatible with workflow, malformed, or missing. |
| `4` | Invalid baseline | Baseline file is missing, malformed, invalid schema/version, or destination exists on create. |
| `5` | Runtime / infrastructure error | Runtime evaluation error or CLI infrastructure failure. |

### Developer Report Contract

Wysteria provides a stable, typed, presentation-independent report model (`DeveloperReport`) that acts as the presentation contract between the verification engine and consumers:
1. CLI terminal and JSON outputs
2. Future developer web interfaces
3. Future GitHub and CI integrations

The report model normalizes diagnostics into structured records, classifies output and assertion states, summarizes execution without performance jitter, and serializes deterministically to machine-readable JSON.

### Inspect schema & installation

```text
wysteria schema --ir-version 1
wysteria doctor
```

### Local Web UI & Verification Server

Wysteria includes a local-first web UI and deterministic verification server (`wysteria serve`) to inspect workflows, fixtures, regressions, and execution graphs locally without external network dependencies.

#### Start the verification server

```text
wysteria serve
# or custom port/host (localhost only)
wysteria serve --host 127.0.0.1 --port 8787
```

Endpoints provided:
- `GET /api/health`: Health status and engine version.
- `GET /api/scenarios`: List preconfigured verification scenarios.
- `GET /api/report?scenario=<id>`: Execute verification and return deterministic `DeveloperReport` JSON.
- `POST /api/verify`: Execute verification dynamically given workflow, fixture, and optional baseline file paths.
- Serves static files from `frontend/dist` as a fallback SPA when built.

#### Run the frontend UI

```text
cd frontend
npm install
npm run dev       # Starts Vite dev server with proxy at http://localhost:5173
npm run build     # Compiles TypeScript and production assets into frontend/dist
npm test          # Runs frontend Vitest suite
```



## Current limitations

v0.1 validates contracts, executes deterministic test fixtures, and tracks regression baselines.
Semantic diffs, adapters, plugins, LLM integration, and external side effects are intentionally out of scope.

## Roadmap

The next phase adds deterministic semantic diffing. Any future adapter or executor remains outside the trusted verification core.

