"""Strict, deliberately small Fixture IR models."""

from typing import Any, Literal

from pydantic import Field, field_validator

from wysteria.ir.models import (
    MAX_ASSERTIONS,
    MAX_INPUTS,
    MAX_NODES,
    MAX_OUTPUTS,
    StrictModel,
    _json_value,
)

CURRENT_FIXTURE_VERSION = 1
SUPPORTED_FIXTURE_VERSIONS = frozenset({CURRENT_FIXTURE_VERSION})


class ExpectedError(StrictModel):
    """Specification of an expected runtime error code."""

    code: str


class FixtureExpected(StrictModel):
    """Expected outcome of a fixture run."""

    outputs: dict[str, Any] | None = Field(default=None, max_length=MAX_OUTPUTS)
    assertions: dict[str, bool] | None = Field(default=None, max_length=MAX_ASSERTIONS)
    error: str | ExpectedError | None = None
    complete_outputs: bool = False

    @property
    def expected_error_code(self) -> str | None:
        if self.error is None:
            return None
        if isinstance(self.error, ExpectedError):
            return self.error.code
        return self.error

    @field_validator("outputs")
    @classmethod
    def _validate_outputs(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return {k: _json_value(v) for k, v in value.items()}


class Fixture(StrictModel):
    """The stable v1 fixture contract."""

    fixture_version: Literal[CURRENT_FIXTURE_VERSION]
    id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    name: str | None = None
    description: str | None = None
    inputs: dict[str, Any] = Field(max_length=MAX_INPUTS)
    expected: FixtureExpected = Field(default_factory=FixtureExpected)
    mocks: dict[str, Any] | None = Field(default=None, max_length=MAX_NODES)

    @field_validator("inputs")
    @classmethod
    def _validate_inputs(cls, value: dict[str, Any]) -> dict[str, Any]:
        return {k: _json_value(v) for k, v in value.items()}

    @field_validator("expected", mode="before")
    @classmethod
    def _normalize_expected(cls, value: Any) -> Any:
        if value is None:
            return {}
        return value

    @field_validator("mocks")
    @classmethod
    def _validate_mocks(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return {k: _json_value(v) for k, v in value.items()}
