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


import typer.core

from wysteria.api import (
    CURRENT_ARTIFACT_VERSION,
    GateDecision,
    build_ci_artifact,
    build_developer_report,
    collect_evidence,
    compare_baseline,
    compile_proposal,
    create_baseline,
    diff_workflows,
    evaluate_policy,
    format_baseline_report,
    format_developer_report,
    format_explanation_human,
    format_github_annotations,
    format_policy_report,
    format_workflow_diff,
    load_baseline,
    load_ci_artifact,
    load_fixture_document,
    load_policy,
    load_proposal,
    load_workflow,
    save_ci_artifact,
    validate_workflow,
    verify_fixture,
)
from wysteria.errors import (
    ArtifactLoadError,
    ArtifactParseError,
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
from wysteria.ir.normalize import normalize_workflow
from wysteria.ir.parser import ParsedWorkflow
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


def version_callback(value: bool):
    if value:
        import wysteria

        typer.echo(wysteria.__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the Wysteria version and exit.",
        ),
    ] = False,
) -> None:
    pass


def _print_error(action: str, err: Exception, filepath: str | None = None) -> None:
    code = getattr(err, "code", "WYS999")
    typer.echo(f"error {code}: {err}", err=True)

    typer.echo(
        "┌─ Error Details ─────────────────────────────────────────────────────────────┐", err=True
    )
    typer.echo(f"│ Action:  {action}", err=True)
    if filepath:
        typer.echo(f"│ File:    {filepath}", err=True)

    hint = getattr(err, "hint", None)
    if hint:
        typer.echo(f"│ Inspect: {hint}", err=True)
    else:
        typer.echo("│ Inspect: Check file syntax or refer to Wysteria documentation.", err=True)

    typer.echo(
        "└─────────────────────────────────────────────────────────────────────────────┘", err=True
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
def init(
    directory: Annotated[
        Path, typer.Argument(help="Target directory to initialize the workspace in.")
    ],
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing generated Wysteria files.")
    ] = False,
) -> None:
    """Scaffold a complete, valid Wysteria workspace with integrated CI."""
    from wysteria.cli.templates import (
        FIXTURE_YAML,
        GITHUB_WORKFLOW_YAML,
        POLICY_YAML,
        WORKFLOW_YAML,
    )

    typer.echo(f"Initializing Wysteria workspace in {directory}...")

    # Create directories
    directory.mkdir(parents=True, exist_ok=True)
    github_dir = directory / ".github" / "workflows"
    github_dir.mkdir(parents=True, exist_ok=True)

    workflow_file = directory / "workflow.yaml"
    fixture_file = directory / "fixture.yaml"
    policy_file = directory / "policy.yaml"
    ci_file = github_dir / "wysteria.yml"

    files_to_create = [
        (workflow_file, WORKFLOW_YAML),
        (fixture_file, FIXTURE_YAML),
        (policy_file, POLICY_YAML),
        (ci_file, GITHUB_WORKFLOW_YAML),
    ]

    # Safety check
    if not force:
        existing = [f[0] for f in files_to_create if f[0].exists()]
        if existing:
            typer.echo("error: Target directory already contains Wysteria files:", err=True)
            for file_path in existing:
                typer.echo(f"  - {file_path}", err=True)
            typer.echo("Use --force to overwrite them.", err=True)
            raise typer.Exit(1)

    # Write files
    for file_path, content in files_to_create:
        file_path.write_text(content, encoding="utf-8")

    typer.echo("\nCreated:")
    typer.echo("  workflow.yaml")
    typer.echo("  fixture.yaml")
    typer.echo("  policy.yaml")
    typer.echo("  .github/workflows/wysteria.yml")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {directory}")
    typer.echo("  wysteria verify workflow.yaml --fixture fixture.yaml --policy policy.yaml")


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
            _print_error(f"Validating workflow {workflow}", error, filepath=str(workflow))
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


