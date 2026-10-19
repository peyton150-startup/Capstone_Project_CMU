"""Compatibility probes only; synthetic samples do not implement new faults."""

from datetime import datetime

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.events import Event
from capstone.simulator.scenarios import (
    BearingDegradation,
    ProductionLine,
    WrongSetting,
)
from capstone.simulator.sensors import SensorReading, VibrationSensor
from capstone.simulator.simulator import Simulator
from capstone.simulator.state import Job, MachineState
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools


def setup_factory():
    sim = Simulator(seed=42, start=datetime(2026, 1, 1))
    sim.add_machine(MachineState(id="M1", job=Job(id=1, load=0.5)))
    sim.add_sensor(VibrationSensor("M1", sim.rng, noise_sd=0))
    sim.add_scenario(
        ProductionLine("line", sim.rng, machine_ids=["M1"], min_load=0.5, max_load=0.5)
    )
    desk = ApprovalDesk(sim)
    provider = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, desk))
    return sim, desk, provider


def call(provider, name, **arguments):
    result = provider.call(ToolRequest(name=name, arguments=arguments))
    assert result.success, result.error
    return result.data


@pytest.mark.parametrize("values", [(2, 3, 4), (9, 2, 2)])
def test_drift_or_transient_samples_use_existing_reading_and_summary_formats(values):
    sim, _, provider = setup_factory()
    # Inject observation fixtures to probe formats, not a causal fault model.
    sim._readings.extend(
        SensorReading(
            sensor="vibration", machine_id="M1", tick=tick, value=value, unit="mm/s"
        )
        for tick, value in zip((1, 4, 10), values)
    )
    arguments = dict(machine_id="M1", sensor="vibration", from_tick=0, to_tick=10)
    readings = call(provider, "get_readings", **arguments)
    summary = call(provider, "get_sensor_summary", **arguments)
    assert [row["tick"] for row in readings] == [1, 4, 10]
    assert [row["value"] for row in readings] == list(values)
    assert summary["sample_count"] == 3
    assert summary["rate_of_change"] == pytest.approx((values[-1] - values[0]) / 9)
    empty = call(provider, "get_sensor_summary", **(arguments | {"to_tick": 0}))
    assert empty["sample_count"] == 0
    assert empty["mean"] is None


def test_compound_fault_repair_can_leave_a_symptom_through_unchanged_tools():
    sim, desk, provider = setup_factory()
    sim.add_scenario(
        BearingDegradation(
            "wear",
            sim.rng,
            machine_id="M1",
            start_tick=1,
            rate=0.1,
            variation=0,
            speed_exponent=0,
        )
    )
    sim.add_scenario(
        WrongSetting(
            "speed",
            sim.rng,
            machine_id="M1",
            start_tick=1,
            factor=2,
        )
    )
    call(provider, "wait", ticks=4)
    before = call(
        provider,
        "get_readings",
        machine_id="M1",
        sensor="vibration",
        from_tick=4,
        to_tick=4,
    )[0]["value"]
    assert len(sim.ground_truth()) == 2
    proposal = call(
        provider,
        "propose_action",
        machine_id="M1",
        action="replace_bearing",
        reason="Investigate persistent vibration",
    )
    assert proposal["status"] == "pending"
    assert sim.state.machines["M1"].maintenance_until is None
    desk.approve(proposal["id"])
    call(provider, "execute_action", proposal_id=proposal["id"])
    call(provider, "wait", ticks=46)
    after = call(
        provider,
        "get_readings",
        machine_id="M1",
        sensor="vibration",
        from_tick=50,
        to_tick=50,
    )[0]["value"]
    assert 2 < after < before  # healthy baseline is 2; speed fault remains
    assert call(provider, "get_settings")[0]["speed_rpm"] == 2000
    assert call(provider, "get_proposals")[0]["status"] == "approved"
    events = call(provider, "get_events", from_tick=0, to_tick=50)
    assert any("bearing" in event["message"] for event in events)
    exposed = str(events)
    assert "bearing_health" not in exposed
    assert "scenario" not in exposed


def test_delayed_historical_record_cannot_be_appended_to_current_event_log():
    sim, _, _ = setup_factory()
    sim.event_log.record(
        Event(
            tick=10, machine_id="M1", kind="maintenance", message="Inspection recorded"
        )
    )
    with pytest.raises(ValueError, match="older than"):
        sim.event_log.record(
            Event(
                tick=2,
                machine_id="M1",
                kind="maintenance",
                message="Earlier inspection reported late",
            )
        )


def test_different_causes_can_produce_same_vibration_without_format_changes():
    sim, _, _ = setup_factory()
    machine = sim.state.machines["M1"]
    sensor = VibrationSensor("M1", sim.rng, noise_sd=0)
    machine.condition.bearing_health = 0.5
    worn = sensor.read(machine, 1)
    machine.condition.bearing_health = 1
    machine.speed_setting = machine.standard_speed * 1.75
    overspeed = sensor.read(machine, 1)
    assert worn == overspeed
    assert "bearing_health" not in worn.model_dump_json()
