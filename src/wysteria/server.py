"""Local-only deterministic verification HTTP server for Wysteria frontend."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from wysteria.baselines.comparator import compare_baseline
from wysteria.baselines.storage import load_baseline
from wysteria.errors import (
    BaselineLoadError,
    BaselineParseError,
    FixtureLoadError,
    FixtureParseError,
    WorkflowLoadError,
    WorkflowParseError,
)
from wysteria.fixtures.parser import load_fixture_document
from wysteria.ir.parser import load_workflow
from wysteria.reporting.builder import build_developer_report
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.reporting.models import DeveloperReport
from wysteria.verification.engine import verify_fixture
from wysteria.verification.models import VerificationResult, VerificationStatus

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

# Controlled registry of example scenarios
DEFAULT_SCENARIOS: dict[str, dict[str, Any]] = {
    "successful-verification": {
        "id": "successful-verification",
        "name": "Successful Verification (PASS)",
        "description": "Deterministic execution of user_transform_flow against happy-path fixture. All assertions and outputs match.",
        "workflow": "examples/workflows/user_transform_flow.yaml",
        "fixture": "examples/fixtures/fixture_trim_upper.yaml",
        "baseline": None,
    },
    "failed-output": {
        "id": "failed-output",
        "name": "Output Mismatch Failure (FAIL)",
        "description": "Workflow produced 'Welcome, BERAT!' but fixture strictly expected 'Welcome, BERATCAN!'.",
        "workflow": "examples/workflows/user_transform_flow.yaml",
        "fixture": "examples/fixtures/fixture_mismatch.yaml",
        "baseline": None,
    },
    "regression-result": {
        "id": "regression-result",
        "name": "Regression Detected (REGRESSION)",
        "description": "Workflow proposal changed greeting output contract and fingerprint. Baseline diff flags output regression while assertions remain unchanged.",
        "workflow": "examples/workflows/user_transform_proposal.yaml",
        "fixture": "examples/fixtures/fixture_trim_upper.yaml",
        "baseline": "examples/baselines/user_transform_baseline.json",
    },
    "runtime-error": {
        "id": "runtime-error",
        "name": "Runtime Pointer Error (ERROR)",
        "description": "Select node failed at runtime due to missing JSON pointer segment in fixture input.",
        "workflow": "examples/workflows/data_extractor.yaml",
        "fixture": "examples/fixtures/fixture_missing_email.yaml",
        "baseline": None,
    },
}


def resolve_safe_path(base_dir: Path, target: str | Path) -> Path:
    """Safely resolve a path within base_dir, rejecting path traversal attacks."""
    resolved_base = base_dir.resolve()
    target_path = (resolved_base / target).resolve()
    if resolved_base != target_path and resolved_base not in target_path.parents:
        raise PermissionError(f"Access denied: path '{target}' traverses outside workspace")
    if not target_path.is_file():
        raise FileNotFoundError(f"File not found: '{target}'")
    return target_path


def execute_verification_report(
    workflow_path: Path,
    fixture_path: Path,
    baseline_path: Path | None = None,
    workflow_display: str = "",
    fixture_display: str = "",
) -> DeveloperReport:
    """Execute deterministic verification and return a canonical DeveloperReport."""
    parsed_wf = None
    wf_error = None
    try:
        parsed_wf = load_workflow(workflow_path)
    except (WorkflowLoadError, WorkflowParseError) as err:
        wf_error = err

    parsed_fix = None
    fix_error = None
    if wf_error is None:
        try:
            parsed_fix = load_fixture_document(fixture_path)
        except (FixtureLoadError, FixtureParseError) as err:
            fix_error = err

    if wf_error is not None:
        code = getattr(wf_error, "code", "WYS900")
        result = VerificationResult(
            status=VerificationStatus.INVALID_WORKFLOW,
            success=False,
            fixture_id=fixture_path.stem,
            diagnostics=[Diagnostic(code=code, severity=Severity.ERROR, message=str(wf_error))],
        )
    elif fix_error is not None:
        code = getattr(fix_error, "code", "WYS700")
        result = VerificationResult(
            status=VerificationStatus.INVALID_FIXTURE,
            success=False,
            fixture_id=fixture_path.stem,
            diagnostics=[Diagnostic(code=code, severity=Severity.ERROR, message=str(fix_error))],
        )
    else:
        assert parsed_wf is not None
        assert parsed_fix is not None
        result = verify_fixture(parsed_wf, parsed_fix)

    comparison = None
    if (
        baseline_path is not None
        and baseline_path.is_file()
        and wf_error is None
        and fix_error is None
    ):
        try:
            base_model = load_baseline(baseline_path)
            comparison = compare_baseline(result, base_model)
        except (BaselineLoadError, BaselineParseError):
            pass

    if workflow_display:
        wf_disp = workflow_display
    elif parsed_wf and hasattr(parsed_wf, "raw") and isinstance(parsed_wf.raw, dict):
        wf_disp = parsed_wf.raw.get("name") or workflow_path.name
    elif parsed_wf and hasattr(parsed_wf, "name"):
        wf_disp = parsed_wf.name or workflow_path.name
    else:
        wf_disp = workflow_path.name

    if fixture_display:
        fix_disp = fixture_display
    elif parsed_fix and hasattr(parsed_fix, "raw") and isinstance(parsed_fix.raw, dict):
        fix_disp = parsed_fix.raw.get("name") or parsed_fix.raw.get("id") or fixture_path.name
    elif parsed_fix and hasattr(parsed_fix, "id"):
        fix_disp = parsed_fix.id or fixture_path.name
    else:
        fix_disp = fixture_path.name

    return build_developer_report(
        result,
        workflow=parsed_wf,
        fixture=parsed_fix,
        baseline_comparison=comparison,
        workflow_display=wf_disp,
        fixture_display=fix_disp,
    )


class WysteriaRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler providing deterministic verification reports to frontend."""

    workspace_root: Path = Path.cwd()
    scenarios: dict[str, dict[str, Any]] = DEFAULT_SCENARIOS

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        if isinstance(data, str):
            payload = data.encode("utf-8")
        else:
            payload = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_json(
        self, message: str, code: str = "ERROR", status: int = HTTPStatus.BAD_REQUEST
    ) -> None:
        self._send_json({"error": message, "code": code}, status=status)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path.rstrip("/")
        query = parse_qs(parsed_url.query)

        # Health endpoint
        if path == "/api/health":
            self._send_json({"status": "ok", "version": "0.1.0"})
            return

        # Scenarios list endpoint
        if path == "/api/scenarios":
            scenario_list = list(self.scenarios.values())
            self._send_json(scenario_list)
            return

        # Report / verify endpoint via GET
        if path in {"/api/report", "/api/verify"}:
            scenario_id = query.get("scenario", [None])[0]
            if scenario_id:
                if scenario_id not in self.scenarios:
                    self._send_error_json(
                        f"Unknown scenario: '{scenario_id}'",
                        code="UNKNOWN_SCENARIO",
                        status=HTTPStatus.NOT_FOUND,
                    )
                    return
                sc = self.scenarios[scenario_id]
                try:
                    wf_path = resolve_safe_path(self.workspace_root, sc["workflow"])
                    fix_path = resolve_safe_path(self.workspace_root, sc["fixture"])
                    base_path = (
                        resolve_safe_path(self.workspace_root, sc["baseline"])
                        if sc.get("baseline")
                        else None
                    )
                    report = execute_verification_report(
                        wf_path,
                        fix_path,
                        base_path,
                        workflow_display=Path(sc["workflow"]).name,
                        fixture_display=Path(sc["fixture"]).name,
                    )
                    self._send_json(report.to_json())
                except Exception as err:
                    self._send_error_json(str(err), code="VERIFICATION_FAILED")
                return

            # Direct file path query
            wf_arg = query.get("workflow", [None])[0]
            fix_arg = query.get("fixture", [None])[0]
            base_arg = query.get("baseline", [None])[0]

            if not wf_arg or not fix_arg:
                self._send_error_json(
                    "Missing 'workflow' or 'fixture' parameter", code="MISSING_PARAMETERS"
                )
                return

            try:
                wf_path = resolve_safe_path(self.workspace_root, wf_arg)
                fix_path = resolve_safe_path(self.workspace_root, fix_arg)
                base_path = resolve_safe_path(self.workspace_root, base_arg) if base_arg else None
                report = execute_verification_report(wf_path, fix_path, base_path)
                self._send_json(report.to_json())
            except Exception as err:
                self._send_error_json(str(err), code="VERIFICATION_FAILED")
            return

        # Fallback static files if frontend/dist exists
        dist_dir = self.workspace_root / "frontend" / "dist"
        if dist_dir.is_dir():
            rel_path = parsed_url.path.lstrip("/") or "index.html"
            target_file = (dist_dir / rel_path).resolve()
            if dist_dir in target_file.parents or dist_dir == target_file:
                if target_file.is_file():
                    content_type = "text/html; charset=utf-8"
                    if target_file.suffix == ".js":
                        content_type = "application/javascript; charset=utf-8"
                    elif target_file.suffix == ".css":
                        content_type = "text/css; charset=utf-8"
                    elif target_file.suffix in {".png", ".jpg", ".jpeg"}:
                        content_type = "image/png"

                    data = target_file.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                # SPA fallback
                index_html = dist_dir / "index.html"
                if index_html.is_file():
                    data = index_html.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return

        self._send_error_json(
            f"Endpoint not found: {self.path}", code="NOT_FOUND", status=HTTPStatus.NOT_FOUND
        )

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if path != "/api/verify":
            self._send_error_json(
                f"Endpoint not found: {self.path}", code="NOT_FOUND", status=HTTPStatus.NOT_FOUND
            )
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0 or content_length > 1024 * 1024:
            self._send_error_json("Invalid payload size", code="INVALID_PAYLOAD")
            return

        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except Exception:
            self._send_error_json("Invalid JSON payload", code="INVALID_JSON")
            return

        scenario_id = body.get("scenario")
        if scenario_id:
            if scenario_id not in self.scenarios:
                self._send_error_json(
                    f"Unknown scenario: '{scenario_id}'",
                    code="UNKNOWN_SCENARIO",
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            sc = self.scenarios[scenario_id]
            wf_arg = sc["workflow"]
            fix_arg = sc["fixture"]
            base_arg = sc.get("baseline")
        else:
            wf_arg = body.get("workflow") or body.get("workflow_path")
            fix_arg = body.get("fixture") or body.get("fixture_path")
            base_arg = body.get("baseline") or body.get("baseline_path")

        if not wf_arg or not fix_arg:
            self._send_error_json("Missing 'workflow' or 'fixture' field", code="MISSING_FIELDS")
            return

        try:
            wf_path = resolve_safe_path(self.workspace_root, wf_arg)
            fix_path = resolve_safe_path(self.workspace_root, fix_arg)
            base_path = resolve_safe_path(self.workspace_root, base_arg) if base_arg else None
            report = execute_verification_report(wf_path, fix_path, base_path)
            self._send_json(report.to_json())
        except Exception as err:
            self._send_error_json(str(err), code="VERIFICATION_FAILED")

    def log_message(self, format: str, *args: Any) -> None:
        # Avoid noisy logging during tests unless DEBUG is set
        if os.environ.get("WYSTERIA_DEBUG"):
            super().log_message(format, *args)


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    workspace_root: Path | None = None,
    scenarios: dict[str, dict[str, Any]] | None = None,
) -> ThreadingHTTPServer:
    """Create a configured ThreadingHTTPServer bound to localhost."""
    # Security: enforce localhost/loopback
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("wysteria server only binds to localhost/loopback interfaces for security")

    root = workspace_root or Path.cwd()
    sc_dict = scenarios or DEFAULT_SCENARIOS

    class BoundHandler(WysteriaRequestHandler):
        workspace_root = root
        scenarios = sc_dict

    server = ThreadingHTTPServer((host, port), BoundHandler)
    return server
