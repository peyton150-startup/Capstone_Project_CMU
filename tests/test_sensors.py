import pytest
from pydantic import ValidationError

from capstone.simulator.rng import RandomSource
from capstone.simulator.sensors import SensorReading, VibrationSensor
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus


def machine(health: float = 1.0, status: MachineStatus = MachineStatus.RUNNING) -> MachineState:
    return MachineState(id="CNC-04", status=status, condition=MachineCondition(bearing_health=health))


def exact_sensor(seed: int = 42) -> VibrationSensor:
    return VibrationSensor("CNC-04", RandomSource(seed), noise_sd=0.0)


def test_reading_carries_identity_tick_and_unit():
    r = VibrationSensor("CNC-04", RandomSource(42)).read(machine(), tick=17)
    assert (r.sensor, r.machine_id, r.tick, r.unit) == ("vibration", "CNC-04", 17, "mm/s")


def test_stream_name_follows_the_frozen_convention():
    assert VibrationSensor("CNC-04", RandomSource(42)).stream_name == "sensor.CNC-04.vibration"


def test_same_seed_gives_identical_reading_history():
    def history(seed):
        s, m = VibrationSensor("CNC-04", RandomSource(seed)), machine(0.8)
        return [s.read(m, t).value for t in range(50)]

    assert history(42) == history(42)
    assert history(42) != history(43)


def test_noise_makes_consecutive_readings_differ_for_identical_state():
    s, m = VibrationSensor("CNC-04", RandomSource(42)), machine()
    assert s.read(m, 0).value != s.read(m, 1).value


def test_more_wear_means_more_vibration():
    s = exact_sensor()
    values = [s.read(machine(h), 0).value for h in (1.0, 0.9, 0.7, 0.5, 0.3, 0.1)]
    assert values == sorted(values)
    assert values[0] < values[-1]


def test_wear_curve_accelerates():
    s = exact_sensor()
    early = s.read(machine(0.9), 0).value - s.read(machine(1.0), 0).value
    late = s.read(machine(0.3), 0).value - s.read(machine(0.4), 0).value
    assert late > early


def test_stopped_machine_barely_vibrates_regardless_of_wear():
    s = exact_sensor()
    worn_but_down = s.read(machine(0.2, MachineStatus.DOWN), 0).value
    healthy_running = s.read(machine(1.0), 0).value
    assert worn_but_down < healthy_running


def test_reading_never_goes_negative():
    s, m = VibrationSensor("CNC-04", RandomSource(42), noise_sd=1.0), machine(1.0, MachineStatus.IDLE)
    assert all(s.read(m, t).value >= 0.0 for t in range(500))


def test_sensor_does_not_mutate_the_machine():
    s, m = VibrationSensor("CNC-04", RandomSource(42)), machine(0.6)
    before = m.model_dump()
    for t in range(20):
        s.read(m, t)
    assert m.model_dump() == before


def test_sensor_refuses_a_machine_it_is_not_attached_to():
    s = VibrationSensor("CNC-04", RandomSource(42))
    with pytest.raises(ValueError):
        s.read(MachineState(id="CNC-02"), 0)


def test_reading_is_immutable():
    r = VibrationSensor("CNC-04", RandomSource(42)).read(machine(), 0)
    with pytest.raises(ValidationError):
        r.value = 99.0
    assert isinstance(r, SensorReading)
