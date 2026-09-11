import json

import pytest

from wysteria.api import (
    WorkflowParseError,
    parse_workflow,
    strict_equals,
    validate_workflow,
)
from wysteria.server import resolve_safe_path


def test_resolve_safe_path_blocks_traversal(tmp_path):
    base_dir = tmp_path / "workspace"
    base_dir.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("sensitive")

    # Valid
    safe_file = base_dir / "safe.txt"
    safe_file.write_text("ok")
    assert resolve_safe_path(base_dir, "safe.txt") == safe_file.resolve()

    # Path traversal attempt
    with pytest.raises(PermissionError, match="traverses outside workspace"):
        resolve_safe_path(base_dir, "../secret.txt")

    # Absolute path attempt
    with pytest.raises(PermissionError, match="traverses outside workspace"):
        resolve_safe_path(base_dir, str(secret.resolve()))


def test_oversized_workflow_rejected():
    large_text = (
        "ir_version: 1\nname: large\n" + "nodes:\n" + ("  - id: n{i}\n    kind: noop\n" * 50000)
    )
    # The file exceeds MAX_DOCUMENT_BYTES (1MB)
    if len(large_text.encode("utf-8")) > 1_000_000:
        with pytest.raises(WorkflowParseError, match="exceeds the 1000000 byte limit"):
            parse_workflow(large_text, filename="large.yaml")


def test_boolean_integer_strict_equality():
    # In JSON, True is 1, but we must strictly differentiate them if possible
    assert not strict_equals(True, 1)
    assert not strict_equals(False, 0)
    assert strict_equals(True, True)
    assert strict_equals(1, 1)


def test_excessive_nodes_validation():
    # If the workflow parses but has > 1000 nodes, Pydantic should catch it during validation
    # Actually MAX_NODES in ir/models is 500
    nodes = [
        {"id": f"n{i}", "kind": "constant", "output_type": "string", "config": {"value": ""}}
        for i in range(501)
    ]
    wf = {
        "ir_version": 1,
        "name": "too_many_nodes",
        "nodes": nodes,
    }
    parsed = parse_workflow(json.dumps(wf), format="json")
    result = validate_workflow(parsed)
    assert not result.valid
    assert any(diag.code == "WYS104" for diag in result.diagnostics)  # Schema error
