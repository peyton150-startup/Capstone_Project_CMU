# The sensor models that turn true state into noisy readings.
# Responsibility: produce repeatable evidence without changing the state they read.
from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from capstone.simulator.rng import RandomSource
from capstone.simulator.state import (
    NORMAL_LOAD,
    FactoryState,
    MachineState,
    MachineStatus,
)


class SensorReading(BaseModel):
    """One observation. Immutable once produced."""

    model_config = ConfigDict(frozen=True)

    sensor: str
    machine_id: str | None  # None for a sensor that belongs to the factory
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
            value=self._measure(machine)
            + sum(
                effect.offset
                for effect in machine.sensor_effects.values()
                if effect.sensor == self.name
            ),
            unit=self.unit,
        )

    def available(self, machine: MachineState) -> bool:
        """Whether the instrument transmits this tick; no RNG is consumed here."""
        return not any(
            effect.missing
            for effect in machine.sensor_effects.values()
            if effect.sensor == self.name
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
        load_gain: float = 1.5,
        speed_gain: float = 2.0,
        noise_sd: float = 0.15,
        idle_floor: float = 0.1,
    ):
        super().__init__(machine_id, rng)
        self.baseline = baseline
        self.wear_gain = wear_gain
        self.load_gain = load_gain
        self.speed_gain = speed_gain
        self.noise_sd = noise_sd
        self.idle_floor = idle_floor

    def _measure(self, machine: MachineState) -> float:
        noise = (
            self._stream.gauss(0.0, self.noise_sd)
            + machine.condition.vibration_sensor_offset
        )
        if machine.status is not MachineStatus.RUNNING:
            return max(0.0, self.idle_floor + noise)
        wear = 1.0 - machine.condition.bearing_health
        work = self.load_gain * (machine.load - NORMAL_LOAD)
        speed = self.speed_gain * (machine.speed_ratio - 1.0)
        return max(0.0, self.baseline + work + speed + self.wear_gain * wear**2 + noise)


class TemperatureSensor(Sensor):
    """Reads the machine's real temperature. What makes a machine warm is in thermal.py."""

    name = "temperature"
    unit = "°F"

    def __init__(self, machine_id: str, rng: RandomSource, *, noise_sd: float = 1.0):
        super().__init__(machine_id, rng)
        self.noise_sd = noise_sd

    def _measure(self, machine: MachineState) -> float:
        return machine.temperature + self._stream.gauss(0.0, self.noise_sd)


class LoadSensor(Sensor):
    """Reports how hard the motor is working, as a percentage.

    Mostly the workload, plus a little friction from a worn bearing. The
    friction shows up here, in the reading, and never in `load` itself.
    """

    name = "load"
    unit = "%"

    def __init__(
        self,
        machine_id: str,
        rng: RandomSource,
        *,
        friction_gain: float = 8.0,
        noise_sd: float = 2.0,
    ):
        super().__init__(machine_id, rng)
        self.friction_gain = friction_gain
        self.noise_sd = noise_sd

    def _measure(self, machine: MachineState) -> float:
        noise = self._stream.gauss(0.0, self.noise_sd)
        if machine.status is not MachineStatus.RUNNING:
            return max(0.0, noise)
        wear = 1.0 - machine.condition.bearing_health
        return max(0.0, 100.0 * machine.load + self.friction_gain * wear**2 + noise)


class PowerSensor(Sensor):
    """The machine's electrical power demand right now, in kilowatts.

    A whole-machine meter, not an electrical model. Three hidden causes add up:

    - stopped (down, locked out for repair or broken): about nothing;
    - idle: `idle_kw` for controls, coolant pump and an idling spindle drive;
    - running: idle draw plus spindle power, `spindle_kw` x load x speed ratio
      (cutting power is torque times speed, so the same work at a higher
      speed draws more), plus `friction_kw` x wear squared from a worn bearing,
      plus `drive_kw` x axis wear squared from a worn axis servo drive (a
      worn drive draws more current for the same moves).

    kW is instantaneous; energy (kWh) is kW summed over simulated time, and
    is not a reading. Power reads the same hidden load and wear as
    `LoadSensor`, so the two move together: they are correlated evidence,
    not two independent witnesses. What power adds is the speed: a wrong
    setting changes power at the same load, which the load reading does not show.
    The defaults are working assumptions for a mid-size CNC mill, not
    measured values (docs/MVP_SCOPE.md, Future Work 8 B).
    """

    name = "power"
    unit = "kW"

    def __init__(
        self,
        machine_id: str,
        rng: RandomSource,
        *,
        idle_kw: float = 2.0,
        spindle_kw: float = 15.0,
        friction_kw: float = 1.5,
        drive_kw: float = 1.0,
        noise_sd: float = 0.2,
    ):
        super().__init__(machine_id, rng)
        self.idle_kw = idle_kw
        self.spindle_kw = spindle_kw
        self.friction_kw = friction_kw
        self.drive_kw = drive_kw
        self.noise_sd = noise_sd

    def _measure(self, machine: MachineState) -> float:
        noise = self._stream.gauss(0.0, self.noise_sd)
        if machine.status is MachineStatus.DOWN:
            return max(0.0, noise)
        if machine.status is MachineStatus.IDLE:
            return max(0.0, self.idle_kw + noise)
        wear = 1.0 - machine.condition.bearing_health
        axis_wear = 1.0 - machine.condition.axis_health
        spindle = self.spindle_kw * machine.load * machine.speed_ratio
        return max(
            0.0,
            self.idle_kw
            + spindle
            + self.friction_kw * wear**2
            + self.drive_kw * axis_wear**2
            + noise,
        )


