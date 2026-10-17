import json
from io import StringIO
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from capstone.contracts.investigations import investigation_id_for, run_id_for
from capstone.contracts.tools import ToolRequest
from capstone.observability import create_event_logger
from capstone.providers.factory import (
    TOOL_DESCRIPTIONS,
    FactorySensor,
    MachineSensor,
    SimulatorFactoryProvider,
)
from capstone.simulator.line import build_line
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools


def provider():
    sim = build_line(42, machines=3)
    desk = ApprovalDesk(sim)
    return (
        sim,
        desk,
        SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, desk)),
    )


def test_observations_carry_simulation_time_and_trace_ids_without_advancing():
    sim, _, factory = provider()
    run = run_id_for("run-42")
    investigation = investigation_id_for(run, 1)
    result = factory.call(
        ToolRequest(name="list_machines"), run_id=run, investigation_id=investigation
    )
    assert result.success
    assert result.tick == sim.clock.tick == 0
    assert result.timestamp == sim.clock.now
    assert result.run_id == run
    assert result.investigation_id == investigation
    assert result.data == ObservationTools(sim).list_machines()
    exposed = result.model_dump_json()
    assert not any(
        secret in exposed
        for secret in ("bearing_health", "defect_risk", "standard_speed")
    )


def test_unknown_tool_cannot_reach_ground_truth_or_approval():
    sim, _, factory = provider()
    for name in ("ground_truth", "approve", "_sim", "__dict__"):
        result = factory.call(ToolRequest(name=name))
        assert not result.success
        assert result.data is None
        assert result.error.code == "unknown_tool"
    assert sim.clock.tick == 0


def test_invalid_arguments_fail_without_mutating_state():
    sim, _, factory = provider()
    result = factory.call(ToolRequest(name="wait", arguments={"ticks": True}))
    assert not result.success
    assert result.error.code == "invalid_arguments"
    assert sim.clock.tick == 0


def test_wait_uses_existing_bounded_action_and_reports_new_time():
    sim, _, factory = provider()
    result = factory.call(ToolRequest(name="wait", arguments={"ticks": 2}))
    assert result.success
    assert result.tick == sim.clock.tick == 2
    assert result.data["tick"] == 2


def test_proposal_remains_pending_until_human_approval():
    sim, desk, factory = provider()
    machine = sim.state.machines["CNC-01"]
    health = machine.condition.bearing_health
    result = factory.call(
        ToolRequest(
            name="propose_action",
            arguments={
                "machine_id": "CNC-01",
                "action": "replace_bearing",
                "reason": "Inspect bearing",
            },
        )
    )
    assert result.success
    assert result.data["status"] == "pending"
    assert machine.condition.bearing_health == health
    assert machine.maintenance_until is None
    assert len(desk.pending()) == 1


def test_execute_action_is_refused_until_a_human_approves_then_reports_the_work():
    sim, desk, factory = provider()
    machine = sim.state.machines["CNC-01"]
    proposed = factory.call(
        ToolRequest(
            name="propose_action",
            arguments={
                "machine_id": "CNC-01",
                "action": "replace_bearing",
                "reason": "Inspect bearing",
            },
        )
    )
    execute = ToolRequest(
        name="execute_action", arguments={"proposal_id": proposed.data["id"]}
    )

    refused = factory.call(execute)
    assert not refused.success
    assert refused.error.code == "invalid_arguments"
    assert machine.maintenance_until is None

    desk.approve(proposed.data["id"], note="go ahead")
    started = factory.call(execute)
    assert started.success
    assert started.data == {
        "proposal_id": 1,
        "machine_id": "CNC-01",
        "action": "replace_bearing",
        "started_tick": 0,
        "finish_tick": machine.maintenance_until,
    }
    [seen] = factory.call(ToolRequest(name="get_proposals")).data
    assert (seen["status"], seen["note"], seen["executed_tick"]) == (
        "approved",
        "go ahead",
        0,
    )
    assert not factory.call(execute).success  # an approval is used once


def test_the_provider_offers_no_way_to_approve_or_reject():
    _, _, factory = provider()
    for name in ("approve", "reject", "approve_proposal", "carry_out"):
        result = factory.call(ToolRequest(name=name, arguments={"proposal_id": 1}))
        assert not result.success
        assert result.error.code == "unknown_tool"


def test_same_seed_and_tool_sequence_produce_same_observations():
    _, _, first = provider()
    _, _, second = provider()
    for request in (
        ToolRequest(name="wait", arguments={"ticks": 3}),
        ToolRequest(
            name="get_readings",
            arguments={
                "machine_id": "CNC-01",
                "sensor": "vibration",
                "from_tick": 0,
                "to_tick": 3,
            },
        ),
    ):
        assert first.call(request) == second.call(request)


def test_invalid_trace_context_is_rejected_before_wait():
    sim, _, factory = provider()
    with pytest.raises(ValidationError):
        factory.call(
            ToolRequest(name="wait", arguments={"ticks": 2}), investigation_id=uuid4()
        )
    assert sim.clock.tick == 0


