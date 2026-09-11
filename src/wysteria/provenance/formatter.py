"""Deterministic formatters for Workflow Provenance and Explanations."""

from __future__ import annotations

from wysteria.provenance.models import Explanation, Provenance


def format_explanation_human(provenance: Provenance | Explanation) -> str:
    """Format an explanation or provenance into a concise, engineering-oriented terminal report."""
    lines: list[str] = []

    if isinstance(provenance, Provenance):
        decision = provenance.gate_decision
        reasons = provenance.reasons
        fingerprint = provenance.workflow_fingerprint
    elif isinstance(provenance, Explanation):
        decision = provenance.decision
        reasons = provenance.reasons
        fingerprint = provenance.fingerprint
    else:
        decision = getattr(provenance, "gate_decision", getattr(provenance, "decision", "UNKNOWN"))
        reasons = getattr(provenance, "reasons", [])
        fingerprint = getattr(
            provenance, "workflow_fingerprint", getattr(provenance, "fingerprint", None)
        )

    dec_str = decision.value if hasattr(decision, "value") else str(decision)
    lines.append(f"DECISION: {dec_str}")
    lines.append("")
    lines.append("Reasons:")

    if not reasons:
        lines.append("  PASS: passing verification")
    else:
        for i, item in enumerate(reasons):
            sev_str = item.severity.value if hasattr(item.severity, "value") else str(item.severity)
            if item.code:
                header = f"  {sev_str} {item.code}: {item.message}"
            else:
                header = f"  {sev_str}: {item.message}"
            lines.append(header)

            detail_lines: list[str] = []
            if item.node_id:
                detail_lines.append(f"    node: {item.node_id}")

            if item.target:
                is_output = item.category == "output" or (
                    bool(item.path) and "/output" in item.path
                )
                is_assertion = item.category == "assertion" or (
                    bool(item.path) and "/assertion" in item.path
                )
                if is_output:
                    detail_lines.append(f"    output: {item.target}")
                elif is_assertion:
                    detail_lines.append(f"    assertion: {item.target}")
                elif not item.node_id:
                    detail_lines.append(f"    target: {item.target}")
            elif item.path and not item.node_id:
                detail_lines.append(f"    path: {item.path}")

            lines.extend(detail_lines)

            if i < len(reasons) - 1:
                lines.append("")

    if fingerprint:
        lines.append("")
        lines.append("Fingerprint:")
        lines.append(f"  {fingerprint}")

    return "\n".join(lines)


def format_provenance_json(provenance: Provenance | Explanation, *, indent: int = 2) -> str:
    """Format provenance or explanation into deterministic canonical JSON."""
    return provenance.to_json(indent=indent)
