"""Evidence snapshot orchestration for CLI consumers."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from wysteria.evidence.fetcher import (
    BlockedAddressError,
    FetchError,
    SafeFetcher,
)
from wysteria.evidence.models import Claim, EvidenceResult, EvidenceStatus
from wysteria.evidence.snapshot import (
    EvidenceSnapshot,
    default_snapshot_dir,
    load_snapshot,
    save_snapshot,
    snapshot_from_fetch,
)
from wysteria.evidence.verifier import verify_claim
from wysteria.policy.models import Policy


def _normalize_host(host: str) -> str:
    value = host.strip().rstrip(".").casefold()
    try:
        return value.encode("idna").decode("ascii")
    except UnicodeError:
        return value


def _evidence_host_policy(
    source_url: str, policy: Policy | None
) -> tuple[bool, int | None, str | None]:
    """Apply exact-match evidence host policy without suffix matching."""
    if policy is None:
        return True, None, None
    hostname = urlparse(source_url).hostname
    if not hostname:
        return False, None, "Evidence source URL has no hostname."
    normalized = _normalize_host(hostname)
    allowed = (
        {_normalize_host(host) for host in policy.allowed_evidence_hosts}
        if policy.allowed_evidence_hosts is not None
        else None
    )
    forbidden = {_normalize_host(host) for host in policy.forbidden_evidence_hosts or []}
    if normalized in forbidden:
        return False, None, f"Evidence host '{hostname}' is explicitly forbidden by policy."
    if allowed is not None and normalized not in allowed:
        return False, None, f"Evidence host '{hostname}' is not in the allowed list."
    tiers = {_normalize_host(host): tier for host, tier in policy.evidence_host_trust_tiers.items()}
    tier = tiers.get(normalized)
    if policy.max_evidence_trust_tier is not None:
        if tier is None:
            return False, None, f"Evidence host '{hostname}' has no configured trust tier."
        if tier > policy.max_evidence_trust_tier:
            return (
                False,
                tier,
                (
                    f"Evidence host '{hostname}' has trust tier {tier}, "
                    f"above the policy maximum of {policy.max_evidence_trust_tier}."
                ),
            )
    return True, tier, None


def collect_evidence(
    claims: list[Claim] | None,
    *,
    base_dir: Path,
    update_snapshots: bool = False,
    snapshot_dir: Path | None = None,
    fetcher: SafeFetcher | None = None,
    policy: Policy | None = None,
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
            allowed, trust_tier, policy_reason = _evidence_host_policy(claim.source_url, policy)
            if not allowed:
                results.append(
                    EvidenceResult(
                        claim_id=claim.id,
                        status=EvidenceStatus.BLOCKED,
                        source=claim.source_url,
                        trust_tier=trust_tier,
                        reason=policy_reason,
                    )
                )
                continue
            try:
                fetched = active_fetcher.get(claim.source_url)
                snapshot = snapshot_from_fetch(claim, fetched, trust_tier=trust_tier)
                save_snapshot(snapshot, directory)
                snapshots.append(snapshot)
                results.append(verify_claim(claim, snapshot))
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
            allowed, expected_tier, policy_reason = _evidence_host_policy(snapshot.source, policy)
            if not allowed:
                results.append(
                    EvidenceResult(
                        claim_id=claim.id,
                        status=EvidenceStatus.BLOCKED,
                        source=snapshot.source,
                        trust_tier=snapshot.trust_tier,
                        reason=policy_reason,
                    )
                )
            elif expected_tier is not None and snapshot.trust_tier != expected_tier:
                results.append(
                    EvidenceResult(
                        claim_id=claim.id,
                        status=EvidenceStatus.UNVERIFIABLE,
                        source=snapshot.source,
                        trust_tier=snapshot.trust_tier,
                        reason="Evidence snapshot trust tier does not match the active policy.",
                    )
                )
            else:
                snapshots.append(snapshot)
                results.append(verify_claim(claim, snapshot))

    return results, snapshots