def test_all_read_tools_preserve_existing_observable_shapes():
    sim, _, factory = provider()
    for _ in range(240):
        sim.step()
    observations = ObservationTools(sim)
    cases = {
        "get_time": {},
        "list_machines": {},
        "get_settings": {},
        "get_readings": {
            "machine_id": "CNC-01",
            "sensor": "vibration",
            "from_tick": 0,
            "to_tick": 240,
        },
        "get_sensor_trend": {
            "machine_id": "CNC-01",
            "sensor": "vibration",
            "from_tick": 0,
            "to_tick": 240,
            "bucket_ticks": 60,
        },
        "get_factory_readings": {
            "sensor": "air_temperature",
            "from_tick": 0,
            "to_tick": 240,
        },
        "get_sensor_summary": {
            "machine_id": "CNC-01",
            "sensor": "vibration",
            "from_tick": 0,
            "to_tick": 240,
        },
        "get_events": {"from_tick": 0, "to_tick": 240},
        "get_job_history": {"job_id": 1},
        "get_inspections": {"from_tick": 0, "to_tick": 240},
    }
    for name, arguments in cases.items():
        result = factory.call(ToolRequest(name=name, arguments=arguments))
        assert result.success, (name, result.error)
        assert result.data == getattr(observations, name)(**arguments)
    assert sim.clock.tick == 240


# --- what a failed call tells the agent ---------------------------------------


@pytest.mark.parametrize(
    "name,arguments,expected",
    [
        (
            "get_events",
            {"from_tick": "0", "to_tick": 5},
            "from_tick: Input should be a valid integer",
        ),
        (
            "get_events",
            {"from_tick": 5, "to_tick": 0},
            "from_tick must not be after to_tick",
        ),
        (
            "get_readings",
            {
                "machine_id": "CNC-01",
                "sensor": "Vibration",
                "from_tick": 0,
                "to_tick": 5,
            },
            "sensor: Input should be 'vibration', 'temperature' or 'load'",
        ),
        (
            "get_sensor_summary",
            {"machine_id": None, "sensor": "temperature", "from_tick": 0, "to_tick": 5},
            "air_temperature belongs to the factory",
        ),
        (
            "get_readings",
            {
                "machine_id": "CNC-99",
                "sensor": "vibration",
                "from_tick": 0,
                "to_tick": 5,
            },
            "unknown machine CNC-99",
        ),
        ("wait", {"ticks": 1000}, "ticks must be a whole number from 1 to 480"),
        (
            "propose_action",
            {"machine_id": "CNC-01", "action": "replace bearing", "reason": "worn"},
            "choose from replace_bearing, reset_setting",
        ),
    ],
)
def test_a_refused_request_says_what_to_correct(name, arguments, expected):
    sim, desk, factory = provider()
    result = factory.call(ToolRequest(name=name, arguments=arguments))
    assert not result.success
    assert result.error.code == "invalid_arguments"
    assert expected in result.error.message
    assert sim.clock.tick == 0
    assert desk.proposals() == []


def test_an_answer_that_breaks_its_contract_is_reported_without_its_content():
    sim = build_line(42, machines=3)
    observations = ObservationTools(sim)
    honest = observations.list_machines
    observations.list_machines = lambda: [
        {**row, "bearing_health": 0.71} for row in honest()
    ]
    factory = SimulatorFactoryProvider(observations, ActionTools(sim))
    result = factory.call(ToolRequest(name="list_machines"))
    assert not result.success
    assert result.error.code == "invalid_result"
    exposed = result.model_dump_json()
    assert "bearing_health" not in exposed
    assert "0.71" not in exposed


def test_any_other_tool_failure_is_reported_without_its_message():
    sim = build_line(42, machines=3)
    observations = ObservationTools(sim)

    def broken():
        raise ValueError("driver said password=hunter2")

    observations.get_settings = broken
    factory = SimulatorFactoryProvider(observations, ActionTools(sim))
    result = factory.call(ToolRequest(name="get_settings"))
    assert result.error.code == "provider_error"
    assert "hunter2" not in result.model_dump_json()


def test_the_sensor_names_a_request_may_use_are_the_simulators():
    sim = build_line(42, machines=3)
    sim.step()
    machine = {r.sensor for r in sim.readings if r.machine_id is not None}
    factory = {r.sensor for r in sim.readings if r.machine_id is None}
    assert machine == set(get_args(MachineSensor))
    assert factory == set(get_args(FactorySensor))


def test_adapter_logs_metadata_without_tool_payloads():
    sim = build_line(42, machines=3)
    stream = StringIO()
    factory = SimulatorFactoryProvider(
        ObservationTools(sim), ActionTools(sim), logger=create_event_logger(stream)
    )
    run = run_id_for("logging-run")
    result = factory.call(ToolRequest(name="list_machines"), run_id=run)
    logged = json.loads(stream.getvalue())
    assert logged == {
        "event": "factory_tool",
        "run_id": str(run),
        "tick": 0,
        "tool": "list_machines",
        "success": result.success,
    }
    assert "CNC-01" not in stream.getvalue()


def test_every_tool_is_described_and_no_description_names_a_missing_tool():
    _, _, factory = provider()
    assert set(TOOL_DESCRIPTIONS) == set(factory._tools)
    assert all(text.strip() for text in TOOL_DESCRIPTIONS.values())


def test_a_trend_is_far_smaller_than_the_readings_it_summarises():
    sim, _, factory = provider()
    for _ in range(600):
        sim.step()
    window = {"machine_id": "CNC-01", "sensor": "vibration", "from_tick": 0}
    trend = factory.call(
        ToolRequest(name="get_sensor_trend", arguments=window | {"to_tick": 599})
    )
    raw = factory.call(
        ToolRequest(name="get_readings", arguments=window | {"to_tick": 599})
    )
    assert trend.success and raw.success
    assert [block["from_tick"] for block in trend.data] == list(range(0, 600, 60))
    assert sum(block["count"] for block in trend.data) == len(raw.data)
    assert len(json.dumps(trend.data)) * 20 < len(json.dumps(raw.data))
