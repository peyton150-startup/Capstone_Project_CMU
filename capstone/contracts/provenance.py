# The ProvenanceReference model: where one piece of evidence came from.
# Responsibility: one shared label, written by trusted code and never by a model.
"""The origin of a piece of evidence, recorded when it was observed.

The reasoning loop writes one of these beside every evidence item, at
the moment the tool answer arrives. The memory gate reads them to refuse
anything that did not come from what an agent is allowed to see.
"""

from typing import Literal

from pydantic import Field

from capstone.contracts import Contract

# The source name of answers recalled from memory. The loop labels them by it.
MEMORY_SOURCE = "memory"


class ProvenanceReference(Contract):
    """The trusted artifact producer labels source origin, not the model."""

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_type: Literal["telemetry", "event", "inspection", "document", "tool_result"]
    # "memory": recalled from an earlier investigation; a past belief, not a look now.
    origin: Literal[
        "observable", "human", "memory", "evaluator_hidden", "simulator_hidden"
    ]
    observed_tick: int | None = Field(default=None, ge=0)
