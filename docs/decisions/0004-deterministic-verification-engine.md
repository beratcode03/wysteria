# ADR 0004: Deterministic Verification Engine

## Context

Phase 2.2a introduced deterministic fixture schemas and safe parsing. Phase 2.2b implemented the pure in-process node evaluator and execution tracing. Phase 2.2c connects these components into a unified verification engine to evaluate whether a workflow proposal satisfies contract invariants and produces expected results against input fixtures.

Under Wysteria's core trust boundary, workflows and fixtures are untrusted input. The verification engine must operate completely in-process, without network, subprocesses, filesystem side effects, or arbitrary code execution, producing deterministic and machine-readable outcomes.

## Decision

1. **Verification Engine Pipeline**:
   The engine evaluates workflow proposals and test fixtures through a deterministic verification sequence:
   - **Workflow Validation**: Validates workflow structure, references, DAG acyclicity, capability policies, and node semantics. Invalid workflows halt immediately with `INVALID_WORKFLOW`.
   - **Fixture Structural Validation**: Validates fixture document schema and limits. Malformed or invalid fixtures halt with `INVALID_FIXTURE`.
   - **Fixture Compatibility**: Verifies that fixture inputs match declared workflow inputs and declared types. Mismatches halt with `INVALID_FIXTURE`.
   - **Topological Evaluation**: Executes workflow nodes in Kahn topological sort order.
   - **Runtime Error / Expected Error Handling**: Compares actual runtime failures against `expected.error`.
   - **Assertion Verification**: Evaluates both node-level `AssertNode` outputs and top-level `workflow.assertions` against fixture expectations.
   - **Output Verification**: Compares actual workflow outputs against `expected.outputs` using strict type equality.

2. **Discrete Verification Statuses**:
   Outcomes are mapped to a closed set of machine-readable statuses:
   - `PASSED`: All nodes executed successfully, all assertions passed or met expectations, and outputs matched expected values.
   - `INVALID_WORKFLOW`: Static workflow schema, graph, reference, or policy validation failed.
   - `INVALID_FIXTURE`: Fixture schema or input compatibility failed (`WYS700`-`WYS703`).
   - `RUNTIME_ERROR`: An unrecoverable evaluation error occurred during node execution (`WYS800`-`WYS803`), or an unexpected error occurred.
   - `ASSERTION_FAILED`: A node-level or workflow-level assertion failed to meet expectations (`WYS850`, `WYS851`).
   - `OUTPUT_MISMATCH`: An actual workflow output did not strictly equal the expected output value (`WYS852`).
   - `LIMIT_EXCEEDED`: A runtime limit (such as value size or template depth) was exceeded (`WYS853`).

3. **Assertion Semantics**:
   - `AssertNode` evaluates to a boolean value (`True` or `False`) and stores it into `node_values` for downstream DAG consumption.
   - If an `AssertNode` evaluates to `False`, the evaluator records `WYS850`.
   - If the fixture declares an explicit expectation (e.g. `expected.assertions: {node_id: false}`), and the assertion evaluates to `False`, the expectation is satisfied and verification passes.
   - If the fixture expects `true` (or omits assertion expectations), any assertion evaluating to `False` fails verification with `ASSERTION_FAILED`.

4. **Output Comparison Semantics**:
   - Actual outputs are collected from `workflow.outputs` and compared to `expected.outputs` using `strict_equals()`.
   - Loose Python equality (e.g. `True == 1`) is strictly forbidden.
   - If `complete_outputs` is enabled, any actual output produced by the workflow that is not declared in `expected.outputs` produces diagnostic `WYS852` ("unexpected actual output").
   - Any expected output missing from actual workflow outputs produces diagnostic `WYS852` ("missing actual output").

5. **Expected Runtime Error Semantics**:
   - When `expected.error` is specified (e.g. `expected.error: "WYS801"` or `expected.error: {code: "WYS801"}`):
     - If the workflow execution fails with exactly that diagnostic code, verification **passes** (`PASSED`).
     - If the workflow succeeds without error, verification **fails** (`RUNTIME_ERROR`).
     - If the workflow fails with a different diagnostic code, verification **fails** (`RUNTIME_ERROR`) and reports both expected and actual codes.

6. **Determinism Guarantees**:
   - Zero wall-clock timestamps or execution durations in traces or results.
   - Zero randomness or PRNG usage.
   - Lexicographical tie-breaking in topological ordering.
   - Deterministic iteration over sorted dictionary keys.

## Consequences

- The verification engine provides a clean, unified public API (`verify_fixture`) returning a structured `VerificationResult`.
- Verification distinguishes precisely between static contract defects, environmental/runtime crashes, logic/assertion violations, and output discrepancies.
- Workflows and fixtures can be validated and evaluated in headless CI, automated tests, or Git hooks without external dependencies.
