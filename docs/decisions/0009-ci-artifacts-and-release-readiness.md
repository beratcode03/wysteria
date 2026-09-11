# ADR 0009: CI Artifacts & Release Readiness

## Context

Previous phases established:
- Deterministic workflow contract validation (Phase 1)
- Test fixture verification (Phase 2)
- Regression baselines (Phase 3)
- Presentation-independent developer reports (Phase 4)
- Semantic workflow diffing (Phase 5)
- Deterministic governance policy evaluation (Phase 6)
- Workflow provenance and explainability (Phase 7)

As Wysteria prepares for real-world automated continuous integration (CI) environments and open-source release, automated pipelines need a standardized, reproducible, and strictly versioned representation of verification outcomes.

Downstream consumers (GitHub Actions, GitLab CI, PR bots, compliance auditing systems, deployment gates) require:
1. A single authoritative record consolidating developer reports, provenance, gate decisions, explanations, baseline comparisons, semantic diffs, and policy findings.
2. Canonical, deterministic serialization guaranteeing that identical inputs produce byte-for-byte identical artifacts regardless of host OS, directory paths, or execution environment.
3. Strict validation rejecting malformed or unsupported artifact versions before deployment gating.
4. Packaging release readiness checks guaranteeing that distributed artifacts, metadata, CLI entrypoints, and core dependencies are complete and verified.

## Decision

### 1. Versioned CI Artifact Architecture (`CIArtifact` v1)

We define a strict, machine-readable CI artifact contract (`CIArtifact`):
- `artifact_version: Literal[1] = 1`: Explicit contract version for schema evolution and backwards compatibility.
- `schema_version: int = 1`: Standard schema identifier for external tooling.
- `gate_decision: GateDecision`: Deterministic outcome (`PASS`, `FAIL`, `BLOCK`).
- `workflow_fingerprint`: Canonical SHA-256 fingerprint of the verified workflow.
- `workflow`: Workflow identity metadata (`name`, `fingerprint`, `display_name`).
- `fixture`: Fixture identity metadata (`id`, `name`, `display_name`).
- `developer_report`: The complete `DeveloperReport` contract including execution traces, outputs, assertions, and normalized diagnostics.
- `provenance`: The full `Provenance` model recording lineage and audit trails.
- `baseline`: Optional `BaselineSummary` comparing against historical regression records.
- `semantic_diff`: Optional `WorkflowDiff` detailing contract modifications.
- `policy`: Optional `PolicyResult` detailing capability and cardinality violations.
- `explanation`: The structured `Explanation` summary.
- `reasons`: Ordered list of `ExplanationItem` objects explaining the gate outcome.

Business logic is never duplicated: `CIArtifact` composes existing domain models (`DeveloperReport`, `Provenance`, `PolicyResult`, `WorkflowDiff`, `BaselineSummary`).

### 2. Why Artifact Generation is Separate from Verification

Verification and artifact generation have fundamentally distinct responsibilities:
- **Verification (`wysteria verify`)** is focused on contract correctness and interactive developer feedback. It executes workflow steps against fixture inputs, evaluates predicates, compares outputs, and outputs readable developer diagnostics or GitHub workflow annotations.
- **Artifact Generation (`wysteria artifact`)** is an auditing and serialization boundary. It aggregates the complete multi-subsystem decision (verification, baseline regression, semantic diff, policy evaluation, gate rules, provenance lineage) and emits a versioned, machine-readable canonical artifact for archival, automated gating, and downstream tooling.

Separating artifact generation from verification ensures:
- Verification remains lightweight, fast, and focused on developers working locally.
- Artifact creation acts as an immutable snapshot for CI systems, release gates, and compliance auditors.
- Independent evolvability: artifact schemas can evolve or add metadata without breaking verification execution mechanics.

### 3. Canonical Serialization & Determinism Guarantees

CI artifacts enforce strict byte-for-byte determinism:
- **No Non-Deterministic Fields**: Wall-clock timestamps, run durations, monotonic counters, host IDs, process IDs, and random UUIDs are strictly forbidden.
- **Machine-Independent Paths**: All file paths and display names are converted to POSIX format (`/` instead of `\`) and relativized against the repository root. A test run on Windows produces identical JSON to one run on Ubuntu or macOS.
- **Deterministic Key Ordering**: Keys at all nesting levels are serialized with `sort_keys=True`.
- **Deterministic List Ordering**: All list collections (outputs, assertions, diagnostics, traces, explanation items, policy violations, diff entries) are sorted by deterministic composite keys.
- **Stable Formatting**: Canonical JSON is emitted with two-space indentation and a trailing newline.

### 4. Compatibility Strategy

To ensure seamless schema evolution across versions:
- `artifact_version` is checked explicitly upon parsing. Unsupported versions are rejected with error code `WYS950`.
- Field aliasing: `report` is an alias for `developer_report`, `semantic_diff` for `workflow_diff`, `policy` for `policy_result`, and `baseline` for `baseline_result`.
- Extra fields are rejected via Pydantic's `strict=True` and `extra="forbid"`, preventing silent drift or accidental field additions.
- Future versions (v2, v3) will introduce explicit up-migration converters while preserving v1 parsers.

### 5. CLI Surface

The CLI introduces a dedicated `artifact` command group:
```bash
# Generate artifact (default command)
wysteria artifact workflow.yaml --fixture fixture.yaml
wysteria artifact workflow.yaml --fixture fixture.yaml --format json
wysteria artifact workflow.yaml --fixture fixture.yaml --policy policy.yaml --output artifact.json

# Validate existing artifact
wysteria artifact validate artifact.json
wysteria artifact validate artifact.json --format json
```

Exit codes preserve existing Wysteria conventions:
- `0`: PASS
- `1`: FAIL / BLOCK / output mismatch / assertion failure / policy violation / regression
- `2`: Invalid workflow contract
- `3`: Invalid fixture or policy
- `4`: Invalid baseline or runtime error

### 6. Release Readiness Framework

To prepare Wysteria for open-source distribution without introducing complex release frameworks, `wysteria doctor` is extended:
- `wysteria doctor`: Reports installation environment and release readiness status.
- `wysteria doctor --release`: Enforces strict checks across 6 dimensions:
  1. Package metadata in `pyproject.toml`
  2. Version consistency across `pyproject.toml`, `wysteria.__version__`, and distribution metadata
  3. Required project files (`pyproject.toml`, `README.md`)
  4. Build system configuration (`uv_build`) and package source tree
  5. Package importability of all core modules
  6. CLI entrypoint availability and callability

### 7. CI Integration

GitHub Actions workflow (`.github/workflows/ci.yml`) is updated to:
- Run release readiness validation during CI build (`wysteria doctor --release`).
- Generate canonical CI artifacts for both successful and failing verification runs.
- Validate generated artifacts via `wysteria artifact validate`.
- Upload verification reports and canonical CI artifacts using pinned `actions/upload-artifact`.
- Preserve existing GitHub annotations, testing, linting, and package build steps.

## Consequences

- CI pipelines and external tools have an immutable, versioned, strictly validated artifact format.
- Output reproducibility is guaranteed across operating systems and execution environments.
- Open-source releases have automated readiness validation embedded in standard development and CI workflows.
