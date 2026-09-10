"""Unit tests for GitHub Actions workflow command / annotation formatting."""

from wysteria.api import (
    Diagnostic,
    Severity,
    format_github_annotations,
    parse_fixture,
    parse_workflow,
    verify_fixture,
)
from wysteria.reporting.builder import build_developer_report
from wysteria.reporting.diagnostics import SourceLocation
from wysteria.reporting.github import (
    escape_github_data,
    escape_github_property,
    format_diagnostic_annotation,
    normalize_file_path,
)

SAMPLE_WORKFLOW_TEXT = """ir_version: 1
name: greeter
inputs:
  name:
    type: string
nodes:
  - id: msg
    kind: construct
    inputs:
      who:
        input: name
    config:
      template:
        greeting: "Hello, ${who}!"
    output_type: object
edges:
  - source: {input: name}
    target_node: msg
    target_input: who
capabilities: []
assertions: []
outputs:
  output:
    source: {node: msg}
    type: object
"""

HAPPY_FIXTURE_TEXT = """fixture_version: 1
id: happy-path
name: Happy Path Fixture
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, BERAT!"
"""

MISMATCH_FIXTURE_TEXT = """fixture_version: 1
id: mismatch-path
inputs:
  name: "BERAT"
expected:
  outputs:
    output:
      greeting: "Hello, WRONG!"
"""


def test_escape_github_property():
    assert escape_github_property("simple") == "simple"
    assert escape_github_property("a:b,c%d\re\nf") == "a%3Ab%2Cc%25d%0De%0Af"


def test_escape_github_data():
    assert escape_github_data("simple text") == "simple text"
    assert escape_github_data("line1\nline2\rline3%end") == "line1%0Aline2%0Dline3%25end"
    # colons and commas in message are NOT escaped (only % \r \n)
    assert escape_github_data("key: value, other: item") == "key: value, other: item"


def test_normalize_file_path():
    assert normalize_file_path("path\\to\\file.yaml") == "path/to/file.yaml"
    assert normalize_file_path("path/to/file.yaml") == "path/to/file.yaml"


def test_format_diagnostic_annotation():
    diag = Diagnostic(
        code="WYS102",
        severity=Severity.ERROR,
        message="Invalid workflow schema",
        location=SourceLocation(file="workflows/test.yaml", line=10, column=4),
        hint="check required fields",
    )
    line = format_diagnostic_annotation(diag)
    assert (
        line
        == "::error file=workflows/test.yaml,line=10,col=4,title=WYS102::Invalid workflow schema (hint: check required fields)"
    )

    diag_no_loc = Diagnostic(
        code="WYS900",
        severity=Severity.WARNING,
        message="Warning message",
    )
    line2 = format_diagnostic_annotation(diag_no_loc)
    assert line2 == "::warning title=WYS900::Warning message"

    # Ignored memory location
    diag_mem = Diagnostic(
        code="WYS700",
        severity=Severity.ERROR,
        message="Parse error",
        location=SourceLocation(file="<memory>", line=1, column=1),
    )
    line3 = format_diagnostic_annotation(diag_mem)
    assert "file=" not in line3
    assert line3 == "::error title=WYS700::Parse error"


def test_format_github_annotations_passing_report():
    wf = parse_workflow(SAMPLE_WORKFLOW_TEXT, filename="workflow.yaml")
    fix = parse_fixture(HAPPY_FIXTURE_TEXT, filename="fixture.yaml")
    res = verify_fixture(wf, fix)
    assert res.status == "PASSED"

    report = build_developer_report(res, workflow=wf, fixture=fix)
    annotations = format_github_annotations(report)
    assert annotations == []


def test_format_github_annotations_mismatch_report():
    wf = parse_workflow(SAMPLE_WORKFLOW_TEXT, filename="workflow.yaml")
    fix = parse_fixture(MISMATCH_FIXTURE_TEXT, filename="fixture.yaml")
    res = verify_fixture(wf, fix)
    assert res.status == "OUTPUT_MISMATCH"

    report = build_developer_report(res, workflow=wf, fixture=fix)
    annotations = format_github_annotations(report)
    assert len(annotations) >= 1
    assert any("::error" in a and "WYS852" in a for a in annotations)


def test_format_github_annotations_deduplication():
    wf = parse_workflow(SAMPLE_WORKFLOW_TEXT, filename="workflow.yaml")
    fix = parse_fixture(MISMATCH_FIXTURE_TEXT, filename="fixture.yaml")
    res = verify_fixture(wf, fix)
    report = build_developer_report(res, workflow=wf, fixture=fix)

    # Duplicating diagnostics
    report.diagnostics.extend(report.diagnostics)
    annotations = format_github_annotations(report)
    # Ensure no duplicates in formatted annotations
    assert len(annotations) == len(set(annotations))
