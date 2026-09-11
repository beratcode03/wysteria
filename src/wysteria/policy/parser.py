"""Safe YAML/JSON policy parsing with bounded resource use and structural validation."""

from __future__ import annotations

import json
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

from wysteria.errors import PolicyLoadError, PolicyParseError
from wysteria.policy.models import SUPPORTED_POLICY_VERSIONS, Policy

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


def _error(message: str, code: str = "WYS450") -> PolicyParseError:
    return PolicyParseError(message, code=code)


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _error(f"policy exceeds the {MAX_DOCUMENT_BYTES} byte limit")


def _check_json_depth(text: str) -> None:
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
        elif character in "{[":
            depth += 1
            if depth > MAX_DOCUMENT_DEPTH:
                raise _error(f"policy exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}")
        elif character in "}]":
            depth -= 1
            if depth < 0:
                raise _error("unmatched closing delimiter in JSON text")
    if in_string:
        raise _error("unclosed string in JSON text")


def _parse_yaml_text(text: str, filename: str) -> dict[str, Any]:
    depth = 0
    try:
        loader = yaml.BaseLoader(text)
        while loader.check_token():
            token = loader.get_token()
            if isinstance(token, AnchorToken):
                raise _error("YAML anchors and aliases are forbidden")
            if isinstance(token, AliasToken):
                raise _error("YAML anchors and aliases are forbidden")
            if isinstance(token, TagToken) and token.value not in (None, "!", "!!str"):
                raise _error(f"custom YAML tags like '{token.value}' are forbidden")
            if isinstance(token, _YAML_DEPTH_START):
                depth += 1
                if depth > MAX_DOCUMENT_DEPTH:
                    raise _error(
                        f"policy exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}"
                    )
            elif isinstance(token, _YAML_DEPTH_END):
                depth -= 1

        data = yaml.load(text, Loader=DuplicateKeyLoader)  # noqa: S506
    except yaml.YAMLError as error:
        raise _error(f"invalid YAML: {error}") from error

    if data is None:
        raise _error("policy document is empty")
    if not isinstance(data, dict):
        raise _error("policy root must be a mapping")
    return data


def _parse_json_text(text: str) -> dict[str, Any]:
    _check_json_depth(text)

    def pairs_hook(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if not isinstance(key, str):
                raise _error(f"JSON object key must be a string: {key!r}")
            if key in result:
                raise _error(f"duplicate JSON object key: {key!r}")
            result[key] = value
        return result

    def parse_constant(value: str) -> Any:
        raise _error(f"non-finite JSON number is not permitted: {value}")

    try:
        data = json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=parse_constant,
        )
    except json.JSONDecodeError as error:
        raise _error(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}"
        ) from error
    except RecursionError as error:
        raise _error("policy nesting exceeded parser limits") from error

    if not isinstance(data, dict):
        raise _error("policy root must be an object")
    return data


def parse_policy(text: str, filename: str = "policy.yaml") -> Policy:
    """Safely parse a policy YAML or JSON string and structurally validate it."""
    _check_size(text)

    is_json = False
    stripped = text.lstrip()
    if filename.endswith(".json") or stripped.startswith("{"):
        is_json = True

    if is_json:
        data = _parse_json_text(text)
    else:
        data = _parse_yaml_text(text, filename)

    version = data.get("policy_version")
    if version is not None and version not in SUPPORTED_POLICY_VERSIONS:
        raise _error(f"unsupported policy version: {version}")

    try:
        return Policy.model_validate(data)
    except ValidationError as err:
        messages = []
        for e in err.errors(include_url=False):
            loc = "/".join(str(p) for p in e["loc"])
            messages.append(f"{loc}: {e['msg']}")
        raise _error(f"policy schema validation error: {'; '.join(messages)}") from err


def load_policy(path: str | Path) -> Policy:
    """Read and validate a policy file from the local filesystem."""
    policy_path = Path(path)
    try:
        text = policy_path.read_text(encoding="utf-8")
    except OSError as err:
        raise PolicyLoadError(f"cannot read policy file '{policy_path}': {err}") from err

    return parse_policy(text, filename=policy_path.name)
