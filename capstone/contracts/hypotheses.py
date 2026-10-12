# The Hypothesis model: one explanation the agent is considering.
# Responsibility: hold the agent's belief, kept apart from the simulator's truth.
from pydantic import Field

from capstone.contracts import Contract


class Hypothesis(Contract):
    """The agent's explicit belief and evidence references; not ground truth."""

    id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
