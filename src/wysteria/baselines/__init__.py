"""Regression baseline support for Wysteria verification results."""

from wysteria.baselines.comparator import compare_baseline, format_baseline_report
from wysteria.baselines.models import (
    CURRENT_BASELINE_VERSION,
    SUPPORTED_BASELINE_VERSIONS,
    AssertionDiff,
    Baseline,
    BaselineComparison,
    BaselineComparisonStatus,
    BaselineResult,
    DiffKind,
    OutputDiff,
)
from wysteria.baselines.storage import (
    create_baseline,
    load_baseline,
    parse_baseline,
    serialize_baseline,
)

__all__ = [
    "CURRENT_BASELINE_VERSION",
    "SUPPORTED_BASELINE_VERSIONS",
    "AssertionDiff",
    "Baseline",
    "BaselineComparison",
    "BaselineComparisonStatus",
    "BaselineResult",
    "DiffKind",
    "OutputDiff",
    "compare_baseline",
    "create_baseline",
    "format_baseline_report",
    "load_baseline",
    "parse_baseline",
    "serialize_baseline",
]
