# Run the calibrated real-machine detector over a recorded capture.
# Responsibility: qualify, window and score approved signals; never name a cause.
"""Deterministic screening of a recorded MTConnect capture (PR B wiring).

`qualify_numeric` and `assess_calibrated_window` (#310) were tested building
blocks with no caller. This module is the caller: for each technician-approved
baseline it qualifies the capture's samples of that one signal, keeps the
current source epoch inside an optional window before the cutoff, reads the
machine's Execution state over that window, and asks the detector for a score.
A scored window over its threshold becomes an `IncidentTrigger`: evidence that
one signal moved away from its fault-free baseline, never a fault cause.

No model is called here and nothing is sent anywhere; the caller decides what
a trigger starts (`capstone.recorded_investigation --baseline`).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from capstone.ingestion.channel_map import ChannelMap
from capstone.ingestion.qualified import (
    QualifiedNumericObservation,
    RejectReason,
    qualify_numeric,
)
from capstone.ingestion.real_detector import (
    CalibratedSignalBaseline,
    DetectorWindow,
    assess_calibrated_window,
)
from capstone.ingestion.record import Line, TelemetryRecord

# MTConnect Execution values that mean the machine is cutting. The replay's
# status tool uses the same set; READY and every stop state are not running.
RUNNING_STATES = frozenset({"ACTIVE"})

OperatingState = Literal["running", "not_running", "unknown"]


class IncidentTrigger(BaseModel):
    """One signal far from its calibrated baseline: a reason to look, not a cause."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    machine_id: str
    data_item_id: str
    unit: str
    calibration_id: str
    robust_score: float = Field(allow_inf_nan=False)
    score_threshold: float = Field(gt=0, allow_inf_nan=False)
    sample_count: int = Field(ge=1)
    window_start: AwareDatetime
    window_end: AwareDatetime
    source: str
    instance_id: str
    first_sequence: int = Field(ge=1)
    last_sequence: int = Field(ge=1)

    def description(self) -> str:
        """The operator-style observation an investigation starts from."""
        return (
            f"Calibrated detector flagged {self.data_item_id} on {self.machine_id}: "
            f"robust score {self.robust_score:g} (threshold {self.score_threshold:g}) "
            f"over {self.sample_count} samples between "
            f"{self.window_start.isoformat()} and {self.window_end.isoformat()}. "
            "Investigate whether this reflects a machine problem; the score is "
            "not a diagnosis."
        )


class SignalScreen(BaseModel):
    """What the detector said about one baseline's signal, with safe counts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    calibration_id: str
    machine_id: str
    data_item_id: str
    operating_state: OperatingState
    window: DetectorWindow
    rejected: dict[RejectReason, int]
    duplicates_dropped: int = Field(ge=0)
    older_epoch_dropped: int = Field(ge=0)


class ScreenReport(BaseModel):
    """Every baseline's verdict at one cutoff, and the strongest trigger if any."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cutoff: AwareDatetime
    window_seconds: float | None
    screens: tuple[SignalScreen, ...]
    trigger: IncidentTrigger | None = None


def load_baselines(
    path: Path, channel_map: ChannelMap
) -> tuple[CalibratedSignalBaseline, ...]:
    """Read approved baselines and refuse any made for a different probe."""
    # Variables:
    #   raw: The file's JSON list; one object per approved signal baseline.
    #   baselines: Each object validated as a CalibratedSignalBaseline.
    #   seen: (machine, data item) pairs, so one signal cannot have two baselines.
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("the baseline file must hold a nonempty JSON list")
    baselines = tuple(CalibratedSignalBaseline.model_validate(item) for item in raw)
    seen: set[tuple[str, str]] = set()
    for baseline in baselines:
        if baseline.mapping_revision != channel_map.probe_sha256:
            raise ValueError(
                f"baseline {baseline.calibration_id} was made for a different probe"
            )
        signal = (baseline.machine_id, baseline.data_item_id)
        if signal in seen:
            raise ValueError(f"two baselines for {signal[1]} on {signal[0]}")
        seen.add(signal)
    return baselines


def _operating_state(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    machine_id: str,
    *,
    start: datetime,
    end: datetime,
) -> OperatingState:
    """Whether the machine was running for the whole window, by its Execution."""
    # Variables:
    #   in_effect: The machine's Execution value at the window's start (the
    #     last one at or before it); None means the state was not known then.
    #   during: Execution values that arrived inside the window.
    #   states: Every state the machine was in over the window; one unknown or
    #     unavailable value makes the whole window unknown.
    in_effect: tuple[datetime, str | None] | None = None
    during: list[str | None] = []
    for line in lines:
        if not isinstance(line, TelemetryRecord) or line.type.upper() != "EXECUTION":
            continue
        entry = channel_map.entry_for(line)
        if entry is None or entry.device != machine_id:
            continue
        value = line.value if line.available else None
        if line.source_timestamp <= start:
            if in_effect is None or line.source_timestamp >= in_effect[0]:
                in_effect = (line.source_timestamp, value)
        elif line.source_timestamp <= end:
            during.append(value)
    if in_effect is None:
        return "unknown"
    states = [in_effect[1], *during]
    if any(state is None for state in states):
        return "unknown"
    return (
        "running" if all(state in RUNNING_STATES for state in states) else "not_running"
    )


