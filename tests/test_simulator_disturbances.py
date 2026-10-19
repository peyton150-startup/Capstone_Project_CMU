from datetime import datetime

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.disturbances import (
    SensorDrift,
    SensorDropout,
    TransientAnomaly,
)
from capstone.simulator.scenarios import BearingDegradation, ProductionLine
from capstone.simulator.sensors import TemperatureSensor, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import MachineState
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools


def factory():
    sim = Simulator(42, datetime(2026, 1, 1))
    sim.add_machine(MachineState(id="M1", ticks_per_job=1000))
    sim.add_sensor(VibrationSensor("M1", sim.rng, noise_sd=0))
    sim.add_sensor(TemperatureSensor("M1", sim.rng, noise_sd=0))
    sim.add_scenario(
        ProductionLine(
            "line",
            sim.rng,
            machine_ids=["M1"],
            min_load=0.5,
            max_load=0.5,
        )
    )
    return sim


def run(sim, ticks):
    return [sim.step() for _ in range(ticks)]


def vibration(sim):
    return [r.value for r in sim.readings if r.sensor == "vibration"]


def test_drift_has_exact_window_and_does_not_change_physical_condition():
    sim = factory()
    sim.add_scenario(
        SensorDrift(
            "drift",
            sim.rng,
            machine_id="M1",
            sensor="vibration",
            start_tick=2,
            duration=3,
            per_tick=0.5,
        )
    )
    run(sim, 5)
    assert vibration(sim) == [2, 2.5, 3, 3.5, 2]
    assert sim.state.machines["M1"].condition.bearing_health == 1
    assert sim.state.machines["M1"].sensor_effects == {}
    assert sim.ground_truth()[0].fault == "sensor_drift"


def test_transient_coexists_with_wear_and_ends_without_repair():
    baseline, transient = factory(), factory()
    for sim in (baseline, transient):
        sim.add_scenario(
            BearingDegradation(
                "wear",
                sim.rng,
                machine_id="M1",
                start_tick=1,
                rate=0.01,
                variation=0,
            )
        )
    transient.add_scenario(
        TransientAnomaly(
            "spike",
            transient.rng,
            machine_id="M1",
            sensor="vibration",
            start_tick=2,
            duration=2,
            offset=5,
        )
    )
    run(baseline, 5)
    run(transient, 5)
    assert [b - a for a, b in zip(vibration(baseline), vibration(transient))] == (
        pytest.approx([0, 5, 5, 0, 0])
    )
    assert (
        transient.state.machines["M1"].condition
        == baseline.state.machines["M1"].condition
    )
    assert {truth.fault for truth in transient.ground_truth()} == {
        "bearing_degradation",
        "false_alarm",
    }


def test_overlapping_disturbances_only_remove_their_own_contribution():
    sim = factory()
    for name, start, duration, offset in (("a", 1, 2, 3), ("b", 2, 3, 5)):
        sim.add_scenario(
            TransientAnomaly(
                name,
                sim.rng,
                machine_id="M1",
                sensor="vibration",
                start_tick=start,
                duration=duration,
                offset=offset,
            )
        )
    run(sim, 5)
    assert vibration(sim) == [5, 10, 7, 7, 2]


def test_dropout_omits_samples_and_alarms_but_preserves_other_sensor_noise():
    baseline, dropout = factory(), factory()
    # Nonzero noise verifies that missing samples do not shift the sensor RNG.
    for sim in (baseline, dropout):
        sim._sensors[0].noise_sd = 0.15
    dropout.add_scenario(
        SensorDropout(
            "missing",
            dropout.rng,
            machine_id="M1",
            sensor="vibration",
            start_tick=2,
            duration=2,
        )
    )
    run(baseline, 5)
    run(dropout, 5)
    assert [r for r in baseline.readings if r.sensor == "temperature"] == [
        r for r in dropout.readings if r.sensor == "temperature"
    ]
    expected = [
        r for r in baseline.readings if r.sensor == "vibration" and r.tick not in (2, 3)
    ]
    assert [r for r in dropout.readings if r.sensor == "vibration"] == expected
    observations = ObservationTools(dropout)
    assert observations.get_readings("M1", "vibration", 2, 3) == []
    summary = observations.get_sensor_summary("M1", "vibration", 2, 3)
    assert summary["sample_count"] == 0 and summary["mean"] is None


def test_spike_and_dropout_share_existing_provider_and_alarm_boundary():
    from capstone.simulator.events import ThresholdAlarm

    sim = factory()
    sim.add_alarm(ThresholdAlarm("vibration", 4.5))
    sim.add_scenario(
        TransientAnomaly(
            "spike",
            sim.rng,
            machine_id="M1",
            sensor="vibration",
            start_tick=1,
            duration=3,
            offset=5,
        )
    )
    sim.add_scenario(
        SensorDropout(
            "missing",
            sim.rng,
            machine_id="M1",
            sensor="vibration",
            start_tick=2,
            duration=1,
        )
    )
    desk = ApprovalDesk(sim)
    provider = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, desk))
    assert provider.call(ToolRequest(name="wait", arguments={"ticks": 4})).success
    result = provider.call(
        ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 4})
    )
    assert result.success
    assert [e["tick"] for e in result.data if e["kind"] == "alarm"] == [1, 3]
    assert "sensor_effects" not in result.model_dump_json()
    assert "false_alarm" not in result.model_dump_json()


@pytest.mark.parametrize("kind", [SensorDrift, SensorDropout, TransientAnomaly])
@pytest.mark.parametrize(
    "change", [{"duration": 0}, {"start_tick": -1}, {"sensor": ""}]
)
def test_invalid_windows_and_empty_sensor_are_rejected(kind, change):
    sim = factory()
    arguments = dict(machine_id="M1", sensor="vibration", start_tick=1, duration=3)
    if kind is SensorDrift:
        arguments["per_tick"] = 0.1
    if kind is TransientAnomaly:
        arguments["offset"] = 5
    with pytest.raises(ValueError):
        kind("bad", sim.rng, **(arguments | change))


@pytest.mark.parametrize(
    "kind,parameter", [(SensorDrift, "per_tick"), (TransientAnomaly, "offset")]
)
@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_nonfinite_offsets_are_rejected(kind, parameter, value):
    sim = factory()
    with pytest.raises(ValueError):
        kind(
            "bad",
            sim.rng,
            machine_id="M1",
            sensor="vibration",
            start_tick=1,
            duration=3,
            **{parameter: value},
        )
