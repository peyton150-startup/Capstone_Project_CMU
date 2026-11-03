# Deterministic rules over collected telemetry that raise and clear alerts.
# Responsibility: notice changes worth a human's (or later the agent's) attention; no LLM.
"""The smallest deterministic monitor.

Rules, all edge-triggered (an alert fires when a state starts, and a
`recovered` alert when it ends, never once per record):

- condition:     a CONDITION goes to WARNING or FAULT.
- unavailable:   a channel that had a value becomes UNAVAILABLE.
- status_change: Execution, ControllerMode or EmergencyStop changes value
                 (EmergencyStop TRIGGERED is a fault).
- threshold:     a numeric channel leaves an operator-given [low, high] range.
- stale:         a device's records are more than `stale_after` seconds apart
                 (measured on the records' receive times, not the wall clock).

This is plain code: no model or agent monitors, and nothing here reads a
clock, the network or a random source. The monitor is a pure function of
the records it is given, so the same records always give the same alerts.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from capstone.ingestion.record import TelemetryRecord

AlertKind = Literal[
    "condition", "unavailable", "status_change", "threshold", "stale", "recovered"
]
Severity = Literal["info", "warning", "fault"]

STATUS_TYPES = frozenset({"Execution", "ControllerMode", "EmergencyStop"})


class Alert(BaseModel):
    """One thing the monitor noticed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   kind: Which rule fired, or `recovered` when a flagged state ended.
    #   severity: info for changes and recoveries; warning or fault for problems.
    #   data_item_id: The channel concerned; None for a whole-device alert (stale).
    #   at: The record's source time, or the check time for a stale alert.
    #   sequence: The record that caused the alert, to find it in the file.
    kind: AlertKind
    severity: Severity
    device: str
    data_item_id: str | None
    message: str
    at: datetime
    sequence: int | None = None


@dataclass(frozen=True)
class Threshold:
    """An operator-given safe range for one channel (by data item id or name)."""

    low: float
    high: float


