"""Safe YAML/JSON fixture parsing with bounded resource use and structural validation."""

import json
import re
from dataclasses import dataclass
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

from wysteria.errors import FixtureLoadError, FixtureParseError
from wysteria.fixtures.models import SUPPORTED_FIXTURE_VERSIONS, Fixture
from wysteria.reporting.diagnostics import Diagnostic, Severity, SourceLocation
from wysteria.validation.common import diagnostic

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
class ParsedFixture:
    """A public parsed fixture document with source locations."""

    data: dict[str, Any]
    filename: str
    locations: dict[str, SourceLocation]


def _error(message: str, code: str = "WYS700") -> FixtureParseError:
    return FixtureParseError(message, code=code)


def _check_size(text: str) -> None:
    if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise _error(f"fixture exceeds the {MAX_DOCUMENT_BYTES} byte limit", "WYS700")


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
                    f"fixture exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}", "WYS700"
                )
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise _error("unmatched closing delimiter in JSON text", "WYS700")
    if in_string:
        raise _error("unclosed string in JSON text", "WYS700")


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
        f"YAML scalar {value!r} is not in Wysteria's JSON-compatible scalar subset", "WYS700"
    )


def _walk_locations(
    node: yaml.Node, filename: str, path: str, output: dict[str, SourceLocation], depth: int = 0
) -> None:
    if depth > MAX_DOCUMENT_DEPTH:
        raise _error(f"fixture exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}", "WYS700")
    output[path] = SourceLocation(
        file=filename, line=node.start_mark.line + 1, column=node.start_mark.column + 1
    )
    if isinstance(node, yaml.ScalarNode):
        _check_yaml_scalar(node)
    elif isinstance(node, yaml.MappingNode):
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                raise _error("fixture mapping keys must be string scalars", "WYS700")
            key_text = key.value.replace("~", "~0").replace("/", "~1")
            _walk_locations(value, filename, f"{path}/{key_text}", output, depth + 1)
    elif isinstance(node, yaml.SequenceNode):
        for index, value in enumerate(node.value):
            _walk_locations(value, filename, f"{path}/{index}", output, depth + 1)


def _parse_yaml(text: str, filename: str) -> ParsedFixture:
    try:
        depth = 0
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise _error("YAML aliases, anchors, and explicit tags are not permitted", "WYS700")
            if isinstance(token, _YAML_DEPTH_START):
                depth += 1
                if depth > MAX_DOCUMENT_DEPTH:
                    raise _error(
                        f"fixture exceeds the maximum nesting depth of {MAX_DOCUMENT_DEPTH}",
                        "WYS700",
                    )
            elif isinstance(token, _YAML_DEPTH_END):
                depth -= 1
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if root is None:
            raise _error("fixture document is empty", "WYS700")
        locations: dict[str, SourceLocation] = {}
        _walk_locations(root, filename, "", locations)
        data = yaml.load(text, Loader=DuplicateKeyLoader)
    except FixtureParseError:
        raise
    except (yaml.YAMLError, RecursionError) as error:
        raise _error(str(error), "WYS700") from error
    if not isinstance(data, dict):
        raise _error("fixture root must be a mapping", "WYS700")
    return ParsedFixture(data=data, filename=filename, locations=locations)


def _parse_json(text: str, filename: str) -> ParsedFixture:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise _error(f"duplicate JSON object key: {key!r}", "WYS700")
            output[key] = value
        return output

    def reject_constant(value: str) -> None:
        raise _error(f"non-finite JSON number is not permitted: {value}", "WYS700")

    try:
        _check_json_depth(text)
        data = json.loads(
            text, object_pairs_hook=reject_duplicate_keys, parse_constant=reject_constant
        )
    except FixtureParseError:
        raise
    except json.JSONDecodeError as error:
        raise _error(
            f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}", "WYS700"
        ) from error
    except RecursionError as error:
        raise _error("fixture nesting exceeded parser limits", "WYS700") from error
    if not isinstance(data, dict):
        raise _error("fixture root must be an object", "WYS700")
    return ParsedFixture(data=data, filename=filename, locations={})


def parse_fixture_document(
    text: str, *, filename: str = "<memory>", format: str | None = None
) -> ParsedFixture:
    """Safely parse YAML or JSON fixture text into a document with source locations."""

    _check_size(text)
    selected = format or Path(filename).suffix.lstrip(".").lower()
    if selected in {"yaml", "yml"}:
        return _parse_yaml(text, filename)
    if selected == "json":
        return _parse_json(text, filename)
    raise _error("fixture format must be YAML (.yaml/.yml) or JSON (.json)", "WYS700")


def load_fixture_document(path: str | Path) -> ParsedFixture:
    """Read and safely parse a fixture file into a document with source locations."""

    source = Path(path)
    if not source.is_file():
        raise FixtureLoadError(f"fixture path is not a readable regular file: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise FixtureLoadError(f"cannot read {source}: {error}") from error
    return parse_fixture_document(text, filename=str(source))


def _pointer(location: tuple[object, ...]) -> str:
    return "".join(f"/{part}" for part in location)


def validate_fixture_structure(
    parsed: ParsedFixture,
) -> tuple[Fixture | None, list[Diagnostic]]:
    """Validate parsed fixture data against strict Pydantic models."""

    try:
        return Fixture.model_validate(parsed.data), []
    except ValidationError as error:
        diagnostics: list[Diagnostic] = []
        for item in error.errors(include_url=False):
            path = _pointer(item["loc"])
            kind = item["type"]
            code = "WYS701"
            hint = None
            if kind == "extra_forbidden":
                hint = "Remove the unsupported field."
            elif kind == "missing":
                hint = "Provide the required field."
            elif kind == "literal_error":
                hint = f"Supported fixture versions: {sorted(SUPPORTED_FIXTURE_VERSIONS)}."
            elif kind in {"too_long", "string_too_long", "iterable_too_long"}:
                hint = "Reduce the collection size to stay within cardinality limits."
            diagnostics.append(
                diagnostic(
                    code, item["msg"], path, parsed=parsed, severity=Severity.ERROR, hint=hint
                )
            )
        return None, diagnostics


def parse_fixture(text: str, *, filename: str = "<memory>", format: str | None = None) -> Fixture:
    """Safely parse and structurally validate YAML or JSON fixture text."""

    parsed = parse_fixture_document(text, filename=filename, format=format)
    fixture, diagnostics = validate_fixture_structure(parsed)
    if fixture is None or diagnostics:
        first = diagnostics[0]
        prefix = f"{first.path}: " if first.path else ""
        raise _error(f"{prefix}{first.message}", code=first.code)
    return fixture


def load_fixture(path: str | Path) -> Fixture:
    """Read, safely parse, and structurally validate a YAML or JSON fixture file."""

    source = Path(path)
    if not source.is_file():
        raise FixtureLoadError(f"fixture path is not a readable regular file: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise FixtureLoadError(f"cannot read {source}: {error}") from error
    return parse_fixture(text, filename=str(source))
