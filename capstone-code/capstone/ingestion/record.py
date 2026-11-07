# One normalized telemetry observation, the unit every later layer reads.
# Responsibility: define the stored record shape; no I/O and no interpretation.
"""The versioned lines the collector writes and the monitor reads.

A telemetry file holds two kinds of line, told apart by `record_type`:
`observation` (a TelemetryRecord) and `collector` (a CollectorMarker saying
the collector started, is alive, stopped on purpose, or lost data). Lines
written before markers existed have no `record_type` and are read as
observations.

A `gap` marker sits where data was lost (SM-2 in docs/MVP_SCOPE.md): no
reading in the file may be joined across it, because the values in between
were never received. `gap_free_runs` splits a file at those places.
"""

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["SAMPLE", "EVENT", "CONDITION"]


class TelemetryRecord(BaseModel):
    """One observation from a real machine, as the MTConnect agent reported it.

    A missing reading stays missing: `available` is False and `value` is None.
    It is never replaced by zero or by a simulator assumption.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   record_type: Always "observation"; tells this line apart from a marker.
    #   schema_version: Bumped if the stored shape changes, so old files stay readable.
    #   source: The agent's base URL, so records from two agents never mix silently.
    #   instance_id: The agent's run id; it changes when the agent restarts and its
    #     sequence numbers start again.
    #   device: The machine name from the DeviceStream.
    #   component: The part of the machine the item belongs to (Controller, Rotary...).
    #   data_item_id: The agent's id for the channel; the stable key for one signal.
    #   category: SAMPLE (a number), EVENT (a state or word) or CONDITION (health).
    #   type: The observation's kind, e.g. RotaryVelocity, Execution, or for a
    #     condition its data item type, e.g. SYSTEM.
    #   value: The reported value as text; for a condition, its level (NORMAL,
    #     WARNING, FAULT). None when the agent said UNAVAILABLE.
    #   available: False when the agent reported the channel as unavailable.
    #   message: A condition's text, e.g. the alarm description; else None.
    #   native_code: A condition's controller alarm number, when given.
    #   sequence: The agent's sequence number; orders records and finds gaps.
    #   source_timestamp: When the agent says the value was observed.
    #   received_at: When this collector received it (UTC), to measure lag.
    record_type: Literal["observation"] = "observation"
    schema_version: Literal[1] = 1
    source: str
    instance_id: str | None
    device: str
    component: str
    data_item_id: str
    name: str | None = None
    category: Category
    type: str
    sub_type: str | None = None
    value: str | None
    available: bool
    message: str | None = None
    native_code: str | None = None
    sequence: int
    source_timestamp: datetime
    received_at: datetime

    def number(self) -> float | None:
        """The value as a float, or None if it is missing or not numeric."""
        # Variables:
        #   value: The stored text; event words like "ACTIVE" give None, never 0.
        if self.value is None:
            return None
        try:
            return float(self.value)
        except ValueError:
            return None


GapCause = Literal["buffer_overrun", "out_of_range", "agent_restart"]


class GapDetail(BaseModel):
    """Where and why data was lost, as far as the collector can know it.

    Nothing here is guessed: a bound the collector cannot know is None.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   cause: buffer_overrun (the agent had already overwritten what we asked
    #     for), out_of_range (it refused the request for that reason) or
    #     agent_restart (its instanceId changed, so its sequence numbers
    #     started again).
    #   lost_from_sequence, lost_to_sequence: The sequence numbers lost,
    #     inclusive. Both are known for a buffer overrun; only the start for
    #     out_of_range; neither for a restart, whose old numbers mean nothing
    #     in the new run.
    #   last_received_at: When the last observation before the gap was
    #     received; None if none had been written yet in this run. With the
    #     marker's `at` it bounds the gap in time.
    #   instance_id_before, instance_id_after: The agent runs either side of a
    #     restart; None for the other causes.
    cause: GapCause
    lost_from_sequence: int | None = Field(default=None, ge=0)
    lost_to_sequence: int | None = Field(default=None, ge=0)
    last_received_at: datetime | None = None
    instance_id_before: str | None = None
    instance_id_after: str | None = None


class CollectorMarker(BaseModel):
    """A line saying the collector started, is alive, or stopped on purpose.

    A gap is written where observations were lost (`gap` says how and how
    much). A heartbeat is written when polls succeed but nothing new has been written
    for a while (a quiet machine), so silence in the file means the collector
    or its connection is down, not that the machine is idle. A clean stop (Ctrl+C or the poll limit) writes `stopped`. A crash, a
    killed process or a power cut writes nothing, so a `started` line that is
    not preceded by `stopped` means the previous run did not end cleanly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   record_type: Always "collector"; tells this line apart from an observation.
    #   source: The agent the collector was reading, matching its records' source.
    #   schema_version: 2 since the gap event (SM-2); version 1 lines, which
    #     have no gap, still read.
    #   event: "started" when collection begins, "heartbeat" when it is alive
    #     but has had nothing new to write, "stopped" when it ends on purpose,
    #     "gap" when observations were lost just before this line.
    #   at: The collector's clock (UTC) when the event happened; for a gap,
    #     when the loss was noticed.
    #   reason: Why it stopped, e.g. "interrupted" or "poll limit reached".
    #   gap: For a gap only: what was lost and why.
    record_type: Literal["collector"] = "collector"
    schema_version: Literal[1, 2] = 2
    source: str
    event: Literal["started", "heartbeat", "stopped", "gap"]
    at: datetime
    reason: str | None = None
    gap: GapDetail | None = None

    @model_validator(mode="after")
    def gap_detail_only_on_a_gap(self):
        """Refuse a gap with no detail, or detail on any other marker."""
        if (self.event == "gap") != (self.gap is not None):
            raise ValueError("a gap marker, and only a gap marker, carries gap")
        return self


Line = TelemetryRecord | CollectorMarker


def parse_line(text: str) -> Line:
    """Read one JSONL line as an observation or a collector marker.

    Raises pydantic.ValidationError (or ValueError for bad JSON) if it is neither.
    """
    # Variables:
    #   text: One line of the telemetry file, without its newline.
    #   data: The line's JSON object.
    #   kind: The line's record_type; missing means an observation written
    #     before markers existed.
    data = json.loads(text)
    kind = data.get("record_type", "observation") if isinstance(data, dict) else None
    if kind == "collector":
        return CollectorMarker.model_validate(data)
    return TelemetryRecord.model_validate(data)


def gap_free_runs(lines: Iterable[Line]) -> list[list[TelemetryRecord]]:
    """The observations split wherever collection was broken, oldest first.

    A run ends at a `gap` marker (observations were lost) and at a `started`
    marker (the collector was not running before it). Anything computed over
    readings, such as a mean or a slope, should stay inside one run, so it
    never joins two values across time that was not collected.
    Empty runs are left out.
    """
    # Variables:
    #   runs: The finished runs.
    #   current: Observations since the last break.
    runs: list[list[TelemetryRecord]] = []
    current: list[TelemetryRecord] = []
    for line in lines:
        if isinstance(line, CollectorMarker):
            if line.event in ("gap", "started") and current:
                runs.append(current)
                current = []
            continue
        current.append(line)
    if current:
        runs.append(current)
    return runs
