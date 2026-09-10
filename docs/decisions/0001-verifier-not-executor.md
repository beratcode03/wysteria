# ADR 0001: Wysteria is a verifier, not an executor

## Decision

Wysteria v0.1 is a deterministic verifier of declarative workflow contracts. It does not execute
arbitrary code, commands, SQL, HTTP requests, or external side effects.

## Rationale

Verification has a smaller trusted computing base and can be deterministic, Git-native, and
local-first. An LLM or compiler may create a workflow document, but is untrusted input and is never
on the verification path. DuckDB is not a core dependency because it solves local analytical SQL,
not generic workflow verification. Arbitrary code execution would invalidate the v0.1 security and
determinism guarantees; it is prohibited rather than weakly sandboxed.

## Consequences

The IR is deliberately small and explicit. Future execution adapters must be separate, capability
scoped, and designed with an OS-level isolation model before they can be trusted with side effects.

