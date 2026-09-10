"""Wysteria's CLI foundation."""

import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from wysteria.api import load_workflow, validate_workflow
from wysteria.errors import WorkflowLoadError, WorkflowParseError
from wysteria.ir.models import Workflow
from wysteria.ir.versioning import CURRENT_IR_VERSION

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


if __name__ == "__main__":
    app()
