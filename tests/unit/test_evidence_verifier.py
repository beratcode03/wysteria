import json
from datetime import UTC, datetime

from wysteria.evidence.models import Claim, ClaimType, EvidenceStatus
from wysteria.evidence.snapshot import EvidenceSnapshot
from wysteria.evidence.verifier import verify_claim


def test_verify_claim_no_snapshot():
    claim = Claim(
        id="claim-1", type=ClaimType.API_ENDPOINT, subject="Test", source_url="http://test.local"
    )
    result = verify_claim(claim, None)
    assert result.status == EvidenceStatus.NEEDS_EVIDENCE
    assert result.claim_id == "claim-1"


def test_verify_api_endpoint_verified():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="GET",
        path="/api/v1/users",
        expected_status=200,
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="To get a list of users, make a GET /api/v1/users request. It returns 200.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        trust_tier=1,
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.VERIFIED


def test_verify_api_endpoint_wrong_method():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="POST",
        path="/api/v1/users",
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="You can use GET /api/v1/users to list users.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.FAILED


def test_verify_api_endpoint_wrong_path():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="GET",
        path="/api/v2/users",
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="You can use GET /api/v1/users to list users.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.FAILED


def test_verify_api_endpoint_wrong_status():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="GET",
        path="/api/v1/users",
        expected_status=201,
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="The endpoint GET /api/v1/users usually returns 200.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.FAILED


def test_verify_api_endpoint_unrelated_mention():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="POST",
        path="/api/v1/customers",
        expected_status=200,
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="The documentation only lists GET /api/v1/orders which returns 200.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_api_endpoint_obsolete():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="POST",
        path="/api/v1/customers",
        expected_status=200,
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="The old endpoint was POST /api/v1/customers and returned 200.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_api_endpoint_negative_mention():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="POST",
        path="/api/v1/customers",
        expected_status=200,
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="The API documentation mentions POST /api/v1/customers, but this endpoint returns 400.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_api_endpoint_multiple_ambiguous():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        operation="POST",
        path="/api/v1/customers",
        expected_status=200,
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="Endpoints POST /api/v1/customers and GET /api/v1/customers both return 200.",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_api_endpoint_unverifiable():
    claim = Claim(
        id="claim-1",
        type=ClaimType.API_ENDPOINT,
        subject="Test API",
        # Missing operation and path
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="Some random text",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_json_schema_verified():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }
    claim = Claim(
        id="claim-2",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test",
        description=json.dumps(schema),
    )
    body = {"name": "Alice", "age": 30}
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text=json.dumps(body),
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.VERIFIED


def test_verify_json_schema_mismatch():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }
    claim = Claim(
        id="claim-2",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test",
        description=json.dumps(schema),
    )
    # Missing required field "name", or wrong type
    body = {"age": "thirty"}
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text=json.dumps(body),
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.FAILED


def test_verify_json_schema_malformed_json():
    schema = {"type": "object"}
    claim = Claim(
        id="claim-2",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test",
        description=json.dumps(schema),
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="Not a valid JSON",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.FAILED


def test_verify_json_schema_unsupported_schema():
    # If the schema itself is not valid JSON
    claim = Claim(
        id="claim-2",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test",
        description="Not a JSON schema",
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text='{"test": 1}',
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_factual_unverifiable():
    claim = Claim(
        id="claim-3",
        type=ClaimType.FACTUAL,
        subject="Factual Test",
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="Some text",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_unknown_unverifiable():
    claim = Claim(
        id="claim-4",
        type=ClaimType.UNKNOWN,
        subject="Unknown Test",
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text="Some text",
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_json_schema_unsupported_keyword():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "unevaluatedProperties": False,
    }
    claim = Claim(
        id="claim-5",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test Unsupported",
        description=json.dumps(schema),
    )
    body = {"name": "Alice"}
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text=json.dumps(body),
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE


def test_verify_json_schema_nested_within_limit():
    # Max limit is 32. Let's do 10 deep.
    schema = {
        "type": "object",
        "properties": {"level1": {"type": "object", "properties": {"level2": {"type": "string"}}}},
    }
    claim = Claim(
        id="claim-6",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test Depth",
        description=json.dumps(schema),
    )
    body = {"level1": {"level2": "test"}}
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text=json.dumps(body),
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.VERIFIED


def test_verify_json_schema_depth_limit_exceeded():
    # Build schema deeper than MAX_SCHEMA_DEPTH (32)
    schema = {"type": "string"}
    body = "test"
    for _ in range(35):
        schema = {"type": "object", "properties": {"nested": schema}}
        body = {"nested": body}

    claim = Claim(
        id="claim-7",
        type=ClaimType.JSON_SCHEMA,
        subject="Schema Test Limit Exceeded",
        description=json.dumps(schema),
    )
    snapshot = EvidenceSnapshot(
        claim_id=claim.id,
        claim_hash="abc",
        source="http://test.local",
        status_code=200,
        evidence_text=json.dumps(body),
        content_hash="def",
        body_base64="YmFzZTY0",
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    result = verify_claim(claim, snapshot)
    assert result.status == EvidenceStatus.UNVERIFIABLE
