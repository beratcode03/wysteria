"""External evidence retrieval and verification."""

from wysteria.evidence.models import Claim, ClaimType, EvidenceResult, EvidenceStatus
from wysteria.evidence.snapshot import EvidenceSnapshot
from wysteria.evidence.verifier import verify_claim

__all__ = [
    "Claim",
    "ClaimType",
    "EvidenceResult",
    "EvidenceSnapshot",
    "EvidenceStatus",
    "verify_claim",
]
