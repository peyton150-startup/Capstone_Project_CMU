# The models for what the observation and action tools return.
# Responsibility: allow only observable fields in tool output, never hidden truth.
"""Models for the existing tools' observable fields only."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from capstone.contracts import Contract


class ClockObservation(Contract):
    tick: int = Field(ge=0)
    time: datetime


class MachineObservation(Contract):
    machine_id: str
    status: Literal["running", "idle", "down"]
    job_id: int | None


class SensorObservation(Contract):
    tick: int = Field(ge=0)
    machine_id: str | None = None
    sensor: str
    value: float
    unit: str


class SensorSummaryObservation(Contract):
    """Statistics derived only from observable samples; rate uses units per tick."""

    machine_id: str | None
    sensor: str
    from_tick: int = Field(ge=0)
    to_tick: int = Field(ge=0)
    sample_count: int = Field(ge=0)
    unit: str | None
    first_tick: int | None = Field(ge=0)
    last_tick: int | None = Field(ge=0)
    start_value: float | None = Field(allow_inf_nan=False)
    end_value: float | None = Field(allow_inf_nan=False)
    minimum: float | None = Field(allow_inf_nan=False)
    maximum: float | None = Field(allow_inf_nan=False)
    mean: float | None = Field(allow_inf_nan=False)
    delta: float | None = Field(allow_inf_nan=False)
    rate_of_change: float | None = Field(allow_inf_nan=False)


class SettingObservation(Contract):
    machine_id: str
    speed_rpm: float


class EventObservation(Contract):
    tick: int = Field(ge=0)
    machine_id: str | None
    kind: str
    message: str
    job_id: int | None


class InspectionObservation(Contract):
    tick: int = Field(ge=0)
    job_id: int
    batch_id: int | None
    result: Literal["passed", "failed"]


class ProposalObservation(Contract):
    id: int = Field(ge=1)
    machine_id: str
    action: str
    reason: str
    proposed_tick: int = Field(ge=0)
    status: Literal["pending", "approved", "rejected"]
    decided_tick: int | None
    note: str
