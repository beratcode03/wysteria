# Wysteria Command Catalog

This catalog defines the deterministic verification features provided by the Wysteria CLI.
It serves as the canonical source for command behaviors.

## Security & Permission Model

- **Z/B Permissions**: Not currently defined. Wysteria is a local deterministic CLI verifier, not a multi-user service. The architecture does not contain or require abstract role-based access control (RBAC) like Z or B permissions.
- **Admin Permissions (0/Public)**: All commands execute under the context of the local OS user (Public/0). Server-side enforcement applies only to binding the local UI server (`wysteria serve`) to localhost.
- **SQL / Database**: Not required and rejected. Wysteria operates entirely on declarative YAML/JSON files and git tracked baselines. Introducing a persistent relational database violates the deterministic, stateless design.

### `wysteria init`

**What it is:** Scaffold a complete, valid Wysteria workspace with integrated CI.

**What it does:** Scaffold a complete, valid Wysteria workspace with integrated CI

**Syntax:** `wysteria init [OPTIONS] [ARGS]`

**Example:** `wysteria init --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria validate`

**What it is:** Validate a workflow contract without executing it.

**What it does:** Validate a workflow contract without executing it

**Syntax:** `wysteria validate [OPTIONS] [ARGS]`

**Example:** `wysteria validate --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria compile`

**What it is:** Deterministically compile a WorkflowProposal into a trusted typed Workflow IR.

**What it does:** Deterministically compile a WorkflowProposal into a trusted typed Workflow IR

**Syntax:** `wysteria compile [OPTIONS] [ARGS]`

**Example:** `wysteria compile --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria verify`

**What it is:** Verify a workflow proposal deterministically against a fixture.

**What it does:** Verify a workflow proposal deterministically against a fixture

**Syntax:** `wysteria verify [OPTIONS] [ARGS]`

**Example:** `wysteria verify --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria explain`

**What it is:** Explain deterministically why Wysteria PASS, FAIL, or BLOCK a workflow.

**What it does:** Explain deterministically why Wysteria PASS, FAIL, or BLOCK a workflow

**Syntax:** `wysteria explain [OPTIONS] [ARGS]`

**Example:** `wysteria explain --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria diff`

**What it is:** Deterministically diff two workflow contracts.

**What it does:** Deterministically diff two workflow contracts

**Syntax:** `wysteria diff [OPTIONS] [ARGS]`

**Example:** `wysteria diff --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria schema`

**What it is:** Print the JSON Schema for a supported Workflow IR version.

**What it does:** Print the JSON Schema for a supported Workflow IR version

**Syntax:** `wysteria schema [OPTIONS] [ARGS]`

**Example:** `wysteria schema --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria doctor`

**What it is:** Report local installation, trusted-core status, and release readiness.

**What it does:** Report local installation, trusted-core status, and release readiness

**Syntax:** `wysteria doctor [OPTIONS] [ARGS]`

**Example:** `wysteria doctor --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria serve`

**What it is:** Start a local deterministic verification HTTP server for frontend integration.

**What it does:** Start a local deterministic verification HTTP server for frontend integration

**Syntax:** `wysteria serve [OPTIONS] [ARGS]`

**Example:** `wysteria serve --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria demo`

**What it is:** Run the repository's deterministic verification showcase.

**What it does:** Run the repository's deterministic verification showcase

**Syntax:** `wysteria demo [OPTIONS] [ARGS]`

**Example:** `wysteria demo --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria baseline create`

**What it is:** Create a regression baseline from a successful verification run.

**What it does:** Create a regression baseline from a successful verification run

**Syntax:** `wysteria baseline create [OPTIONS] [ARGS]`

**Example:** `wysteria baseline create --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria baseline check`

**What it is:** Compare a current verification run against an existing regression baseline.

**What it does:** Compare a current verification run against an existing regression baseline

**Syntax:** `wysteria baseline check [OPTIONS] [ARGS]`

**Example:** `wysteria baseline check --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria policy check`

**What it is:** Evaluate a validated workflow against an explicit policy.

**What it does:** Evaluate a validated workflow against an explicit policy

**Syntax:** `wysteria policy check [OPTIONS] [ARGS]`

**Example:** `wysteria policy check --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria artifact generate`

**What it is:** Generate a canonical, versioned CI artifact representing the verification decision.

**What it does:** Generate a canonical, versioned CI artifact representing the verification decision

**Syntax:** `wysteria artifact generate [OPTIONS] [ARGS]`

**Example:** `wysteria artifact generate --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.

### `wysteria artifact validate`

**What it is:** Validate an existing CI artifact against the canonical specification.

**What it does:** Validate an existing CI artifact against the canonical specification

**Syntax:** `wysteria artifact validate [OPTIONS] [ARGS]`

**Example:** `wysteria artifact validate --help`

**Required Permission:** None (Local OS User execution)

**Who can use it:** Any developer with local file read access.

**State/Data Impact:** Pure function / Read-only (unless generating artifacts/baselines locally). No database or external state modified.

**Errors/Security Considerations:** Subject to local file permissions and standard input validation. No RCE or network impact.
