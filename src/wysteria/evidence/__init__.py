"""External evidence retrieval and verification."""

from wysteria.evidence.models import EvidenceResult, EvidenceStatus
from wysteria.evidence.snapshot import EvidenceSnapshot
from wysteria.evidence.verifier import verify_claim
from wysteria.ir.models import Claim, ClaimType

__all__ = [
    "Claim",
    "ClaimType",
    "EvidenceResult",
    "EvidenceSnapshot",
    "EvidenceStatus",
    "verify_claim",
]
