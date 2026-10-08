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
