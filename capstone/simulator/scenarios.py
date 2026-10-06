import math
from abc import ABC, abstractmethod

from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.rng import RandomSource
from capstone.simulator.state import NORMAL_LOAD, FactoryState, Job, MachineStatus


class Scenario(ABC):
    """Changes reality over time. Never writes evidence.

    `apply` is handed the factory state and the tick, nothing else, so a
    scenario cannot reach the reading log or the event log. Whatever it
    causes becomes visible only when sensors read the state it changed.

    Each scenario owns one RNG stream named `scenario.<name>`. That name
    is part of the seed; it is a frozen contract.
    """

    def __init__(self, name: str, rng: RandomSource):
        self.name = name
        self.stream_name = f"scenario.{name}"
        self._stream = rng.stream(self.stream_name)

    @abstractmethod
    def apply(self, state: FactoryState, tick: int) -> None: ...

    @abstractmethod
    def ground_truth(self) -> GroundTruth | None:
        """The real story, from this scenario's own settings, not from state.

        None for normal factory life that is not a fault.
        """


class BearingDegradation(Scenario):
    """Wears one machine's bearing from `start_tick` on, while it runs.

    Changes `bearing_health` and nothing else. It knows nothing about
    vibration or any other sensor: the symptoms come from sensors reading
    the health it lowers.

    Wear scales with (load / normal load) ** load_exponent; bearing life
    falls roughly with the cube of load. It reads `load`, never writes it.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_id: str,
        start_tick: int,
        rate: float,
        variation: float = 0.5,
        load_exponent: float = 3.0,
    ):
        if rate <= 0:
            raise ValueError("rate must be positive")
        if not 0.0 <= variation < 1.0:
            raise ValueError("variation must be in [0, 1)")
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.start_tick = start_tick
        self.rate = rate
        self.variation = variation
        self.load_exponent = load_exponent

    def apply(self, state: FactoryState, tick: int) -> None:
        if tick < self.start_tick:
            return
        # Drawn before the status check so the stream's position depends
        # only on ticks since start, not on the machine's status history.
        loss = self.rate * self._stream.uniform(1.0 - self.variation, 1.0 + self.variation)
        machine = state.machines[self.machine_id]
        if machine.status is not MachineStatus.RUNNING:
            return
        loss *= (machine.load / NORMAL_LOAD) ** self.load_exponent
        machine.condition.bearing_health = max(0.0, machine.condition.bearing_health - loss)

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="bearing_degradation",
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )


class ProductionLine(Scenario):
    """Normal factory life: jobs enter at the first machine and move down the line.

    Each tick, in two passes. Movement, from the last machine back to the
    first: a finished job moves on if the next machine is free and not
    down, or leaves the line at the end; a new job enters whenever the
    first machine is free. Then work: a machine with unfinished work runs
    at its job's load, and any other machine is idle. A machine that is
    down is left alone and keeps its job, which blocks everything behind
    it. Not a fault, so no ground truth.

    Add it before any scenario that reads `load` or status, so that
    scenario sees this tick's work.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_ids: list[str],
        min_ticks: int = 30,
        max_ticks: int = 90,
        min_load: float = 0.3,
        max_load: float = 0.8,
    ):
        if not machine_ids or len(set(machine_ids)) != len(machine_ids):
            raise ValueError("the line needs at least one machine, each listed once")
        if not 1 <= min_ticks <= max_ticks:
            raise ValueError("need 1 <= min_ticks <= max_ticks")
        if not 0.0 <= min_load <= max_load <= 1.0:
            raise ValueError("need 0 <= min_load <= max_load <= 1")
        super().__init__(name, rng)
        self.machine_ids = list(machine_ids)
        self.min_ticks, self.max_ticks = min_ticks, max_ticks
        self.min_load, self.max_load = min_load, max_load
        self._next_job_id = 1

    def apply(self, state: FactoryState, tick: int) -> None:
        line = [state.machines[machine_id] for machine_id in self.machine_ids]
        self._move_jobs(state, line)
        for machine in line:
            if machine.status is MachineStatus.DOWN:
                continue
            if machine.job is not None and machine.job_progress < machine.job.ticks_per_machine:
                machine.status = MachineStatus.RUNNING
                machine.load = machine.job.load
                machine.job_progress += 1
            else:
                machine.status = MachineStatus.IDLE
                machine.load = 0.0

    def _move_jobs(self, state: FactoryState, line: list) -> None:
        for position in reversed(range(len(line))):
            machine = line[position]
            if machine.status is MachineStatus.DOWN or machine.job is None:
                continue
            if machine.job_progress < machine.job.ticks_per_machine:
                continue
            if position == len(line) - 1:
                state.completed_jobs.append(machine.job.id)
            else:
                following = line[position + 1]
                if following.job is not None or following.status is MachineStatus.DOWN:
                    continue  # nowhere to go: the finished job waits here
                following.job, following.job_progress = machine.job, 0
            machine.job, machine.job_progress = None, 0
        first = line[0]
        if first.job is None and first.status is not MachineStatus.DOWN:
            first.job = Job(
                id=self._next_job_id,
                load=self._stream.uniform(self.min_load, self.max_load),
                ticks_per_machine=self._stream.randint(self.min_ticks, self.max_ticks),
            )
            first.job_progress = 0
            self._next_job_id += 1

    def ground_truth(self) -> None:
        return None


