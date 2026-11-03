# One normalized telemetry observation, the unit every later layer reads.
# Responsibility: define the stored record shape; no I/O and no interpretation.
"""The versioned record the collector writes and the monitor reads."""

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
        if self.value is None:
            return None
        try:
            return float(self.value)
        except ValueError:
            return None
