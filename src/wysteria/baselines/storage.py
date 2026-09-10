"""Safe parsing, deterministic serialization, and atomic storage for regression baselines."""

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.tokens import (
    AliasToken,
    AnchorToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
    TagToken,
)

from wysteria.baselines.models import (
    CURRENT_BASELINE_VERSION,
    SUPPORTED_BASELINE_VERSIONS,
    Baseline,
    BaselineResult,
)
from wysteria.errors import (
    BaselineCreationError,
    BaselineLoadError,
    BaselineParseError,
)
from wysteria.verification.models import VerificationResult, VerificationStatus

MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENT_DEPTH = 64
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")
_YAML_DEPTH_START = (
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingStartToken,
    FlowSequenceStartToken,
)
_YAML_DEPTH_END = (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken)


class DuplicateKeyLoader(yaml.SafeLoader):
    """Safe loader which refuses duplicate mapping keys."""


def _construct_mapping(
    loader: DuplicateKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "mapping keys must be strings",
                key_node.start_mark,
            )
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


DuplicateKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _error(message: str, code: str = "WYS600") -> BaselineParseError:
    return BaselineParseError(message, code=code)


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _error(f"baseline exceeds the {MAX_DOCUMENT_BYTES} byte limit", "WYS600")


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
                raise _error(
                    f"baseline exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}", "WYS600"
                )
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise _error("unmatched closing delimiter in JSON text", "WYS600")
    if in_string:
        raise _error("unclosed string in JSON text", "WYS600")


def _check_yaml_scalar(node: yaml.ScalarNode) -> None:
    """Restrict YAML scalars to unambiguous JSON scalar subset."""
    tag = node.tag
    value = node.value
    if tag.endswith(":str"):
        return
    if tag.endswith(":null") and value == "null":
        return
    if tag.endswith(":bool") and value in {"true", "false"}:
        return
    if (
        tag.endswith(":int")
        and _JSON_NUMBER.fullmatch(value)
        and "." not in value
        and "e" not in value.lower()
    ):
        return
    if tag.endswith(":float") and _JSON_NUMBER.fullmatch(value):
        return
    raise _error(
        f"YAML scalar {value!r} is not in Wysteria's JSON-compatible scalar subset", "WYS600"
    )


def _walk_yaml_scalars(node: yaml.Node, depth: int = 0) -> None:
    if depth > MAX_DOCUMENT_DEPTH:
        raise _error(
            f"baseline exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}", "WYS600"
        )
    if isinstance(node, yaml.ScalarNode):
        _check_yaml_scalar(node)
    elif isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise _error("baseline mapping keys must be string scalars", "WYS600")
            _walk_yaml_scalars(value, depth + 1)
    elif isinstance(node, yaml.SequenceNode):
        for value in node.value:
            _walk_yaml_scalars(value, depth + 1)


def _parse_yaml_data(text: str) -> dict[str, Any]:
    try:
        depth = 0
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise _error(
                    "YAML aliases, anchors, and explicit tags are not permitted in baselines",
                    "WYS600",
                )
            if isinstance(token, _YAML_DEPTH_START):
                depth += 1
                if depth > MAX_DOCUMENT_DEPTH:
                    raise _error(
                        f"baseline exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}",
                        "WYS600",
                    )
            elif isinstance(token, _YAML_DEPTH_END):
                depth -= 1
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if root is None:
            raise _error("baseline document is empty", "WYS600")
        _walk_yaml_scalars(root)
        data = yaml.load(text, Loader=DuplicateKeyLoader)
    except BaselineParseError:
        raise
    except (yaml.YAMLError, RecursionError) as error:
        raise _error(str(error), "WYS600") from error
    if not isinstance(data, dict):
        raise _error("baseline root must be a mapping", "WYS600")
    return data


def _parse_json_data(text: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise _error(f"duplicate JSON object key: {key!r}", "WYS600")
            output[key] = value
        return output

    def reject_constant(value: str) -> None:
        raise _error(f"non-finite JSON number is not permitted: {value}", "WYS600")

    try:
        _check_json_depth(text)
        data = json.loads(
            text, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant
        )
    except BaselineParseError:
        raise
    except json.JSONDecodeError as error:
        raise _error(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}", "WYS600"
        ) from error
    except RecursionError as error:
        raise _error("baseline nesting exceeded parser limits", "WYS600") from error
    if not isinstance(data, dict):
        raise _error("baseline root must be an object", "WYS600")
    return data


def parse_baseline(text: str, *, filename: str = "<memory>", format: str | None = None) -> Baseline:
    """Safely parse and validate baseline text into a Baseline model."""
    _check_size(text)
    selected = format or Path(filename).suffix.lstrip(".").lower()
    if selected in {"yaml", "yml"}:
        data = _parse_yaml_data(text)
    elif selected == "json" or not selected:
        # Default to JSON, or try JSON then YAML if format unspecified
        try:
            data = _parse_json_data(text)
        except BaselineParseError:
            if not selected:
                try:
                    data = _parse_yaml_data(text)
                except BaselineParseError:
                    raise
            else:
                raise
    else:
        raise _error("baseline format must be JSON (.json) or YAML (.yaml/.yml)", "WYS600")

    # Check version explicitly
    version = data.get("baseline_version")
    if version not in SUPPORTED_BASELINE_VERSIONS:
        raise _error(
            f"unsupported baseline version {version!r}; supported versions: {sorted(SUPPORTED_BASELINE_VERSIONS)}",
            "WYS600",
        )

    try:
        return Baseline.model_validate(data)
    except ValidationError as err:
        errors = err.errors(include_url=False)
        first = errors[0]
        path = "/" + "/".join(str(loc) for loc in first["loc"])
        msg = first["msg"]
        raise _error(f"baseline schema validation error at {path}: {msg}", "WYS600") from err


def load_baseline(path: str | Path) -> Baseline:
    """Read, safely parse, and validate a baseline file."""
    source = Path(path)
    if not source.is_file():
        raise BaselineLoadError(f"baseline path is not a readable regular file: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise BaselineLoadError(f"cannot read baseline at {source}: {error}") from error
    return parse_baseline(text, filename=str(source))


def serialize_baseline(baseline: Baseline) -> str:
    """Deterministically serialize a Baseline model to canonical formatted JSON."""
    data = baseline.model_dump(mode="json")
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def create_baseline(
    result: VerificationResult,
    path: str | Path,
    *,
    force: bool = False,
) -> Baseline:
    """Create and safely persist a regression baseline from a successful verification result."""
    if not result.success or result.status != VerificationStatus.PASSED:
        raise BaselineCreationError(
            f"cannot create baseline from {result.status.value} verification"
        )
    if not result.workflow_fingerprint:
        raise BaselineCreationError("cannot create baseline without workflow fingerprint")

    dest = Path(path).resolve()
    if dest.exists() and not force:
        raise BaselineCreationError(
            f"baseline file already exists: {dest} (use --force to overwrite)"
        )

    baseline = Baseline(
        baseline_version=CURRENT_BASELINE_VERSION,
        workflow_fingerprint=result.workflow_fingerprint,
        fixture_id=result.fixture_id,
        result=BaselineResult(
            status=result.status,
            success=result.success,
            actual_outputs=dict(sorted(result.actual_outputs.items())),
            actual_assertions=dict(sorted(result.actual_assertions.items())),
            expected_error_code=result.expected_error_code,
        ),
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_file = dest.with_name(f".{dest.name}.tmp")
    content = serialize_baseline(baseline)

    try:
        with open(temp_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, dest)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise

    return baseline
