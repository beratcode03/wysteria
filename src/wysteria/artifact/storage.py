"""Deterministic serialization, safe parsing, and strict validation for CI Artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from wysteria.artifact.models import (
    SUPPORTED_ARTIFACT_VERSIONS,
    CIArtifact,
)
from wysteria.errors import (
    ArtifactCreationError,
    ArtifactLoadError,
    ArtifactParseError,
)

MAX_DOCUMENT_BYTES = 2_000_000
MAX_DOCUMENT_DEPTH = 64


def _normalize_paths_in_data(data: Any) -> Any:
    """Recursively convert Windows path backslashes to forward slashes for machine independence."""
    if isinstance(data, dict):
        return {k: _normalize_paths_in_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_normalize_paths_in_data(item) for item in data]
    if isinstance(data, str):
        if "\\" in data:
            return data.replace("\\", "/")
        return data
    return data


def serialize_ci_artifact(artifact: CIArtifact, *, indent: int = 2) -> str:
    """Deterministically serialize a CIArtifact to canonical formatted JSON."""
    data = artifact.model_dump(mode="json")
    normalized = _normalize_paths_in_data(data)
    return json.dumps(normalized, indent=indent, sort_keys=True) + "\n"


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ArtifactParseError(
            f"artifact exceeds the {MAX_DOCUMENT_BYTES} byte limit", code="WYS950"
        )


def _check_json_depth(text: str) -> None:
    """Bound nesting before handing untrusted JSON to the decoder."""
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_DOCUMENT_DEPTH:
                raise ArtifactParseError(
                    f"artifact exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}",
                    code="WYS950",
                )
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ArtifactParseError("unmatched closing delimiter in JSON text", code="WYS950")
    if in_string:
        raise ArtifactParseError("unclosed string in JSON text", code="WYS950")


def _parse_json_data(text: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ArtifactParseError(f"duplicate JSON object key: {key!r}", code="WYS950")
            output[key] = value
        return output

    def reject_constant(value: str) -> None:
        raise ArtifactParseError(f"non-finite JSON number is not permitted: {value}", code="WYS950")

    try:
        _check_json_depth(text)
        data = json.loads(
            text, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant
        )
    except ArtifactParseError:
        raise
    except json.JSONDecodeError as error:
        raise ArtifactParseError(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}",
            code="WYS950",
        ) from error
    except RecursionError as error:
        raise ArtifactParseError(
            "artifact nesting exceeded parser limits", code="WYS950"
        ) from error

    if not isinstance(data, dict):
        raise ArtifactParseError("artifact root must be an object", code="WYS950")
    return data


def parse_ci_artifact(text: str, *, filename: str = "<memory>") -> CIArtifact:
    """Safely parse and validate JSON text into a strict CIArtifact."""
    _check_size(text)
    data = _parse_json_data(text)

    # Check version explicitly
    version = data.get("artifact_version")
    if version is None:
        version = data.get("schema_version")

    if version not in SUPPORTED_ARTIFACT_VERSIONS:
        raise ArtifactParseError(
            f"unsupported artifact version {version!r}; supported versions: {sorted(SUPPORTED_ARTIFACT_VERSIONS)}",
            code="WYS950",
        )

    try:
        return CIArtifact.model_validate_json(text)
    except ValidationError as err:
        errors = err.errors(include_url=False)
        first = errors[0]
        path = "/" + "/".join(str(loc) for loc in first["loc"])
        msg = first["msg"]
        raise ArtifactParseError(
            f"artifact schema validation error at {path}: {msg}", code="WYS950"
        ) from err


def load_ci_artifact(path: str | Path) -> CIArtifact:
    """Read, safely parse, and validate a CI artifact file."""
    source = Path(path)
    if not source.is_file():
        raise ArtifactLoadError(f"artifact path is not a readable regular file: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise ArtifactLoadError(f"cannot read artifact at {source}: {error}") from error
    return parse_ci_artifact(text, filename=str(source))


def validate_ci_artifact(artifact_input: str | Path | dict[str, Any] | CIArtifact) -> CIArtifact:
    """Validate a CI artifact strictly, raising ArtifactParseError or ArtifactLoadError on invalid input."""
    if isinstance(artifact_input, CIArtifact):
        return artifact_input
    if isinstance(artifact_input, Path):
        return load_ci_artifact(artifact_input)
    if isinstance(artifact_input, str):
        p = Path(artifact_input)
        if p.is_file():
            return load_ci_artifact(p)
        return parse_ci_artifact(artifact_input)
    if isinstance(artifact_input, dict):
        version = artifact_input.get("artifact_version") or artifact_input.get("schema_version")
        if version not in SUPPORTED_ARTIFACT_VERSIONS:
            raise ArtifactParseError(
                f"unsupported artifact version {version!r}; supported versions: {sorted(SUPPORTED_ARTIFACT_VERSIONS)}",
                code="WYS950",
            )
        json_str = json.dumps(artifact_input)
        try:
            return CIArtifact.model_validate_json(json_str)
        except ValidationError as err:
            errors = err.errors(include_url=False)
            first = errors[0]
            path = "/" + "/".join(str(loc) for loc in first["loc"])
            raise ArtifactParseError(
                f"artifact schema validation error at {path}: {first['msg']}", code="WYS950"
            ) from err
    raise ArtifactParseError(
        "artifact input must be a CIArtifact, JSON string, dict, or file path", code="WYS950"
    )


def save_ci_artifact(artifact: CIArtifact, path: str | Path) -> Path:
    """Atomically write canonical CI artifact JSON to disk."""
    dest = Path(path).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_file = dest.with_name(f".{dest.name}.tmp")
    content = serialize_ci_artifact(artifact)

    try:
        with open(temp_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, dest)
    except Exception as err:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise ArtifactCreationError(f"failed to write CI artifact to {dest}: {err}") from err

    return dest
