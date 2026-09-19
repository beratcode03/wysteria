"""Data models for external evidence verification."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

from wysteria.ir.models import ClaimTypeField, _enum_value


class EvidenceStatus(StrEnum):
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_EVIDENCE = "needs_evidence"
    UNVERIFIABLE = "unverifiable"


EvidenceStatusField = Annotated[EvidenceStatus, BeforeValidator(_enum_value(EvidenceStatus))]


class EvidenceResult(BaseModel):
    """The result of verifying a Claim against external evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str
    claim_type: ClaimTypeField | None = None
    status: EvidenceStatusField
    source: str | None = None
    trust_tier: int | None = None
    evidence_text: str | None = None
    content_hash: str | None = None
    reason: str | None = None
