import pytest

from wysteria.api import parse_workflow
from wysteria.errors import WorkflowParseError


def test_yaml_source_location_is_preserved():
    parsed = parse_workflow("ir_version: 1\nname: sample\n", filename="sample.yaml")
    location = parsed.locations["/name"]
    assert (location.file, location.line, location.column) == ("sample.yaml", 2, 7)


@pytest.mark.parametrize(
    "text",
    [
        "name: one\nname: two\n",
        "name: &value one\nother: *value\n",
        "name: !custom one\n",
    ],
)
def test_unsafe_or_ambiguous_yaml_is_rejected(text):
    with pytest.raises(WorkflowParseError):
        parse_workflow(text, filename="unsafe.yaml")


def test_malformed_json_is_rejected():
    with pytest.raises(WorkflowParseError, match="invalid JSON"):
        parse_workflow("{", filename="workflow.json")


def test_unknown_extension_is_rejected():
    with pytest.raises(WorkflowParseError, match="format"):
        parse_workflow("{}", filename="workflow.txt")
