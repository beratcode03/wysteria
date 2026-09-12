from pathlib import Path

from wysteria.evidence.fetcher import FetchResult
from wysteria.evidence.models import Claim, EvidenceStatus
from wysteria.evidence.service import collect_evidence


class FakeFetcher:
    def get(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"ok":true}',
            content_type="application/json",
        )


def test_collect_without_update_is_offline(tmp_path: Path):
    claim = Claim(id="c1", type="api_endpoint", subject="Example", source_url="https://example.com")
    results, snapshots = collect_evidence([claim], base_dir=tmp_path)
    assert not snapshots
    assert results[0].status == EvidenceStatus.NEEDS_EVIDENCE


def test_collect_update_writes_snapshot(tmp_path: Path):
    claim = Claim(id="c1", type="api_endpoint", subject="Example", source_url="https://example.com")
    results, snapshots = collect_evidence(
        [claim], base_dir=tmp_path, update_snapshots=True, fetcher=FakeFetcher()
    )
    assert results[0].status == EvidenceStatus.NEEDS_EVIDENCE
    assert len(snapshots) == 1
    assert list((tmp_path / ".wysteria" / "evidence").glob("*.json"))


def test_update_without_source_url_needs_evidence(tmp_path: Path):
    claim = Claim(id="c1", type="api_endpoint", subject="Example")
    results, snapshots = collect_evidence(
        [claim], base_dir=tmp_path, update_snapshots=True, fetcher=FakeFetcher()
    )
    assert not snapshots
    assert results[0].status == EvidenceStatus.NEEDS_EVIDENCE
