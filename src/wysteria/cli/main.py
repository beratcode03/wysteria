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
    build_developer_report,
    compare_baseline,
    create_baseline,
    format_baseline_report,
    load_baseline,
    load_fixture_document,
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
    WorkflowLoadError,
    WorkflowParseError,
)
from wysteria.ir.models import Workflow
from wysteria.ir.versioning import CURRENT_IR_VERSION
from wysteria.reporting.diagnostics import Diagnostic, Severity
from wysteria.reporting.verification import (
    EXIT_CODES,
    format_verification_json,
    format_verification_report,
)
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
) -> None:
    """Validate a workflow contract without executing it."""

    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(3)
    try:
        result = validate_workflow(load_workflow(workflow))
    except (WorkflowLoadError, WorkflowParseError) as error:
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
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
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
    )

    if output_format == "json":
        typer.echo(format_verification_json(dev_report))
    else:
        typer.echo(format_verification_report(dev_report))

    exit_code = EXIT_CODES.get(result.status, 4)
    raise typer.Exit(exit_code)


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
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
) -> None:
    """Compare a current verification run against an existing regression baseline."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(5)

    try:
        parsed_wf = load_workflow(workflow)
    except (WorkflowLoadError, WorkflowParseError) as err:
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

    comparison = compare_baseline(result, base_model)

    if output_format == "json":
        typer.echo(json.dumps(comparison.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(format_baseline_report(comparison))

    if comparison.matches:
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
