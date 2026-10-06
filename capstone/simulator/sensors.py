from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from capstone.simulator.rng import RandomSource
from capstone.simulator.state import MachineState, MachineStatus


class SensorReading(BaseModel):
    """One observation. Immutable once produced."""

    model_config = ConfigDict(frozen=True)

    sensor: str
    machine_id: str
    tick: int
    value: float
    unit: str


class Sensor(ABC):
    """Reads reality, emits evidence. Never writes to the machine.

    Each sensor owns one RNG stream named `sensor.<machine_id>.<name>`.
    That name is part of the seed; it is a frozen contract.
    """

    name: str
    unit: str

    def __init__(self, machine_id: str, rng: RandomSource):
        self.machine_id = machine_id
        self.stream_name = f"sensor.{machine_id}.{self.name}"
        self._stream = rng.stream(self.stream_name)

    def read(self, machine: MachineState, tick: int) -> SensorReading:
        if machine.id != self.machine_id:
            raise ValueError(f"{self.stream_name} cannot read machine {machine.id}")
        return SensorReading(
            sensor=self.name,
            machine_id=machine.id,
            tick=tick,
            value=self._measure(machine),
            unit=self.unit,
        )

    @abstractmethod
    def _measure(self, machine: MachineState) -> float: ...


class VibrationSensor(Sensor):
    name = "vibration"
    unit = "mm/s"

    def __init__(
        self,
        machine_id: str,
        rng: RandomSource,
        *,
        baseline: float = 2.0,
        wear_gain: float = 6.0,
        noise_sd: float = 0.15,
        idle_floor: float = 0.1,
    ):
        super().__init__(machine_id, rng)
        self.baseline = baseline
        self.wear_gain = wear_gain
        self.noise_sd = noise_sd
        self.idle_floor = idle_floor

    def _measure(self, machine: MachineState) -> float:
        noise = self._stream.gauss(0.0, self.noise_sd)
        if machine.status is not MachineStatus.RUNNING:
            return max(0.0, self.idle_floor + noise)
        wear = 1.0 - machine.condition.bearing_health
        return max(0.0, self.baseline + self.wear_gain * wear**2 + noise)


class TemperatureSensor(Sensor):
    name = "temperature"
    unit = "°F"

    def __init__(
        self,
        machine_id: str,
        rng: RandomSource,
        *,
        baseline: float = 115.0,
        wear_gain: float = 45.0,
        noise_sd: float = 1.0,
        ambient: float = 72.0,
    ):
        super().__init__(machine_id, rng)
        self.baseline = baseline
        self.wear_gain = wear_gain
        self.noise_sd = noise_sd
        self.ambient = ambient

    def _measure(self, machine: MachineState) -> float:
        noise = self._stream.gauss(0.0, self.noise_sd)
        if machine.status is not MachineStatus.RUNNING:
            return self.ambient + noise
        wear = 1.0 - machine.condition.bearing_health
        return self.baseline + self.wear_gain * wear + noise
