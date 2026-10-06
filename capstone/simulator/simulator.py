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
from capstone.simulator.sensors import Sensor, SensorReading
from capstone.simulator.state import FactoryState, MachineState, MachineStatus


class Simulator:
    """Owns the parts and the one legal way to move the world forward."""

    def __init__(
        self,
        seed: int,
        start: datetime,
        tick_duration: timedelta = timedelta(minutes=1),
        *,
        bearing_failure_health: float = 0.1,
    ):
        self.bearing_failure_health = bearing_failure_health
        self.clock = SimulationClock(start, tick_duration)
        self.rng = RandomSource(seed)
        self.state = FactoryState()
        self._sensors: list[Sensor] = []
        self._readings: list[SensorReading] = []
        self.event_log = EventLog()
        self._alarms: list[ThresholdAlarm] = []
        self._scenarios: list[Scenario] = []

    def add_machine(self, machine: MachineState) -> None:
        self.state.add(machine)

    def add_sensor(self, sensor: Sensor) -> None:
        if sensor.machine_id not in self.state.machines:
            raise ValueError(f"{sensor.stream_name}: no machine {sensor.machine_id}")
        if any(s.stream_name == sensor.stream_name for s in self._sensors):
            raise ValueError(f"{sensor.stream_name} already exists")
        self._sensors.append(sensor)

    def add_alarm(self, alarm: ThresholdAlarm) -> None:
        self._alarms.append(alarm)

    def add_scenario(self, scenario: Scenario) -> None:
        if any(s.stream_name == scenario.stream_name for s in self._scenarios):
            raise ValueError(f"{scenario.stream_name} already exists")
        self._scenarios.append(scenario)

    def ground_truth(self) -> tuple[GroundTruth, ...]:
        """The answer key, one record per scenario. For evaluation only, never tools."""
        return tuple(s.ground_truth() for s in self._scenarios)

    @property
    def readings(self) -> tuple[SensorReading, ...]:
        """Every reading so far, oldest first."""
        return tuple(self._readings)

    def step(self) -> list[SensorReading]:
        """Advance one tick: clock, reality, consequences, observation, alarms.

        The order is a contract: a reading stamped tick T is evidence of
        reality as of tick T, never of T-1. Alarms see only the readings.
        """
        tick = self.clock.advance()
        self._update_reality(tick)
        self._apply_consequences(tick)
        readings = [s.read(self.state.machines[s.machine_id], tick) for s in self._sensors]
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
                    Event(tick=tick, machine_id=machine.id, kind="status", message="machine stopped")
                )
