"""Domain exceptions raised for operational failures."""


class WysteriaError(Exception):
    """Base exception for Wysteria."""


class WorkflowParseError(WysteriaError):
    """Raised when a workflow document cannot be parsed."""

    def __init__(self, message: str, *, code: str = "WYS900") -> None:
        super().__init__(message)
        self.code = code


class WorkflowLoadError(WysteriaError):
    """Raised when a workflow document cannot be read."""


class FixtureParseError(WysteriaError):
    """Raised when a fixture document cannot be parsed or fails structural validation."""

    def __init__(self, message: str, *, code: str = "WYS700") -> None:
        super().__init__(message)
        self.code = code


class FixtureLoadError(WysteriaError):
    """Raised when a fixture document cannot be read."""


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
