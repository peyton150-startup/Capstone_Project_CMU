from datetime import datetime

import pytest

from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.scenarios import Scenario
from capstone.simulator.sensors import VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState

START = datetime(2026, 1, 5, 6, 0)


class SetHealthAt(Scenario):
    """Test stand-in: one sudden change to one machine at one tick."""

    def __init__(self, name, rng, *, machine_id, at_tick, health):
        super().__init__(name, rng)
        self.machine_id, self.at_tick, self.health = machine_id, at_tick, health

    def apply(self, state, tick):
        if tick == self.at_tick:
            state.machines[self.machine_id].condition.bearing_health = self.health

    def ground_truth(self):
        return GroundTruth(scenario=self.name, fault="test", machine_id=self.machine_id, start_tick=self.at_tick)


class RandomWear(Scenario):
    """Test stand-in: wear by a random amount each tick, from its own stream."""

    def apply(self, state, tick):
        state.machines["CNC-04"].condition.bearing_health -= self._stream.uniform(0.0, 0.01)

    def ground_truth(self):
        return GroundTruth(scenario=self.name, fault="test", machine_id="CNC-04", start_tick=1)


def factory(seed: int = 42) -> Simulator:
    sim = Simulator(seed, START)
    sim.add_machine(MachineState(id="CNC-04"))
    sim.add_sensor(VibrationSensor("CNC-04", sim.rng, noise_sd=0.0))
    return sim


def values(sim: Simulator) -> dict[int, float]:
    return {r.tick: r.value for r in sim.readings}


def test_scenario_is_abstract():
    with pytest.raises(TypeError):
        Scenario("x", factory().rng)


def test_stream_name_follows_the_frozen_convention():
    sim = factory()
    assert RandomWear("wear", sim.rng).stream_name == "scenario.wear"


def test_duplicate_scenario_name_is_rejected():
    sim = factory()
    sim.add_scenario(RandomWear("wear", sim.rng))
    with pytest.raises(ValueError):
        sim.add_scenario(RandomWear("wear", sim.rng))


def test_scenario_changes_reality_and_the_sensor_reports_it_the_same_tick():
    sim = factory()
    sim.add_scenario(SetHealthAt("drop", sim.rng, machine_id="CNC-04", at_tick=3, health=0.2))
    for _ in range(3):
        sim.step()
    assert values(sim)[2] == pytest.approx(2.0)
    assert values(sim)[3] == pytest.approx(2.0 + 6.0 * 0.8**2)
    assert sim.state.machines["CNC-04"].condition.bearing_health == 0.2


def test_scenario_adds_no_readings_of_its_own():
    sim = factory()
    sim.add_scenario(SetHealthAt("drop", sim.rng, machine_id="CNC-04", at_tick=1, health=0.2))
    for _ in range(5):
        sim.step()
    assert [r.tick for r in sim.readings] == [1, 2, 3, 4, 5]


def test_scenarios_apply_in_the_order_they_were_added():
    sim = factory()
    sim.add_scenario(SetHealthAt("first", sim.rng, machine_id="CNC-04", at_tick=1, health=0.2))
    sim.add_scenario(SetHealthAt("second", sim.rng, machine_id="CNC-04", at_tick=1, health=0.9))
    sim.step()
    assert sim.state.machines["CNC-04"].condition.bearing_health == 0.9


def test_same_seed_gives_identical_scenario_history():
    def history(seed):
        sim = factory(seed)
        sim.add_scenario(RandomWear("wear", sim.rng))
        for _ in range(50):
            sim.step()
        return sim.readings

    assert history(42) == history(42)
    assert history(42) != history(43)
