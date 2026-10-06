from datetime import datetime

import pytest

from capstone.simulator.sensors import LoadSensor, TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineCondition, MachineState, MachineStatus
from capstone.simulator.thermal import settle, settling_temperature, warm_or_cool

START = datetime(2026, 1, 5, 6, 0)
LAG = 20.0


def machine(load: float = 0.5, health: float = 1.0, status: MachineStatus = MachineStatus.RUNNING) -> MachineState:
    return MachineState(id="CNC-04", status=status, load=load, condition=MachineCondition(bearing_health=health))


def factory(load: float = 0.4, lag: float = LAG) -> Simulator:
    sim = Simulator(42, START, thermal_lag_ticks=lag)
    sim.add_machine(machine(load=load))
    for sensor in (TemperatureSensor, VibrationSensor, LoadSensor):
        sim.add_sensor(sensor("CNC-04", sim.rng, noise_sd=0.0))
    return sim


def temperatures(sim: Simulator, ticks: int) -> list[float]:
    seen = []
    for _ in range(ticks):
        sim.step()
        seen.append(sim.state.machines["CNC-04"].temperature)
    return seen


def test_where_a_machine_settles_depends_on_air_work_and_wear():
    assert settling_temperature(machine(), 72.0) == pytest.approx(115.0)
    assert settling_temperature(machine(load=0.9), 72.0) == pytest.approx(127.0)
    assert settling_temperature(machine(health=0.7), 72.0) == pytest.approx(128.5)
    assert settling_temperature(machine(), 78.0) == pytest.approx(121.0)


def test_a_machine_that_is_not_running_settles_at_the_air_temperature():
    for status in (MachineStatus.IDLE, MachineStatus.DOWN):
        assert settling_temperature(machine(load=0.9, health=0.2, status=status), 68.0) == 68.0


def test_a_machine_added_to_the_factory_starts_already_warmed_up():
    sim = factory(load=0.9)
    assert sim.state.machines["CNC-04"].temperature == pytest.approx(127.0)


def test_lag_below_one_tick_is_refused():
    with pytest.raises(ValueError):
        Simulator(42, START, thermal_lag_ticks=0.5)


def test_with_a_lag_of_one_the_change_is_immediate():
    sim = factory(lag=1.0)
    sim.state.machines["CNC-04"].load = 0.8
    assert temperatures(sim, 1) == pytest.approx([124.0])


def test_each_tick_closes_one_twentieth_of_the_gap():
    m = settle(machine(load=0.4), 72.0)
    m.load = 0.8
    warm_or_cool(m, 72.0, LAG)
    assert m.temperature == pytest.approx(112.0 + 12.0 / 20.0)


def test_a_heavier_job_warms_the_machine_gradually_and_never_overshoots():
    sim = factory(load=0.4)
    assert temperatures(sim, 30) == pytest.approx([112.0] * 30)
    sim.state.machines["CNC-04"].load = 0.8
    after = temperatures(sim, 120)
    assert after[0] == pytest.approx(112.6)
    assert after[19] == pytest.approx(112.0 + 12.0 * (1 - 0.95**20))  # about two thirds of the way
    assert 123.0 < after[59] < 124.0
    assert all(b > a for a, b in zip(after, after[1:]))
    assert max(after) < 124.0


def test_after_heavy_work_the_machine_stays_warm_at_a_light_load():
    sim = factory(load=0.8)
    temperatures(sim, 10)
    sim.state.machines["CNC-04"].load = 0.4
    after = temperatures(sim, 60)
    settled_for_this_load = 112.0
    assert after[19] - settled_for_this_load > 4.0
    assert after[59] - settled_for_this_load < 1.0


def test_a_stopped_machine_cools_gradually_to_the_air():
    sim = factory(load=0.5)
    sim.state.machines["CNC-04"].status = MachineStatus.DOWN
    after = temperatures(sim, 150)
    assert after[0] == pytest.approx(115.0 - 43.0 / 20.0)
    assert all(b < a for a, b in zip(after, after[1:]))
    assert after[-1] == pytest.approx(72.0, abs=0.1)


def test_the_sensor_reports_the_machines_temperature_and_does_not_change_it():
    sim = factory(load=0.4)
    sim.state.machines["CNC-04"].load = 0.8
    for _ in range(25):
        readings = {r.sensor: r.value for r in sim.step()}
        assert readings["temperature"] == sim.state.machines["CNC-04"].temperature


def test_vibration_and_load_still_respond_at_once():
    sim = factory(load=0.4)
    sim.step()
    sim.state.machines["CNC-04"].load = 0.8
    readings = {r.sensor: r.value for r in sim.step()}
    assert readings["vibration"] == pytest.approx(2.0 + 1.5 * 0.3)
    assert readings["load"] == pytest.approx(80.0)
    assert readings["temperature"] == pytest.approx(112.6)


def test_same_setup_gives_the_same_temperatures():
    def history():
        sim = factory(load=0.4)
        sim.state.machines["CNC-04"].load = 0.8
        return temperatures(sim, 100)

    assert history() == history()
