# The models for tool requests, tool results, and tool errors.
# Responsibility: give every tool call one checked format, with its source and time.
from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from capstone.contracts import Contract

T = TypeVar("T")


class ToolRequest(Contract):
    name: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolSpec(Contract):
    """One tool as a model is shown it: what it is called, what it does, and
    the JSON schema its arguments must match."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    arguments: dict[str, JsonValue]


class ToolError(Contract):
    """What went wrong with one call, in words that are safe to show the agent.

    invalid_arguments: the request was wrong, and the message says how.
    invalid_result: the tool's answer broke its own contract. That is a bug,
    never the agent's fault, and the message never says what the answer held.
    """

    code: Literal[
        "unknown_tool", "invalid_arguments", "invalid_result", "provider_error"
    ]
    message: str


class TraceContext(Contract):
    run_id: UUID | None = None
    investigation_id: UUID | None = None

    @model_validator(mode="after")
    def consistent_context(self):
        if self.investigation_id is not None and self.run_id is None:
            raise ValueError("investigation context requires a run_id")
        return self


class ToolResult(TraceContext, Generic[T]):
    """Common result envelope; timestamp and tick come from the source clock."""

    success: bool
    tool: str
    source: str
    tick: int = Field(ge=0)
    timestamp: datetime
    data: T | None = None
    error: ToolError | None = None

    @model_validator(mode="after")
    def consistent_outcome(self):
        if self.success == (self.error is not None):
            raise ValueError("success and error must describe one consistent outcome")
        if not self.success and self.data is not None:
            raise ValueError("failed tools cannot return data")
        return self