def screen_signal(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    baseline: CalibratedSignalBaseline,
    *,
    authorized_item_ids: frozenset[str],
    cutoff: datetime,
    window_seconds: float | None = None,
) -> tuple[SignalScreen, list[QualifiedNumericObservation]]:
    """Qualify, window and score one approved signal at the cutoff."""
    # Variables:
    #   rejected: Why each refused sample was refused, counted by reason only,
    #     so no reading or address reaches a log or report.
    #   seen: (source, instance, sequence) already kept; a restart's /current
    #     repeats unchanged values, and the repeat is the same observation.
    #   accepted: Qualified samples of this signal at or before the cutoff.
    #   epoch: The (source, instance) of the newest sample; the detector scores
    #     one epoch only, so older epochs are dropped and counted.
    #   window: The epoch's samples in sequence order, inside window_seconds
    #     before the cutoff when that is given.
    #   operating_state: The machine's Execution state over the window.
    #   duplicates, older: How many repeats and older-epoch samples were left
    #     out, reported so a short window can be explained.
    rejected: Counter[RejectReason] = Counter()
    seen: set[tuple[str, str | None, int]] = set()
    duplicates = 0
    accepted: list[QualifiedNumericObservation] = []
    for line in lines:
        if not isinstance(line, TelemetryRecord):
            continue
        if line.data_item_id != baseline.data_item_id or line.source_timestamp > cutoff:
            continue
        entry = channel_map.entry_for(line)
        if entry is None or entry.device != baseline.machine_id:
            continue
        key = (line.source, line.instance_id, line.sequence)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        verdict = qualify_numeric(
            line, channel_map, authorized_item_ids=authorized_item_ids
        )
        if verdict.sample is None:
            rejected[verdict.reason] += 1
            continue
        accepted.append(verdict.sample)

    older = 0
    window: list[QualifiedNumericObservation] = []
    if accepted:
        newest = max(accepted, key=lambda sample: sample.timestamp)
        epoch = (newest.source, newest.instance_id)
        current = [s for s in accepted if (s.source, s.instance_id) == epoch]
        older = len(accepted) - len(current)
        current.sort(key=lambda sample: sample.sequence)
        if window_seconds is not None:
            start = cutoff - timedelta(seconds=window_seconds)
            current = [s for s in current if s.timestamp >= start]
        window = current

    if window:
        operating_state = _operating_state(
            lines,
            channel_map,
            baseline.machine_id,
            start=window[0].timestamp,
            end=window[-1].timestamp,
        )
    else:
        operating_state = "unknown"
    # An empty window has no samples to score; the detector reports that as
    # too few samples once the machine state is known, so pass it through.
    verdict_window = assess_calibrated_window(
        baseline,
        window,
        operating_state="running" if not window else operating_state,
    )
    return (
        SignalScreen(
            calibration_id=baseline.calibration_id,
            machine_id=baseline.machine_id,
            data_item_id=baseline.data_item_id,
            operating_state=operating_state,
            window=verdict_window,
            rejected=dict(rejected),
            duplicates_dropped=duplicates,
            older_epoch_dropped=older,
        ),
        window,
    )


def screen_capture(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    baselines: Sequence[CalibratedSignalBaseline],
    *,
    authorized_item_ids: frozenset[str],
    cutoff: datetime,
    window_seconds: float | None = None,
) -> ScreenReport:
    """Screen every approved signal at the cutoff; return the strongest trigger."""
    # Variables:
    #   baselines: The technician-approved signals; only these are scored.
    #   authorized_item_ids: Data items a person approved for analysis; a
    #     baseline for any other item is refused rather than silently skipped.
    #   screens: One verdict per baseline, kept whether or not it triggered.
    #   candidates: Scored windows over threshold, with their samples, so the
    #     trigger can cite the exact first and last sequence numbers.
    if cutoff.utcoffset() is None:
        raise ValueError("the screening cutoff needs a UTC offset")
    if window_seconds is not None and window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    unapproved = {b.data_item_id for b in baselines} - authorized_item_ids
    if unapproved:
        raise ValueError("a baseline names a data item that is not authorized")
    screens: list[SignalScreen] = []
    candidates: list[tuple[SignalScreen, CalibratedSignalBaseline, list]] = []
    for baseline in baselines:
        screen, window = screen_signal(
            lines,
            channel_map,
            baseline,
            authorized_item_ids=authorized_item_ids,
            cutoff=cutoff,
            window_seconds=window_seconds,
        )
        screens.append(screen)
        if screen.window.threshold_exceeded:
            candidates.append((screen, baseline, window))
    trigger = None
    if candidates:
        screen, baseline, window = max(
            candidates, key=lambda item: item[0].window.robust_score or 0.0
        )
        trigger = IncidentTrigger(
            machine_id=baseline.machine_id,
            data_item_id=baseline.data_item_id,
            unit=baseline.unit,
            calibration_id=baseline.calibration_id,
            robust_score=screen.window.robust_score,
            score_threshold=baseline.score_threshold,
            sample_count=screen.window.sample_count,
            window_start=window[0].timestamp,
            window_end=window[-1].timestamp,
            source=window[0].source,
            instance_id=window[0].instance_id,
            first_sequence=window[0].sequence,
            last_sequence=window[-1].sequence,
        )
    return ScreenReport(
        cutoff=cutoff,
        window_seconds=window_seconds,
        screens=tuple(screens),
        trigger=trigger,
    )
