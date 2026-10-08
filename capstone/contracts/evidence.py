from datetime import datetime
from typing import Literal

from pydantic import Field

from capstone.contracts import Contract


class Evidence(Contract):
    """A sourced research artifact, not a claim of hidden simulator truth."""

    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_type: Literal["telemetry", "event", "inspection", "document", "tool_result"]
    content: str
    observed_tick: int | None = Field(default=None, ge=0)
    observed_at: datetime | None = None