@app.command(name="check")
def check_command(
    proposal: Annotated[
        Path, typer.Argument(metavar="PROPOSAL", help="Untrusted AI Proposal YAML or JSON file.")
    ],
    fixture: Annotated[
        Path | None, typer.Option("--fixture", "-f", help="Fixture for verification.")
    ] = None,
    policy: Annotated[
        Path | None, typer.Option("--policy", "-p", help="Optional policy YAML or JSON file.")
    ] = None,
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
    evidence: Annotated[
        bool,
        typer.Option("--evidence", help="Use committed evidence snapshots without network access."),
    ] = False,
    update_snapshots: Annotated[
        bool,
        typer.Option(
            "--update-snapshots", help="Refresh evidence snapshots from explicit claim URLs."
        ),
    ] = False,
    evidence_dir: Annotated[
        Path | None,
        typer.Option(
            "--evidence-dir", help="Evidence snapshot directory (default: .wysteria/evidence)."
        ),
    ] = None,
) -> None:
    """Safely ingest and evaluate an untrusted AI-generated workflow proposal."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)
    if update_snapshots and not evidence:
        typer.echo("error WYS900: --update-snapshots requires --evidence", err=True)
        raise typer.Exit(4)

    try:
        parsed_prop = load_proposal(proposal)
    except (WorkflowLoadError, WorkflowParseError) as err:
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "success": False,
                        "diagnostics": [
                            {"code": "WYS900", "severity": "error", "message": str(err)}
                        ],
                    }
                ),
                err=True,
            )
        else:
            _print_error("Loading proposal during check", err)
        raise typer.Exit(2) from err

    policy_obj = None
    if policy:
        try:
            policy_obj = load_policy(policy)
        except Exception as err:
            _print_error("Loading policy during check", err)
            raise typer.Exit(3) from err

    cap_policy = None
    if policy_obj:
        allowed = set(Capability)
        if policy_obj.forbidden_capabilities:
            for c in policy_obj.forbidden_capabilities:
                if c in allowed:
                    allowed.remove(c)
        cap_policy = CapabilityPolicy(allowed=frozenset(allowed))

    result = compile_proposal(parsed_prop, filename=str(proposal), policy=cap_policy)

    if not result.success or result.workflow is None:
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "success": False,
                        "diagnostics": [d.model_dump(mode="json") for d in result.diagnostics],
                    }
                )
            )
        else:
            for d in result.diagnostics:
                typer.echo(f"error {d.code}: {d.message}", err=True)
        raise typer.Exit(2)  # WYS400+ or WYS100+ is validation/structure failure

    compiled_wf_json = normalize_workflow(result.workflow)
    parsed_wf = ParsedWorkflow(data=compiled_wf_json, filename=str(proposal), locations={})

    evidence_results = None
    if evidence:
        try:
            evidence_results, _ = collect_evidence(
                parsed_prop.claims,
                base_dir=proposal.parent,
                update_snapshots=update_snapshots,
                snapshot_dir=evidence_dir,
                policy=policy_obj,
            )
        except OSError as err:
            _print_error("Managing evidence snapshots during check", err)
            raise typer.Exit(5) from err

    if fixture is None:
        # Without a fixture, just policy check & validate
        policy_res = None
        if policy_obj:
            policy_res = evaluate_policy(result.workflow, policy_obj)

        dev_report = build_developer_report(
            VerificationResult(
                status=VerificationStatus.PASSED,
                success=True,
                fixture_id="<none>",
                diagnostics=[],
            ),
            workflow=parsed_wf,
            workflow_display=str(proposal),
            policy_result=policy_res,
            evidence_results=evidence_results,
        )
        if output_format == "json":
            typer.echo(format_verification_json(dev_report))
        else:
            typer.echo(format_verification_report(dev_report))

        if dev_report.provenance.gate_decision != GateDecision.PASS:
            raise typer.Exit(1)
        if evidence_results and any(item.status.value != "verified" for item in evidence_results):
            raise typer.Exit(1)
        raise typer.Exit(0)

    # With a fixture, run deterministic verification
    parsed_fix = None
    try:
        parsed_fix = load_fixture_document(fixture)
    except Exception as err:
        _print_error("Loading fixture during check", err)
        raise typer.Exit(3) from err

    verify_result = verify_fixture(parsed_wf, parsed_fix, policy=cap_policy)

    policy_res = None
    if policy_obj:
        policy_res = evaluate_policy(result.workflow, policy_obj)

    dev_report = build_developer_report(
        verify_result,
        workflow=parsed_wf,
        fixture=parsed_fix,
        workflow_display=str(proposal),
        fixture_display=str(fixture),
        policy_result=policy_res,
        evidence_results=evidence_results,
    )

    if github_annotations:
        for ann in format_github_annotations(dev_report):
            typer.echo(ann, err=True)

    if output_format == "json":
        typer.echo(format_verification_json(dev_report))
    else:
        typer.echo(format_verification_report(dev_report))

    exit_code = EXIT_CODES.get(verify_result.status, 4)
    if exit_code == 0 and dev_report.provenance.gate_decision != GateDecision.PASS:
        exit_code = 1
    if (
        exit_code == 0
        and evidence_results
        and any(item.status.value != "verified" for item in evidence_results)
    ):
        exit_code = 1
    raise typer.Exit(exit_code)


@app.command(name="compile")
def compile_command(
    proposal: Annotated[
        Path, typer.Argument(metavar="PROPOSAL", help="Proposal YAML or JSON file.")
    ],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write compiled Workflow IR to path.")
    ] = None,
    verify: Annotated[
        bool, typer.Option("--verify", help="Verify the compiled proposal immediately.")
    ] = False,
    fixture: Annotated[
        Path | None, typer.Option("--fixture", "-f", help="Fixture for verification.")
    ] = None,
    policy: Annotated[
        Path | None, typer.Option("--policy", "-p", help="Optional policy YAML or JSON file.")
    ] = None,
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
) -> None:
    """Deterministically compile a WorkflowProposal into a trusted typed Workflow IR."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)

    if verify and fixture is None:
        typer.echo("error WYS900: --verify requires --fixture", err=True)
        raise typer.Exit(4)

    try:
        parsed_prop = load_proposal(proposal)
    except (WorkflowLoadError, WorkflowParseError) as err:
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "success": False,
                        "diagnostics": [
                            {"code": "WYS900", "severity": "error", "message": str(err)}
                        ],
                    }
                ),
                err=True,
            )
        else:
            _print_error("Executing compile", err)
        raise typer.Exit(2) from err

    policy_obj = None
    if policy:
        try:
            policy_obj = load_policy(policy)
        except Exception as err:
            _print_error("Loading policy during compile", err)
            raise typer.Exit(3) from err

    cap_policy = None
    if policy_obj:
        allowed = set(Capability)
        if policy_obj.forbidden_capabilities:
            for c in policy_obj.forbidden_capabilities:
                if c in allowed:
                    allowed.remove(c)
        cap_policy = CapabilityPolicy(allowed=frozenset(allowed))

    result = compile_proposal(parsed_prop, filename=str(proposal), policy=cap_policy)

    if not result.success or result.workflow is None:
        if output_format == "json":
            typer.echo(
                json.dumps(
                    {
                        "success": False,
                        "diagnostics": [d.model_dump(mode="json") for d in result.diagnostics],
                    }
                )
            )
        else:
            for d in result.diagnostics:
                typer.echo(f"error {d.code}: {d.message}", err=True)
        raise typer.Exit(1)

    compiled_wf_json = normalize_workflow(result.workflow)

    if output:
        output.write_text(
            json.dumps(compiled_wf_json, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if output_format == "human" and not verify:
            typer.echo(f"PASS compiled to {output}")

    if output_format == "json" and not verify:
        typer.echo(json.dumps(compiled_wf_json, indent=2, sort_keys=True))

    if verify:
        parsed_wf = ParsedWorkflow(data=compiled_wf_json, filename=str(proposal), locations={})
        parsed_fix = None
        try:
            parsed_fix = load_fixture_document(fixture)
        except Exception as err:
            _print_error("Loading fixture during compile", err)
            raise typer.Exit(3) from err

        verify_result = verify_fixture(parsed_wf, parsed_fix, policy=cap_policy)
        dev_report = build_developer_report(
            verify_result,
            workflow=parsed_wf,
            fixture=parsed_fix,
            workflow_display=str(proposal),
            fixture_display=str(fixture),
            policy_result=evaluate_policy(result.workflow, policy_obj) if policy_obj else None,
        )

        if output_format == "json":
            typer.echo(format_verification_json(dev_report))
        else:
            typer.echo(format_verification_report(dev_report))

        exit_code = EXIT_CODES.get(verify_result.status, 4)
        if exit_code == 0 and dev_report.provenance.gate_decision != GateDecision.PASS:
            exit_code = 1
        raise typer.Exit(exit_code)

    raise typer.Exit(0)


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

    policy_obj = None
    cap_policy = None
    if policy is not None:
        try:
            policy_obj = load_policy(policy)
        except (PolicyLoadError, PolicyParseError) as err:
            code = getattr(err, "code", "WYS450")
            _print_error("Loading policy during verify", err)
            raise typer.Exit(3) from err

        allowed = set(Capability)
        if policy_obj.forbidden_capabilities:
            for c in policy_obj.forbidden_capabilities:
                if c in allowed:
                    allowed.remove(c)
        cap_policy = CapabilityPolicy(allowed=frozenset(allowed))

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
        result = verify_fixture(parsed_wf, parsed_fix, policy=cap_policy)

    policy_res = None
    if (
        policy_obj is not None
        and result.status != VerificationStatus.INVALID_WORKFLOW
        and parsed_wf is not None
    ):
        val_wf = validate_workflow(parsed_wf, policy=cap_policy)
        if val_wf.valid and val_wf.workflow is not None:
            policy_res = evaluate_policy(val_wf.workflow, policy_obj)

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
            _print_error("Loading policy during explain", err)
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
            _print_error("Loading baseline during explain", err)
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
                _print_error("Loading workflow during explain", err)
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
            _print_error("Executing explain", err)
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
        _print_error("Loading workflow during diff", err)
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
        _print_error("Loading workflow during diff", err)
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
def doctor(
    release: Annotated[
        bool,
        typer.Option("--release", "-r", help="Run strict release readiness checks."),
    ] = False,
) -> None:
    """Report local installation, trusted-core status, and release readiness."""

    typer.echo(f"Wysteria {version('wysteria')}")
    typer.echo(f"Python {sys.version.split()[0]}")
    typer.echo(f"IR versions: {CURRENT_IR_VERSION}")
    typer.echo(f"Artifact versions: {CURRENT_ARTIFACT_VERSION}")
    typer.echo("Trusted core: local parser, validator, and canonicalizer")
    typer.echo("External execution: disabled")

    from wysteria.release import check_release_readiness

    readiness = check_release_readiness()
    typer.echo("")
    typer.echo(readiness.summary())

    if release and not readiness.all_passed:
        raise typer.Exit(1)


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
        _print_error("Loading workflow during baseline create", err)
        raise typer.Exit(2) from err

    try:
        parsed_fix = load_fixture_document(fixture)
    except (FixtureLoadError, FixtureParseError) as err:
        _print_error("Loading fixture during baseline create", err)
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
        _print_error("Executing baseline create", err)
        raise typer.Exit(4) from err
    except OSError as err:
        _print_error("Executing baseline create", err)
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
            _print_error("Executing baseline check", err)
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
            _print_error("Executing baseline check", err)
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
            _print_error("Executing baseline check", err)
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
                _print_error("Executing baseline check", err)
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
            _print_error("Executing policy check", err)
        raise typer.Exit(2) from err
    except Exception as err:
        _print_error("Executing policy check", err)
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
            _print_error("Executing policy check", err)
        raise typer.Exit(3) from err
    except Exception as err:
        _print_error("Executing policy check", err)
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
        _print_error("Executing serve", err)
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


class ArtifactGroup(typer.core.TyperGroup):
    """Custom Typer group that defaults to 'generate' command when no subcommand is specified."""

    default_cmd_name = "generate"

    def parse_args(self, ctx, args):
        if not args:
            return super().parse_args(ctx, args)
        cmd_name = args[0]
        if (
            cmd_name not in self.commands
            and not cmd_name.startswith("-")
            and cmd_name not in {"--help", "-h"}
        ):
            args = [self.default_cmd_name] + args
        return super().parse_args(ctx, args)


artifact_app = typer.Typer(
    cls=ArtifactGroup,
    help="Versioned CI artifacts representing complete verification decisions.",
    no_args_is_help=True,
)
app.add_typer(artifact_app, name="artifact")


@artifact_app.command(name="generate")
def artifact_generate(
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
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write canonical CI artifact JSON to path."),
    ] = None,
    report_file: Annotated[
        Path | None,
        typer.Option("--report-file", help="Write canonical CI artifact JSON to path."),
    ] = None,
    github_annotations: Annotated[
        bool,
        typer.Option(
            "--github-annotations",
            help="Emit GitHub Actions workflow commands (::error, ::warning).",
        ),
    ] = False,
) -> None:
    """Generate a canonical, versioned CI artifact representing the verification decision."""
    target_output = output or report_file

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

    policy_obj = None
    cap_policy = None
    if policy is not None:
        try:
            policy_obj = load_policy(policy)
        except (PolicyLoadError, PolicyParseError) as err:
            code = getattr(err, "code", "WYS450")
            if github_annotations:
                typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
            _print_error("Loading policy during artifact generate", err)
            raise typer.Exit(3) from err

        allowed = set(Capability)
        if policy_obj.forbidden_capabilities:
            for c in policy_obj.forbidden_capabilities:
                if c in allowed:
                    allowed.remove(c)
        cap_policy = CapabilityPolicy(allowed=frozenset(allowed))

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
        result = verify_fixture(parsed_wf, parsed_fix, policy=cap_policy)

    policy_res = None
    if (
        policy_obj is not None
        and result.status != VerificationStatus.INVALID_WORKFLOW
        and parsed_wf is not None
    ):
        val_wf = validate_workflow(parsed_wf, policy=cap_policy)
        if val_wf.valid and val_wf.workflow is not None:
            policy_res = evaluate_policy(val_wf.workflow, policy_obj)

    comparison = None
    diff_res = None
    if baseline is not None and parsed_wf is not None and parsed_fix is not None:
        try:
            loaded_baseline = load_baseline(baseline)
        except (BaselineLoadError, BaselineParseError) as err:
            code = getattr(err, "code", "WYS600")
            if github_annotations:
                typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
            _print_error("Loading baseline during artifact generate", err)
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
                _print_error("Loading workflow during artifact generate", err)
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
                    old_display=str(baseline_workflow).replace("\\", "/"),
                    new_display=str(workflow).replace("\\", "/"),
                )
        except (WorkflowLoadError, WorkflowParseError) as err:
            code = getattr(err, "code", "WYS900")
            if github_annotations:
                typer.echo(f"::error title={code}::{escape_github_data(str(err))}", err=True)
            _print_error("Executing artifact generate", err)
            raise typer.Exit(2) from err

    try:
        workflow_display = (
            workflow.resolve().relative_to(Path.cwd()).as_posix()
            if workflow.resolve().is_relative_to(Path.cwd())
            else str(workflow).replace("\\", "/")
        )
    except Exception:
        workflow_display = str(workflow).replace("\\", "/")

    try:
        fixture_display = (
            result.fixture_id
            if result.fixture_id and result.fixture_id != "<unknown>"
            else (
                fixture.resolve().relative_to(Path.cwd()).as_posix()
                if fixture.resolve().is_relative_to(Path.cwd())
                else str(fixture).replace("\\", "/")
            )
        )
    except Exception:
        fixture_display = (
            result.fixture_id
            if result.fixture_id and result.fixture_id != "<unknown>"
            else str(fixture).replace("\\", "/")
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

    artifact = build_ci_artifact(dev_report)

    if target_output is not None:
        save_ci_artifact(artifact, target_output)

    if github_annotations:
        for ann in format_github_annotations(dev_report):
            typer.echo(ann, err=True)

    if output_format == "json":
        typer.echo(artifact.to_json())
    else:
        if target_output is not None:
            typer.echo(
                f"CI Artifact created: {target_output} (decision: {artifact.gate_decision.value})"
            )
        else:
            typer.echo(format_developer_report(dev_report))

    gate_decision = artifact.gate_decision
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


@artifact_app.command(name="validate")
def artifact_validate(
    artifact: Annotated[
        Path, typer.Argument(metavar="ARTIFACT", help="Path to CI artifact JSON file.")
    ],
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
) -> None:
    """Validate an existing CI artifact against the canonical specification."""
    if output_format not in {"human", "json"}:
        typer.echo("error WYS900: --format must be 'human' or 'json'", err=True)
        raise typer.Exit(4)

    if not artifact.is_file():
        msg = f"artifact file not found: {artifact}"
        if output_format == "json":
            typer.echo(json.dumps({"valid": False, "code": "WYS950", "error": msg}, indent=2))
        else:
            _print_error("Executing artifact validate", ArtifactLoadError(msg))
        raise typer.Exit(1)

    try:
        loaded = load_ci_artifact(artifact)
    except ArtifactParseError as err:
        if output_format == "json":
            typer.echo(json.dumps({"valid": False, "code": err.code, "error": str(err)}, indent=2))
        else:
            typer.echo(f"error {err.code}: {err}", err=True)
        raise typer.Exit(1) from err
    except Exception as err:
        if output_format == "json":
            typer.echo(json.dumps({"valid": False, "code": "WYS950", "error": str(err)}, indent=2))
        else:
            _print_error("Executing artifact validate", err)
        raise typer.Exit(1) from err

    if output_format == "json":
        typer.echo(
            json.dumps(
                {
                    "valid": True,
                    "artifact_version": loaded.artifact_version,
                    "gate_decision": loaded.gate_decision.value,
                    "workflow_fingerprint": loaded.workflow_fingerprint,
                },
                indent=2,
            )
        )
    else:
        typer.echo(
            f"PASS {artifact} is a valid CI Artifact v{loaded.artifact_version} (decision: {loaded.gate_decision.value})"
        )
    raise typer.Exit(0)


@app.command()
def demo(
    output_format: Annotated[str, typer.Option("--format", help="human or json")] = "human",
) -> None:
    """Run the repository's deterministic verification showcase."""
    examples_dir = Path("examples") / "showcase"
    workflow_path = examples_dir / "workflow.yaml"
    malicious_path = examples_dir / "malicious.yaml"
    fixture_path = examples_dir / "fixture.yaml"
    policy_path = examples_dir / "policy.yaml"

    if (
        not workflow_path.exists()
        or not malicious_path.exists()
        or not fixture_path.exists()
        or not policy_path.exists()
    ):
        typer.echo(
            "Error: Showcase files not found. Are you running this from the repository root?",
            err=True,
        )
        raise typer.Exit(1)

    try:

        def _run_case(wf_path: Path):
            parsed_workflow = load_workflow(wf_path)
            fixture = load_fixture_document(fixture_path)
            policy = load_policy(policy_path)

            cap_policy = CapabilityPolicy(allowed=frozenset(Capability))

            val_result = validate_workflow(parsed_workflow, policy=cap_policy)

            verify_res = verify_fixture(parsed_workflow, fixture, policy=cap_policy)

            policy_res = None
            if val_result.valid and val_result.workflow:
                policy_res = evaluate_policy(val_result.workflow, policy)

            dev_report = build_developer_report(
                verify_res,
                workflow=parsed_workflow,
                fixture=fixture,
                workflow_display=str(wf_path).replace("\\", "/"),
                fixture_display=str(fixture_path).replace("\\", "/"),
                policy_result=policy_res,
            )
            return dev_report

        report_safe = _run_case(workflow_path)
        report_malicious = _run_case(malicious_path)

        if output_format == "json":
            typer.echo(
                json.dumps(
                    [
                        json.loads(report_safe.provenance.to_json()),
                        json.loads(report_malicious.provenance.to_json()),
                    ],
                    indent=2,
                )
            )
            raise typer.Exit(0)

        typer.echo("Wysteria Verification Showcase\n")

        typer.echo("Scenario 1: Validating Safe Proposal...")
        typer.echo(
            "AI proposes a Customer Data Enrichment pipeline (requires network.http and file.read)."
        )
        typer.echo(format_explanation_human(report_safe.provenance))

        typer.echo("\nScenario 2: Validating Malicious Proposal...")
        typer.echo(
            "AI proposes a malicious update with unauthorized capabilities (process.execute)."
        )
        typer.echo(format_explanation_human(report_malicious.provenance))

        raise typer.Exit(0)

    except typer.Exit:
        raise
    except Exception as err:
        typer.echo(f"Demo failed: {err}", err=True)
        raise typer.Exit(1) from err


if __name__ == "__main__":
    app()
