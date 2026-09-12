"""Evidence snapshot orchestration for CLI consumers."""

from __future__ import annotations

from pathlib import Path

from wysteria.evidence.fetcher import (
    BlockedAddressError,
    FetchError,
    SafeFetcher,
)
from wysteria.evidence.models import Claim, EvidenceResult, EvidenceStatus
from wysteria.evidence.snapshot import (
    EvidenceSnapshot,
    default_snapshot_dir,
    evidence_result_from_snapshot,
    load_snapshot,
    save_snapshot,
    snapshot_from_fetch,
)


def collect_evidence(
    claims: list[Claim] | None,
    *,
    base_dir: Path,
    update_snapshots: bool = False,
    snapshot_dir: Path | None = None,
    fetcher: SafeFetcher | None = None,
) -> tuple[list[EvidenceResult], list[EvidenceSnapshot]]:
    """Load committed snapshots, optionally refreshing them from explicit claim URLs."""
    if not claims:
        return [], []
    directory = (snapshot_dir or default_snapshot_dir(base_dir)).resolve()
    active_fetcher = fetcher or SafeFetcher()
    results: list[EvidenceResult] = []
    snapshots: list[EvidenceSnapshot] = []

    for claim in sorted(claims, key=lambda item: item.id):
        if update_snapshots:
            if not claim.source_url:
                results.append(
                    EvidenceResult(
                        claim_id=claim.id,
                        status=EvidenceStatus.NEEDS_EVIDENCE,
                        reason="Claim has no explicit source_url; snapshot cannot be refreshed.",
                    )
                )
                continue
            try:
                fetched = active_fetcher.get(claim.source_url)
                snapshot = snapshot_from_fetch(claim, fetched)
                save_snapshot(snapshot, directory)
                snapshots.append(snapshot)
                results.append(evidence_result_from_snapshot(snapshot))
            except BlockedAddressError as exc:
                results.append(
                    EvidenceResult(
                        claim_id=claim.id,
                        status=EvidenceStatus.BLOCKED,
                        reason=str(exc),
                        source=claim.source_url,
                    )
                )
            except FetchError as exc:
                results.append(
                    EvidenceResult(
                        claim_id=claim.id,
                        status=EvidenceStatus.UNVERIFIABLE,
                        reason=str(exc),
                        source=claim.source_url,
                    )
                )
            continue

        try:
            snapshot = load_snapshot(claim, directory)
        except (OSError, ValueError) as exc:
            results.append(
                EvidenceResult(
                    claim_id=claim.id,
                    status=EvidenceStatus.UNVERIFIABLE,
                    source=claim.source_url,
                    reason=f"Invalid evidence snapshot: {exc}",
                )
            )
            continue
        if snapshot is None:
            results.append(
                EvidenceResult(
                    claim_id=claim.id,
                    status=EvidenceStatus.NEEDS_EVIDENCE,
                    source=claim.source_url,
                    reason="No committed evidence snapshot exists for this claim.",
                )
            )
        else:
            snapshots.append(snapshot)
            results.append(evidence_result_from_snapshot(snapshot))

    return results, snapshots
