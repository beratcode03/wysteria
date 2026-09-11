"""Unit tests for versioned CI Artifact data models, deterministic serialization, and validation."""

import json
from pathlib import Path

import pytest

from wysteria.api import (
    CURRENT_ARTIFACT_VERSION,
    GateDecision,
    build_ci_artifact,
    build_developer_report,
    evaluate_policy,
    load_ci_artifact,
    load_fixture_document,
    load_workflow,
    parse_ci_artifact,
    serialize_ci_artifact,
    validate_ci_artifact,
    verify_fixture,
)
from wysteria.errors import ArtifactLoadError, ArtifactParseError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLE_WORKFLOW = REPO_ROOT / "examples" / "workflows" / "user_transform_flow.yaml"
EXAMPLE_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_trim_upper.yaml"
EXAMPLE_MISMATCH_FIXTURE = REPO_ROOT / "examples" / "fixtures" / "fixture_mismatch.yaml"
EXAMPLE_POLICY = REPO_ROOT / "examples" / "policies" / "security_policy.yaml"


@pytest.fixture
def pass_artifact():
    wf = load_workflow(EXAMPLE_WORKFLOW)
    fix = load_fixture_document(EXAMPLE_FIXTURE)
    res = verify_fixture(wf, fix)
    rep = build_developer_report(
        res,
        workflow=wf,
        fixture=fix,
        workflow_display="examples/workflows/user_transform_flow.yaml",
    )
    return build_ci_artifact(rep)


@pytest.fixture
def fail_artifact():
    wf = load_workflow(EXAMPLE_WORKFLOW)
    fix = load_fixture_document(EXAMPLE_MISMATCH_FIXTURE)
    res = verify_fixture(wf, fix)
    rep = build_developer_report(
        res,
        workflow=wf,
        fixture=fix,
        workflow_display="examples/workflows/user_transform_flow.yaml",
    )
    return build_ci_artifact(rep)


@pytest.fixture
def block_artifact():
    wf = load_workflow(EXAMPLE_WORKFLOW)
    fix = load_fixture_document(EXAMPLE_FIXTURE)
    from wysteria.policy.models import Policy

    pol = Policy(policy_version=1, name="restrictive", max_nodes=2)
    res = verify_fixture(wf, fix)
    from wysteria.api import validate_workflow

    val_wf = validate_workflow(wf)
    pol_res = evaluate_policy(val_wf.workflow, pol)
    rep = build_developer_report(
        res,
        workflow=wf,
        fixture=fix,
        policy_result=pol_res,
        workflow_display="examples/workflows/user_transform_flow.yaml",
    )
    return build_ci_artifact(rep)


def test_pass_ci_artifact_structure(pass_artifact):
    assert pass_artifact.artifact_version == CURRENT_ARTIFACT_VERSION
    assert pass_artifact.schema_version == CURRENT_ARTIFACT_VERSION
    assert pass_artifact.gate_decision == GateDecision.PASS
    assert pass_artifact.passed is True
    assert pass_artifact.failed is False
    assert pass_artifact.blocked is False
    assert pass_artifact.workflow_fingerprint is not None
    assert pass_artifact.workflow.name == "user_transform_flow"
    assert pass_artifact.fixture.id == "fixture-trim-upper"
    assert pass_artifact.developer_report.status == "PASSED"
    assert pass_artifact.developer_report.success is True
    assert pass_artifact.provenance.gate_decision == GateDecision.PASS
    assert len(pass_artifact.reasons) > 0


def test_fail_ci_artifact_structure(fail_artifact):
    assert fail_artifact.gate_decision == GateDecision.FAIL
    assert fail_artifact.passed is False
    assert fail_artifact.failed is True
    assert fail_artifact.blocked is False
    assert fail_artifact.developer_report.success is False
    assert any("mismatch" in r.message.lower() for r in fail_artifact.reasons)


def test_block_ci_artifact_structure(block_artifact):
    assert block_artifact.gate_decision == GateDecision.BLOCK
    assert block_artifact.passed is False
    assert block_artifact.failed is False
    assert block_artifact.blocked is True
    assert block_artifact.policy is not None
    assert not block_artifact.policy.passed
    assert len(block_artifact.policy.violations) > 0
    assert any(r.severity.value == "BLOCK" for r in block_artifact.reasons)


