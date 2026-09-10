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


def test_json_depth_limit_boundary():
    # 64 levels deep should pass the depth check (though invalid workflow schema)
    nested_64 = '{"a": ' * 64 + "0" + "}" * 64
    parsed = parse_workflow(nested_64, filename="workflow.json")
    assert isinstance(parsed.data, dict)

    # 65 levels deep must be rejected with WYS911
    nested_65 = '{"a": ' * 65 + "0" + "}" * 65
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_workflow(nested_65, filename="workflow.json")
    assert exc_info.value.code == "WYS911"


def test_json_depth_underflow_attack_is_rejected():
    # Adversarial attempts to manipulate depth with closing brackets
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_workflow('}{"ir_version": 1}', filename="workflow.json")
    assert exc_info.value.code == "WYS900"
    assert "unmatched closing delimiter" in str(exc_info.value)

    with pytest.raises(WorkflowParseError) as exc_info:
        parse_workflow(']{"ir_version": 1}', filename="workflow.json")
    assert exc_info.value.code == "WYS900"


def test_json_unclosed_string_is_rejected():
    with pytest.raises(WorkflowParseError) as exc_info:
        parse_workflow('{"key": "unclosed', filename="workflow.json")
    assert exc_info.value.code == "WYS900"
