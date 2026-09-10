# ADR 0003: Deterministic Fixture Verification Contract

## Context

Phase 1 and Phase 2.1 established safe, deterministic parsing, graph validation, and semantic type checking for Wysteria workflows. However, static contract validation alone cannot verify runtime dataflow correctness. Phase 2.2 introduces deterministic fixture verification to answer:

"Given a declarative workflow and deterministic input fixtures, does the workflow produce the expected result and satisfy its assertions?"

Under Wysteria's core trust boundary, both workflow documents and test fixtures are untrusted input produced by LLMs, compilers, or third parties. Fixture parsing, representation, and compatibility validation must be hardened, side-effect-free, and local-first.

## Decision

1. **Fixture IR Versioning**: Fixture documents require `fixture_version: 1`. Unsupported versions are rejected with schema diagnostic `WYS701`.
2. **Deterministic Fixture Identification**: Each fixture requires a unique identifier `id` matching `^[A-Za-z][A-Za-z0-9_-]*$`. An optional `name` and `description` provide human-readable metadata.
3. **Strict Fixture Inputs**: Fixture `inputs` must explicitly match the target workflow contract:
   - All workflow inputs declared with `required: true` (the default) must be present in `fixture.inputs`. Missing required inputs produce diagnostic `WYS702`.
   - Undeclared inputs in `fixture.inputs` are strictly forbidden and produce diagnostic `WYS702`.
   - Input values must strictly conform to declared `InputSpec.type` under Wysteria's type compatibility rules (`WYS702`).
4. **Optional Subset Expected Outputs**: `expected.outputs` is optional. When specified, it may define expected values for all or a subset of declared `workflow.outputs`. Undeclared output names or type incompatibilities produce `WYS703`.
5. **Expected Assertions**: `expected.assertions` is optional and maps declared workflow assertion IDs (`workflow.assertions`) or assert node IDs (`workflow.nodes` where `kind: assert`) to expected boolean results (`true` or `false`). Undeclared assertion IDs produce `WYS703`.
6. **Expected Runtime Errors**: `expected.error` is optional and specifies an expected deterministic runtime diagnostic code (e.g., `WYS801`, `WYS802`). This enables deterministic testing of expected failure conditions.
7. **Hardened Parser & Resource Limits**: Fixture parsing enforces the same security boundaries as workflow parsing:
   - Size limit: `MAX_DOCUMENT_BYTES = 1_000_000` (1 MB) (`WYS700`).
   - Depth limit: `MAX_DOCUMENT_DEPTH = 64` (`WYS700`).
   - Rejection of YAML aliases, anchors, and explicit tags (`WYS700`).
   - Rejection of duplicate mapping keys in YAML and JSON (`WYS700`).
   - Rejection of non-finite numbers (`NaN`, `Infinity`) (`WYS700` / `WYS701`).
   - Restriction of YAML scalars to the unambiguous JSON scalar subset (`WYS700`).
8. **Untrusted Input & Side-Effect Free**: Fixture parsing and validation are pure, in-memory, and perform no filesystem modifications, network requests, subprocess execution, or shell calls.
9. **Clean Validation Boundaries**: The fixture parser parses and structurally validates fixture documents independently of any workflow. Workflow compatibility checks are executed by a separate validation function (`validate_fixture_compatibility`).
10. **Relationship to Verification Results**: In future evaluation (Phase 2.2b):
   - If `expected.outputs` is specified, actual workflow outputs must strictly equal expected values; differences yield `OUTPUT_MISMATCH` (`WYS852`).
   - If `expected.assertions` is specified, actual assertion outcomes must match expected booleans. If omitted, all assertions are required to evaluate to `true`.
   - If `expected.error` is specified, execution must fail with the matching diagnostic code.

## Consequences

- Fixtures have a stable, typed, minimal schema that prevents memory bloat, parser DoS, and ambiguity.
- Verification cleanly distinguishes between malformed fixtures (`WYS700`), schema errors (`WYS701`), workflow input mismatches (`WYS702`), and expectation mismatches (`WYS703`).
- Generic fixture parsing remains decoupled from workflow validation, allowing fixtures to be parsed, validated, and inspected independently of workflow execution.
