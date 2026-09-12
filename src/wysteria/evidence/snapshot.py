"""Deterministic, Git-friendly evidence snapshot storage."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from wysteria.evidence.fetcher import FetchResult
from wysteria.evidence.models import Claim, EvidenceResult, EvidenceStatus

CURRENT_SNAPSHOT_VERSION = 1


class EvidenceSnapshot(BaseModel):
    """Immutable-in-content representation of fetched evidence."""

    model_config = ConfigDict(extra="forbid", strict=True)

    snapshot_version: int = CURRENT_SNAPSHOT_VERSION
    claim_id: str
    claim_hash: str
    source: str
    status_code: int
    content_type: str | None = None
    evidence_text: str
    content_hash: str
    body_base64: str
    retrieved_at: str
    trust_tier: int | None = None


def canonical_claim_bytes(claim: Claim) -> bytes:
    """Return canonical JSON bytes used to identify a claim."""
    return json.dumps(
        claim.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def claim_hash(claim: Claim) -> str:
    return hashlib.sha256(canonical_claim_bytes(claim)).hexdigest()


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def snapshot_from_fetch(
    claim: Claim, result: FetchResult, *, trust_tier: int | None = None
) -> EvidenceSnapshot:
    """Create a snapshot from a SafeFetcher result."""
    body = result.body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        text = body.decode("utf-8", errors="replace")
    return EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash=claim_hash(claim),
        source=result.url,
        status_code=result.status_code,
        content_type=result.content_type,
        evidence_text=text,
        content_hash=content_hash(body),
        body_base64=base64.b64encode(body).decode("ascii"),
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        trust_tier=trust_tier,
    )


def default_snapshot_dir(base: Path) -> Path:
    """Return the project-local evidence snapshot directory."""
    return base / ".wysteria" / "evidence"


def _snapshot_path(snapshot_dir: Path, claim: Claim) -> Path:
    # The digest is the filename, so untrusted claim IDs can never become paths.
    return snapshot_dir / f"{claim_hash(claim)}.json"


def _reject_symlinked_components(path: Path) -> None:
    """Reject symlinked snapshot directories to prevent writes escaping the workspace."""
    current = path.absolute()
    for component in (current, *current.parents):
        if component.exists() and component.is_symlink():
            raise ValueError("Evidence snapshot directory contains a symlink")


def save_snapshot(snapshot: EvidenceSnapshot, snapshot_dir: Path) -> Path:
    """Atomically write a snapshot beneath the supplied directory."""
    _reject_symlinked_components(snapshot_dir)
    snapshot_dir = snapshot_dir.resolve()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if snapshot_dir.is_symlink():
        raise ValueError("Evidence snapshot directory contains a symlink")
    target = snapshot_dir / f"{snapshot.claim_hash}.json"
    target = target.resolve()
    if target.parent != snapshot_dir:
        raise ValueError("Snapshot path escapes evidence directory")
    payload = (
        json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, indent=2, ensure_ascii=False)
        + "\n"
    )
    tmp = snapshot_dir / f".{snapshot.claim_hash}.tmp"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, target)
    return target


def load_snapshot(claim: Claim, snapshot_dir: Path) -> EvidenceSnapshot | None:
    """Load and validate the snapshot for a claim, or return None if absent."""
    _reject_symlinked_components(snapshot_dir)
    target = _snapshot_path(snapshot_dir.resolve(), claim)
    if not target.exists():
        return None
    if not target.is_file() or target.is_symlink():
        raise ValueError("Evidence snapshot path is not a regular file")
    data = json.loads(target.read_text(encoding="utf-8"))
    snapshot = EvidenceSnapshot.model_validate(data)
    expected_hash = claim_hash(claim)
    if snapshot.claim_hash != expected_hash or snapshot.claim_id != claim.id:
        raise ValueError("Evidence snapshot does not match claim")
    try:
        raw_body = base64.b64decode(snapshot.body_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid evidence snapshot body encoding") from exc
    actual_hash = hashlib.sha256(raw_body).hexdigest()
    if actual_hash != snapshot.content_hash:
        raise ValueError("Evidence snapshot content hash mismatch")
    try:
        decoded_body = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        decoded_body = None
    if decoded_body is not None and decoded_body != snapshot.evidence_text:
        raise ValueError("Evidence snapshot text does not match body")
    return snapshot


def evidence_result_from_snapshot(snapshot: EvidenceSnapshot) -> EvidenceResult:
    """Convert a stored snapshot into a non-verified evidence result."""
    return EvidenceResult(
        claim_id=snapshot.claim_id,
        status=EvidenceStatus.NEEDS_EVIDENCE,
        source=snapshot.source,
        trust_tier=snapshot.trust_tier,
        evidence_text=snapshot.evidence_text,
        content_hash=snapshot.content_hash,
        reason="Evidence captured; claim-specific validation is not implemented yet.",
    )
