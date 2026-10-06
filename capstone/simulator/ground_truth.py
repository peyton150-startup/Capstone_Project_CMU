from pydantic import BaseModel, ConfigDict


class GroundTruth(BaseModel):
    """What really happened, as declared by the scenario that did it.

    The answer key. Read by evaluation only; it must never be reachable
    through the agent-facing tools.
    """

    model_config = ConfigDict(frozen=True)

    scenario: str
    fault: str
    # A fault names what it is about: a machine or a material batch.
    machine_id: str | None = None
    batch_id: int | None = None
    # None when the fault is not tied to a tick chosen in advance.
    start_tick: int | None = None
