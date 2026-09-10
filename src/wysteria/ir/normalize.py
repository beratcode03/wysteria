"""Canonical Workflow IR normalization and fingerprinting."""

import hashlib
import json
from typing import Any

from wysteria.ir.models import Workflow


def normalize_workflow(workflow: Workflow) -> dict[str, Any]:
    """Return a deterministic, explicit, key-order-independent IR representation."""

    normalized = workflow.model_dump(mode="json", exclude_none=False)
    normalized["nodes"] = sorted(normalized["nodes"], key=lambda node: node["id"])
    normalized["edges"] = sorted(
        normalized["edges"],
        key=lambda edge: (
            edge["target_node"],
            edge["target_input"],
            edge["source"].get("input") or edge["source"].get("node"),
        ),
    )
    normalized["assertions"] = sorted(
        normalized["assertions"], key=lambda assertion: assertion["id"]
    )
    normalized["capabilities"] = sorted(normalized["capabilities"])
    return normalized


def canonical_json(workflow: Workflow) -> str:
    """Serialize normalized IR as stable compact UTF-8 JSON text."""

    return json.dumps(
        normalize_workflow(workflow), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def fingerprint_workflow(workflow: Workflow) -> str:
    """Return the SHA-256 fingerprint of canonical workflow JSON."""

    return hashlib.sha256(canonical_json(workflow).encode("utf-8")).hexdigest()
