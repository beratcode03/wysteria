"""Data models for external evidence verification."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from wysteria.ir.models import _enum_value


class ClaimType(StrEnum):
    API_ENDPOINT = "api_endpoint"
    JSON_SCHEMA = "json_schema"
    FACTUAL = "factual"
    UNKNOWN = "unknown"


ClaimTypeField = Annotated[ClaimType, BeforeValidator(_enum_value(ClaimType))]


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_EVIDENCE = "needs_evidence"
    UNVERIFIABLE = "unverifiable"


EvidenceStatusField = Annotated[EvidenceStatus, BeforeValidator(_enum_value(EvidenceStatus))]


class Claim(BaseModel):
    """A structured claim made by an AI output requiring external evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(..., description="Unique identifier for the claim in this proposal.")
    type: ClaimTypeField = ClaimType.UNKNOWN
    subject: str = Field(..., description="The subject or domain of the claim (e.g. 'Stripe API').")

    # Optional context depending on the claim type
    operation: str | None = None
    path: str | None = None
    expected_status: int | None = None
    description: str | None = None


class EvidenceResult(BaseModel):
    """The result of verifying a Claim against external evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str
    status: EvidenceStatusField
    source: str | None = None
    trust_tier: int | None = None
    evidence_text: str | None = None
    content_hash: str | None = None
    reason: str | None = None