class FollowingErrorSensor(Sensor):
    """How far the feed axis lags behind its commanded position, in micrometres.

    The servo controller measures this itself on every move. A healthy drive
    keeps it small; it grows a little with a heavy cut or a faster setting,
    and a lot with a worn drive (`wear_gain` x axis wear squared). While the
    machine is idle or stopped the drive only holds the axis still.
    """

    name = "following_error"
    unit = "µm"

    def __init__(
        self,
        machine_id: str,
        rng: RandomSource,
        *,
        baseline: float = 4.0,
        load_gain: float = 4.0,
        speed_gain: float = 6.0,
        wear_gain: float = 40.0,
        holding: float = 1.0,
        noise_sd: float = 0.6,
    ):
        super().__init__(machine_id, rng)
        self.baseline = baseline
        self.load_gain = load_gain
        self.speed_gain = speed_gain
        self.wear_gain = wear_gain
        self.holding = holding
        self.noise_sd = noise_sd

    def _measure(self, machine: MachineState) -> float:
        noise = self._stream.gauss(0.0, self.noise_sd)
        if machine.status is not MachineStatus.RUNNING:
            return max(0.0, self.holding + noise)
        wear = 1.0 - machine.condition.axis_health
        work = self.load_gain * (machine.load - NORMAL_LOAD)
        speed = self.speed_gain * (machine.speed_ratio - 1.0)
        return max(0.0, self.baseline + work + speed + self.wear_gain * wear**2 + noise)


class HydraulicPressureSensor(Sensor):
    """The hydraulic system's pressure, in bar. Only on machines that have hydraulics.

    The pump holds about `nominal` bar whenever the machine is powered; a leak
    costs `leak_gain` x leak squared (early seepage barely shows). Cutting
    draws a little on it. With the machine down the hydraulic unit and its
    transducer are switched off, so nothing is sent (`available`): a stopped
    machine is not a pressure loss, and must not trip the low-pressure alarm.
    """

    name = "hydraulic_pressure"
    unit = "bar"

    def __init__(
        self,
        machine_id: str,
        rng: RandomSource,
        *,
        nominal: float = 70.0,
        leak_gain: float = 40.0,
        cutting_draw: float = 2.0,
        noise_sd: float = 0.8,
    ):
        super().__init__(machine_id, rng)
        self.nominal = nominal
        self.leak_gain = leak_gain
        self.cutting_draw = cutting_draw
        self.noise_sd = noise_sd

    def _measure(self, machine: MachineState) -> float:
        noise = self._stream.gauss(0.0, self.noise_sd)
        if machine.status is MachineStatus.DOWN:
            return max(0.0, noise)
        leak = 1.0 - machine.condition.hydraulic_health
        running = machine.status is MachineStatus.RUNNING
        cutting = self.cutting_draw * machine.load if running else 0.0
        return max(0.0, self.nominal - self.leak_gain * leak**2 - cutting + noise)

    def available(self, machine: MachineState) -> bool:
        """Off while the machine is down; otherwise as any instrument (dropouts)."""
        return machine.status is not MachineStatus.DOWN and super().available(machine)


class FactoryThermometer:
    """Measures the air in the factory. Belongs to no machine.

    Reads `air_temperature`, so it shows the daily cycle and the loading
    door alike. Its stream is `sensor.factory.air_temperature`.
    """

    name = "air_temperature"
    unit = "°F"

    def __init__(self, rng: RandomSource, *, noise_sd: float = 0.3):
        self.noise_sd = noise_sd
        self.stream_name = f"sensor.factory.{self.name}"
        self._stream = rng.stream(self.stream_name)

    def read(self, state: FactoryState, tick: int) -> SensorReading:
        value = state.air_temperature + self._stream.gauss(0.0, self.noise_sd)
        return SensorReading(
            sensor=self.name, machine_id=None, tick=tick, value=value, unit=self.unit
        )
