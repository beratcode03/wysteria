# ADR 0007: Deterministic Policy Engine

## Context

Previous phases established deterministic workflow contract validation (Phase 1), test fixture verification (Phase 2), regression baselines (Phase 3), presentation-independent developer reports (Phase 4), and semantic workflow diffing (Phase 5).

However, validating that a workflow is syntactically, structurally, and semantically well-formed does not ensure it complies with organizational governance, security constraints, and resource limits. For example, a workflow may be valid DAG syntax while requesting unauthorized external capabilities (e.g., HTTP requests), declaring excessive graph size, lacking required assertions or outputs, or containing dead/unreachable nodes.

We need a deterministic, side-effect-free policy engine that evaluates validated workflow contracts against explicit security and governance policies to produce `PASS` / `FAIL` / `BLOCK` gating semantics.

## Decision

### 1. Clear Architectural Pipeline
```
Workflow
   ↓
Validation (structural, reference, graph, capability schema)
   ↓
Verification (deterministic fixture evaluation)
   ↓
Regression (baseline comparison)
   ↓
Semantic Diff (canonical IR comparison)
   ↓
Policy Evaluation (deterministic governance rules)
   ↓
Final Gate (GateDecision: PASS / FAIL / BLOCK)
```

### 2. Separation of Policy Evaluation from Workflow Validation
Workflow validation and policy evaluation are intentionally decoupled:
- **Workflow Validation** is intrinsic to the workflow contract. It verifies that untrusted workflow documents satisfy strict schema rules, referential integrity, directed acyclicity, and type compatibility. It answers: *"Is this workflow valid and executable according to the Wysteria IR contract?"*
- **Policy Evaluation** is extrinsic and organizational. It enforces governance rules, security boundaries, and enterprise constraints defined outside the workflow. It answers: *"Is this valid workflow permissible under the organization's governance rules?"*

### 3. Strict Deterministic Policy Model
Policies are defined using strict versioned contracts (`policy_version: 1`) without arbitrary code execution, script hooks, or network dependencies:
- `max_nodes`: Upper bound on the number of nodes in `workflow.nodes`.
- `max_edges`: Upper bound on the number of edges in `workflow.edges`.
- `forbidden_capabilities`: Explicit deny-list of prohibited capabilities (e.g., `network.http`, `process.execute`).
- `required_capabilities`: Mandatory capabilities that the workflow must declare.
- `require_assertions`: Fails when the workflow has no assertions (neither workflow-level assertions nor `assert` nodes).
- `require_outputs`: Fails when the workflow has no outputs (neither output specs nor `output` nodes).
- `forbid_unreachable_nodes`: Fails when nodes cannot contribute to an output or assertion via reverse DAG reachability.

### 4. Stable WYS Diagnostic Codes
Policy violations use dedicated, stable diagnostic codes within the `WYS450`-`WYS457` range (`DiagnosticCategory.POLICY`):
- `WYS450`: Policy parsing or schema validation error (`PolicyParseError`).
- `WYS451`: Workflow node count exceeds `max_nodes`.
- `WYS452`: Workflow edge count exceeds `max_edges`.
- `WYS453`: Workflow requests a capability in `forbidden_capabilities`.
- `WYS454`: Workflow is missing a capability required by `required_capabilities`.
- `WYS455`: Workflow lacks assertions when `require_assertions` is enabled.
- `WYS456`: Workflow lacks outputs when `require_outputs` is enabled.
- `WYS457`: Workflow contains nodes that cannot contribute to an output or assertion under `forbid_unreachable_nodes`.

### 5. Deterministic Violation Ordering
Policy violations enforce strict, deterministic sorting:
1. Severity (`ERROR` before `WARNING`)
2. Diagnostic code
3. Policy rule name
4. Node ID (if applicable)
5. Capability (if applicable)
6. Document path
7. Message

### 6. Gate Integration and PASS / FAIL / BLOCK Semantics
The final gating decision integrates verification status, semantic diff, and policy evaluation:
- `GateDecision.BLOCK`: Triggered when policy evaluation produces violations. Policy violations represent governance/security blocks and take precedence over ordinary test failures.
- `GateDecision.FAIL`: Triggered when verification fails (e.g. output mismatch, assertion failure, runtime limit exceeded) or when semantic diff detects non-informational or breaking changes without policy violations.
- `GateDecision.PASS`: Verification succeeds, semantic changes (if any) are purely informational, and policy evaluation passes.

Informational metadata changes (e.g. description, labels) never cause policy failures or gate blocks.

### 7. CLI Surface
An explicit CLI command evaluates policies:
```bash
wysteria policy check workflow.yaml --policy policy.yaml
wysteria policy check workflow.yaml --policy policy.yaml --format json
```
Exit codes follow deterministic CLI conventions:
- `0`: Policy check passed (`PASS`).
- `1`: Policy violation detected (`BLOCK`).
- `2`: Invalid workflow contract.
- `3`: Invalid policy contract.
- `4`: Runtime or command infrastructure failure.

Additionally, `wysteria verify` accepts `--policy` to evaluate policies alongside test fixtures and reflect governance decisions directly in the `DeveloperReport`.

## Consequences
- Policy evaluation remains completely side-effect free, in-memory, and local-first.
- Organizations can enforce strict governance without modifying workflow contracts or executors.
- The `DeveloperReport` contract exposes policy evaluations and the three-state gate decision (`PASS`, `FAIL`, `BLOCK`) in presentation-independent format for CLI, CI, and Web UI consumers.
