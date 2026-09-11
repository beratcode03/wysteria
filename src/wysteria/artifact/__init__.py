"""Versioned CI Artifacts for reliable CI consumption and gating."""

from wysteria.artifact.builder import build_ci_artifact
from wysteria.artifact.models import (
    CURRENT_ARTIFACT_VERSION,
    SUPPORTED_ARTIFACT_VERSIONS,
    CIArtifact,
    VerificationArtifact,
)
from wysteria.artifact.storage import (
    load_ci_artifact,
    parse_ci_artifact,
    save_ci_artifact,
    serialize_ci_artifact,
    validate_ci_artifact,
)

__all__ = [
    "CURRENT_ARTIFACT_VERSION",
    "SUPPORTED_ARTIFACT_VERSIONS",
    "CIArtifact",
    "VerificationArtifact",
    "build_ci_artifact",
    "load_ci_artifact",
    "parse_ci_artifact",
    "save_ci_artifact",
    "serialize_ci_artifact",
    "validate_ci_artifact",
]
