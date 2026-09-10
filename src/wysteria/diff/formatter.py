"""Deterministic compiler/git-style formatter for WorkflowDiff."""

from __future__ import annotations

import json
from typing import Any

from wysteria.diff.models import ChangeCategory, WorkflowDiff


def _format_diff_val(val: Any) -> str:
    """Format scalar or structure for diff lines without extra quotes on strings."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, (dict, list)):
        return json.dumps(val, separators=(",", ":"), sort_keys=True)
    return str(val)


def _entity_line(change) -> str:
    """Format the change header line, e.g. '~ node normalize_name'."""
    prefix = "~"
    if change.category in {
        ChangeCategory.NODE_ADDED,
        ChangeCategory.EDGE_ADDED,
    } or change.change_type in {
        "input_added",
        "output_added",
        "assertion_added",
        "capability_added",
    }:
        prefix = "+"
    elif change.category in {
        ChangeCategory.NODE_REMOVED,
        ChangeCategory.EDGE_REMOVED,
    } or change.change_type in {
        "input_removed",
        "output_removed",
        "assertion_removed",
        "capability_removed",
    }:
        prefix = "-"

    entity_type = "node"
    target = change.target_id or change.node_id or change.edge_id or ""
    if change.category in {
        ChangeCategory.EDGE_ADDED,
        ChangeCategory.EDGE_REMOVED,
        ChangeCategory.EDGE_CHANGED,
    }:
        entity_type = "edge"
        target = change.edge_id or target
    elif change.category == ChangeCategory.INPUT_CHANGED:
        entity_type = "input"
    elif change.category == ChangeCategory.OUTPUT_CHANGED:
        entity_type = "output"
    elif change.category == ChangeCategory.ASSERTION_CHANGED:
        entity_type = "assertion"
    elif change.category == ChangeCategory.CAPABILITY_CHANGED:
        entity_type = "capability"
    elif change.category == ChangeCategory.METADATA_CHANGED:
        entity_type = "metadata"

    return f"  {prefix} {entity_type} {target}".rstrip()


def format_workflow_diff(diff: WorkflowDiff) -> str:
    """Format WorkflowDiff as a deterministic compiler/git-style diagnostic report."""
    old_name = diff.old_workflow or (diff.old_fingerprint[:8] if diff.old_fingerprint else "old")
    new_name = diff.new_workflow or (diff.new_fingerprint[:8] if diff.new_fingerprint else "new")

    lines: list[str] = [
        "WORKFLOW DIFF",
        "",
        f"  {old_name}",
        f"  → {new_name}",
    ]

    if diff.identical or not diff.changes:
        lines.append("")
        lines.append("No semantic changes.")
        return "\n".join(lines)

    lines.append("")
    lines.append("CHANGES")

    for change in diff.changes:
        lines.append("")
        lines.append(_entity_line(change))

        # Field diff if both before and after exist
        if change.before is not None and change.after is not None:
            field_name = change.path.split("/")[-1] if "/" in change.path else change.path
            lines.append(f"      {field_name}")
            lines.append(f"      - {_format_diff_val(change.before)}")
            lines.append(f"      + {_format_diff_val(change.after)}")

        lines.append(f"      {change.severity.value}")

    lines.append("")
    lines.append("SUMMARY")
    lines.append("")
    lines.append(f"  {diff.summary.breaking_count} breaking")
    if diff.summary.warning_count > 0:
        lines.append(f"  {diff.summary.warning_count} warning")
    lines.append(f"  {diff.summary.info_count} informational")

    return "\n".join(lines)
