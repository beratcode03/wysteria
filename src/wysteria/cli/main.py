"""Wysteria's CLI foundation."""

import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


from wysteria.api import (
    GateDecision,
    build_developer_report,
    compare_baseline,
    create_baseline,
    diff_workflows,
    evaluate_policy,
    format_baseline_report,
    format_explanation_human,
    format_github_annotations,
    format_policy_report,
    format_workflow_diff,
    load_baseline,
    load_fixture_document,
    load_policy,
    load_workflow,
    validate_workflow,
    verify_fixture,
)
from wysteria.errors import (
    BaselineCreationError,
    BaselineLoadError,
    BaselineParseError,
    FixtureLoadError,
    FixtureParseError,
    PolicyLoadError,
    PolicyParseError,
    WorkflowLoadError,
    WorkflowParseError,
)
from wysteria.ir.models import Capability, Workflow
from wysteria.ir.versioning import CURRENT_IR_VERSION
from wysteria.reporting import escape_github_data, format_diagnostic_annotation
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.reporting.verification import (
    EXIT_CODES,
    format_verification_json,
    format_verification_report,
)
from wysteria.validation.capabilities import CapabilityPolicy
from wysteria.verification.models import VerificationResult, VerificationStatus

app = typer.Typer(
    help="Deterministic verification for declarative workflow contracts.", no_args_is_help=True
)


def _print_diagnostics(result, output_format: str) -> None:
    if output_format == "json":
        typer.echo(result.model_dump_json(exclude={"workflow"}, indent=2))
        return
    for item in result.diagnostics:
        location = ""
        if item.location:
            location = f"{item.location.file}:{item.location.line}:{item.location.column}: "
        path = f" [{item.path}]" if item.path else ""
        typer.echo(f"{location}{item.severity.value} {item.code}{path}: {item.message}", err=True)
        if item.hint:
            typer.echo(f"  hint: {item.hint}", err=True)


@app.command()
def validate(
    workflow: Annotated[
        Path, typer.Argument(exists=True, readable=True, help="Workflow YAML or JSON file.")
    ],
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
) -> None:
    """Validate a workflow contract without executing it."""

    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(3)
    try:
        result = validate_workflow(load_workflow(workflow))
    except (WorkflowLoadError, WorkflowParseError) as error:
        if github_annotations:
            typer.echo(f"::error title=WYS900::{escape_github_data(str(error))}", err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "valid": False,
                        "blocked": False,
                        "diagnostics": [
                            {
                                "code": "WYS900",
                                "severity": "error",
                                "message": str(error),
                                "path": "",
                            }
                        ],
                    }
                )
            )
        else:
            typer.echo(f"error WYS900: {error}", err=True)
        raise typer.Exit(3) from error
    if github_annotations:
        for item in result.diagnostics:
            typer.echo(format_diagnostic_annotation(item), err=True)
    _print_diagnostics(result, output_format)
    if result.valid:
        if output_format == "human":
            typer.echo(f"PASS {workflow} is a valid Workflow IR v{CURRENT_IR_VERSION}")
        raise typer.Exit(0)
    raise typer.Exit(2 if result.blocked else 1)


