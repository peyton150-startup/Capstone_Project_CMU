import math
from abc import ABC, abstractmethod

from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.rng import RandomSource
from capstone.simulator.state import NORMAL_LOAD, FactoryState, MachineStatus


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


class Workload(Scenario):
    """Normal factory life: one machine's load changes in blocks of work.

    Stands in for jobs until they exist. Each new block raises the
    machine's job number; the simulator reports that as an event. Not a
    fault, so it declares no ground truth. Add it before any scenario that reads `load`, so that
    scenario sees this tick's load rather than the last one's.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_id: str,
        min_block: int = 30,
        max_block: int = 90,
        min_load: float = 0.3,
        max_load: float = 0.8,
    ):
        if not 1 <= min_block <= max_block:
            raise ValueError("need 1 <= min_block <= max_block")
        if not 0.0 <= min_load <= max_load <= 1.0:
            raise ValueError("need 0 <= min_load <= max_load <= 1")
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.min_block, self.max_block = min_block, max_block
        self.min_load, self.max_load = min_load, max_load
        self._next_change = 1

    def apply(self, state: FactoryState, tick: int) -> None:
        if tick < self._next_change:
            return
        machine = state.machines[self.machine_id]
        if machine.status is not MachineStatus.RUNNING:
            return  # no new work on a machine that is not running; resumes when it is
        machine.load = self._stream.uniform(self.min_load, self.max_load)
        machine.job_number += 1
        self._next_change = tick + self._stream.randint(self.min_block, self.max_block)

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