def test_provenance_complete_embedding(pass_artifact):
    prov = pass_artifact.provenance
    assert prov is not None
    assert prov.provenance_version == 1
    assert prov.workflow.fingerprint == pass_artifact.workflow_fingerprint
    assert prov.fixture.id == pass_artifact.fixture.id
    assert prov.gate_decision == pass_artifact.gate_decision
    assert prov.explanation is not None
    assert prov.explanation.decision == pass_artifact.gate_decision


def test_canonical_json_deterministic_serialization(pass_artifact):
    json1 = serialize_ci_artifact(pass_artifact)
    json2 = serialize_ci_artifact(pass_artifact)
    assert json1 == json2

    # Check key ordering
    parsed = json.loads(json1)
    keys = list(parsed.keys())
    assert keys == sorted(keys)

    # Check no backslashes in display paths
    assert "\\" not in json1


def test_canonical_json_path_normalization(pass_artifact):
    # Simulate a report built with Windows backslashes
    art = pass_artifact.model_copy()
    art.workflow.display_name = r"examples\workflows\user_transform_flow.yaml"
    serialized = serialize_ci_artifact(art)
    assert r"examples\workflows\user_transform_flow.yaml" not in serialized
    assert "examples/workflows/user_transform_flow.yaml" in serialized


def test_validate_ci_artifact_roundtrip(pass_artifact, tmp_path):
    out_file = tmp_path / "art.json"
    out_file.write_text(pass_artifact.to_json(), encoding="utf-8")

    loaded = load_ci_artifact(out_file)
    assert loaded.artifact_version == CURRENT_ARTIFACT_VERSION
    assert loaded.gate_decision == GateDecision.PASS
    assert loaded.workflow_fingerprint == pass_artifact.workflow_fingerprint

    val = validate_ci_artifact(out_file)
    assert val.workflow_fingerprint == pass_artifact.workflow_fingerprint


def test_reject_unsupported_version(pass_artifact):
    data = json.loads(pass_artifact.to_json())
    data["artifact_version"] = 99
    data["schema_version"] = 99
    with pytest.raises(ArtifactParseError) as exc:
        parse_ci_artifact(json.dumps(data))
    assert exc.value.code == "WYS950"
    assert "unsupported artifact version" in str(exc.value)


def test_reject_malformed_json():
    with pytest.raises(ArtifactParseError) as exc:
        parse_ci_artifact("{not valid json")
    assert exc.value.code == "WYS950"
    assert "invalid JSON" in str(exc.value)


def test_reject_duplicate_keys():
    duplicate_json = """{
      "artifact_version": 1,
      "artifact_version": 1,
      "gate_decision": "PASS"
    }"""
    with pytest.raises(ArtifactParseError) as exc:
        parse_ci_artifact(duplicate_json)
    assert exc.value.code == "WYS950"
    assert "duplicate JSON object key" in str(exc.value)


def test_reject_missing_required_fields(pass_artifact):
    data = json.loads(pass_artifact.to_json())
    del data["workflow"]
    with pytest.raises(ArtifactParseError) as exc:
        parse_ci_artifact(json.dumps(data))
    assert exc.value.code == "WYS950"
    assert "workflow" in str(exc.value)


def test_reject_invalid_enum_value(pass_artifact):
    data = json.loads(pass_artifact.to_json())
    data["gate_decision"] = "INVALID_DECISION"
    with pytest.raises(ArtifactParseError) as exc:
        parse_ci_artifact(json.dumps(data))
    assert exc.value.code == "WYS950"


def test_reject_structurally_invalid_nested_object(pass_artifact):
    data = json.loads(pass_artifact.to_json())
    data["developer_report"] = "not an object"
    with pytest.raises(ArtifactParseError) as exc:
        parse_ci_artifact(json.dumps(data))
    assert exc.value.code == "WYS950"


def test_load_nonexistent_file():
    with pytest.raises(ArtifactLoadError):
        load_ci_artifact("nonexistent_path_file.json")
