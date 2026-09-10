"""Safe YAML/JSON parsing with bounded resource use and source locations."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
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

from wysteria.errors import WorkflowLoadError, WorkflowParseError
from wysteria.reporting.diagnostics import SourceLocation

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


@dataclass(frozen=True)
class ParsedWorkflow:
    """A public parsed workflow document with optional source locations."""

    data: dict[str, Any]
    filename: str
    locations: dict[str, SourceLocation]


def _error(message: str, code: str) -> WorkflowParseError:
    return WorkflowParseError(message, code=code)


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _error(f"workflow exceeds the {MAX_DOCUMENT_BYTES} byte limit", "WYS912")


def _check_json_depth(text: str) -> None:
    """Bound nesting before handing untrusted JSON to the recursive decoder."""

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
                    f"workflow exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}", "WYS911"
                )
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise _error("unmatched closing delimiter in JSON text", "WYS900")
    if in_string:
        raise _error("unclosed string in JSON text", "WYS900")


def _check_yaml_scalar(node: yaml.ScalarNode) -> None:
    """Restrict YAML scalars to the unambiguous JSON scalar subset."""

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
        f"YAML scalar {value!r} is not in Wysteria's JSON-compatible scalar subset", "WYS915"
    )


def _walk_locations(
    node: yaml.Node, filename: str, path: str, output: dict[str, SourceLocation], depth: int = 0
) -> None:
    if depth > MAX_DOCUMENT_DEPTH:
        raise _error(
            f"workflow exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}", "WYS911"
        )
    output[path] = SourceLocation(
        file=filename, line=node.start_mark.line + 1, column=node.start_mark.column + 1
    )
    if isinstance(node, yaml.ScalarNode):
        _check_yaml_scalar(node)
    elif isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise _error("workflow mapping keys must be string scalars", "WYS915")
            key_text = key.value.replace("~", "~0").replace("/", "~1")
            _walk_locations(value, filename, f"{path}/{key_text}", output, depth + 1)
    elif isinstance(node, yaml.SequenceNode):
        for index, value in enumerate(node.value):
            _walk_locations(value, filename, f"{path}/{index}", output, depth + 1)


def _parse_yaml(text: str, filename: str) -> ParsedWorkflow:
    try:
        depth = 0
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise _error("YAML aliases, anchors, and explicit tags are not permitted", "WYS914")
            if isinstance(token, _YAML_DEPTH_START):
                depth += 1
                if depth > MAX_DOCUMENT_DEPTH:
                    raise _error(
                        f"workflow exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}",
                        "WYS911",
                    )
            elif isinstance(token, _YAML_DEPTH_END):
                depth -= 1
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if root is None:
            raise _error("workflow document is empty", "WYS900")
        locations: dict[str, SourceLocation] = {}
        _walk_locations(root, filename, "", locations)
        data = yaml.load(text, Loader=DuplicateKeyLoader)
    except WorkflowParseError:
        raise
    except (yaml.YAMLError, RecursionError) as error:
        raise _error(str(error), "WYS900") from error
    if not isinstance(data, dict):
        raise _error("workflow root must be a mapping", "WYS900")
    return ParsedWorkflow(data=data, filename=filename, locations=locations)


def _parse_json(text: str, filename: str) -> ParsedWorkflow:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise _error(f"duplicate JSON object key: {key!r}", "WYS910")
            output[key] = value
        return output

    def reject_constant(value: str) -> None:
        raise _error(f"non-finite JSON number is not permitted: {value}", "WYS913")

    try:
        _check_json_depth(text)
        data = json.loads(
            text, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant
        )
    except WorkflowParseError:
        raise
    except json.JSONDecodeError as error:
        raise _error(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}", "WYS900"
        ) from error
    except RecursionError as error:
        raise _error("workflow nesting exceeded parser limits", "WYS911") from error
    if not isinstance(data, dict):
        raise _error("workflow root must be an object", "WYS900")
    return ParsedWorkflow(data=data, filename=filename, locations={})


def parse_workflow(
    text: str, *, filename: str = "<memory>", format: str | None = None
) -> ParsedWorkflow:
    """Safely parse YAML or JSON workflow text without validating the IR."""

    _check_size(text)
    selected = format or Path(filename).suffix.lstrip(".").lower()
    if selected in {"yaml", "yml"}:
        return _parse_yaml(text, filename)
    if selected == "json":
        return _parse_json(text, filename)
    raise _error("workflow format must be YAML (.yaml/.yml) or JSON (.json)", "WYS900")


def load_workflow(path: str | Path) -> ParsedWorkflow:
    """Read and safely parse a workflow file."""

    source = Path(path)
    if not source.is_file():
        raise WorkflowLoadError(f"workflow path is not a readable regular file: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowLoadError(f"cannot read {source}: {error}") from error
    return parse_workflow(text, filename=str(source))
