"""Strict versioned proposal models."""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from wysteria.evidence.models import Claim
from wysteria.ir.models import _enum_value

CURRENT_PROPOSAL_VERSION = 1


class ProposalSource(StrEnum):
    HUMAN = "human"
    LLM = "llm"
    IDE = "ide"
    UNKNOWN = "unknown"


ProposalSourceField = Annotated[ProposalSource, BeforeValidator(_enum_value(ProposalSource))]


class WorkflowProposal(BaseModel):
    """An untrusted workflow proposal before it becomes trusted Workflow IR."""

    model_config = ConfigDict(extra="forbid", strict=True)

    proposal_version: Literal[CURRENT_PROPOSAL_VERSION] = CURRENT_PROPOSAL_VERSION
    source: ProposalSourceField = ProposalSource.UNKNOWN
    intent: str | None = None
    proposed_name: str | None = None
    workflow: dict[str, Any] = Field(default_factory=dict)
    claims: list[Claim] | None = None

    @model_validator(mode="after")
    def check_duplicate_claim_ids(self) -> "WorkflowProposal":
        if self.claims:
            seen = set()
            for claim in self.claims:
                if claim.id in seen:
                    raise ValueError(f"Duplicate claim id: {claim.id}")
                seen.add(claim.id)
        return self
