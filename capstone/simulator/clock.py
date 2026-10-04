from datetime import datetime, timedelta


class SimulationClock:
    """The single owner of simulated time.

    Time is an integer tick count. The datetime view is derived from it, never
    stored, so there is exactly one source of truth and no float drift.
    Time only moves forward, and only through `advance()`.
    """

    def __init__(self, start: datetime, tick_duration: timedelta = timedelta(minutes=1)):
        if tick_duration <= timedelta(0):
            raise ValueError("tick_duration must be positive")
        self._start = start
        self._tick_duration = tick_duration
        self._tick = 0

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def tick_duration(self) -> timedelta:
        return self._tick_duration

    @property
    def now(self) -> datetime:
        return self.time_at(self._tick)

    def time_at(self, tick: int) -> datetime:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        return self._start + self._tick_duration * tick

    def advance(self, ticks: int = 1) -> int:
        if ticks < 1:
            raise ValueError("time only moves forward: ticks must be >= 1")
        self._tick += ticks
        return self._tick
