# The Hypothesis model: one explanation the agent is considering.
# Responsibility: hold the agent's belief, kept apart from the simulator's truth.
from typing import Literal

from pydantic import Field, model_validator

from capstone.contracts import Contract


class NumericClaim(Contract):
    """A measurement assertion that can be checked without judging its cause."""

    evidence_id: str
    machine_id: str | None = None
    sensor: str
    metric: Literal["minimum", "maximum", "mean", "delta", "sample_count"]
    value: float = Field(allow_inf_nan=False)
    unit: str | None = None
    from_tick: int | None = Field(default=None, ge=0)
    to_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def ordered_window(self):
        """Refuse a reversed claimed interval without inspecting simulator state."""
        if self.from_tick is not None and self.to_tick is not None:
            if self.from_tick > self.to_tick:
                raise ValueError("numeric claim window must be ordered")
        return self


class Hypothesis(Contract):
    """The agent's explicit belief and evidence references; not ground truth."""

    id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    expected_observations: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unexplained_evidence_ids: tuple[str, ...] = ()
    discriminating_check: str | None = None
    numeric_claims: tuple[NumericClaim, ...] = ()
