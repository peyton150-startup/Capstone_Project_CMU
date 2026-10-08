"""Top-level simulator facade.

Planned composition (see CLAUDE.md §6); parts marked * exist today:

    Simulator
      ├── clock *      SimulationClock         — owns "now"; nothing else does
      ├── rng *        seeded random source    — all randomness flows from here
      ├── state *      FactoryState            — machines, jobs, batches (reality)
      ├── sensors *    Sensor[]                — read state → noisy observations
      ├── production   jobs / material batches
      ├── maintenance  records + bounded actions
      ├── quality      inspections / rejects
      ├── events *     event + alarm log
      ├── scenarios *  Scenario[]              — inject causal effects over time
      └── ground_truth * hidden truth            — never crosses the tool boundary

The agent never imports this module. It reaches the simulator only through
`capstone/tools/`, which exposes observations and accepts actions.
"""

from datetime import datetime, timedelta

from capstone.simulator.clock import SimulationClock
from capstone.simulator.events import Event, EventLog, ThresholdAlarm
from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import Scenario
from capstone.simulator.sensors import FactoryThermometer, Sensor, SensorReading
from capstone.simulator.state import FactoryState, MachineState, MachineStatus
from capstone.simulator.thermal import settle, warm_or_cool


class Simulator:
    """Owns the parts and the one legal way to move the world forward."""

    def __init__(
        self,
        seed: int,
        start: datetime,
        tick_duration: timedelta = timedelta(minutes=1),
        *,
        bearing_failure_health: float = 0.1,
        thermal_lag_ticks: float = 1.0,
        planned_repair_ticks: int = 45,
        breakdown_repair_ticks: int = 135,
    ):
        if thermal_lag_ticks < 1.0:
            raise ValueError("thermal_lag_ticks must be at least 1 (1 means no lag)")
        self.bearing_failure_health = bearing_failure_health
        self.thermal_lag_ticks = thermal_lag_ticks
        self.planned_repair_ticks = planned_repair_ticks
        self.breakdown_repair_ticks = breakdown_repair_ticks
        self.clock = SimulationClock(start, tick_duration)
        self.rng = RandomSource(seed)
        self.state = FactoryState()
        self._sensors: list[Sensor] = []
        self._factory_sensors: list[FactoryThermometer] = []
        self._readings: list[SensorReading] = []
        self.event_log = EventLog()
        self._alarms: list[ThresholdAlarm] = []
        self._scenarios: list[Scenario] = []
        # Per machine: the job last seen there and how far its story has been reported.
        self._job_seen: dict[str, tuple[int | None, str | None]] = {}
        self._last_door_open = self.state.door_open
        self._inspections_reported = 0
        self._batch_reported: int | None = None

    def add_machine(self, machine: MachineState) -> None:
        self.state.add(machine)
        settle(machine, self.state.air_temperature)  # machines start already warmed up
        self._job_seen[machine.id] = (
            (machine.job.id, "working") if machine.job else (None, None)
        )

    def add_sensor(self, sensor: Sensor) -> None:
        if sensor.machine_id not in self.state.machines:
            raise ValueError(f"{sensor.stream_name}: no machine {sensor.machine_id}")
        if any(s.stream_name == sensor.stream_name for s in self._sensors):
            raise ValueError(f"{sensor.stream_name} already exists")
        self._sensors.append(sensor)

    def add_factory_sensor(self, sensor: FactoryThermometer) -> None:
        if any(s.stream_name == sensor.stream_name for s in self._factory_sensors):
            raise ValueError(f"{sensor.stream_name} already exists")
        self._factory_sensors.append(sensor)

    def add_alarm(self, alarm: ThresholdAlarm) -> None:
        self._alarms.append(alarm)

    def add_scenario(self, scenario: Scenario) -> None:
        if any(s.stream_name == scenario.stream_name for s in self._scenarios):
            raise ValueError(f"{scenario.stream_name} already exists")
        self._scenarios.append(scenario)

    def ground_truth(self) -> tuple[GroundTruth, ...]:
        """The answer key, one record per fault. For evaluation only, never tools."""
        records = (s.ground_truth() for s in self._scenarios)
        return tuple(r for r in records if r is not None)

    def start_bearing_replacement(self, machine_id: str) -> int:
        """Take a machine out of service to replace its bearing. Returns the tick it will be done.

        A machine that has already broken down takes longer to put right
        than one caught while still running. Either way the machine is
        down for the whole repair and keeps the job it was holding.
        """
        machine = self.state.machines.get(machine_id)
        if machine is None:
            raise ValueError(f"unknown machine {machine_id}")
        if machine.maintenance_until is not None:
            raise ValueError(f"{machine_id} is already under maintenance")
        broken_down = machine.status is MachineStatus.DOWN
        duration = (
            self.breakdown_repair_ticks if broken_down else self.planned_repair_ticks
        )
        now = self.clock.tick
        machine.status = MachineStatus.DOWN
        machine.maintenance_until = now + duration
        self.event_log.record(
            Event(
                tick=now,
                machine_id=machine_id,
                kind="maintenance",
                message="bearing replacement started",
            )
        )
        return machine.maintenance_until

    @property
    def readings(self) -> tuple[SensorReading, ...]:
        """Every reading so far, oldest first."""
        return tuple(self._readings)

    def step(self) -> list[SensorReading]:
        """Advance one tick: clock, reality, consequences and warming, observation, alarms.

        The order is a contract: a reading stamped tick T is evidence of
        reality as of tick T, never of T-1. Alarms see only the readings.
        """
        tick = self.clock.advance()
        self._update_reality(tick)
        self._record_job_events(tick)
        self._record_inspections(tick)
        self._record_batch(tick)
        self._record_door(tick)
        self._finish_maintenance(tick)
        self._apply_consequences(tick)
        self._warm_or_cool_machines()
        readings = [
            s.read(self.state.machines[s.machine_id], tick) for s in self._sensors
        ]
        readings += [s.read(self.state, tick) for s in self._factory_sensors]
        self._readings.extend(readings)
        for reading in readings:
            for alarm in self._alarms:
                if event := alarm.check(reading):
                    self.event_log.record(event)
        return readings

    def _update_reality(self, tick: int) -> None:
        """Scenarios run in the order they were added; later ones see earlier changes."""
        for scenario in self._scenarios:
            scenario.apply(self.state, tick)

    def _record_job_events(self, tick: int) -> None:
        """Report a job starting, finishing, and being held up on each machine.

        Says what a person on the floor could see: which job, on which
        machine, and which machine it is waiting for. Never how heavy the
        job is, and never why the machine ahead is not ready.
        """
        for machine in self.state.machines.values():
            job_id = machine.job.id if machine.job else None
            seen_id, stage = self._job_seen[machine.id]
            if job_id != seen_id:
                stage = None
                if job_id is not None:
                    self._record_job(tick, machine.id, job_id, "started")
                    stage = "working"
            if machine.job_done:
                if stage == "working":
                    self._record_job(tick, machine.id, job_id, "finished")
                    stage = "finished"
                elif stage == "finished" and (
                    following := self.state.next_on_line(machine.id)
                ):
                    # Still here a tick after finishing: the next machine has not taken it.
                    self._record_job(
                        tick, machine.id, job_id, f"blocked by {following}"
                    )
                    stage = "blocked"
            self._job_seen[machine.id] = (job_id, stage)

    def _record_job(self, tick: int, machine_id: str, job_id: int, what: str) -> None:
        self.event_log.record(
            Event(
                tick=tick,
                machine_id=machine_id,
                kind="job",
                message=f"job {job_id} {what}",
                job_id=job_id,
            )
        )

    def _record_inspections(self, tick: int) -> None:
        """Report each new inspection result. Pass or fail only: never the risk behind it."""
        for inspection in self.state.inspections[self._inspections_reported :]:
            result = "passed" if inspection.passed else "failed"
            self.event_log.record(
                Event(
                    tick=tick,
                    machine_id=None,
                    kind="inspection",
                    message=f"job {inspection.job_id} {result} inspection",
                    job_id=inspection.job_id,
                )
            )
        self._inspections_reported = len(self.state.inspections)

    def _record_batch(self, tick: int) -> None:
        """Report a new material batch being opened. Its number only: never its quality."""
        batch = self.state.batch
        if batch is not None and batch.id != self._batch_reported:
            self._batch_reported = batch.id
            self.event_log.record(
                Event(
                    tick=tick,
                    machine_id=None,
                    kind="batch",
                    message=f"material batch {batch.id} opened",
                )
            )

    def _record_door(self, tick: int) -> None:
        """Report the loading door changing. A factory event: it belongs to no machine."""
        if self.state.door_open != self._last_door_open:
            self._last_door_open = self.state.door_open
            message = (
                "loading door opened" if self.state.door_open else "loading door closed"
            )
            self.event_log.record(
                Event(tick=tick, machine_id=None, kind="door", message=message)
            )

    def _warm_or_cool_machines(self) -> None:
        """Every machine drifts toward the temperature its work, wear and the air call for."""
        for machine in self.state.machines.values():
            warm_or_cool(machine, self.state.air_temperature, self.thermal_lag_ticks)

    def _finish_maintenance(self, tick: int) -> None:
        """Return repaired machines to service with a new bearing."""
        for machine in self.state.machines.values():
            if (
                machine.maintenance_until is not None
                and tick >= machine.maintenance_until
            ):
                machine.maintenance_until = None
                finding = self._describe_old_bearing(machine.condition.bearing_health)
                machine.condition.bearing_health = 1.0
                machine.bearing_replaced_tick = tick
                machine.status = (
                    MachineStatus.IDLE
                )  # the line gives it work again next tick
                self.event_log.record(
                    Event(
                        tick=tick,
                        machine_id=machine.id,
                        kind="maintenance",
                        message=f"bearing replacement finished: old bearing {finding}",
                    )
                )

    def _describe_old_bearing(self, health: float) -> str:
        """What the technician can see once the old bearing is out of the machine.

        In words, not as a number: an inspection by eye, and only available
        after paying for the repair.
        """
        if health <= self.bearing_failure_health:
            return "had failed"
        if health < 0.5:
            return "badly worn"
        if health < 0.9:
            return "worn"
        return "in good condition"

    def _apply_consequences(self, tick: int) -> None:
        """What the factory's own physics does with the state scenarios left.

        Lives here, not in a scenario, so every cause of bearing damage
        ends the same way. The event reports the stop, never the reason.
        """
        for machine in self.state.machines.values():
            if (
                machine.status is MachineStatus.RUNNING
                and machine.condition.bearing_health <= self.bearing_failure_health
            ):
                machine.status = MachineStatus.DOWN
                self.event_log.record(
                    Event(
                        tick=tick,
                        machine_id=machine.id,
                        kind="status",
                        message="machine stopped",
                    )
                )
