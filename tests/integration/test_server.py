"""Integration tests for Wysteria local HTTP verification server (Phase 2.4c)."""

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from wysteria.api import create_server


@pytest.fixture(scope="module")
def local_server():
    repo_root = Path(__file__).parent.parent.parent.resolve()
    # Use dedicated test port to avoid conflict
    test_port = 8799
    server = create_server(host="127.0.0.1", port=test_port, workspace_root=repo_root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{test_port}"
    server.shutdown()
    server.server_close()


def test_server_health(local_server):
    with urllib.request.urlopen(f"{local_server}/api/health") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


def test_server_scenarios(local_server):
    with urllib.request.urlopen(f"{local_server}/api/scenarios") as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert isinstance(data, list)
        scenario_ids = [s["id"] for s in data]
        assert "successful-verification" in scenario_ids
        assert "failed-output" in scenario_ids
        assert "regression-result" in scenario_ids
        assert "runtime-error" in scenario_ids


def test_server_successful_report(local_server):
    url = f"{local_server}/api/report?scenario=successful-verification"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["overall_status"] == "PASS"
        assert data["status"] == "PASSED"
        assert data["success"] is True
        assert data["status_presentation"]["badge"] == "success"
        assert data["validation"]["workflow_valid"] is True
        assert len(data["outputs"]) == 1
        assert data["outputs"][0]["match_state"] == "MATCH"
        assert len(data["assertions"]) == 2
        assert all(a["match_state"] == "MATCH" for a in data["assertions"])


def test_server_output_mismatch_report(local_server):
    url = f"{local_server}/api/report?scenario=failed-output"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["overall_status"] == "FAIL"
        assert data["status"] == "OUTPUT_MISMATCH"
        assert data["success"] is False
        assert data["status_presentation"]["badge"] == "failure"
        assert data["outputs"][0]["match_state"] == "MISMATCH"
        assert any(d["code"] == "WYS852" for d in data["diagnostics"])


def test_server_regression_report(local_server):
    url = f"{local_server}/api/report?scenario=regression-result"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["overall_status"] == "FAIL"
        assert data["status"] == "REGRESSION"
        assert data["success"] is False
        assert data["baseline"] is not None
        assert data["baseline"]["matches"] is False
        assert data["baseline"]["outputs_changed"] is True
        assert data["baseline"]["assertions_changed"] is False
        assert len(data["baseline"]["output_diffs"]) >= 1


def test_server_runtime_error_report(local_server):
    url = f"{local_server}/api/report?scenario=runtime-error"
    with urllib.request.urlopen(url) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["overall_status"] == "FAIL"
        assert data["status"] == "RUNTIME_ERROR"
        assert data["success"] is False
        assert data["status_presentation"]["badge"] == "error"
        assert any(d["code"] == "WYS801" for d in data["diagnostics"])


def test_server_post_verify_scenario(local_server):
    req = urllib.request.Request(
        f"{local_server}/api/verify",
        data=json.dumps({"scenario": "successful-verification"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["overall_status"] == "PASS"
    except urllib.error.HTTPError as err:
        print("POST ERROR BODY:", err.read().decode())
        raise


def test_server_post_verify_paths(local_server):
    payload = {
        "workflow_path": "examples/workflows/user_transform_flow.yaml",
        "fixture_path": "examples/fixtures/fixture_trim_upper.yaml",
    }
    req = urllib.request.Request(
        f"{local_server}/api/verify",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["overall_status"] == "PASS"
        assert data["execution"]["total_nodes_executed"] == 4


def test_security_rejects_path_traversal(local_server):
    payload = {
        "workflow_path": "../../secret.yaml",
        "fixture_path": "examples/fixtures/fixture_trim_upper.yaml",
    }
    req = urllib.request.Request(
        f"{local_server}/api/verify",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        pytest.fail("Expected HTTP 400 for path traversal")
    except urllib.error.HTTPError as err:
        assert err.code == 400
        body = json.loads(err.read().decode())
        assert "outside workspace" in body["error"]


def test_security_rejects_non_localhost_binding():
    with pytest.raises(ValueError, match="only binds to localhost/loopback"):
        create_server(host="0.0.0.0")
