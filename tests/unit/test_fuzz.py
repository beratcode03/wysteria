import json

from hypothesis import given
from hypothesis import strategies as st

from wysteria.api import WorkflowParseError, parse_workflow, validate_workflow


@given(st.text())
def test_fuzz_parser_does_not_crash_on_random_text(text):
    try:
        parse_workflow(text, format="yaml")
    except WorkflowParseError:
        pass  # expected
    try:
        parse_workflow(text, format="json")
    except WorkflowParseError:
        pass  # expected


@given(st.dictionaries(st.text(), st.text()))
def test_fuzz_parser_does_not_crash_on_random_dict(d):
    try:
        parsed = parse_workflow(json.dumps(d), format="json")
        validate_workflow(parsed)
    except WorkflowParseError:
        pass
