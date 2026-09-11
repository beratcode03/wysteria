# Wysteria Threat Model

Wysteria is a deterministic verification and regression testing engine for declarative workflows. Its primary security goal is to ensure that verifying an untrusted workflow contract does not result in arbitrary code execution, denial of service, or unintended data exposure on the host system.

## Trust Boundaries

Wysteria operates with a strict separation between trusted core code and untrusted inputs.

### What Wysteria Trusts
*   **Wysteria Core Codebase:** The Wysteria package itself, its parsing logic, and the Python runtime.
*   **The Host Environment:** Wysteria trusts that the execution environment (e.g., CI runner) is appropriately isolated for the task.

### What Wysteria DOES NOT Trust
*   **Workflow Inputs:** Workflow IR (`.yaml` or `.json` files) are strictly untrusted. They may contain adversarial input, cyclic graphs, path traversal strings, or excessively deep JSON.
*   **Fixture Inputs:** Fixture files are untrusted. They may attempt to mock external systems with adversarial payloads.
*   **Policy Inputs:** Policy definitions are untrusted.
*   **Baseline and Artifact Files:** Previously saved baselines and verification artifacts are treated as untrusted input when loaded back into the engine.

## Security Guarantees & Mitigations

To protect the host environment from untrusted inputs, Wysteria implements several layers of hardening:

### 1. Deterministic Verification (No Execution)
**v0.1 of Wysteria intentionally does NOT execute arbitrary code.** It does not spin up subprocesses, make external network requests, or execute embedded JavaScript/Python/SQL. It only performs deterministic verification of the static DAG structure and predefined data transformations against local fixtures.

### 2. Resource Exhaustion Protection
*   **Bounded Parsing:** YAML/JSON parsers enforce a hard `MAX_DOCUMENT_BYTES` limit (1 MB) and a strict `MAX_DOCUMENT_DEPTH` limit (64 levels) to prevent memory exhaustion and recursion bombs.
*   **Cardinality Limits:** Workflows and fixtures enforce strict cardinality limits (e.g., max 500 nodes, 100 inputs) via schema validation.
*   **Cycle Detection:** The topological sorting algorithm guarantees failure on cyclic dependencies before evaluation begins.

### 3. Safe Parsing
*   **No YAML Anchors/Aliases:** To prevent YAML billion-laughs attacks, Wysteria's parser strictly forbids YAML anchors, aliases, and explicit tags.
*   **Strict JSON/YAML subset:** The IR parser enforces a strict subset of JSON-compatible types. Duplicate keys in objects are rejected natively by the parser rather than silently overridden.

### 4. Path Traversal Prevention
*   **Sandboxed Paths:** When running the deterministic verification server, paths are resolved using a `resolve_safe_path` function that explicitly guarantees all referenced files remain within the declared workspace root. Absolute paths pointing outside the workspace are rejected.

## Known Limitations

*   **Informational Performance Boundaries:** While cardinality limits protect against resource exhaustion, highly complex graphs at the maximum limits could cause non-trivial CPU time. Users exposing Wysteria in multi-tenant environments should enforce standard compute quotas.
*   **Host Isolation:** Wysteria provides defense-in-depth against malicious workflow IR. However, any system running untrusted code artifacts in CI (even declaratively) should use appropriately isolated runners.

## Future Risks

If future versions of Wysteria (e.g., v1.0+) introduce plugins, arbitrary script executors, or live external adapters, the trust model will fundamentally change. At that time, execution layers must explicitly isolate untrusted logic (e.g., via sandboxing, WebAssembly, or strict network boundaries) beyond Wysteria's static verification guarantees.