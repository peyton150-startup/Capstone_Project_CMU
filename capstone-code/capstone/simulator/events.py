# The factory event record, the event log, and threshold alarms.
# Responsibility: store what the factory noticed and raise alarms from sensor readings.
from pydantic import BaseModel, ConfigDict

from capstone.simulator.sensors import SensorReading


class Event(BaseModel):
    """Something the factory's systems noticed. Immutable once recorded.

    Evidence, not truth: an event may only say what a sensor, record or
    operator could have seen. Hidden condition never appears here.
    """

    model_config = ConfigDict(frozen=True)

    tick: int
    machine_id: str | None  # None for something about the factory as a whole
    kind: str
    message: str
    job_id: int | None = None  # set on events about a job


class EventLog:
    """Append-only, in tick order."""

    def __init__(self):
        self._events: list[Event] = []

    @property
    def events(self) -> tuple[Event, ...]:
        """Every event so far, oldest first."""
        return tuple(self._events)

    def record(self, event: Event) -> None:
        if self._events and event.tick < self._events[-1].tick:
            raise ValueError(
                f"event at tick {event.tick} is older than the log's latest entry"
            )
        self._events.append(event)


class ThresholdAlarm:
    """Fires on a reading, never on machine state.

    It inherits the sensor's flaws on purpose: it can fire late, flicker
    near the threshold, and trip on a healthy machine.
    """

    def __init__(self, sensor: str, threshold: float, *, below: bool = False):
        self.sensor = sensor
        self.threshold = threshold
        # True: fires when a reading falls below the threshold (a pressure that drops).
        self.below = below

    def check(self, reading: SensorReading) -> Event | None:
        if reading.sensor != self.sensor:
            return None
        if self.below:
            if reading.value >= self.threshold:
                return None
            side = "below"
        else:
            if reading.value <= self.threshold:
                return None
            side = "above"
        return Event(
            tick=reading.tick,
            machine_id=reading.machine_id,
            kind="alarm",
            message=f"{reading.sensor} {reading.value:.2f} {reading.unit} {side} {self.threshold:.2f}",
        )
