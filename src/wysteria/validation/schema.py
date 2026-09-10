"""Structural/schema validation for untrusted workflow documents."""

from pydantic import ValidationError

from wysteria.ir.models import Workflow
from wysteria.ir.parser import ParsedWorkflow
from wysteria.reporting.diagnostics import Diagnostic
from wysteria.validation.common import diagnostic


def _pointer(location: tuple[object, ...]) -> str:
    return "".join(f"/{part}" for part in location)


def validate_structure(parsed: ParsedWorkflow) -> tuple[Workflow | None, list[Diagnostic]]:
    """Validate the document against strict Pydantic IR models."""

    try:
        return Workflow.model_validate(parsed.data), []
    except ValidationError as error:
        diagnostics: list[Diagnostic] = []
        for item in error.errors(include_url=False):
            path = _pointer(item["loc"])
            kind = item["type"]
            code = "WYS100"
            hint = None
            if kind == "extra_forbidden":
                code = "WYS101"
                hint = "Remove the unsupported field."
            elif kind == "missing":
                code = "WYS102"
                hint = "Provide the required field."
            elif kind == "union_tag_invalid":
                code = "WYS103"
                hint = "Use one of the documented deterministic node kinds."
            diagnostics.append(diagnostic(code, item["msg"], path, parsed=parsed, hint=hint))
        return None, diagnostics