class Monitor:
    """Holds the last known state per channel and turns changes into alerts."""

    def __init__(
        self,
        *,
        thresholds: dict[str, Threshold] | None = None,
        stale_after: float = 60.0,
    ) -> None:
        # Variables:
        #   thresholds: Safe ranges keyed by data item id or name; empty means
        #     no threshold rule runs.
        #   stale_after: Seconds of silence after which a device is called stale.
        #   _last: The last record seen for each (device, data item).
        #   _flagged: (device, data item, rule) states that are currently
        #     alerting, so the same problem is not reported twice.
        #   _last_seen: When each device last sent anything (receive time).
        #   _known: The last record with a value for each channel, so a status
        #     change is measured against what was last reported, not a gap.
        #   _levels: Each condition channel's current WARNING/FAULT level; a
        #     channel absent here is normal.
        self.thresholds = thresholds or {}
        self.stale_after = stale_after
        self._last: dict[tuple[str, str], TelemetryRecord] = {}
        self._known: dict[tuple[str, str], TelemetryRecord] = {}
        self._levels: dict[tuple[str, str], str] = {}
        self._flagged: set[tuple[str, str | None, str]] = set()
        self._last_seen: dict[str, datetime] = {}

    def observe(self, record: TelemetryRecord) -> list[Alert]:
        """Update state with one record and return the alerts it causes."""
        # Variables:
        #   key: The channel this record belongs to.
        #   previous: The channel's last record, or None the first time.
        #   known: The channel's last record that had a value, or None.
        alerts = self._device_back(record)
        key = (record.device, record.data_item_id)
        previous = self._last.get(key)
        known = self._known.get(key)
        self._last[key] = record
        if record.available:
            self._known[key] = record
        self._last_seen[record.device] = record.received_at

        alerts += self._availability(record, previous)
        if record.category == "CONDITION":
            alerts += self._condition(record)
        elif record.type in STATUS_TYPES:
            alerts += self._status(record, known)
        alerts += self._threshold(record)
        return alerts

    def check_stale(self, now: datetime) -> list[Alert]:
        """Alert for every device silent for longer than stale_after at `now`."""
        # Variables:
        #   now: The time to measure silence against: the wall clock when
        #     following live, or a record's receive time when replaying.
        #   silent: Seconds since the device last sent anything.
        alerts = []
        for device, seen in sorted(self._last_seen.items()):
            silent = (now - seen).total_seconds()
            if silent > self.stale_after and self._start((device, None, "stale")):
                alerts.append(
                    Alert(
                        kind="stale",
                        severity="warning",
                        device=device,
                        data_item_id=None,
                        message=f"no data for {silent:.0f} s",
                        at=now,
                    )
                )
        return alerts

    def _start(self, flag: tuple[str, str | None, str]) -> bool:
        """Mark a state as alerting; True only the first time."""
        if flag in self._flagged:
            return False
        self._flagged.add(flag)
        return True

    def _end(self, flag: tuple[str, str | None, str]) -> bool:
        """Clear an alerting state; True only if it was alerting."""
        if flag not in self._flagged:
            return False
        self._flagged.discard(flag)
        return True

    def _alert(
        self, record: TelemetryRecord, kind: AlertKind, severity: Severity, message: str
    ) -> Alert:
        """An alert about one record's channel."""
        return Alert(
            kind=kind,
            severity=severity,
            device=record.device,
            data_item_id=record.data_item_id,
            message=message,
            at=record.source_timestamp,
            sequence=record.sequence,
        )

    def _device_back(self, record: TelemetryRecord) -> list[Alert]:
        """A recovered alert if this record ends a stale period for its device."""
        if self._end((record.device, None, "stale")):
            return [
                self._alert(record, "recovered", "info", "device sending data again")
            ]
        return []

    def _availability(
        self, record: TelemetryRecord, previous: TelemetryRecord | None
    ) -> list[Alert]:
        """Alert when a channel that had a value goes UNAVAILABLE, and when it returns.

        A channel unavailable from the start is not an alert: many controls
        list channels they never fill.
        """
        # Variables:
        #   previous: The channel's last record; only a channel that had a value
        #     can "go" unavailable.
        #   flag: Marks this channel as currently reported unavailable.
        flag = (record.device, record.data_item_id, "unavailable")
        if not record.available:
            if previous is not None and previous.available and self._start(flag):
                return [
                    self._alert(
                        record, "unavailable", "warning", f"{record.type} unavailable"
                    )
                ]
            return []
        if self._end(flag):
            return [
                self._alert(
                    record, "recovered", "info", f"{record.type} available again"
                )
            ]
        return []

    def _condition(self, record: TelemetryRecord) -> list[Alert]:
        """Alert when a condition goes WARNING/FAULT; recover when it is NORMAL."""
        # Variables:
        #   level: The channel's level before this record (None if never bad);
        #     a change from WARNING to FAULT is reported again.
        key = (record.device, record.data_item_id)
        level = self._levels.get(key)
        if record.value in ("WARNING", "FAULT"):
            if level == record.value:
                return []
            self._levels[key] = record.value
            code = f" [{record.native_code}]" if record.native_code else ""
            severity: Severity = "fault" if record.value == "FAULT" else "warning"
            message = f"{record.message or record.type}{code}"
            return [self._alert(record, "condition", severity, message)]
        if record.value == "NORMAL" and level is not None:
            del self._levels[key]
            return [
                self._alert(
                    record, "recovered", "info", f"{record.type} condition normal"
                )
            ]
        return []

    def _status(
        self, record: TelemetryRecord, previous: TelemetryRecord | None
    ) -> list[Alert]:
        """An info alert when machine status changes; E-stop triggered is a fault."""
        # Variables:
        #   previous: The last record with a value; a value returning after a
        #     gap is compared with what was reported before the gap.
        if previous is None or not record.available or previous.value == record.value:
            return []
        severity: Severity = (
            "fault"
            if record.type == "EmergencyStop" and record.value == "TRIGGERED"
            else "info"
        )
        return [
            self._alert(
                record,
                "status_change",
                severity,
                f"{record.type}: {previous.value} -> {record.value}",
            )
        ]

    def _threshold(self, record: TelemetryRecord) -> list[Alert]:
        """Alert when a numeric channel leaves its range; recover when it returns."""
        # Variables:
        #   limit: The channel's safe range, looked up by data item id first,
        #     then by name; None means no threshold applies.
        #   number: The value as a float; text values are never compared.
        limit = self.thresholds.get(record.data_item_id) or (
            self.thresholds.get(record.name) if record.name else None
        )
        number = record.number()
        if limit is None or number is None:
            return []
        flag = (record.device, record.data_item_id, "threshold")
        if not limit.low <= number <= limit.high:
            if self._start(flag):
                return [
                    self._alert(
                        record,
                        "threshold",
                        "warning",
                        f"{record.type} {number:g} outside [{limit.low:g}, {limit.high:g}]",
                    )
                ]
            return []
        if self._end(flag):
            return [
                self._alert(record, "recovered", "info", f"{record.type} back in range")
            ]
        return []
