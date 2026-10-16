# The read-only tools that show the agent what the factory reports.
# Responsibility: return evidence without advancing time or revealing hidden truth.
from math import isfinite
from statistics import fmean

from capstone.simulator.simulator import Simulator
from capstone.tools.errors import ToolInputError


class ObservationTools:
    """The agent's only view of the factory. Read-only.

    Every answer is built from scratch, field by field, out of plain
    values. Anything not named here stays hidden, including whatever is
    added to the simulator later. Nothing here advances time.
    """

    def __init__(self, simulator: Simulator):
        self._sim = simulator

    def get_time(self) -> dict:
        clock = self._sim.clock
        return {"tick": clock.tick, "time": clock.now.isoformat()}

    def list_machines(self) -> list[dict]:
        return [
            {
                "machine_id": machine.id,
                "status": machine.status.value,
                "job_id": machine.job.id if machine.job else None,
            }
            for machine in self._sim.state.machines.values()
        ]

    def get_settings(self) -> list[dict]:
        """The speed each machine is set to now. Not what it is meant to be set to."""
        return [
            {"machine_id": machine.id, "speed_rpm": machine.speed}
            for machine in self._sim.state.machines.values()
        ]

    def get_readings(
        self, machine_id: str, sensor: str, from_tick: int, to_tick: int
    ) -> list[dict]:
        if machine_id is None:
            raise ToolInputError(
                "a machine is required; use get_factory_readings for the factory's own sensors"
            )
        self._check(machine_id, from_tick, to_tick)
        return [
            {
                "tick": r.tick,
                "machine_id": r.machine_id,
                "sensor": r.sensor,
                "value": r.value,
                "unit": r.unit,
            }
            for r in self._sim.readings
            if r.machine_id == machine_id
            and r.sensor == sensor
            and from_tick <= r.tick <= to_tick
        ]

    def get_sensor_trend(
        self,
        machine_id: str,
        sensor: str,
        from_tick: int,
        to_tick: int,
        bucket_ticks: int = 60,
    ) -> list[dict]:
        """The same readings as get_readings, summarised per block of ticks: mean, min, max, count.

        Only arithmetic on readings the agent could fetch anyway; idle
        readings are included as they are.
        """
        if not isinstance(bucket_ticks, int) or bucket_ticks < 1:
            raise ToolInputError("bucket_ticks must be a whole number of at least 1")
        buckets: dict[int, list[float]] = {}
        for row in self.get_readings(machine_id, sensor, from_tick, to_tick):
            buckets.setdefault((row["tick"] - from_tick) // bucket_ticks, []).append(
                row["value"]
            )
        return [
            {
                "from_tick": from_tick + index * bucket_ticks,
                "to_tick": min(to_tick, from_tick + (index + 1) * bucket_ticks - 1),
                "mean": round(sum(values) / len(values), 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "count": len(values),
            }
            for index, values in sorted(buckets.items())
        ]

    def get_factory_readings(
        self, sensor: str, from_tick: int, to_tick: int
    ) -> list[dict]:
        """Readings from sensors that belong to the factory, not to a machine."""
        self._check(None, from_tick, to_tick)
        return [
            {"tick": r.tick, "sensor": r.sensor, "value": r.value, "unit": r.unit}
            for r in self._sim.readings
            if r.machine_id is None
            and r.sensor == sensor
            and from_tick <= r.tick <= to_tick
        ]

    def get_sensor_summary(
        self, machine_id: str | None, sensor: str, from_tick: int, to_tick: int
    ) -> dict:
        """Summarize public readings in an inclusive window, without advancing time.

        None selects a factory sensor. Mean is sample-weighted; rate is endpoint
        change per elapsed simulation tick, not a fitted trend. Missing samples
        are not filled in. Empty windows have null statistics; zero elapsed
        time has no rate. First/last refer to chronological observations.
        """
        if any(type(tick) is not int or tick < 0 for tick in (from_tick, to_tick)):
            raise ToolInputError("ticks must be nonnegative integers")
        if machine_id is None:
            readings = self.get_factory_readings(sensor, from_tick, to_tick)
        else:
            readings = self.get_readings(machine_id, sensor, from_tick, to_tick)
        readings.sort(key=lambda row: row["tick"])
        summary = {
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
        if len({row["unit"] for row in readings}) != 1:
            raise ValueError("cannot summarize readings with mixed units")
        values = [row["value"] for row in readings]
        if not all(isfinite(value) for value in values):
            raise ValueError("sensor values must be finite")
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
            mean=fmean(values),
            delta=delta,
            rate_of_change=delta / elapsed if elapsed else None,
        )
        return summary

    def get_events(
        self, from_tick: int, to_tick: int, machine_id: str | None = None
    ) -> list[dict]:
        self._check(machine_id, from_tick, to_tick)
        return [
            self._event_row(e)
            for e in self._sim.event_log.events
            if from_tick <= e.tick <= to_tick and machine_id in (None, e.machine_id)
        ]

    def get_job_history(self, job_id: int) -> list[dict]:
        """Everything the event log says about one job, oldest first, across all machines."""
        return [
            self._event_row(e) for e in self._sim.event_log.events if e.job_id == job_id
        ]

    def get_inspections(self, from_tick: int, to_tick: int) -> list[dict]:
        """Inspection results for jobs that left the line in this tick range."""
        self._check(None, from_tick, to_tick)
        batch_of = {i.job_id: i.batch_id for i in self._sim.state.inspections}
        return [
            {
                "tick": e.tick,
                "job_id": e.job_id,
                "batch_id": batch_of[e.job_id],
                "result": e.message.split()[2],
            }
            for e in self._sim.event_log.events
            if e.kind == "inspection" and from_tick <= e.tick <= to_tick
        ]

    @staticmethod
    def _event_row(e) -> dict:
        return {
            "tick": e.tick,
            "machine_id": e.machine_id,
            "kind": e.kind,
            "message": e.message,
            "job_id": e.job_id,
        }

    def _check(self, machine_id: str | None, from_tick: int, to_tick: int) -> None:
        if machine_id is not None and machine_id not in self._sim.state.machines:
            raise ToolInputError(f"unknown machine {machine_id}")
        if from_tick > to_tick:
            raise ToolInputError("from_tick must not be after to_tick")
