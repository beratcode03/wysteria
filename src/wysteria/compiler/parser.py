"""Safe YAML/JSON parsing for workflow proposals."""

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from wysteria.compiler.models import WorkflowProposal
from wysteria.errors import WorkflowLoadError
from wysteria.ir.parser import DuplicateKeyLoader, _check_size, _error


def parse_proposal(text: str, *, filename: str = "<memory>", format: str | None = None) -> WorkflowProposal:
    """Safely parse YAML or JSON text into a WorkflowProposal."""
    _check_size(text)
    selected = format or Path(filename).suffix.lstrip(".").lower()
    
    if selected in {"yaml", "yml"}:
        try:
            data = yaml.load(text, Loader=DuplicateKeyLoader)
        except (yaml.YAMLError, RecursionError) as error:
            raise _error(str(error), "WYS900") from error
    elif selected == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise _error(
                f"invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}", "WYS900"
            ) from error
        except RecursionError as error:
            raise _error("workflow nesting exceeded parser limits", "WYS911") from error
    else:
        raise _error("proposal format must be YAML (.yaml/.yml) or JSON (.json)", "WYS900")

    if not isinstance(data, dict):
        raise _error("proposal root must be a mapping", "WYS900")
        
    try:
        return WorkflowProposal.model_validate(data)
    except ValidationError as error:
        raise _error(f"invalid proposal structure: {error}", "WYS900") from error


def load_proposal(path: str | Path) -> WorkflowProposal:
    """Read and safely parse a workflow proposal file."""
    source = Path(path)
    if not source.is_file():
        raise WorkflowLoadError(f"proposal path is not a readable regular file: {source}")
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowLoadError(f"cannot read {source}: {error}") from error
    return parse_proposal(text, filename=str(source))
