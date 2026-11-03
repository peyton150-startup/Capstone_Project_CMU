# One normalized telemetry observation, the unit every later layer reads.
# Responsibility: define the stored record shape; no I/O and no interpretation.
"""The versioned lines the collector writes and the monitor reads.

A telemetry file holds two kinds of line, told apart by `record_type`:
`observation` (a TelemetryRecord) and `collector` (a CollectorMarker saying
the collector started or stopped on purpose). Lines written before markers
existed have no `record_type` and are read as observations.
"""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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


class CollectorMarker(BaseModel):
    """A line saying the collector started, is alive, or stopped on purpose.

    A heartbeat is written when polls succeed but nothing new has been written
    for a while (a quiet machine), so silence in the file means the collector
    or its connection is down, not that the machine is idle. A clean stop (Ctrl+C or the poll limit) writes `stopped`. A crash, a
    killed process or a power cut writes nothing, so a `started` line that is
    not preceded by `stopped` means the previous run did not end cleanly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   record_type: Always "collector"; tells this line apart from an observation.
    #   source: The agent the collector was reading, matching its records' source.
    #   event: "started" when collection begins, "heartbeat" when it is alive
    #     but has had nothing new to write, "stopped" when it ends on purpose.
    #   at: The collector's clock (UTC) when the event happened.
    #   reason: Why it stopped, e.g. "interrupted" or "poll limit reached".
    record_type: Literal["collector"] = "collector"
    schema_version: Literal[1] = 1
    source: str
    event: Literal["started", "heartbeat", "stopped"]
    at: datetime
    reason: str | None = None


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
