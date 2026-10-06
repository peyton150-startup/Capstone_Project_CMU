from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


NORMAL_LOAD = 0.5


class MachineStatus(StrEnum):
    RUNNING = "running"
    IDLE = "idle"
    DOWN = "down"


class MachineCondition(BaseModel):
    """Hidden physical truth. Never crosses the tool boundary."""

    model_config = ConfigDict(validate_assignment=True)

    bearing_health: float = Field(default=1.0, ge=0.0, le=1.0)


class MachineState(BaseModel):
    """Reality for one machine: observable facts plus hidden condition.

    Written only by scenarios, actions, and step logic. Sensors read it
    and produce evidence; they never write to it.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(min_length=1)
    status: MachineStatus = MachineStatus.RUNNING
    # How hard the machine is working, 0 to 1. An operating fact, not a fault.
    load: float = Field(default=NORMAL_LOAD, ge=0.0, le=1.0)
    condition: MachineCondition = Field(default_factory=MachineCondition)


class FactoryState(BaseModel):
    """Reality for the whole factory, as of now.

    Plain data: holds what is true, not how it changes and not what was
    observed. Sensors and the reading log live outside it.
    """

    machines: dict[str, MachineState] = Field(default_factory=dict)

    def add(self, machine: MachineState) -> None:
        if machine.id in self.machines:
            raise ValueError(f"machine {machine.id} already exists")
        self.machines[machine.id] = machine