class AmbientTemperature(Scenario):
    """Normal factory life: the air warms through the day and cools overnight.

    A daily cycle plus a slow drift, so no two days are quite alike. One
    value for the whole factory. Not a fault, so no ground truth.
    `warmest_tick` is the tick of the first afternoon peak; the default
    suits a run that starts at 6 am with one-minute ticks (peak at 4 pm).
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        mean: float = 73.0,
        swing: float = 4.5,
        ticks_per_day: int = 1440,
        warmest_tick: int = 600,
        drift_step: float = 0.03,
        drift_pull: float = 0.001,
    ):
        super().__init__(name, rng)
        self.mean, self.swing = mean, swing
        self.ticks_per_day, self.warmest_tick = ticks_per_day, warmest_tick
        self.drift_step, self.drift_pull = drift_step, drift_pull
        self._drift = 0.0

    def apply(self, state: FactoryState, tick: int) -> None:
        self._drift = (1.0 - self.drift_pull) * self._drift + self._stream.gauss(0.0, self.drift_step)
        time_of_day = 2.0 * math.pi * (tick - self.warmest_tick) / self.ticks_per_day
        state.ambient_temperature = self.mean + self.swing * math.cos(time_of_day) + self._drift

    def ground_truth(self) -> None:
        return None


class LoadingDoor(Scenario):
    """Normal factory life: the loading door opens now and then and lets cool air in.

    Always a cooling, whatever the season. It writes the door and the
    door's own cooling, never the building temperature, so it does not
    matter whether it runs before or after AmbientTemperature. Not a
    fault, so no ground truth.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        cooling: float = 5.0,
        chance_per_tick: float = 1 / 300,
        min_open: int = 5,
        max_open: int = 20,
        cool_per_tick: float = 0.5,
        recover_per_tick: float = 0.2,
    ):
        if not 1 <= min_open <= max_open:
            raise ValueError("need 1 <= min_open <= max_open")
        if cooling < 0 or not 0.0 <= chance_per_tick <= 1.0:
            raise ValueError("cooling must be >= 0 and chance_per_tick within 0..1")
        super().__init__(name, rng)
        self.cooling = cooling
        self.chance_per_tick = chance_per_tick
        self.min_open, self.max_open = min_open, max_open
        self.cool_per_tick, self.recover_per_tick = cool_per_tick, recover_per_tick
        self._closes_at = 0

    def apply(self, state: FactoryState, tick: int) -> None:
        # One draw every tick, so the stream's position depends only on the tick.
        opens = self._stream.random() < self.chance_per_tick
        if state.door_open:
            if tick >= self._closes_at:
                state.door_open = False
        elif opens:
            state.door_open = True
            self._closes_at = tick + self._stream.randint(self.min_open, self.max_open)
        if state.door_open:
            state.door_cooling = min(self.cooling, state.door_cooling + self.cool_per_tick)
        else:
            state.door_cooling = max(0.0, state.door_cooling - self.recover_per_tick)

    def ground_truth(self) -> None:
        return None
