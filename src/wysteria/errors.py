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
