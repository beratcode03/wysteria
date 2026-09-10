# ADR 0005: Deterministic Regression Baselines

## Context

Phase 2.2 established deterministic verification connecting Workflow IR and test fixtures. To support iterative development, refactoring, and regression testing across workflow modifications, developers need a reliable way to snapshot passing verification outcomes and compare future verification runs against those snapshots.

Under Wysteria's local-first trust boundary, regression baselines must be:
- Deterministic, repeatable, and byte-identical across runs.
- Machine-readable and safe to commit to Git version control.
- Isolated from non-deterministic run artifacts (such as timestamps, node execution traces, execution durations, or local filesystem paths).
- Bounded and hardened against hostile or malformed baseline files.

## Decision

1. **Explicit Regression Contract**:
   A baseline does not serialize the entire `VerificationResult`. Instead, it captures an explicit, versioned contract:
   - `baseline_version`: Current schema version (`1`).
   - `workflow_fingerprint`: SHA-256 canonical hash of the workflow IR.
   - `fixture_id`: Identifier of the verified fixture.
   - `result`:
     - `status`: Verification outcome status (`PASSED`).
     - `success`: Boolean success flag.
     - `actual_outputs`: Key-sorted map of deterministic workflow output values.
     - `actual_assertions`: Key-sorted map of assertion outcomes (`true` or `false`).
     - `expected_error_code`: Expected runtime failure diagnostic code, when fixture specifies expected error outcome.

   Diagnostic traces, timing, and machine-specific metadata are explicitly excluded.

2. **Deterministic Serialization**:
   - Baselines are serialized as canonical JSON text with keys sorted at all depths (`indent=2, sort_keys=True`) and explicit trailing newline.
   - Atomic file writing via temporary sibling replacement (`os.replace`) ensures safety and avoids partial file corruption.
   - Baseline creation refuses overwrite by default; `--force` is required to overwrite.
   - Baselines cannot be created from failed or non-passing verifications.

3. **Safe Parsing and Boundary Limits**:
   Baseline documents are untrusted input:
   - Enforce maximum document size (`1,000,000` bytes).
   - Enforce maximum document depth (`64`).
   - Reject YAML anchors, aliases, and custom tags.
   - Reject duplicate mapping/object keys.
   - Reject non-finite numeric constants (`NaN`, `Infinity`).
   - Validate strictly against `Baseline` Pydantic models with `extra="forbid"`.

4. **Structured Comparison**:
   Comparison evaluates differences deterministically and classifies:
   - `NO_BASELINE`: Baseline does not exist.
   - `MATCH`: Verification exactly satisfies the baseline contract.
   - `REGRESSION`: One or more contract fields changed:
     - Workflow fingerprint changed.
     - Fixture ID changed.
     - Actual outputs changed, missing, or unexpected.
     - Actual assertions changed, missing, or unexpected.
     - Verification status changed.
     - Expected runtime-error behavior changed.

   Comparison yields a typed `BaselineComparison` model that formats into both a clean, human-readable terminal report and machine-readable JSON.

5. **CLI and Exit Codes**:
   - `wysteria baseline create WORKFLOW --fixture FIXTURE --output BASELINE [--force]`
   - `wysteria baseline check WORKFLOW --fixture FIXTURE --baseline BASELINE [--format human|json]`
   - Exit codes:
     - `0`: Baseline matches / baseline created.
     - `1`: Regression detected / creation from failing run rejected.
     - `2`: Invalid workflow contract.
     - `3`: Invalid fixture.
     - `4`: Invalid baseline (missing, malformed, invalid schema, or destination collision without `--force`).
     - `5`: Runtime evaluation error or CLI infrastructure failure.

## Consequences

- Teams can store baseline JSON files in Git alongside workflows and fixtures.
- Headless CI pipelines can enforce regression checks without database or network infrastructure.
- Comparison results pinpoint exact output and assertion differences with structured reporting.
