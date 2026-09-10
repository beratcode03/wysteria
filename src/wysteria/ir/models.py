"""Strict, deliberately small Workflow IR models."""

import math
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from wysteria.ir.versioning import CURRENT_IR_VERSION


class StrictModel(BaseModel):
    """Base model that rejects undeclared fields and coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


def _json_value(value: Any) -> Any:
    """Accept only finite JSON-compatible values, including in direct API use."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("numbers must be finite")
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("object keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    raise ValueError("value must be JSON-compatible")


def _enum_value(enum_type: type[StrEnum]):
    def parse(value: Any) -> StrEnum:
        if isinstance(value, enum_type):
            return value
        if type(value) is str:
            try:
                return enum_type(value)
            except ValueError as error:
                raise ValueError(f"unsupported value {value!r}") from error
        raise ValueError("value must be a string")

    return parse


class ValueType(StrEnum):
    ANY = "any"
    NULL = "null"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    ARRAY = "array"
    OBJECT = "object"


ValueTypeField = Annotated[ValueType, BeforeValidator(_enum_value(ValueType))]


class Metadata(StrictModel):
    description: str | None = None
    labels: list[str] = Field(default_factory=list)


class InputSpec(StrictModel):
    type: ValueTypeField
    required: bool = True


class Reference(StrictModel):
    """A reference to a declared input or node output."""

    input: str | None = None
    node: str | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> "Reference":
        if (self.input is None) == (self.node is None):
            raise ValueError("reference must specify exactly one of 'input' or 'node'")
        return self


class ConstantConfig(StrictModel):
    value: Any

    _validate_value = field_validator("value")(_json_value)


class SelectConfig(StrictModel):
    path: str = ""


class ConstructConfig(StrictModel):
    template: dict[str, Any] | list[Any]

    _validate_template = field_validator("template")(_json_value)


class TransformOperation(StrEnum):
    IDENTITY = "identity"
    LOWERCASE = "lowercase"
    UPPERCASE = "uppercase"
    TRIM = "trim"
    TO_STRING = "to_string"
    TO_INTEGER = "to_integer"


TransformOperationField = Annotated[
    TransformOperation, BeforeValidator(_enum_value(TransformOperation))
]


class TransformConfig(StrictModel):
    operation: TransformOperationField


class AssertPredicate(StrEnum):
    EXISTS = "exists"
    EQUALS = "equals"
    TYPE_IS = "type_is"


AssertPredicateField = Annotated[AssertPredicate, BeforeValidator(_enum_value(AssertPredicate))]


class AssertConfig(StrictModel):
    predicate: AssertPredicateField
    expected: Any | None = None

    _validate_expected = field_validator("expected")(_json_value)


class EmptyConfig(StrictModel):
    pass


class NodeBase(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    inputs: dict[str, Reference] = Field(default_factory=dict)
    output_type: ValueTypeField


class ConstantNode(NodeBase):
    kind: Literal["constant"]
    config: ConstantConfig


class SelectNode(NodeBase):
    kind: Literal["select"]
    config: SelectConfig


class ConstructNode(NodeBase):
    kind: Literal["construct"]
    config: ConstructConfig


class TransformNode(NodeBase):
    kind: Literal["transform"]
    config: TransformConfig


class AssertNode(NodeBase):
    kind: Literal["assert"]
    config: AssertConfig


class OutputNode(NodeBase):
    kind: Literal["output"]
    config: EmptyConfig


Node = Annotated[
    ConstantNode | SelectNode | ConstructNode | TransformNode | AssertNode | OutputNode,
    Field(discriminator="kind"),
]


class Edge(StrictModel):
    source: Reference
    target_node: str = Field(min_length=1)
    target_input: str = Field(min_length=1)


class Assertion(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    source: Reference
    predicate: AssertPredicateField
    expected: Any | None = None

    _validate_expected = field_validator("expected")(_json_value)


class OutputSpec(StrictModel):
    source: Reference
    type: ValueTypeField


class Capability(StrEnum):
    """Reserved capabilities; no v0.1 node requires one."""

    FILE_READ = "file.read"
    NETWORK_HTTP = "network.http"
    PROCESS_EXECUTE = "process.execute"


CapabilityField = Annotated[Capability, BeforeValidator(_enum_value(Capability))]


MAX_NODES = 500
MAX_EDGES = 1000
MAX_INPUTS = 100
MAX_OUTPUTS = 100
MAX_ASSERTIONS = 200
MAX_CAPABILITIES = 50


class Workflow(StrictModel):
    """The stable v1 workflow contract."""

    ir_version: Literal[CURRENT_IR_VERSION]
    name: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    metadata: Metadata = Field(default_factory=Metadata)
    inputs: dict[str, InputSpec] = Field(default_factory=dict, max_length=MAX_INPUTS)
    nodes: list[Node] = Field(min_length=1, max_length=MAX_NODES)
    edges: list[Edge] = Field(default_factory=list, max_length=MAX_EDGES)
    capabilities: list[CapabilityField] = Field(default_factory=list, max_length=MAX_CAPABILITIES)
    assertions: list[Assertion] = Field(default_factory=list, max_length=MAX_ASSERTIONS)
    outputs: dict[str, OutputSpec] = Field(min_length=1, max_length=MAX_OUTPUTS)
