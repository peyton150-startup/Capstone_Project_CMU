from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from capstone.contracts import Contract

T = TypeVar("T")


class ToolRequest(Contract):
    name: str = Field(min_length=1)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ToolError(Contract):
    code: Literal["unknown_tool", "invalid_arguments", "provider_error"]
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
