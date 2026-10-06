from datetime import datetime

import pytest

from capstone.simulator.rng import RandomSource
from capstone.simulator.scenarios import AmbientTemperature, BearingDegradation, LoadingDoor
from capstone.simulator.sensors import FactoryThermometer, TemperatureSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import FactoryState, MachineState
from capstone.tools.observation import ObservationTools

START = datetime(2026, 1, 5, 6, 0)
DAY = 1440


def factory(thermometer: bool = True, fault: bool = False, noise_sd: float = 0.0) -> Simulator:
    sim = Simulator(42, START)
    sim.add_scenario(AmbientTemperature("ambient", sim.rng))
    sim.add_scenario(LoadingDoor("door", sim.rng))
    for machine_id in ("CNC-01", "CNC-04"):
        sim.add_machine(MachineState(id=machine_id))
        sim.add_sensor(TemperatureSensor(machine_id, sim.rng, noise_sd=noise_sd))
    if thermometer:
        sim.add_factory_sensor(FactoryThermometer(sim.rng, noise_sd=noise_sd))
    if fault:
        sim.add_scenario(BearingDegradation("bearing", sim.rng, machine_id="CNC-04", start_tick=100, rate=0.0005))
    return sim


def run(sim: Simulator, ticks: int = DAY) -> Simulator:
    for _ in range(ticks):
        sim.step()
    return sim


def own_heat(tools: ObservationTools, machine_id: str) -> list[float]:
    """Machine temperature minus the thermometer, tick by tick, as the agent would work it out."""
    air = {r["tick"]: r["value"] for r in tools.get_factory_readings("air_temperature", 0, DAY)}
    return [r["value"] - air[r["tick"]] for r in tools.get_readings(machine_id, "temperature", 0, DAY)]


def test_the_thermometer_belongs_to_the_factory_and_has_its_own_stream():
    thermometer = FactoryThermometer(RandomSource(42), noise_sd=0.0)
    reading = thermometer.read(FactoryState(ambient_temperature=75.0), tick=9)
    assert (reading.sensor, reading.machine_id, reading.tick, reading.unit) == ("air_temperature", None, 9, "°F")
    assert thermometer.stream_name == "sensor.factory.air_temperature"


def test_it_reads_the_air_including_the_door_cooling():
    state = FactoryState(ambient_temperature=75.0, door_open=True, door_cooling=4.0)
    assert FactoryThermometer(RandomSource(42), noise_sd=0.0).read(state, 0).value == pytest.approx(71.0)


def test_its_noise_is_small_and_repeatable():
    def readings(seed):
        thermometer = FactoryThermometer(RandomSource(seed))
        return [thermometer.read(FactoryState(), t).value for t in range(200)]

    assert readings(42) == readings(42) != readings(43)
    assert all(abs(v - 72.0) < 1.5 for v in readings(42))


def test_a_second_thermometer_is_refused():
    sim = factory()
    with pytest.raises(ValueError):
        sim.add_factory_sensor(FactoryThermometer(sim.rng))


def test_adding_the_thermometer_leaves_every_machine_reading_untouched():
    def machine_readings(sim):
        return [r for r in run(sim).readings if r.machine_id is not None]

    assert machine_readings(factory(thermometer=True, noise_sd=1.0)) == machine_readings(
        factory(thermometer=False, noise_sd=1.0)
    )


def test_one_reading_per_tick_follows_the_air_through_the_day():
    sim = run(factory())
    values = [r.value for r in sim.readings if r.sensor == "air_temperature"]
    assert len(values) == DAY
    assert values[-1] == pytest.approx(sim.state.air_temperature)
    assert max(values) - min(values) > 6.0


def test_the_machine_tool_cannot_return_the_thermometer():
    tools = ObservationTools(run(factory(), 50))
    for machine in tools.list_machines():
        assert tools.get_readings(machine["machine_id"], "air_temperature", 0, 50) == []
    with pytest.raises(ValueError):
        tools.get_readings(None, "air_temperature", 0, 50)


def test_the_agent_reads_it_through_get_factory_readings():
    tools = ObservationTools(run(factory(), 50))
    got = tools.get_factory_readings("air_temperature", 10, 12)
    assert [r["tick"] for r in got] == [10, 11, 12]
    assert set(got[0]) == {"tick", "sensor", "value", "unit"}
    assert tools.get_factory_readings("humidity", 0, 50) == []
    assert tools.get_factory_readings("temperature", 0, 50) == []


def test_a_healthy_machines_own_heat_is_43_degrees_all_day_whatever_the_air_does():
    tools = ObservationTools(run(factory()))
    assert own_heat(tools, "CNC-01") == pytest.approx([43.0] * DAY)


def test_wear_shows_as_own_heat_climbing_above_43():
    sim = run(factory(fault=True))
    heat = own_heat(ObservationTools(sim), "CNC-04")
    assert heat[50] == pytest.approx(43.0)
    assert heat[400] < heat[800] < heat[1200]
    wear = 1.0 - sim.state.machines["CNC-04"].condition.bearing_health
    assert heat[-1] == pytest.approx(43.0 + 45.0 * wear, abs=0.1)
