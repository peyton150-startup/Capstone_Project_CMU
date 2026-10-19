import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.challenge import build_challenge
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools


def observe(seed):
    sim = build_challenge(seed, machines=3)
    provider = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim))
    results = []
    for name, arguments in (
        ("wait", {"ticks": 300}),
        ("list_machines", {}),
        ("get_settings", {}),
        ("get_events", {"from_tick": 0, "to_tick": 300}),
        ("get_inspections", {"from_tick": 0, "to_tick": 300}),
        (
            "get_sensor_summary",
            {
                "machine_id": "CNC-01",
                "sensor": "vibration",
                "from_tick": 0,
                "to_tick": 300,
            },
        ),
    ):
        result = provider.call(ToolRequest(name=name, arguments=arguments))
        assert result.success, result.error
        results.append(result)
    return sim, results


def test_challenge_is_replayable_through_unchanged_tools_and_keeps_truth_hidden():
    sim, first = observe(42)
    replay, second = observe(42)
    assert first == second
    assert sim.readings == replay.readings
    assert sim.ground_truth() == replay.ground_truth()
    assert {truth.fault for truth in sim.ground_truth()} == {
        "bearing_degradation",
        "wrong_setting",
        "false_alarm",
        "sensor_drift",
        "sensor_dropout",
    }
    for result in first:
        exposed = result.model_dump_json()
        for secret in ("sensor_effects", "per_tick", "bearing_health", "ground_truth"):
            assert secret not in exposed


def test_challenge_has_sparse_samples_and_self_ending_anomaly_alongside_real_faults():
    sim, _ = observe(42)
    truths = {truth.fault: truth for truth in sim.ground_truth()}
    assert (
        truths["bearing_degradation"].machine_id == truths["wrong_setting"].machine_id
    )
    assert truths["false_alarm"].machine_id != truths["bearing_degradation"].machine_id
    dropout = truths["sensor_dropout"]
    temperatures = [
        r
        for r in sim.readings
        if r.sensor == "temperature" and r.machine_id == dropout.machine_id
    ]
    ticks = {r.tick for r in temperatures}
    assert dropout.start_tick not in ticks
    assert dropout.start_tick - 1 in ticks
    assert 300 in ticks
    assert sim.state.machines[dropout.machine_id].sensor_effects == {}
    assert len(temperatures) < 300


def test_different_seeds_change_observations_but_keep_the_same_challenge_logic():
    first, _ = observe(42)
    second, _ = observe(43)
    assert first.readings != second.readings
    assert {t.fault for t in first.ground_truth()} == {
        t.fault for t in second.ground_truth()
    }


@pytest.mark.parametrize("machines", [3, 8])
def test_challenge_supports_existing_line_sizes(machines):
    sim = build_challenge(42, machines=machines)
    assert len(sim.state.machines) == machines
    assert all(t.machine_id in sim.state.machines for t in sim.ground_truth())
