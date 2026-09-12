"""Deterministic verification of claims against evidence snapshots."""

from __future__ import annotations

import json
import re
from typing import Any

from wysteria.evidence.models import Claim, ClaimType, EvidenceResult, EvidenceStatus
from wysteria.evidence.snapshot import EvidenceSnapshot


class UnsupportedSchemaError(Exception):
    """Raised when an unsupported JSON Schema keyword or limit is encountered."""

    pass


MAX_SCHEMA_DEPTH = 32
SUPPORTED_KEYWORDS = {"type", "properties", "required", "items"}


def _check_openapi(data: dict, claim: Claim) -> EvidenceStatus | None:
    """Attempt to verify the claim against an OpenAPI/Swagger JSON structure.
    Returns None if the JSON doesn't look like an OpenAPI doc with paths.
    """
    if "paths" not in data or not isinstance(data["paths"], dict):
        return None

    paths = data["paths"]
    if claim.path not in paths:
        return EvidenceStatus.FAILED

    path_item = paths[claim.path]
    if not isinstance(path_item, dict):
        return EvidenceStatus.UNVERIFIABLE

    op = claim.operation.lower()
    if op not in path_item:
        return EvidenceStatus.FAILED

    op_item = path_item[op]
    if not isinstance(op_item, dict):
        return EvidenceStatus.UNVERIFIABLE

    if op_item.get("deprecated") is True:
        return EvidenceStatus.UNVERIFIABLE

    if claim.expected_status is not None:
        responses = op_item.get("responses", {})
        if not isinstance(responses, dict):
            return EvidenceStatus.UNVERIFIABLE
        if str(claim.expected_status) not in responses:
            return EvidenceStatus.FAILED

    return EvidenceStatus.VERIFIED


def _verify_api_endpoint(claim: Claim, snapshot: EvidenceSnapshot) -> EvidenceStatus:
    if not claim.operation or not claim.path:
        return EvidenceStatus.UNVERIFIABLE

    text = snapshot.evidence_text

    # 1. Try JSON / OpenAPI parsing first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            result = _check_openapi(data, claim)
            if result is not None:
                return result
    except json.JSONDecodeError:
        pass

    # 2. Plain text regex parsing
    # Look for explicit HTTP endpoint expressions like METHOD PATH
    pattern = r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(/[A-Za-z0-9_/{}\.-]+)\b"

    matches = []
    lines = text.splitlines()
    for line in lines:
        for m in re.finditer(pattern, line, flags=re.IGNORECASE):
            matches.append({"method": m.group(1).upper(), "path": m.group(2), "line": line})

    if not matches:
        return EvidenceStatus.UNVERIFIABLE

    exact_matches = [
        m for m in matches if m["path"] == claim.path and m["method"] == claim.operation.upper()
    ]

    if not exact_matches:
        has_same_path = any(m["path"] == claim.path for m in matches)
        has_same_method = any(m["method"] == claim.operation.upper() for m in matches)

        if has_same_path:
            return EvidenceStatus.FAILED
        elif has_same_method:
            return EvidenceStatus.FAILED
        else:
            return EvidenceStatus.UNVERIFIABLE

    negative_words = {
        "old",
        "deprecated",
        "obsolete",
        "removed",
        "not",
        "wrong",
        "instead",
        "however",
        "unsupported",
        "but",
    }
    http_statuses = {
        "200",
        "201",
        "202",
        "204",
        "400",
        "401",
        "403",
        "404",
        "405",
        "409",
        "422",
        "429",
        "500",
        "502",
        "503",
        "504",
    }

    has_status_mismatch = False
    valid_matches = []

    for m in exact_matches:
        line = m["line"]
        line_lower = line.lower()
        words = set(re.findall(r"[a-z]+", line_lower))
        if words.intersection(negative_words):
            continue

        # Check for ambiguity: multiple distinct endpoints in the same line
        endpoints_in_line = set(
            (em.group(1).upper(), em.group(2))
            for em in re.finditer(pattern, line, flags=re.IGNORECASE)
        )
        if len(endpoints_in_line) > 1:
            continue

        if claim.expected_status is not None:
            expected_str = str(claim.expected_status)
            statuses_in_line = set(re.findall(r"\b[1-5][0-9]{2}\b", line)).intersection(
                http_statuses
            )

            if expected_str in statuses_in_line:
                if len(statuses_in_line) > 1:
                    continue  # ambiguous status
                valid_matches.append(m)
            elif statuses_in_line:
                has_status_mismatch = True
        else:
            valid_matches.append(m)

    if valid_matches:
        return EvidenceStatus.VERIFIED

    if has_status_mismatch:
        return EvidenceStatus.FAILED

    return EvidenceStatus.UNVERIFIABLE


def _validate_json_schema(instance: Any, schema: dict[str, Any], depth: int = 0) -> bool:
    """A minimal deterministic JSON Schema validator for basic types."""
    if depth >= MAX_SCHEMA_DEPTH:
        raise UnsupportedSchemaError(f"Max schema depth of {MAX_SCHEMA_DEPTH} exceeded.")

    if not isinstance(schema, dict):
        return True

    unsupported = set(schema.keys()) - SUPPORTED_KEYWORDS
    if unsupported:
        raise UnsupportedSchemaError(f"Unsupported schema keywords: {unsupported}")

    # Check type
    if "type" in schema:
        schema_type = schema["type"]
        if schema_type == "object" and not isinstance(instance, dict):
            return False
        if schema_type == "array" and not isinstance(instance, list):
            return False
        if schema_type == "string" and not isinstance(instance, str):
            return False
        if schema_type == "number" and not isinstance(instance, (int, float)):
            if isinstance(instance, bool):
                return False
            return False
        if schema_type == "integer" and not isinstance(instance, int):
            if isinstance(instance, bool):
                return False
            return False
        if schema_type == "boolean" and not isinstance(instance, bool):
            return False
        if schema_type == "null" and instance is not None:
            return False

    # Object properties
    if isinstance(instance, dict):
        if "required" in schema:
            for req in schema["required"]:
                if req not in instance:
                    return False
        if "properties" in schema:
            for prop, prop_schema in schema["properties"].items():
                if prop in instance:
                    if not _validate_json_schema(instance[prop], prop_schema, depth + 1):
                        return False

    # Array items
    if isinstance(instance, list) and "items" in schema:
        for item in instance:
            if not _validate_json_schema(item, schema["items"], depth + 1):
                return False

    return True


def _verify_json_schema_claim(claim: Claim, snapshot: EvidenceSnapshot) -> EvidenceStatus:
    if not claim.description:
        return EvidenceStatus.UNVERIFIABLE

    try:
        schema = json.loads(claim.description)
        if not isinstance(schema, dict):
            return EvidenceStatus.UNVERIFIABLE
    except json.JSONDecodeError:
        return EvidenceStatus.UNVERIFIABLE

    try:
        body = json.loads(snapshot.evidence_text)
    except json.JSONDecodeError:
        return EvidenceStatus.FAILED

    try:
        is_valid = _validate_json_schema(body, schema)
    except UnsupportedSchemaError:
        return EvidenceStatus.UNVERIFIABLE

    if is_valid:
        return EvidenceStatus.VERIFIED
    else:
        return EvidenceStatus.FAILED


def verify_claim(claim: Claim, snapshot: EvidenceSnapshot | None) -> EvidenceResult:
    """Deterministically verify a claim against its snapshot."""
    if snapshot is None:
        return EvidenceResult(
            claim_id=claim.id,
            status=EvidenceStatus.NEEDS_EVIDENCE,
            source=claim.source_url,
            reason="No snapshot available for verification.",
        )

    if claim.type == ClaimType.API_ENDPOINT:
        status = _verify_api_endpoint(claim, snapshot)
        return EvidenceResult(
            claim_id=claim.id,
            status=status,
            source=snapshot.source,
            trust_tier=snapshot.trust_tier,
            evidence_text=snapshot.evidence_text,
            content_hash=snapshot.content_hash,
            reason=f"Deterministic verification of {claim.type} yielded {status.value}.",
        )
    elif claim.type == ClaimType.JSON_SCHEMA:
        status = _verify_json_schema_claim(claim, snapshot)
        return EvidenceResult(
            claim_id=claim.id,
            status=status,
            source=snapshot.source,
            trust_tier=snapshot.trust_tier,
            evidence_text=snapshot.evidence_text,
            content_hash=snapshot.content_hash,
            reason=f"Deterministic verification of {claim.type} yielded {status.value}.",
        )
    elif claim.type in (ClaimType.FACTUAL, ClaimType.UNKNOWN):
        return EvidenceResult(
            claim_id=claim.id,
            status=EvidenceStatus.UNVERIFIABLE,
            source=snapshot.source,
            trust_tier=snapshot.trust_tier,
            evidence_text=snapshot.evidence_text,
            content_hash=snapshot.content_hash,
            reason=f"Claim type '{claim.type}' cannot be verified deterministically.",
        )
    else:
        return EvidenceResult(
            claim_id=claim.id,
            status=EvidenceStatus.UNVERIFIABLE,
            source=snapshot.source,
            trust_tier=snapshot.trust_tier,
            evidence_text=snapshot.evidence_text,
            content_hash=snapshot.content_hash,
            reason=f"Unsupported claim type '{claim.type}'.",
        )
