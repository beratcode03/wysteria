"""Core deterministic compiler for Workflow Proposals."""

from dataclasses import dataclass

from wysteria.compiler.models import WorkflowProposal
from wysteria.ir.models import Workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.capabilities import CapabilityPolicy


@dataclass(frozen=True)
class CompilationResult:
    """The result of compiling a WorkflowProposal."""

    success: bool
    workflow: Workflow | None
    diagnostics: list[Diagnostic]


def compile_proposal(
    proposal: WorkflowProposal,
    *,
    filename: str = "<proposal>",
    policy: CapabilityPolicy | None = None,
) -> CompilationResult:
    """
    Compile a WorkflowProposal into a trusted Workflow IR.

    This does NOT execute arbitrary code. It deterministically validates
    and constructs the strict Workflow IR model.
    """

    # Extract the untrusted workflow dict from the proposal
    untrusted_workflow = proposal.workflow

    if not isinstance(untrusted_workflow, dict):
        diag = Diagnostic(
            severity="error",
            code="WYS900",
            message="proposal 'workflow' field must be a mapping",
            path="/workflow",
        )
        return CompilationResult(success=False, workflow=None, diagnostics=[diag])

    # Ensure ir_version is populated if missing, or whatever normalizations
    if "ir_version" not in untrusted_workflow:
        untrusted_workflow["ir_version"] = 1

    if "name" not in untrusted_workflow and proposal.proposed_name:
        untrusted_workflow["name"] = proposal.proposed_name

    # Create a ParsedWorkflow from the untrusted workflow dictionary
    # Locations are omitted since we already parsed into a python dict
    parsed = ParsedWorkflow(data=untrusted_workflow, filename=filename, locations={})

    # Feed through the trusted validation pipeline
    from wysteria.api import validate_workflow

    validation_result = validate_workflow(parsed, policy=policy)

    return CompilationResult(
        success=validation_result.valid,
        workflow=validation_result.workflow,
        diagnostics=validation_result.diagnostics,
    )
