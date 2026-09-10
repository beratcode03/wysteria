"""Runtime errors for deterministic workflow evaluation."""

from wysteria.errors import WysteriaError


class RuntimeEvaluationError(WysteriaError):
    """Raised when an unrecoverable deterministic evaluation error occurs."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "WYS800",
        node_id: str | None = None,
        path: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.node_id = node_id
        self.path = path
