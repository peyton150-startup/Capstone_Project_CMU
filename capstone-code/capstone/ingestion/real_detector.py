"""Small deterministic, quality-gated real-machine anomaly assessment.

Uses only explicitly qualified samples and a technician-approved, per-source
baseline. It does not declare a fault cause, consume the simulator reference,
or initiate controller operations.
"""

from __future__ import annotations

import statistics
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from capstone.ingestion.qualified import QualifiedNumericObservation


class CalibratedSignalBaseline(BaseModel):
    """Immutable baseline from verified fault-free operation of one signal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    calibration_id: str = Field(min_length=1)
    machine_id: str = Field(min_length=1)
    data_item_id: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    mapping_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    median: float = Field(allow_inf_nan=False)
    robust_spread: float = Field(gt=0, allow_inf_nan=False)
    score_threshold: float = Field(gt=0, allow_inf_nan=False)
    min_samples: int = Field(default=20, ge=3)
    min_span_seconds: float = Field(default=30, ge=0, allow_inf_nan=False)


class DetectorWindow(BaseModel):
    """Scored magnitude or unscorable window; neither is a root-cause claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["scored", "unscorable"]
    reason: Literal[
        "qualified",
        "not_running",
        "operating_state_unknown",
        "too_few_samples",
        "window_too_short",
        "different_signals",
        "out_of_order",
        "different_source_epoch",
    ]
    calibration_id: str
    sample_count: int = Field(ge=0)
    robust_score: float | None = Field(default=None, allow_inf_nan=False)
    threshold_exceeded: bool = False

    @model_validator(mode="after")
    def consistent_score(self) -> "DetectorWindow":
        if (self.status == "scored") != (self.robust_score is not None):
            raise ValueError("only scored windows carry numeric evidence")
        if self.status != "scored" and self.threshold_exceeded:
            raise ValueError("an unscorable window cannot trigger an anomaly")
        return self


def assess_calibrated_window(
    baseline: CalibratedSignalBaseline,
    observations: Sequence[QualifiedNumericObservation],
    *,
    operating_state: Literal["running", "not_running", "unknown"],
) -> DetectorWindow:
    """Score a chronological homogeneous window; abstain on any ambiguity."""
    count = len(observations)

    def unscorable(reason: str) -> DetectorWindow:
        return DetectorWindow(
            status="unscorable",
            reason=reason,
            calibration_id=baseline.calibration_id,
            sample_count=count,
        )

    if operating_state != "running":
        return unscorable(
            "not_running" if operating_state == "not_running" else "operating_state_unknown"
        )
    if count < baseline.min_samples:
        return unscorable("too_few_samples")
    if any(
        x.device != baseline.machine_id
        or x.data_item_id != baseline.data_item_id
        or x.units != baseline.unit
        or x.probe_sha256 != baseline.mapping_revision
        for x in observations
    ):
        return unscorable("different_signals")
    if len({(x.source, x.instance_id) for x in observations}) != 1:
        return unscorable("different_source_epoch")
    if any(
        later.timestamp <= earlier.timestamp or later.sequence <= earlier.sequence
        for earlier, later in zip(observations, observations[1:])
    ):
        return unscorable("out_of_order")
    span = (observations[-1].timestamp - observations[0].timestamp).total_seconds()
    if span < baseline.min_span_seconds:
        return unscorable("window_too_short")

    window_median = statistics.median(sample.value for sample in observations)
    score = abs(window_median - baseline.median) / baseline.robust_spread
    return DetectorWindow(
        status="scored",
        reason="qualified",
        calibration_id=baseline.calibration_id,
        sample_count=count,
        robust_score=round(score, 4),
        threshold_exceeded=score >= baseline.score_threshold,
    )
