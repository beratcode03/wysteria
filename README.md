# Wysteria

It is a local-first, deterministic verifier for declarative workflow contracts. It lets developers validate a workflow's structure, references, graph, capabilities, and deterministic representation before handing it to any executor.

It is not a chatbot, LLM provider, workflow scheduler, browser automation tool, general workflow executor, or autonomous agent. v0.1 executes no code, shell command, SQL, HTTP request, or external side effect.

## Quickstart

Get up and running and verify the built-in scenario in 30 seconds:

```bash
uv sync --all-groups
uv run wysteria demo
```

The output gives you a concise view of Wysteria's policy and verification engine in action:

* **Scenario 1 (Safe Proposal)**: AI proposes a valid data pipeline. Wysteria validates it against capabilities, evaluates it against the fixture, and allows it to **PASS**.
* **Scenario 2 (Malicious Proposal)**: AI hallucinated a `process.execute` node. Wysteria catches the unauthorized capability during policy evaluation and immediately issues a **BLOCK**.

## Trust boundary

An LLM, IDE, or person may produce a workflow document. Wysteria treats that document as untrusted input. Its parser, typed IR, validators, and policy checks form the trusted core and work without an LLM or network connection.

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

### Explain a workflow decision

Explain deterministically why Wysteria `PASS`, `FAIL`, or `BLOCK` a workflow:

```text
wysteria explain workflow.yaml --fixture fixture.yaml
wysteria explain workflow.yaml --fixture fixture.yaml --policy policy.yaml
wysteria explain workflow.yaml --fixture fixture.yaml --format json
```

#### Example Output

```text
DECISION: BLOCK

Reasons:
  BLOCK WYS453: forbidden capability "network"
    node: fetch_data

  BREAKING: output type changed
    output: final_result

  FAIL WYS852: output mismatch
    output: final_result

Fingerprint:
  2c441b8a9f00...
```

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

### Workflow Diff

Fingerprint comparison tells you that a workflow changed.
Semantic diff tells you **what** changed.

Wysteria compares the canonical typed IR of two workflows to detect additions, removals, and modifications with deterministic severity ratings (`INFO`, `WARNING`, `BREAKING`). It operates entirely on typed contract semantics, ignoring whitespace, comment, and document key-order formatting differences.

#### Diff two workflows

```text
wysteria diff old_workflow.yaml new_workflow.yaml
wysteria diff old_workflow.yaml new_workflow.yaml --format json
```

#### Diff exit codes

| Exit Code | Meaning | Description |
|---|---|---|
| `0` | No semantic changes | Workflows have identical semantic structure and IR representation. |
| `1` | Changes detected | One or more semantic changes (info, warning, or breaking) were detected. |
| `2` | Invalid old workflow | Old workflow is structurally invalid, malformed, or missing. |
| `3` | Invalid new workflow | New workflow is structurally invalid, malformed, or missing. |
| `4` | Runtime error | Runtime or infrastructure failure. |

#### Baseline integration

When checking against a baseline, optionally provide `--baseline-workflow` to automatically generate semantic diff diagnostics when workflow fingerprint changes are detected:

```text
wysteria baseline check current.yaml --fixture fixture.yaml --baseline baseline.json --baseline-workflow baseline.yaml
```

The semantic diff will be formatted in the terminal report and embedded into the `DeveloperReport` JSON artifact under `workflow_diff`.

### Deterministic Policy Engine

Wysteria includes a deterministic, side-effect-free Policy Engine to evaluate validated workflows against explicit organizational security and governance policies, producing `PASS` / `FAIL` / `BLOCK` gating semantics.

#### Why Policy Evaluation is Separate from Workflow Validation

- **Workflow Validation** is intrinsic to the workflow contract. It verifies that untrusted workflow documents satisfy strict schema rules, referential integrity, directed acyclicity, and type compatibility. It checks: *"Is this workflow structurally valid and executable according to Wysteria IR rules?"*
- **Policy Evaluation** is extrinsic and organizational. It enforces governance rules, capability boundaries, size limits, and security controls defined outside the workflow document. It checks: *"Is this valid workflow permissible under our organization's governance rules?"*

#### Policy File Example

Policies are written in strict YAML or JSON (`policy_version: 1`):

```yaml
policy_version: 1
name: security-governance-baseline
description: Enterprise baseline governing workflow cardinality and capability boundaries.
max_nodes: 25
max_edges: 50
forbidden_capabilities:
  - network.http
  - process.execute
required_capabilities: []
require_assertions: true
require_outputs: true
forbid_unreachable_nodes: true
```

#### Supported Policy Rules

