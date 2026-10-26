"""Instrument faults change hidden state; sensors alone produce observations."""

from math import isfinite

from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import Scenario
from capstone.simulator.state import FactoryState, SensorEffect


class _SensorDisturbance(Scenario):
    """Own a finite window and one hidden contribution, never a reading or event."""

    fault: str

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_id: str,
        sensor: str,
        start_tick: int,
        duration: int,
    ):
        if not name.strip() or not machine_id.strip():
            raise ValueError("name and machine_id must be nonempty")
        if sensor not in (
            "vibration",
            "temperature",
            "load",
            "power",
            "following_error",
            "hydraulic_pressure",
        ):
            raise ValueError(
                "sensor must be vibration, temperature, load, power, following_error "
                "or hydraulic_pressure"
            )
        if type(start_tick) is not int or start_tick < 0:
            raise ValueError("start_tick must be a nonnegative integer")
        if type(duration) is not int or duration < 1:
            raise ValueError("duration must be a positive integer")
        super().__init__(name, rng)
        self.machine_id, self.sensor = machine_id, sensor
        self.start_tick, self.duration = start_tick, duration

    def apply(self, state: FactoryState, tick: int) -> None:
        effects = state.machines[self.machine_id].sensor_effects
        if self.start_tick <= tick < self.start_tick + self.duration:
            effects[self.stream_name] = self._effect(tick - self.start_tick + 1)
        else:
            effects.pop(self.stream_name, None)

    def _effect(self, elapsed: int) -> SensorEffect:
        raise NotImplementedError

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault=self.fault,
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )


class SensorDrift(_SensorDisturbance):
    """Calibration bias grows by per_tick each tick, then clears at window end."""

    fault = "sensor_drift"

    def __init__(self, name: str, rng: RandomSource, *, per_tick: float, **window):
        if not isfinite(per_tick) or per_tick == 0:
            raise ValueError("per_tick must be finite and nonzero")
        super().__init__(name, rng, **window)
        self.per_tick = per_tick

    def _effect(self, elapsed: int) -> SensorEffect:
        return SensorEffect(sensor=self.sensor, offset=self.per_tick * elapsed)


class TransientAnomaly(_SensorDisturbance):
    """Temporary instrument bias; no damage, physical change or repair required."""

    fault = "false_alarm"

    def __init__(self, name: str, rng: RandomSource, *, offset: float, **window):
        if not isfinite(offset) or offset == 0:
            raise ValueError("offset must be finite and nonzero")
        super().__init__(name, rng, **window)
        self.offset = offset

    def _effect(self, elapsed: int) -> SensorEffect:
        return SensorEffect(sensor=self.sensor, offset=self.offset)


class SensorDropout(_SensorDisturbance):
    """Signal loss removes samples; it never invents a zero or changes reality."""

    fault = "sensor_dropout"

    def _effect(self, elapsed: int) -> SensorEffect:
        return SensorEffect(sensor=self.sensor, missing=True)
