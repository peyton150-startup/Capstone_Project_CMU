# The models for what the observation and action tools return.
# Responsibility: allow only observable fields in tool output, never hidden truth.
"""Models for the existing tools' observable fields only."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from capstone.contracts import Contract


class ClockObservation(Contract):
    tick: int = Field(ge=0)
    time: datetime


class MachineObservation(Contract):
    machine_id: str
    status: Literal["running", "idle", "down"]
    job_id: int | None
    hydraulics: bool  # equipment: whether the machine has a hydraulic system


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


# Why a sensor, or a whole machine, has no score. feed_unavailable is set only
# by the hazard provider, while a machine's sensor feed is down.
ScreeningReason = Literal[
    "not_running_yet", "too_few_running_readings", "no_reference", "feed_unavailable"
]
Score = Annotated[float, Field(allow_inf_nan=False)]
# One sensor: [robust_score, plain_score], temperature adding its warm-up
# stage, or why there is no score.
SensorScreen = (
    tuple[Score, Score]
    | tuple[Score, Score, Literal["start", "warming", "steady"]]
    | ScreeningReason
)


class LineScreeningObservation(Contract):
    """Every machine's recent running readings against a saved healthy line.

    Numbers and coverage only: no "abnormal" label and no cause. Scores are
    in units of the healthy spread; how far is too far is for the reader.
    A machine maps to its sensors, or to one reason when none has a score.
    """

    reference: str
    machines: dict[str, dict[str, SensorScreen] | ScreeningReason]


class SensorTrendObservation(Contract):
    """One block of a sensor's readings: arithmetic on observable samples only."""

    from_tick: int = Field(ge=0)
    to_tick: int = Field(ge=0)
    mean: float = Field(allow_inf_nan=False)
    min: float = Field(allow_inf_nan=False)
    max: float = Field(allow_inf_nan=False)
    count: int = Field(ge=1)


class SettingObservation(Contract):
    machine_id: str
    speed_rpm: float


class EventObservation(Contract):
    tick: int = Field(ge=0)
    machine_id: str | None
    kind: str
    message: str
    job_id: int | None


class MaintenanceObservation(Contract):
    machine_id: str
    performed_at: str  # ISO date and time
    tick: int | None = Field(ge=0)  # None: before the run began
    kind: str
    note: str


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
    executed_tick: int | None
    finish_tick: int | None


class ExecutionObservation(Contract):
    """What was started when an approved proposal was carried out."""

    proposal_id: int = Field(ge=1)
    machine_id: str
    action: str
    started_tick: int = Field(ge=0)
    finish_tick: int = Field(ge=0)