- `max_nodes`: Fails when total node count exceeds the limit (`WYS451`).
- `max_edges`: Fails when total edge count exceeds the limit (`WYS452`).
- `forbidden_capabilities`: Fails if any forbidden capability is requested (`WYS453`).
- `required_capabilities`: Fails if a required capability is absent (`WYS454`).
- `require_assertions`: Fails when the workflow has no assertions (`WYS455`).
- `require_outputs`: Fails when the workflow has no outputs (`WYS456`).
- `forbid_unreachable_nodes`: Fails when nodes cannot contribute to an output or assertion (`WYS457`).

#### Check a workflow against a policy

```text
wysteria policy check workflow.yaml --policy policy.yaml
wysteria policy check workflow.yaml --policy policy.yaml --format json
```

#### Policy Check Exit Codes

| Exit Code | Meaning | Description |
|---|---|---|
| `0` | `PASS` | Policy evaluation passed with no violations. |
| `1` | `BLOCK` | One or more policy violations detected. |
| `2` | Invalid workflow | Workflow is structurally invalid, malformed, or missing. |
| `3` | Invalid policy | Policy document is invalid, malformed, has unknown fields, or is missing. |
| `4` | Runtime / CLI error | Unsupported format or execution error. |

#### Gate Integration & PASS / FAIL / BLOCK Semantics

The final gate integrates verification status, semantic workflow diff, and policy evaluation into a unified `GateDecision`:

```text
verification status
+ semantic workflow diff
+ policy result
→ final GateDecision (PASS / FAIL / BLOCK)
```

- **`PASS`**: Verification succeeds, semantic changes (if any) are purely informational, and policy evaluation passes.
- **`FAIL`**: Verification fails (output mismatch, assertion failure, runtime limit exceeded) or non-informational/breaking diff is detected without policy violations.
- **`BLOCK`**: Policy evaluation fails. Policy violations represent governance/security blocks and take precedence over ordinary test failures.

Informational metadata changes never cause policy failures or gate blocks.

#### Example Terminal Output

##### Policy Check (PASS):
```text
Wysteria Policy Check
Workflow: workflow.yaml
Policy: security_policy.yaml

Result
  ✓ PASS
  All policy checks passed.
```

##### Policy Check (BLOCK):
```text
Wysteria Policy Check
Workflow: workflow.yaml
Policy: security_policy.yaml

Result
  ✗ BLOCK

Violations
  ✗ WYS453 (forbidden_capabilities)
    Capability: network.http
    Path: [/capabilities/0]
    forbidden capability requested: 'network.http'
  ✗ WYS457 (forbid_unreachable_nodes)
    Node: orphan_node
    Path: [/nodes/2]
    node 'orphan_node' cannot contribute to an output or assertion
```

##### Gated Verification Report (with `--policy`):
```text
Result
  ✓ PASS

Gate Decision
  ✗ BLOCK
    - policy violation (forbidden_capabilities): forbidden capability requested: 'network.http'
```

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



## CI

Put my workflow + fixture + optional baseline in git, then Wysteria verifies it on every PR.

### Smallest GitHub Actions Example

```yaml
name: Wysteria CI
on: [pull_request]
permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --frozen

      # Deterministic contract verification + PR annotations + JSON artifact
      - run: |
          uv run wysteria verify workflow.yaml \
            --fixture fixture.yaml \
            --report-file artifacts/verification-report.json \
            --github-annotations

      # Optional regression baseline check
      - run: |
          uv run wysteria baseline check workflow.yaml \
            --fixture fixture.yaml \
            --baseline baseline.json \
            --report-file artifacts/baseline-report.json \
            --github-annotations

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: verification-reports
          path: artifacts/
```

### CI Artifacts & Release Readiness

Wysteria provides versioned, machine-readable CI artifacts representing the complete verification decision (`CIArtifact` v1).

#### What the CI Artifact is

The CI artifact consolidates all verification and governance subsystems into a single canonical record:
- **DeveloperReport**: Complete execution summary, node traces, outputs, assertions, and normalized diagnostics.
- **Workflow Provenance**: Full lineage including workflow identity, fixture identity, and gate outcomes.
- **GateDecision**: Deterministic outcome (`PASS`, `FAIL`, or `BLOCK`).
- **Structured Explanations & Reasons**: Presentation-independent explanation items answering why the workflow passed, failed, or was blocked.
- **Workflow Fingerprint**: SHA-256 canonical hash of the normalized workflow contract.
- **Regression Baseline Result**: Detailed diff entries and comparison results against historical baselines.
- **Semantic Workflow Diff**: Structural, signature, edge, and contract modifications between versions.
- **Policy Result**: Capability boundary enforcement and organizational compliance violations.

#### Why it is deterministic

