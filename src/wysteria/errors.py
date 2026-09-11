"""Domain exceptions raised for operational failures."""


class WysteriaError(Exception):
    """Base exception for Wysteria."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS999",
        file_path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.file_path = file_path
        self.hint = hint


class WorkflowParseError(WysteriaError):
    """Raised when a workflow document cannot be parsed."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS900",
        file_path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, code=code, file_path=file_path, hint=hint)


class WorkflowLoadError(WysteriaError):
    """Raised when a workflow document cannot be read."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS900",
        file_path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, code=code, file_path=file_path, hint=hint)


class FixtureParseError(WysteriaError):
    """Raised when a fixture document cannot be parsed or fails structural validation."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS700",
        file_path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, code=code, file_path=file_path, hint=hint)


class FixtureLoadError(WysteriaError):
    """Raised when a fixture document cannot be read."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS700",
        file_path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, code=code, file_path=file_path, hint=hint)


class BaselineError(WysteriaError):
    """Base exception for baseline operations."""


class BaselineParseError(BaselineError):
    """Raised when a baseline document cannot be parsed or fails structural validation."""

    def __init__(self, message: str, *, code: str = "WYS600") -> None:
        super().__init__(message)
        self.code = code


class BaselineLoadError(BaselineError):
    """Raised when a baseline document cannot be read."""


class BaselineCreationError(BaselineError):
    """Raised when a baseline cannot be created."""


class PolicyError(WysteriaError):
    """Base exception for policy operations."""


class PolicyParseError(PolicyError):
    """Raised when a policy document cannot be parsed or fails structural validation."""

    def __init__(self, message: str, *, code: str = "WYS450") -> None:
        super().__init__(message)
        self.code = code


class PolicyLoadError(PolicyError):
    """Raised when a policy document cannot be read."""


class ArtifactError(WysteriaError):
    """Base exception for CI artifact operations."""


class ArtifactParseError(ArtifactError):
    """Raised when an artifact document cannot be parsed or fails structural validation."""

    def __init__(self, message: str, *, code: str = "WYS950") -> None:
        super().__init__(message)
        self.code = code


class ArtifactLoadError(ArtifactError):
    """Raised when an artifact document cannot be read."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS950",
        file_path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message, code=code, file_path=file_path, hint=hint)


class ArtifactCreationError(ArtifactError):
    """Raised when a CI artifact cannot be created."""
