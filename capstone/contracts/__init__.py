# The base class for data models that cross the agent boundary.
# Responsibility: make every contract immutable and reject unknown fields.
"""The shared data shapes that cross the agent boundary: tool requests and results,
evidence, hypotheses, and investigation records. They hold only observable data and
the agent's beliefs, never simulator truth.
"""

from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Immutable, explicit fields; unknown data cannot silently cross boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
