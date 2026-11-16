"""Evidence requirements for the opt-in deterministic triage controller.

Requirements describe observations to collect. Results describe what the
observations actually establish. Neither is a diagnosis.
"""

from typing import Literal

from pydantic import Field, model_validator

from capstone.contracts import Contract

RequirementStatus = Literal[
    "pending",
    "satisfied",
    "partial",
    "insufficient",
    "stale",
    "unavailable",
    "unsupported",
    "failed",
]


class ReadRequirement(Contract):
    """One independently checked part of a fixed-plan question."""

    requirement_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    machine_id: str | None = None
    sensor: str | None = None
    job_id: int | None = Field(default=None, ge=1)
    from_tick: int | None = Field(default=None, ge=0)
    to_tick: int | None = Field(default=None, ge=0)
    min_samples: int = Field(default=0, ge=0)
    min_span_ticks: int = Field(default=0, ge=0)
    required: bool = True
    # A snapshot can be read, but cannot prove a historical setting change.
    qualification: Literal[
        "measurement",
        "movement",
        "record",
        "setting_change",
        "inspection_batch",
        "inspection_machine",
        "inspection_recent",
        "inspection_jobs",
        "job_path",
    ] = "record"

    @model_validator(mode="after")
    def valid_window(self):
        """Reject half-specified or reversed measurement windows."""
        if (self.from_tick is None) != (self.to_tick is None):
            raise ValueError("both window endpoints are required together")
        if self.from_tick is not None and self.from_tick > self.to_tick:
            raise ValueError("measurement window is reversed")
        if self.sensor is not None and self.tool != "get_sensor_summary":
            raise ValueError("sensor requirements use get_sensor_summary")
        if self.job_id is not None and self.tool != "get_job_history":
            raise ValueError("job ids belong to job-history requirements")
        return self


class RequirementResult(Contract):
    """Evidence-backed status of a requirement, separate from its definition."""

    status: RequirementStatus = "pending"
    evidence_ids: tuple[str, ...] = ()
    valid_samples: int = Field(default=0, ge=0)
    reason: str = "not checked"


class TriageDecisionRecord(Contract):
    """One deterministic choice and its observed result for the experiment log."""

    phase: Literal["investigate", "test"]
    iteration: int = Field(ge=0)
    kind: Literal["read", "stop"]
    reason: str
    tool: str | None = None
    arguments: dict = Field(default_factory=dict)
    requirement_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    outcome: str | None = None