@app.command()
def verify(
    workflow: Annotated[
        Path, typer.Argument(metavar="WORKFLOW", help="Workflow YAML or JSON file.")
    ],
    fixture: Annotated[Path, typer.Option("--fixture", "-f", help="Fixture YAML or JSON file.")],
    policy: Annotated[
        Path | None,
        typer.Option("--policy", "-p", help="Optional policy YAML or JSON file."),
    ] = None,
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
    report_file: Annotated[
        Path | None,
        typer.Option("--report-file", help="Write JSON report artifact to path."),
    ] = None,
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
) -> None:
    """Verify a workflow proposal deterministically against a fixture."""

    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)

    parsed_wf = None
    wf_error = None
    try:
        parsed_wf = load_workflow(workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        wf_error = err

    parsed_fix = None
    fix_error = None
    if wf_error is None:
        try:
            parsed_fix = load_fixture_document(fixture)
        except (FixtureLoadError, FixtureParseError) as err:
            fix_error = err

    if wf_error is not None:
        code = getattr(wf_error, "code", "WYS900")
        result = VerificationResult(
            status=VerificationStatus.INVALID_WORKFLOW,
            success=False,
            fixture_id=str(fixture.stem) if fixture else "<unknown>",
            diagnostics=[Diagnostic(code=code, severity=Severity.ERROR, message=str(wf_error))],
        )
    elif fix_error is not None:
        code = getattr(fix_error, "code", "WYS700")
        result = VerificationResult(
            status=VerificationStatus.INVALID_FIXTURE,
            success=False,
            fixture_id=str(fixture.stem) if fixture else "<unknown>",
            diagnostics=[Diagnostic(code=code, severity=Severity.ERROR, message=str(fix_error))],
        )
    else:
        assert parsed_wf is not None
        assert parsed_fix is not None
        result = verify_fixture(parsed_wf, parsed_fix)

    policy_res = None
    if policy is not None and result.status == VerificationStatus.PASSED and parsed_wf is not None:
        try:
            loaded_policy = load_policy(policy)
            val_wf = validate_workflow(parsed_wf)
            if val_wf.valid and val_wf.workflow is not None:
                policy_res = evaluate_policy(val_wf.workflow, loaded_policy)
        except (PolicyLoadError, PolicyParseError) as err:
            code = getattr(err, "code", "WYS450")
            typer.echo(f"error {code}: {err}", err=True)
            raise typer.Exit(3) from err

    workflow_display = str(workflow)
    fixture_display = (
        result.fixture_id
        if result.fixture_id and result.fixture_id != "<unknown>"
        else str(fixture)
    )
    dev_report = build_developer_report(
        result,
        workflow=parsed_wf,
        fixture=parsed_fix,
        workflow_display=workflow_display,
        fixture_display=fixture_display,
        policy_result=policy_res,
    )

    if report_file is not None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(format_verification_json(dev_report) + "\n", encoding="utf-8")

    if github_annotations:
        for ann in format_github_annotations(dev_report):
            typer.echo(ann, err=True)

    if output_format == "json":
        typer.echo(format_verification_json(dev_report))
    else:
        typer.echo(format_verification_report(dev_report))

    exit_code = EXIT_CODES.get(result.status, 4)
    if exit_code == 0 and policy_res is not None and not policy_res.passed:
        exit_code = 1
    raise typer.Exit(exit_code)


@app.command()
def explain(
    workflow: Annotated[
        Path, typer.Argument(metavar="WORKFLOW", help="Workflow YAML or JSON file.")
    ],
    fixture: Annotated[Path, typer.Option("--fixture", "-f", help="Fixture YAML or JSON file.")],
    policy: Annotated[
        Path | None,
        typer.Option("--policy", "-p", help="Optional policy YAML or JSON file."),
    ] = None,
    baseline: Annotated[
        Path | None,
        typer.Option("--baseline", "-b", help="Optional baseline YAML or JSON file."),
    ] = None,
    baseline_workflow: Annotated[
        Path | None,
        typer.Option(
            "--baseline-workflow",
            help="Old workflow YAML or JSON file for semantic diffing.",
        ),
    ] = None,
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
    report_file: Annotated[
        Path | None,
        typer.Option("--report-file", help="Write JSON report artifact to path."),
    ] = None,
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
) -> None:
    """Explain deterministically why Wysteria PASS, FAIL, or BLOCK a workflow."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)

    parsed_wf = None
    wf_error = None
    try:
        parsed_wf = load_workflow(workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        wf_error = err

    parsed_fix = None
    fix_error = None
    if wf_error is None:
        try:
            parsed_fix = load_fixture_document(fixture)
        except (FixtureLoadError, FixtureParseError) as err:
            fix_error = err

    if wf_error is not None:
        code = getattr(wf_error, "code", "WYS900")
        result = VerificationResult(
            status=VerificationStatus.INVALID_WORKFLOW,
            success=False,
            fixture_id=str(fixture.stem) if fixture else "<unknown>",
            diagnostics=[Diagnostic(code=code, severity=Severity.ERROR, message=str(wf_error))],
        )
    elif fix_error is not None:
        code = getattr(fix_error, "code", "WYS700")
        result = VerificationResult(
            status=VerificationStatus.INVALID_FIXTURE,
            success=False,
            fixture_id=str(fixture.stem) if fixture else "<unknown>",
            diagnostics=[Diagnostic(code=code, severity=Severity.ERROR, message=str(fix_error))],
        )
    else:
        assert parsed_wf is not None
        assert parsed_fix is not None
        result = verify_fixture(parsed_wf, parsed_fix)

    policy_res = None
    if policy is not None and parsed_wf is not None:
        try:
            loaded_policy = load_policy(policy)
            val_wf = validate_workflow(parsed_wf)
            if val_wf.valid and val_wf.workflow is not None:
                policy_res = evaluate_policy(val_wf.workflow, loaded_policy)
        except (PolicyLoadError, PolicyParseError) as err:
            code = getattr(err, "code", "WYS450")
            if github_annotations:
                typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
            typer.echo(f"error {code}: {err}", err=True)
            raise typer.Exit(3) from err

    comparison = None
    diff_res = None
    if baseline is not None and parsed_wf is not None and parsed_fix is not None:
        try:
            loaded_baseline = load_baseline(baseline)
        except (BaselineLoadError, BaselineParseError) as err:
            code = getattr(err, "code", "WYS600")
            if github_annotations:
                typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
            typer.echo(f"error {code}: {err}", err=True)
            raise typer.Exit(4) from err

        curr_wf_val = validate_workflow(parsed_wf)
        curr_wf = curr_wf_val.workflow if curr_wf_val and curr_wf_val.valid else None

        parsed_base_wf = None
        if baseline_workflow is not None:
            try:
                base_wf_doc = load_workflow(baseline_workflow)
                base_wf_val = validate_workflow(base_wf_doc)
                if base_wf_val.valid and base_wf_val.workflow:
                    parsed_base_wf = base_wf_val.workflow
            except (WorkflowLoadError, WorkflowParseError) as err:
                code = getattr(err, "code", "WYS900")
                if github_annotations:
                    typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
                typer.echo(f"error {code}: {err}", err=True)
                raise typer.Exit(2) from err

        comparison = compare_baseline(
            result,
            loaded_baseline,
            baseline_workflow=parsed_base_wf,
            current_workflow=curr_wf,
        )
        diff_res = getattr(comparison, "workflow_diff", None)
    elif baseline_workflow is not None and parsed_wf is not None:
        try:
            base_wf_doc = load_workflow(baseline_workflow)
            base_wf_val = validate_workflow(base_wf_doc)
            curr_wf_val = validate_workflow(parsed_wf)
            if (
                base_wf_val.valid
                and base_wf_val.workflow
                and curr_wf_val.valid
                and curr_wf_val.workflow
            ):
                diff_res = diff_workflows(
                    base_wf_val.workflow,
                    curr_wf_val.workflow,
                    old_display=str(baseline_workflow),
                    new_display=str(workflow),
                )
        except (WorkflowLoadError, WorkflowParseError) as err:
            code = getattr(err, "code", "WYS900")
            if github_annotations:
                typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
            typer.echo(f"error {code}: {err}", err=True)
            raise typer.Exit(2) from err

    workflow_display = str(workflow)
    fixture_display = (
        result.fixture_id
        if result.fixture_id and result.fixture_id != "<unknown>"
        else str(fixture)
    )
    dev_report = build_developer_report(
        result,
        workflow=parsed_wf,
        fixture=parsed_fix,
        workflow_display=workflow_display,
        fixture_display=fixture_display,
        baseline_comparison=comparison,
        workflow_diff=diff_res,
        policy_result=policy_res,
    )

    provenance = dev_report.provenance
    assert provenance is not None

    if report_file is not None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(provenance.to_json() + "\n", encoding="utf-8")

    if github_annotations:
        for ann in format_github_annotations(dev_report):
            typer.echo(ann, err=True)

    if output_format == "json":
        typer.echo(provenance.to_json())
    else:
        typer.echo(format_explanation_human(provenance))

    gate_decision = provenance.gate_decision
    if gate_decision == GateDecision.PASS:
        raise typer.Exit(0)
    elif gate_decision == GateDecision.BLOCK:
        raise typer.Exit(1)
    else:
        if result.status == VerificationStatus.PASSED:
            exit_code = 1
        else:
            exit_code = EXIT_CODES.get(result.status, 1)
        raise typer.Exit(exit_code)


@app.command(name="diff")
def diff_command(
    old_workflow: Annotated[
        Path, typer.Argument(metavar="OLD_WORKFLOW", help="Old workflow YAML or JSON file.")
    ],
    new_workflow: Annotated[
        Path, typer.Argument(metavar="NEW_WORKFLOW", help="New workflow YAML or JSON file.")
    ],
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
) -> None:
    """Deterministically diff two workflow contracts."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)

    # 1. Load and validate old workflow
    try:
        parsed_old = load_workflow(old_workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        typer.echo(f"error WYS900: failed to load old workflow: {err}", err=True)
        raise typer.Exit(2) from err
    except Exception as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(4) from err

    res_old = validate_workflow(parsed_old)
    if not res_old.valid or res_old.workflow is None:
        for diag in res_old.diagnostics:
            typer.echo(f"error {diag.code}: old workflow: {diag.message}", err=True)
        raise typer.Exit(2)

    # 2. Load and validate new workflow
    try:
        parsed_new = load_workflow(new_workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        typer.echo(f"error WYS900: failed to load new workflow: {err}", err=True)
        raise typer.Exit(3) from err
    except Exception as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(4) from err

    res_new = validate_workflow(parsed_new)
    if not res_new.valid or res_new.workflow is None:
        for diag in res_new.diagnostics:
            typer.echo(f"error {diag.code}: new workflow: {diag.message}", err=True)
        raise typer.Exit(3)

    # 3. Diff workflows
    diff_res = diff_workflows(
        res_old.workflow,
        res_new.workflow,
        old_display=str(old_workflow),
        new_display=str(new_workflow),
    )

    # 4. Output
    if output_format == "json":
        typer.echo(diff_res.to_json())
    else:
        typer.echo(format_workflow_diff(diff_res))

    # 5. Exit codes:
    # 0 = no semantic changes
    # 1 = changes detected
    if diff_res.identical or not diff_res.changes:
        raise typer.Exit(0)
    raise typer.Exit(1)


@app.command()
def schema(
    ir_version: Annotated[int, typer.Option(..., "--ir-version", help="Workflow IR version.")],
) -> None:
    """Print the JSON Schema for a supported Workflow IR version."""

    if ir_version != CURRENT_IR_VERSION:
        typer.echo(f"error WYS901: unsupported IR version {ir_version}", err=True)
        raise typer.Exit(3)
    typer.echo(json.dumps(Workflow.model_json_schema(), indent=2, sort_keys=True))


@app.command()
def doctor() -> None:
    """Report local installation and trusted-core status."""

    typer.echo(f"Wysteria {version('wysteria')}")
    typer.echo(f"Python {sys.version.split()[0]}")
    typer.echo(f"IR versions: {CURRENT_IR_VERSION}")
    typer.echo("Trusted core: local parser, validator, and canonicalizer")
    typer.echo("External execution: disabled")


baseline_app = typer.Typer(
    name="baseline",
    help="Deterministic regression baselines for verification results.",
    no_args_is_help=True,
)
app.add_typer(baseline_app, name="baseline")


@baseline_app.command(name="create")
def baseline_create(
    workflow: Annotated[
        Path, typer.Argument(metavar="WORKFLOW", help="Workflow YAML or JSON file.")
    ],
    fixture: Annotated[Path, typer.Option("--fixture", "-f", help="Fixture YAML or JSON file.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Baseline output file path.")],
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing baseline file if it exists.")
    ] = False,
) -> None:
    """Create a regression baseline from a successful verification run."""
    try:
        parsed_wf = load_workflow(workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        typer.echo(f"error WYS900: {err}", err=True)
        raise typer.Exit(2) from err

    try:
        parsed_fix = load_fixture_document(fixture)
    except (FixtureLoadError, FixtureParseError) as err:
        typer.echo(f"error WYS700: {err}", err=True)
        raise typer.Exit(3) from err

    if output.exists() and not force:
        typer.echo(
            f"error: baseline file already exists: {output} (use --force to overwrite)",
            err=True,
        )
        raise typer.Exit(4)

    result = verify_fixture(parsed_wf, parsed_fix)
    if result.status == VerificationStatus.INVALID_WORKFLOW:
        for diag in result.diagnostics:
            typer.echo(f"error {diag.code}: {diag.message}", err=True)
        raise typer.Exit(2)
    if result.status == VerificationStatus.INVALID_FIXTURE:
        for diag in result.diagnostics:
            typer.echo(f"error {diag.code}: {diag.message}", err=True)
        raise typer.Exit(3)
    if result.status in {VerificationStatus.RUNTIME_ERROR, VerificationStatus.LIMIT_EXCEEDED}:
        typer.echo(f"error: verification runtime error ({result.status.value})", err=True)
        for diag in result.diagnostics:
            typer.echo(f"  {diag.code}: {diag.message}", err=True)
        raise typer.Exit(5)
    if not result.success or result.status != VerificationStatus.PASSED:
        typer.echo(
            f"error: cannot create baseline from failing verification ({result.status.value})",
            err=True,
        )
        for diag in result.diagnostics:
            typer.echo(f"  {diag.code}: {diag.message}", err=True)
        raise typer.Exit(1)

    try:
        create_baseline(result, output, force=force)
    except BaselineCreationError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(4) from err
    except OSError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(5) from err

    typer.echo(f"Baseline created: {output}")
    raise typer.Exit(0)


@baseline_app.command(name="check")
def baseline_check(
    workflow: Annotated[
        Path, typer.Argument(metavar="WORKFLOW", help="Workflow YAML or JSON file.")
    ],
    fixture: Annotated[Path, typer.Option("--fixture", "-f", help="Fixture YAML or JSON file.")],
    baseline: Annotated[Path, typer.Option("--baseline", "-b", help="Baseline YAML or JSON file.")],
    baseline_workflow: Annotated[
        Path | None,
        typer.Option(
            "--baseline-workflow",
            help="Old workflow YAML or JSON file for semantic diffing against current workflow.",
        ),
    ] = None,
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
    report_file: Annotated[
        Path | None,
        typer.Option("--report-file", help="Write JSON report artifact to path."),
    ] = None,
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
) -> None:
    """Compare a current verification run against an existing regression baseline."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(5)

    try:
        parsed_wf = load_workflow(workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        if github_annotations:
            typer.echo(f"::error title=WYS900::{escape_github_data(str(err))}", err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {"status": "INVALID_WORKFLOW", "matches": False, "error": str(err)},
                    indent=2,
                )
            )
        else:
            typer.echo(f"error WYS900: {err}", err=True)
        raise typer.Exit(2) from err

    try:
        parsed_fix = load_fixture_document(fixture)
    except (FixtureLoadError, FixtureParseError) as err:
        if github_annotations:
            typer.echo(f"::error title=WYS700::{escape_github_data(str(err))}", err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {"status": "INVALID_FIXTURE", "matches": False, "error": str(err)},
                    indent=2,
                )
            )
        else:
            typer.echo(f"error WYS700: {err}", err=True)
        raise typer.Exit(3) from err

    try:
        base_model = load_baseline(baseline)
    except (BaselineLoadError, BaselineParseError) as err:
        if github_annotations:
            typer.echo(f"::error title=WYS600::{escape_github_data(str(err))}", err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {"status": "INVALID_BASELINE", "matches": False, "error": str(err)},
                    indent=2,
                )
            )
        else:
            typer.echo(f"error WYS600: {err}", err=True)
        raise typer.Exit(4) from err

    result = verify_fixture(parsed_wf, parsed_fix)
    if result.status == VerificationStatus.INVALID_WORKFLOW:
        if github_annotations:
            for diag in result.diagnostics:
                typer.echo(format_diagnostic_annotation(diag), err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "status": "INVALID_WORKFLOW",
                        "matches": False,
                        "diagnostics": [d.model_dump(mode="json") for d in result.diagnostics],
                    },
                    indent=2,
                )
            )
        else:
            for diag in result.diagnostics:
                typer.echo(f"error {diag.code}: {diag.message}", err=True)
        raise typer.Exit(2)

    if result.status == VerificationStatus.INVALID_FIXTURE:
        if github_annotations:
            for diag in result.diagnostics:
                typer.echo(format_diagnostic_annotation(diag), err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "status": "INVALID_FIXTURE",
                        "matches": False,
                        "diagnostics": [d.model_dump(mode="json") for d in result.diagnostics],
                    },
                    indent=2,
                )
            )
        else:
            for diag in result.diagnostics:
                typer.echo(f"error {diag.code}: {diag.message}", err=True)
        raise typer.Exit(3)

    parsed_base_wf = None
    if baseline_workflow is not None:
        try:
            parsed_base_wf = load_workflow(baseline_workflow)
        except (WorkflowLoadError, WorkflowParseError) as err:
            if github_annotations:
                typer.echo(f"::error title=WYS900::{escape_github_data(str(err))}", err=True)
            if output_format == "json":
                typer.echo(
                    json.dumps(
                        {"status": "INVALID_WORKFLOW", "matches": False, "error": str(err)},
                        indent=2,
                    )
                )
            else:
                typer.echo(f"error WYS900: {err}", err=True)
            raise typer.Exit(2) from err

        base_wf_val = validate_workflow(parsed_base_wf)
        if not base_wf_val.valid or base_wf_val.workflow is None:
            if output_format == "json":
                typer.echo(
                    json.dumps(
                        {
                            "status": "INVALID_WORKFLOW",
                            "matches": False,
                            "diagnostics": [
                                d.model_dump(mode="json") for d in base_wf_val.diagnostics
                            ],
                        },
                        indent=2,
                    )
                )
            else:
                for diag in base_wf_val.diagnostics:
                    typer.echo(f"error {diag.code}: {diag.message}", err=True)
            raise typer.Exit(2)
        parsed_base_wf = base_wf_val.workflow

    curr_wf_val = validate_workflow(parsed_wf)
    curr_wf = curr_wf_val.workflow if curr_wf_val.valid else None

    comparison = compare_baseline(
        result,
        base_model,
        baseline_workflow=parsed_base_wf,
        current_workflow=curr_wf,
    )
    dev_report = build_developer_report(
        result,
        workflow=parsed_wf,
        fixture=parsed_fix,
        workflow_display=str(workflow),
        fixture_display=result.fixture_id or str(fixture),
        baseline_comparison=comparison,
    )

    if report_file is not None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(format_verification_json(dev_report) + "\n", encoding="utf-8")

    if github_annotations:
        for ann in format_github_annotations(dev_report):
            typer.echo(ann, err=True)

    if output_format == "json":
        typer.echo(json.dumps(comparison.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(format_baseline_report(comparison))

    if comparison.matches:
        raise typer.Exit(0)
    raise typer.Exit(1)


policy_app = typer.Typer(
    help="Evaluate deterministic policies against declarative workflows.",
    no_args_is_help=True,
)
app.add_typer(policy_app, name="policy")


@policy_app.command(name="check")
def policy_check(
    workflow: Annotated[
        Path, typer.Argument(metavar="WORKFLOW", help="Workflow YAML or JSON file.")
    ],
    policy: Annotated[Path, typer.Option("--policy", "-p", help="Policy YAML or JSON file.")],
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
    report_file: Annotated[
        Path | None,
        typer.Option("--report-file", help="Write JSON policy artifact to path."),
    ] = None,
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
) -> None:
    """Evaluate a validated workflow against an explicit policy."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)

    try:
        parsed_wf = load_workflow(workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
        if github_annotations:
            typer.echo(f"::error title=WYS900::{escape_github_data(str(err))}", err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "status": "INVALID_WORKFLOW",
                        "passed": False,
                        "blocked": False,
                        "error": str(err),
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"error WYS900: {err}", err=True)
        raise typer.Exit(2) from err
    except Exception as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(4) from err

    val_res = validate_workflow(parsed_wf, policy=CapabilityPolicy(allowed=frozenset(Capability)))
    if not val_res.valid or val_res.workflow is None:
        if github_annotations:
            for diag in val_res.diagnostics:
                typer.echo(format_diagnostic_annotation(diag), err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "status": "INVALID_WORKFLOW",
                        "passed": False,
                        "blocked": False,
                        "diagnostics": [d.model_dump(mode="json") for d in val_res.diagnostics],
                    },
                    indent=2,
                )
            )
        else:
            for diag in val_res.diagnostics:
                typer.echo(f"error {diag.code}: {diag.message}", err=True)
        raise typer.Exit(2)

    actual_wf = val_res.workflow

    try:
        loaded_policy = load_policy(policy)
    except (PolicyLoadError, PolicyParseError) as err:
        code = getattr(err, "code", "WYS450")
        if github_annotations:
            typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "status": "INVALID_POLICY",
                        "passed": False,
                        "blocked": False,
                        "error": str(err),
                    },
                    indent=2,
                )
            )
        else:
            typer.echo(f"error {code}: {err}", err=True)
        raise typer.Exit(3) from err
    except Exception as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(4) from err

    result = evaluate_policy(actual_wf, loaded_policy)

    if report_file is not None:
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(result.to_json() + "\n", encoding="utf-8")

    if github_annotations:
        for v in result.violations:
            typer.echo(f"::error title={v.code}::{escape_github_data(v.message)}", err=True)

    if output_format == "json":
        typer.echo(result.to_json())
    else:
        typer.echo(
            format_policy_report(result, workflow_display=str(workflow), policy_display=str(policy))
        )

    if result.passed:
        raise typer.Exit(0)
    raise typer.Exit(1)


@app.command()
def serve(
    host: Annotated[
        str, typer.Option("--host", "-h", help="Bind host address (localhost only).")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Server port number.")] = 8787,
) -> None:
    """Start a local deterministic verification HTTP server for frontend integration."""
    from wysteria.server import create_server

    try:
        server = create_server(host=host, port=port)
    except ValueError as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(1) from err

    typer.echo(f"Wysteria verification server running at http://{host}:{port}")
    typer.echo("Endpoints:")
    typer.echo("  GET  /api/health")
    typer.echo("  GET  /api/scenarios")
    typer.echo("  GET  /api/report?scenario=<id>")
    typer.echo("  POST /api/verify")
    typer.echo("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("\nStopping server...")
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    app()
