from pydantic import BaseModel, ConfigDict


class GroundTruth(BaseModel):
    """What really happened, as declared by the scenario that did it.

    The answer key. Read by evaluation only; it must never be reachable
    through the agent-facing tools.
    """

    model_config = ConfigDict(frozen=True)

    scenario: str
    fault: str
    machine_id: str
    start_tick: int
