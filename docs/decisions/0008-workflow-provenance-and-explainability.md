# ADR 0008: Workflow Provenance & Explainability

## Context

Previous phases established deterministic workflow contract validation (Phase 1), test fixture verification (Phase 2), regression baselines (Phase 3), presentation-independent developer reports (Phase 4), semantic workflow diffing (Phase 5), and deterministic policy evaluation (Phase 6).

Across these phases, each subsystem produces specialized findings:
- Verification evaluates node execution, assertion predicates, and output equality.
- Baseline comparisons detect regressions against saved historical contracts.
- Semantic diff identifies contract modifications, additions, and breaking changes.
- Policy evaluation enforces organizational governance, resource limits, and capability boundaries.
- Gate logic integrates these inputs into a final `PASS`, `FAIL`, or `BLOCK` decision.

However, developers and automated CI pipelines must be able to unambiguously answer:
> **"Why did Wysteria PASS, FAIL, or BLOCK this workflow?"**

Without a versioned provenance model and structured explanation architecture, consumers must reconstruct reasons by parsing disparate reports, diff trees, and violation lists. We need an immutable, deterministic provenance contract and explanation layer that explains gating decisions without coupling to CLI formatting, environment values, or execution side effects.

## Decision

### 1. Architectural Pipeline
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
Gate (GateDecision: PASS / FAIL / BLOCK)
   ↓
Provenance / Explanation (structured explainability & lineage)
```

### 2. Separation of Provenance from Verification
Workflow verification and workflow provenance serve distinct responsibilities:
- **Verification** is operational and contract-focused. It verifies whether a workflow DAG evaluates correctly against an input/expected fixture. It answers: *"Did this workflow produce the expected outputs and satisfy contract assertions?"*
- **Provenance** is auditable and lineage-focused. It records the complete identity (names, fingerprints), test fixture identity, verification outcome, regression baseline comparison, semantic contract diff, policy violations, and final gating decision. It answers: *"What was the full context of this workflow change, and why did the gate reach its decision?"*

Decoupling provenance from verification maintains separation of concerns: verification remains focused on deterministic contract execution, while provenance provides the definitive, versioned audit trail for governance, compliance, and developer review.

### 3. Structured Explanation Data Model
Explanations are modeled as typed, presentation-independent structured data (`ExplanationItem`), not unstructured log messages:
- `severity`: Deterministic impact rating (`BLOCK`, `BREAKING`, `FAIL`, `WARNING`, `INFO`, `PASS`).
- `source` / `category`: Provenance source category (`policy`, `semantic`, `output`, `assertion`, `runtime`, `validation`, `regression`, `gate`).
- `code`: Stable diagnostic code when applicable (e.g., `WYS453`, `WYS852`, `WYS850`).
- `message`: Concise, human-readable description.
- `node_id`: Target workflow node identifier when applicable.
- `target`: Output name, assertion identifier, capability, or property name when applicable.
- `path`: JSON-pointer document path when applicable.

Explanations are derived strictly from available facts without inventing speculative reasons:
- **Validation failures**: Extracted from validation diagnostics (`WYS100`-`WYS399`, `WYS500`-`WYS599`, `WYS700`-`WYS799`).
- **Runtime failures**: Extracted from runtime execution diagnostics (`WYS800`-`WYS849`, `WYS853`).
- **Assertion failures**: Extracted from assertion predicate evaluations (`WYS850`, `WYS851`).
- **Output mismatches**: Extracted from output comparison results (`WYS852`).
- **Regression mismatches**: Extracted from baseline diff entries and comparison reasons.
- **Breaking semantic changes**: Extracted from canonical workflow diffs (`BREAKING`, `WARNING`).
- **Policy violations**: Extracted from governance policy evaluations (`WYS450`-`WYS457`).
- **Final gate decision**: Synthesized from the gate outcome (`PASS: passing verification`).

### 4. Deterministic Guarantees
Explanations and provenance records provide strict byte-for-byte reproducibility across runs and environments:
- **No Non-Deterministic Elements**: No wall-clock timestamps, monotonic timers, random UUIDs, host-dependent file paths, or environment variables are permitted.
- **Stable Sorting Order**: Explanation items are ordered deterministically by:
  1. Severity rank (`BLOCK` = 0, `BREAKING` = 1, `FAIL` = 2, `WARNING` = 3, `INFO` = 4, `PASS` = 5)
  2. Stable diagnostic code
  3. Category / source
  4. Node ID
  5. Target
  6. Path
  7. Message
- **Canonical Serialization**: JSON output enforces `sort_keys=True` and two-space indentation, guaranteeing byte-level stability.

### 5. DeveloperReport Integration
`DeveloperReport` integrates the `Provenance` and `Explanation` models without breaking backwards compatibility:
- `report.provenance`: Exposes the versioned `Provenance` model (`provenance_version: 1`).
- `report.explanation`: Exposes the `Explanation` summary container.
- `report.reasons`: Direct property alias to structured explanation items.
- Existing report properties (`workflow`, `fixture`, `status`, `diagnostics`, `outputs`, `assertions`) remain unchanged.

### 6. CLI Surface
The CLI provides an explicit explain command:
```bash
wysteria explain workflow.yaml --fixture fixture.yaml
wysteria explain workflow.yaml --fixture fixture.yaml --format json
```
Supported options:
- `--policy`: Evaluates organizational policy and includes policy violations or blocks.
- `--baseline`: Compares against a saved regression baseline.
- `--report-file`: Persists canonical provenance JSON to a specified file.
- `--github-annotations`: Emits native GitHub Actions error and warning commands.

#### Human Terminal Output
Concise, engineering-oriented output clearly displays the gate decision, reasons with targets/nodes, and the canonical workflow fingerprint:
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

### 7. How CI Systems Consume the Result
CI pipelines consume provenance and explanations across three integration points:
1. **Standard Exit Codes**:
   - `0`: Gate passed (`PASS`).
   - `1`: Gate blocked or failed (`BLOCK`, `FAIL`, mismatch, regression, breaking change).
   - `2`: Invalid workflow contract.
   - `3`: Invalid fixture or policy document.
   - `4`: Runtime error or infrastructure fault.
2. **GitHub Actions Workflow Commands**:
   `--github-annotations` emits native `::error` annotations for policy BLOCK violations and verification failures using stable diagnostic codes (`title=WYS453`, `title=WYS852`), rendering inline annotations on pull request diffs.
3. **Machine-Readable Artifacts**:
   `--report-file <path>` writes the full provenance JSON artifact, enabling CI workflows to archive verifiable decision records for compliance audits, automated rollback decisions, and PR bot summaries.

## Consequences
- Every verification, baseline, diff, and policy evaluation is deterministically explainable.
- Developers immediately know why a workflow passed, failed, or was blocked.
- Downstream systems (CLI, CI, Web UI, automated gates) consume typed, structured explanations without parsing log text.
