"""Default-deny capability policy validation."""

from dataclasses import dataclass, field

from wysteria.ir.models import Capability, Workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic


@dataclass(frozen=True)
class CapabilityPolicy:
    """Policy allowlist. The default allows no future side-effect capabilities."""

    allowed: frozenset[Capability] = field(default_factory=frozenset)


def validate_capabilities(
    workflow: Workflow,
    policy: CapabilityPolicy | None = None,
    parsed: ParsedWorkflow | None = None,
) -> list[Diagnostic]:
    """Block declared capabilities absent from the explicit policy allowlist."""

    effective = policy or CapabilityPolicy()
    diagnostics: list[Diagnostic] = []
    for index, capability in enumerate(workflow.capabilities):
        if capability not in effective.allowed:
            diagnostics.append(
                diagnostic(
                    "WYS400",
                    f"capability '{capability.value}' is denied by the active policy",
                    f"/capabilities/{index}",
                    parsed=parsed,
                    hint="Remove it or explicitly allow it in a trusted policy.",
                )
            )
    return diagnostics
