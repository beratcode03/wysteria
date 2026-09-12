import base64
from pathlib import Path

import pytest

from wysteria.evidence.models import Claim
from wysteria.evidence.snapshot import (
    EvidenceSnapshot,
    claim_hash,
    content_hash,
    load_snapshot,
    save_snapshot,
)


def make_claim(**extra):
    data = {"id": "claim-1", "type": "api_endpoint", "subject": "Example", **extra}
    return Claim(**data)


def make_snapshot(claim, text='{"ok":true}'):
    return EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash=claim_hash(claim),
        source=claim.source_url or "https://example.com/api",
        status_code=200,
        content_type="application/json",
        evidence_text=text,
        content_hash=content_hash(text.encode()),
        body_base64=base64.b64encode(text.encode()).decode("ascii"),
        retrieved_at="2026-01-01T00:00:00Z",
    )


def test_claim_hash_is_deterministic():
    assert claim_hash(make_claim()) == claim_hash(make_claim())
    assert claim_hash(make_claim(path="/a")) != claim_hash(make_claim(path="/b"))


def test_snapshot_round_trip(tmp_path: Path):
    claim = make_claim(source_url="https://example.com/api")
    snapshot = make_snapshot(claim)
    path = save_snapshot(snapshot, tmp_path)
    assert path.parent == tmp_path.resolve()
    loaded = load_snapshot(claim, tmp_path)
    assert loaded == snapshot


def test_snapshot_filename_does_not_use_claim_id(tmp_path: Path):
    claim = make_claim(id="../../escape")
    snapshot = make_snapshot(claim)
    path = save_snapshot(snapshot, tmp_path)
    assert path.parent == tmp_path.resolve()
    assert "escape" not in path.name


def test_mismatched_claim_is_rejected(tmp_path: Path):
    claim = make_claim(source_url="https://example.com/a")
    other = make_claim(source_url="https://example.com/b")
    save_snapshot(make_snapshot(claim), tmp_path)
    assert load_snapshot(other, tmp_path) is None


def test_tampered_text_snapshot_is_rejected(tmp_path: Path):
    claim = make_claim()
    path = save_snapshot(make_snapshot(claim), tmp_path)
    text = path.read_text(encoding="utf-8").replace("true", "false")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(
        ValueError, match="Evidence snapshot (content hash mismatch|text does not match body)"
    ):
        load_snapshot(claim, tmp_path)


def test_missing_snapshot_returns_none(tmp_path: Path):
    assert load_snapshot(make_claim(), tmp_path) is None