The CI artifact guarantees byte-for-byte reproducibility across runs, platforms, and environments:
- **No Non-Deterministic Elements**: Free of timestamps, execution durations, random UUIDs, host environments, and process IDs.
- **Machine-Independent Paths**: File paths and display names are normalized to POSIX format (`/`) and relativized to the workspace root.
- **Stable Key Ordering**: All dictionary keys are deterministically sorted at every nesting depth (`sort_keys=True`).
- **Stable List Ordering**: Detail collections (outputs, assertions, diagnostics, traces, reasons, violations, diff entries) use deterministic sort keys.
- **Canonical Serialization**: Uses strict two-space indentation with a trailing newline.

#### Example Artifact Structure

```json
{
  "artifact_version": 1,
  "schema_version": 1,
  "gate_decision": "PASS",
  "workflow_fingerprint": "a431d3755e3d96632bb7a089b19f484b7a2f46cbdb053e47818b27293279793c",
  "workflow": {
    "display_name": "examples/workflows/user_transform_flow.yaml",
    "fingerprint": "a431d3755e3d96632bb7a089b19f484b7a2f46cbdb053e47818b27293279793c",
    "name": "user_transform_flow"
  },
  "fixture": {
    "display_name": "fixture-trim-upper",
    "id": "fixture-trim-upper",
    "name": "Trim and Uppercase User Fixture"
  },
  "developer_report": { ... },
  "provenance": { ... },
  "baseline": { ... },
  "semantic_diff": null,
  "policy": null,
  "explanation": {
    "decision": "PASS",
    "fingerprint": "a431d3755e3d96632bb7a089b19f484b7a2f46cbdb053e47818b27293279793c",
    "reasons": [
      {
        "category": "gate",
        "code": null,
        "message": "passing verification",
        "severity": "PASS",
        "source": "gate"
      }
    ]
  },
  "reasons": [ ... ]
}
```

#### CLI Usage

##### Generate an artifact

```text
# Generate and display summary
wysteria artifact workflow.yaml --fixture fixture.yaml

# Generate canonical JSON output
wysteria artifact workflow.yaml --fixture fixture.yaml --format json

# Write canonical JSON artifact to file with policy and baseline
wysteria artifact workflow.yaml \
  --fixture fixture.yaml \
  --policy policy.yaml \
  --baseline baseline.json \
  --output artifacts/ci-artifact.json
```

##### Validate an artifact

Strictly validate an existing CI artifact file against schema rules, enum values, and version requirements:

```text
# Human readable validation
wysteria artifact validate artifacts/ci-artifact.json

# Machine readable JSON validation
wysteria artifact validate artifacts/ci-artifact.json --format json
```

#### Release Readiness & Doctor Checks

Wysteria includes built-in release readiness checks to ensure packages and distribution environments meet open-source release standards:

```text
# General installation diagnostic
wysteria doctor

# Strict release readiness verification
wysteria doctor --release
```

Readiness verification includes:
- **Package metadata**: Verifies `pyproject.toml` defines required fields (`name`, `version`, `description`, `requires-python`, `license`).
- **Version consistency**: Ensures package version matches `wysteria.__version__` and installed distribution metadata.
- **Required project files**: Verifies `pyproject.toml` and non-empty `README.md` are present.
- **Build configuration**: Validates build-system specifications (`uv_build`) and package source tree integrity.
- **Package importability**: Tests importing core package modules without side effects or errors.
- **CLI availability**: Confirms CLI entrypoint (`wysteria.cli.main:app`) resolves to a valid callable command.

### How it works in CI

- **Deterministic Verification**: Verifies workflow contracts against fixtures without external network calls or side effects.
- **Canonical CI Artifacts**: Produces versioned, deterministic CI artifacts (`ci-artifact-pass.json`, `ci-artifact-fail.json`) archived via GitHub Actions `upload-artifact`.
- **Artifact Validation**: Validates artifact integrity directly within CI (`wysteria artifact validate`).
- **Release Readiness Verification**: `wysteria doctor --release` validates packaging standards during the CI build stage.
- **Clear PR Diagnostics**: On failure, the CI log highlights status, workflow, fixture, fingerprint, failure category, and expected vs actual values.
- **GitHub Annotations**: `--github-annotations` emits native `::error` and `::warning` workflow commands with file/line locations for inline PR diff annotations.
- **Machine-Readable Artifacts**: `--report-file <path>` and `--output <path>` write the canonical JSON artifacts for post-run analysis or CI archiving.
- **Exit Codes**: Preserves standard verification exit codes (`0` pass, `1` mismatch/assertion/policy/gate failure, `2` invalid workflow, `3` invalid fixture/policy, `4` invalid baseline/runtime error), failing the CI job when verification fails.

## Current limitations

v0.1 validates contracts, executes deterministic test fixtures, tracks regression baselines, and computes semantic workflow diffs.
Adapters, plugins, LLM integration, and external side effects are intentionally out of scope.

## Roadmap

Deterministic semantic diffing is now implemented. Future phases explore deterministic workflow migration assistants and contract linting. Any future adapter or executor remains outside the trusted verification core.

