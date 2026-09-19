"""Core deterministic compiler for Workflow Proposals."""

from dataclasses import dataclass
from typing import Any

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
    proposal: WorkflowProposal | dict[str, Any],
    *,
    filename: str = "<proposal>",
    policy: CapabilityPolicy | None = None,
) -> CompilationResult:
    """
    Compile a WorkflowProposal into a trusted Workflow IR.

    This does NOT execute arbitrary code. It deterministically validates
    and constructs the strict Workflow IR model.
    """

    if isinstance(proposal, dict):
        prop_copy = dict(proposal)
        raw_claims = prop_copy.pop("claims", None)
        try:
            WorkflowProposal.model_validate(prop_copy)
        except Exception as e:
            diag = Diagnostic(
                severity="error",
                code="WYS900",
                message=f"invalid proposal structure: {e}",
            )
            return CompilationResult(success=False, workflow=None, diagnostics=[diag])

        untrusted_workflow = proposal.get("workflow", {})
        proposed_name = proposal.get("proposed_name")
    else:
        untrusted_workflow = proposal.workflow
        proposed_name = proposal.proposed_name
        raw_claims = proposal.claims

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

    if "name" not in untrusted_workflow and proposed_name:
        untrusted_workflow["name"] = proposed_name

    # Create a ParsedWorkflow from the untrusted workflow dictionary
    # Locations are omitted since we already parsed into a python dict
    parsed = ParsedWorkflow(data=untrusted_workflow, filename=filename, locations={})

    # Feed through the trusted validation pipeline
    from wysteria.api import validate_workflow
    from wysteria.evidence.models import Claim

    validation_result = validate_workflow(parsed, policy=policy)

    diagnostics = validation_result.diagnostics
    valid = validation_result.valid

    # Validate claims as first-class input
    valid_node_ids = set()
    if isinstance(untrusted_workflow.get("nodes"), list):
        for node in untrusted_workflow["nodes"]:
            if isinstance(node, dict) and "id" in node:
                valid_node_ids.add(node["id"])

    seen_claim_ids = set()
    valid_claims = []
    if raw_claims:
        for i, claim_data in enumerate(raw_claims):
            if isinstance(claim_data, dict):
                try:
                    claim = Claim.model_validate(claim_data)
                except Exception as e:
                    diagnostics.append(
                        Diagnostic(
                            severity="error",
                            code="WYS900",
                            message=f"malformed claim structure: {e}",
                            path=f"/claims/{i}",
                        )
                    )
                    valid = False
                    continue
            else:
                claim = claim_data

            if claim.id in seen_claim_ids:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="WYS900",
                        message=f"duplicate claim id: {claim.id}",
                        path=f"/claims/{i}",
                    )
                )
                valid = False
            seen_claim_ids.add(claim.id)
            valid_claims.append(claim)

            if claim.type == "unknown":
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="WYS900",
                        message=f"unsupported claim type: {claim.type}",
                        path=f"/claims/{i}",
                    )
                )
                valid = False

            if not claim.node_id:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="WYS900",
                        message=f"claim {claim.id} has no associated node_id (orphan/unrelated)",
                        path=f"/claims/{i}",
                    )
                )
            elif claim.node_id not in valid_node_ids:
                diagnostics.append(
                    Diagnostic(
                        severity="error",
                        code="WYS900",
                        message=f"claim {claim.id} is not explicitly associated with a valid workflow node",
                        path=f"/claims/{i}",
                    )
                )
                valid = False

    if valid and validation_result.workflow:
        validation_result.workflow.claims = valid_claims

    return CompilationResult(
        success=valid,
        workflow=validation_result.workflow if valid else None,
        diagnostics=diagnostics,
    )
