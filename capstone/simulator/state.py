from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


NORMAL_LOAD = 0.5
REFERENCE_AMBIENT_F = 72.0


class MachineStatus(StrEnum):
    RUNNING = "running"
    IDLE = "idle"
    DOWN = "down"


class Job(BaseModel):
    """One piece of work. Keeps the same id on every machine it visits."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(ge=1)
    # How demanding the work is, 0 to 1; becomes the load of whichever machine holds it.
    load: float = Field(ge=0.0, le=1.0)


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
    # How warm the machine really is, in °F. Changes gradually; see thermal.py.
    temperature: float = REFERENCE_AMBIENT_F + 43.0
    # How long this machine's operation takes on any job: its normal cycle time.
    ticks_per_job: int = Field(default=60, ge=1)
    # The job on this machine now, and how many ticks of it are done here.
    job: Job | None = None
    job_progress: int = Field(default=0, ge=0)
    condition: MachineCondition = Field(default_factory=MachineCondition)


class FactoryState(BaseModel):
    """Reality for the whole factory, as of now.

    Plain data: holds what is true, not how it changes and not what was
    observed. Sensors and the reading log live outside it.
    """

    machines: dict[str, MachineState] = Field(default_factory=dict)
    # The machines in the order a job visits them. Empty until a line is set up.
    line: list[str] = Field(default_factory=list)
    # Ids of jobs that have left the end of the line, oldest first.
    completed_jobs: list[int] = Field(default_factory=list)
    # The building's own temperature for the time of day, in °F.
    ambient_temperature: float = REFERENCE_AMBIENT_F
    door_open: bool = False
    # How many °F the loading door is currently taking off the air.
    door_cooling: float = Field(default=0.0, ge=0.0)

    @property
    def air_temperature(self) -> float:
        """What the machines actually sit in: one value, read by all."""
        return self.ambient_temperature - self.door_cooling

    def add(self, machine: MachineState) -> None:
        if machine.id in self.machines:
            raise ValueError(f"machine {machine.id} already exists")
        self.machines[machine.id] = machine
