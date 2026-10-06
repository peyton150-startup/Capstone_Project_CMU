from abc import ABC, abstractmethod

from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.rng import RandomSource
from capstone.simulator.state import FactoryState, MachineStatus


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
    def ground_truth(self) -> GroundTruth:
        """The real story, from this scenario's own settings, not from state."""


class BearingDegradation(Scenario):
    """Wears one machine's bearing from `start_tick` on, while it runs.

    Changes `bearing_health` and nothing else. It knows nothing about
    vibration or any other sensor: the symptoms come from sensors reading
    the health it lowers.
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

    def apply(self, state: FactoryState, tick: int) -> None:
        if tick < self.start_tick:
            return
        # Drawn before the status check so the stream's position depends
        # only on ticks since start, not on the machine's status history.
        loss = self.rate * self._stream.uniform(1.0 - self.variation, 1.0 + self.variation)
        machine = state.machines[self.machine_id]
        if machine.status is not MachineStatus.RUNNING:
            return
        machine.condition.bearing_health = max(0.0, machine.condition.bearing_health - loss)

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="bearing_degradation",
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )
