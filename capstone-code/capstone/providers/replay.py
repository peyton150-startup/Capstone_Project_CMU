# A read-only factory provider that answers the agent's tools from a recorded capture.
# Responsibility: map a real machine's recording onto the existing tool contracts,
# never showing a reading after the replay's cutoff and never changing anything.
"""Read-only real-data provider over a recorded capture (SM-3 in docs/MVP_SCOPE.md).

The research agent asks the factory questions through `FactoryProvider`. The
simulator answers them from its own state; this module answers the same
questions from a capture the collector recorded, with the same argument and
answer contracts, so the agent's code does not change.

How the recording is mapped:

- **Time.** Tick 0 is the capture's first observation; one tick is
  `tick_seconds` (60 by default, the tools' "one tick is one minute"). Times
  are the machine's own `source_timestamp`.
- **Cutoff.** The replay stands at a moment `now` inside the capture. No
  answer includes a reading after it; `wait` moves it forward, but never past
  the end of the capture.
- **Channels.** Only channels a person assigned a `tool_sensor` in the SM-1
  channel map are visible. Each device with at least one is a machine; a
  channel assigned `air_temperature` is the factory's thermometer.
- **What is missing stays missing.** UNAVAILABLE records and event words are
  never readings. A tool the recording cannot answer (events, maintenance,
  inspections, settings, line screening) refuses and says so, instead of
  returning an empty answer that would look like "nothing happened".
- **Statistics** use SM-5's holds: a trend block's mean is time-weighted and
  never spans a gap in collection.
- **Read-only.** No change can be proposed or carried out.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from math import floor

from capstone.ingestion.channel_map import ChannelEntry, ChannelMap
from capstone.ingestion.record import Line, TelemetryRecord
from capstone.ingestion.time_stats import Hold, channel_holds
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.tools.actions import MAX_WAIT_TICKS
from capstone.tools.errors import ToolInputError

FACTORY_SENSOR = "air_temperature"
# Execution values that mean the program is running; any other known value
# means the machine is not cutting (MTConnect Execution).
RUNNING = frozenset({"ACTIVE"})
UNSTATED_UNIT = "unstated"


class RecordedObservationTools:
    """The observation tools, answered from a recorded capture up to a cutoff."""

    def __init__(
        self,
        lines: Sequence[Line],
        channel_map: ChannelMap,
        *,
        tick_seconds: int = 60,
        now: datetime | None = None,
    ):
        # Variables:
        #   lines: The capture, observations and collector markers in file order.
        #   channel_map: SM-1's map; only entries with a tool_sensor are visible.
        #   tick_seconds: Seconds of machine time in one tick.
        #   start: The capture's first observation time, which is tick 0.
        #   end: Its last observation time; the cutoff never moves past it.
        #   now: The replay's cutoff; nothing after it is ever shown.
        #   _sensors: For each machine, its tool sensor names and their channels.
        #   _factory: The channel behind air_temperature, if one was assigned.
        if tick_seconds < 1:
            raise ValueError("tick_seconds must be at least 1")
        observations = [line for line in lines if isinstance(line, TelemetryRecord)]
        if not observations:
            raise ValueError("the capture holds no observations")
        self._lines = list(lines)
        self._tick = timedelta(seconds=tick_seconds)
        self.start = min(r.source_timestamp for r in observations)
        self.end = max(r.source_timestamp for r in observations)
        self.now = self.end if now is None else now
        if not self.start <= self.now <= self.end:
            raise ValueError("now must lie inside the capture")
        self._sensors: dict[str, dict[str, ChannelEntry]] = {}
        self._factory: ChannelEntry | None = None
        for entry in channel_map.entries:
            if entry.tool_sensor is None:
                continue
            if entry.tool_sensor == FACTORY_SENSOR:
                if self._factory is not None:
                    raise ValueError("two channels are assigned air_temperature")
                self._factory = entry
                continue
            sensors = self._sensors.setdefault(entry.device, {})
            if entry.tool_sensor in sensors:
                raise ValueError(
                    f"{entry.device} has two channels assigned {entry.tool_sensor}"
                )
            sensors[entry.tool_sensor] = entry

    # --- time -----------------------------------------------------------------

    def tick_of(self, at: datetime) -> int:
        """The tick a machine time falls in."""
        return floor((at - self.start) / self._tick)

    def time_of(self, tick: int) -> datetime:
        """The machine time at which a tick begins."""
        return self.start + tick * self._tick

    def advance(self, ticks: int) -> None:
        """Move the cutoff forward, stopping at the end of the capture."""
        # Variables:
        #   ticks: How many ticks to move; now never passes end.
        self.now = min(self.end, self.now + ticks * self._tick)

    def _visible(self) -> list[Line]:
        """The capture up to the cutoff, in file order, markers included."""
        # Variables:
        #   visible: Lines before the first observation after the cutoff; a
        #     marker after that point belongs to time not yet replayed.
        visible: list[Line] = []
        for line in self._lines:
            if isinstance(line, TelemetryRecord) and line.source_timestamp > self.now:
                break
            visible.append(line)
        return visible

    # --- tools the recording answers --------------------------------------------

    def get_time(self) -> dict:
        return {"tick": self.tick_of(self.now), "time": self.now.isoformat()}

    def list_machines(self) -> list[dict]:
        """Each machine, running or idle by its last Execution value."""
        # Variables:
        #   execution: Each device's last Execution value up to the cutoff; a
        #     machine without one cannot be called running or idle, so the
        #     tool refuses rather than guess.
        execution: dict[str, str | None] = {}
        for line in self._visible():
            if isinstance(line, TelemetryRecord) and line.type == "Execution":
                execution[line.device] = line.value if line.available else None
        rows = []
        for device, sensors in self._sensors.items():
            value = execution.get(device)
            if value is None:
                raise ToolInputError(
                    f"the capture has no Execution value for {device}, so whether "
                    "it is running is not known"
                )
            rows.append(
                {
                    "machine_id": device,
                    "status": "running" if value in RUNNING else "idle",
                    "job_id": None,
                    "hydraulics": "hydraulic_pressure" in sensors,
                }
            )
        return rows

    def get_readings(
        self, machine_id: str, sensor: str, from_tick: int, to_tick: int
    ) -> list[dict]:
        return self._rows(
            self._entry(machine_id, sensor), machine_id, sensor, from_tick, to_tick
        )

    def get_factory_readings(
        self, sensor: str, from_tick: int, to_tick: int
    ) -> list[dict]:
        if sensor != FACTORY_SENSOR or self._factory is None:
            raise ToolInputError(f"the capture has no channel mapped to {sensor}")
        return self._rows(self._factory, None, sensor, from_tick, to_tick)

    def get_sensor_trend(
        self,
        machine_id: str,
        sensor: str,
        from_tick: int,
        to_tick: int,
        bucket_ticks: int = 60,
    ) -> list[dict]:
        """Blocks of ticks: time-weighted mean, min, max and count of readings.

        A block's mean weights each value by how long it held inside the
        block; no value is carried across a gap in collection.
        """
        # Variables:
        #   entry: The channel behind this machine's sensor.
        #   holds: The channel's values as they held, split at every gap.
        #   first, last: The block's first and last tick.
        #   block: The holds cut to the block's time, for the mean, min and max.
        #   readings: The holds that began inside the block; their number is
        #     the count, and a block with none is left out.
        entry = self._entry(machine_id, sensor)
        holds = self._holds(entry)
        rows = []
        for first in range(from_tick, to_tick + 1, bucket_ticks):
            last = min(to_tick, first + bucket_ticks - 1)
            block = _clip(holds, self.time_of(first), self.time_of(last + 1))
            readings = [h for h in block if self.time_of(first) <= h.start]
            if not readings:
                continue
            rows.append(
                {
                    "from_tick": first,
                    "to_tick": last,
                    "mean": round(_weighted(block), 3),
                    "min": round(min(h.value for h in block), 3),
                    "max": round(max(h.value for h in block), 3),
                    "count": len(readings),
                }
            )
        return rows

    def get_sensor_summary(
        self, machine_id: str | None, sensor: str, from_tick: int, to_tick: int
    ) -> dict:
        """The window's readings summarised; the mean is time-weighted.

        As in the simulator, the rate is the change from the first to the last
        reading per tick, not a fitted trend, because the tool's description
        says so.
        """
        # Variables:
        #   entry: The channel behind the sensor; the factory's for machine_id None.
        #   readings: The readings in the window, oldest first.
        #   block: The channel's holds cut to the window, for the mean.
        entry = self._factory if machine_id is None else self._entry(machine_id, sensor)
        if machine_id is None and (sensor != FACTORY_SENSOR or entry is None):
            raise ToolInputError(f"the capture has no channel mapped to {sensor}")
        readings = self._rows(entry, machine_id, sensor, from_tick, to_tick)
        summary: dict = {
            "machine_id": machine_id,
            "sensor": sensor,
            "from_tick": from_tick,
            "to_tick": to_tick,
            "sample_count": len(readings),
            "unit": None,
            "first_tick": None,
            "last_tick": None,
            "start_value": None,
            "end_value": None,
            "minimum": None,
            "maximum": None,
            "mean": None,
            "delta": None,
            "rate_of_change": None,
        }
        if not readings:
            return summary
        values = [row["value"] for row in readings]
        block = _clip(
            self._holds(entry), self.time_of(from_tick), self.time_of(to_tick + 1)
        )
        elapsed = readings[-1]["tick"] - readings[0]["tick"]
        delta = values[-1] - values[0]
        summary.update(
            unit=readings[0]["unit"],
            first_tick=readings[0]["tick"],
            last_tick=readings[-1]["tick"],
            start_value=values[0],
            end_value=values[-1],
            minimum=min(values),
            maximum=max(values),
            mean=_weighted(block) if block else None,
            delta=delta,
            rate_of_change=delta / elapsed if elapsed else None,
        )
        return summary

    # --- tools the recording cannot answer ----------------------------------------

    def _not_recorded(self, what: str):
        raise ToolInputError(f"a machine capture does not record {what}")

    def get_settings(self) -> list[dict]:
        self._not_recorded("standard settings")

    def get_line_screening(self) -> dict:
        self._not_recorded("a healthy-line reference to screen against")

    def get_events(self, from_tick: int, to_tick: int, machine_id: str | None = None):
        self._not_recorded("the event log")

    def get_job_history(self, job_id: int):
        self._not_recorded("jobs")

    def get_maintenance_history(self, machine_id: str | None = None):
        self._not_recorded("maintenance history")

    def get_inspections(self, from_tick: int, to_tick: int):
        self._not_recorded("inspections")

    # --- helpers -------------------------------------------------------------------

    def _entry(self, machine_id: str | None, sensor: str) -> ChannelEntry:
        """The channel behind one machine's sensor, or a refusal saying why not."""
        if machine_id is None or machine_id not in self._sensors:
            raise ToolInputError(f"unknown machine {machine_id}")
        entry = self._sensors[machine_id].get(sensor)
        if entry is None:
            raise ToolInputError(f"{machine_id} has no channel mapped to {sensor}")
        return entry

    def _rows(
        self,
        entry: ChannelEntry,
        machine_id: str | None,
        sensor: str,
        from_tick: int,
        to_tick: int,
    ) -> list[dict]:
        """The channel's numeric readings in a tick range, up to the cutoff."""
        # Variables:
        #   entry: The channel; its device and id pick the records, and its
        #     units, exactly as the probe states them, label each row.
        #   value: A record's number; UNAVAILABLE and words give None and no row.
        if from_tick > to_tick:
            raise ToolInputError("from_tick must not be after to_tick")
        rows = []
        for line in self._visible():
            if not isinstance(line, TelemetryRecord) or not _is(line, entry):
                continue
            value = line.number() if line.available else None
            tick = self.tick_of(line.source_timestamp)
            if value is None or not from_tick <= tick <= to_tick:
                continue
            rows.append(
                {
                    "tick": tick,
                    "machine_id": machine_id,
                    "sensor": sensor,
                    "value": value,
                    "unit": entry.units or UNSTATED_UNIT,
                }
            )
        return rows

    def _holds(self, entry: ChannelEntry) -> list[Hold]:
        """The channel's values as they held, up to the cutoff, never across a gap."""
        # Variables:
        #   visible: The capture up to the cutoff, markers included, so holds
        #     split at its gaps.
        #   names: How the records name the device: its name, its uuid, or both.
        visible = self._visible()
        names = {
            line.device
            for line in visible
            if isinstance(line, TelemetryRecord) and _is(line, entry)
        }
        holds = [
            hold
            for name in sorted(names)
            for run in channel_holds(visible, name, entry.data_item_id)
            for hold in run
        ]
        return sorted(holds, key=lambda hold: hold.start)


