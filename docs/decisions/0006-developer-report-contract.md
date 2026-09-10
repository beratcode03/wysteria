# ADR 0006: Developer Report Contract

## Context

Phase 2.2 and Phase 2.3 established deterministic verification and regression baselines connecting Workflow IR and test fixtures. The verification engine produces low-level evaluation outcomes captured in `VerificationResult`. However, presenting this information to developers requires a stable, typed, and presentation-independent reporting contract suitable for:

1. The existing terminal CLI.
2. Future developer web interfaces.
3. Future GitHub and CI integrations.

The reporting layer must function purely as a presentation adapter without altering verification engine semantics or introducing a secondary evaluation engine.

## Decision

1. **Clear Architectural Separation**:
   ```
   Verification Engine
           ↓
   VerificationResult
           ↓
   DeveloperReport
           ↓
   CLI / Web UI / CI
   ```
   `DeveloperReport` serves as the public presentation model. It transforms `VerificationResult` and optional fixture/baseline metadata into structured developer-facing records. It does not re-evaluate or modify verification outcomes.

2. **Presentation-Neutral Status Representation**:
   Verification outcomes are mapped into a presentation-neutral status model covering:
   - `PASS` / `PASSED`: Verification succeeded.
   - `FAIL`: Overall verification failure.
   - `INVALID WORKFLOW`: Static schema, reference, graph, or policy failure.
   - `INVALID FIXTURE`: Fixture schema or input compatibility failure.
   - `RUNTIME ERROR`: In-process node evaluation error.
   - `ASSERTION FAILED`: Assertion predicate evaluation failure.
   - `OUTPUT MISMATCH`: Output discrepancy against fixture expectations.
   - `LIMIT EXCEEDED`: Runtime resource limit exceeded.
   - `REGRESSION`: Mismatch detected against recorded regression baseline.

   Statuses provide semantic badges (`success`, `failure`, `error`) and labels without hard-coded terminal ANSI escape sequences or presentation styling.

3. **Normalized Diagnostics**:
   Diagnostics are normalized into structured `NormalizedDiagnostic` records containing:
   - `code`: Stable WYS diagnostic code.
   - `severity`: Diagnostic severity (`error`, `warning`).
   - `message`: Diagnostic description.
   - `node_id`: Target DAG node identifier where available.
   - `location`: 1-based source location (`file`, `line`, `column`).
   - `category`: Semantic diagnostic category (`schema`, `reference`, `graph`, `capability`, `semantic`, `baseline`, `fixture`, `runtime`, `assertion`, `output`, `limit`, `system`).
   - `path`: JSON Pointer/document path.
   - `hint`: Optional remediation advice.

4. **Structured Outputs and Assertions**:
   - `OutputReportItem`: Encapsulates output ID, actual value, expected value, and deterministic `MatchState` (`MATCH`, `MISMATCH`, `MISSING`, `UNEXPECTED`, `UNCHECKED`).
   - `AssertionReportItem`: Encapsulates assertion ID, actual boolean, expected boolean, and `MatchState`.

5. **Deterministic Ordering and Execution Traces**:
   All report collections enforce strict deterministic ordering:
   - Diagnostics are sorted by severity, code, location, node ID, and message.
   - Outputs and assertions are sorted alphabetically by ID.
   - Execution traces retain Kahn topological step order.
   - Baseline diff entries are sorted deterministically.
   - No non-deterministic values (timestamps, durations, memory addresses, or random IDs) are included.

6. **Regression Baseline Integration**:
   When a baseline comparison is supplied, `DeveloperReport` integrates a typed `BaselineSummary` exposing regression status, change flags (workflow, outputs, assertions, status, expected error), and structured diff entries without duplicating baseline comparison logic.

7. **Deterministic JSON Serialization**:
   `DeveloperReport.to_json()` outputs canonical formatted JSON with sorted keys, valid syntax, and no ANSI codes, suitable for machine consumption in CI pipelines.

8. **Pure and Local**:
   Report transformation is pure, in-memory, and local-first. It accesses no network, reads no arbitrary files, executes no subprocesses, and invokes no LLMs.

## Consequences

- The terminal CLI consumes `DeveloperReport` directly for both human and JSON formats.
- Future web interfaces and CI integrations can consume the identical typed report contract.
- Internal engine representation changes do not leak directly into presentation consumers.
