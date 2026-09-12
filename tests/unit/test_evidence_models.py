import pytest
from pydantic import ValidationError

from wysteria.compiler.models import WorkflowProposal
from wysteria.evidence.models import ClaimType, EvidenceResult, EvidenceStatus


def test_workflow_proposal_backward_compatibility():
    # Proposal without claims should parse correctly
    data = {"proposal_version": 1, "source": "llm", "proposed_name": "test", "workflow": {}}
    proposal = WorkflowProposal(**data)
    assert proposal.claims is None


def test_workflow_proposal_with_empty_claims():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "proposed_name": "test",
        "workflow": {},
        "claims": [],
    }
    proposal = WorkflowProposal(**data)
    assert proposal.claims == []


def test_valid_claim():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "workflow": {},
        "claims": [
            {
                "id": "claim_1",
                "type": "api_endpoint",
                "subject": "Stripe API",
                "operation": "GET",
                "path": "/v1/charges",
            }
        ],
    }
    proposal = WorkflowProposal(**data)
    assert len(proposal.claims) == 1
    claim = proposal.claims[0]
    assert claim.id == "claim_1"
    assert claim.type == ClaimType.API_ENDPOINT
    assert claim.subject == "Stripe API"


def test_missing_required_fields():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "workflow": {},
        "claims": [
            {
                "id": "claim_1"
                # Missing 'subject' which is required
            }
        ],
    }
    with pytest.raises(ValidationError) as exc:
        WorkflowProposal(**data)
    assert "subject" in str(exc.value)


def test_extra_fields():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "workflow": {},
        "claims": [{"id": "claim_1", "subject": "Test", "unsupported_field": "test"}],
    }
    with pytest.raises(ValidationError) as exc:
        WorkflowProposal(**data)
    assert "Extra inputs are not permitted" in str(exc.value)


def test_duplicate_claim_id():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "workflow": {},
        "claims": [{"id": "claim_1", "subject": "Test"}, {"id": "claim_1", "subject": "Test2"}],
    }
    with pytest.raises(ValueError) as exc:
        WorkflowProposal(**data)
    assert "Duplicate claim id: claim_1" in str(exc.value)


def test_unknown_claim_type():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "workflow": {},
        "claims": [{"id": "claim_1", "subject": "Test", "type": "some_random_type"}],
    }
    with pytest.raises(ValidationError) as exc:
        WorkflowProposal(**data)
    assert "unsupported value" in str(exc.value)


def test_malformed_claim():
    data = {
        "proposal_version": 1,
        "source": "llm",
        "workflow": {},
        "claims": "this is a string, not a list of dicts",
    }
    with pytest.raises(ValidationError):
        WorkflowProposal(**data)


def test_evidence_result_model():
    result = EvidenceResult(
        claim_id="claim_1",
        status="verified",
        source="https://docs.example.com",
        trust_tier=1,
        evidence_text="Endpoint exists.",
    )
    assert result.status == EvidenceStatus.VERIFIED
    assert result.claim_id == "claim_1"

    with pytest.raises(ValidationError):
        EvidenceResult(claim_id="claim_1", status="random_status")