class RecordedActionTools:
    """The action tools for a replay: time can pass, nothing can change."""

    def __init__(self, observations: RecordedObservationTools):
        # Variables:
        #   observations: The replay whose cutoff `wait` moves.
        self._observations = observations

    def wait(self, ticks: int) -> dict:
        """Move the replay forward; at the end of the capture time stops."""
        # Variables:
        #   ticks: How far to move; the same limit as the simulator's wait.
        if not 1 <= ticks <= MAX_WAIT_TICKS:
            raise ToolInputError(f"ticks must be between 1 and {MAX_WAIT_TICKS}")
        self._observations.advance(ticks)
        return self._observations.get_time()

    def propose_action(self, machine_id: str, action: str, reason: str):
        raise ToolInputError("a recorded capture is read-only: nothing can be changed")

    def get_proposals(self) -> list[dict]:
        return []

    def execute_action(self, proposal_id: int):
        raise ToolInputError("a recorded capture is read-only: nothing can be changed")


def replay_provider(
    lines: Sequence[Line],
    channel_map: ChannelMap,
    *,
    tick_seconds: int = 60,
    now: datetime | None = None,
) -> SimulatorFactoryProvider:
    """A FactoryProvider over a capture: the same tools and contracts, source 'replay'."""
    # Variables:
    #   look: The recorded observation tools, standing at the cutoff.
    look = RecordedObservationTools(
        lines, channel_map, tick_seconds=tick_seconds, now=now
    )
    return SimulatorFactoryProvider(look, RecordedActionTools(look), source="replay")


def _is(record: TelemetryRecord, entry: ChannelEntry) -> bool:
    """Whether a record belongs to a channel, by device name or uuid and id."""
    return record.data_item_id == entry.data_item_id and record.device in (
        entry.device,
        entry.device_uuid,
    )


def _clip(holds: Sequence[Hold], start: datetime, end: datetime) -> list[Hold]:
    """The holds cut to [start, end); a hold outside it is dropped."""
    return [
        Hold(start=max(h.start, start), end=min(h.end, end), value=h.value)
        for h in holds
        if h.end > start and h.start < end
    ]


def _weighted(holds: Sequence[Hold]) -> float:
    """The time-weighted mean of holds; a zero-length set falls back to plain."""
    total = sum(h.seconds for h in holds)
    if total == 0:
        return sum(h.value for h in holds) / len(holds)
    return sum(h.value * h.seconds for h in holds) / total
