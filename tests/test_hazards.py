"""Unreliable tools: each fault fires on schedule, is recoverable, and leaves reality alone."""

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.episode import run_episode
from capstone.experiment import Case, record_of
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.providers.hazards import (
    TIMEOUT_MESSAGE,
    Gap,
    StaleRecord,
    Timeout,
    UnreliableProvider,
    standard_hazards,
)
from capstone.simulator.generator import build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.test_episode import wear_policy

BEFORE_RUN = "2026-01-04T06:00:00"


def factory(seed=6, ticks=600):
    sim = build_scenario(seed, fault="bearing_degradation")
    for _ in range(ticks):
        sim.step()
    look = ObservationTools(sim)
    return sim, SimulatorFactoryProvider(look, ActionTools(sim, ApprovalDesk(sim)))


def readings(machine="CNC-01", low=300, high=599):
    return ToolRequest(
        name="get_readings",
        arguments={
            "machine_id": machine,
            "sensor": "vibration",
            "from_tick": low,
            "to_tick": high,
        },
    )


def test_a_timeout_fails_only_the_scheduled_call_and_asking_again_works():
    _, clean = factory()
    tools = UnreliableProvider(clean, (Timeout("get_readings", 1),))

    first, second = tools.call(readings()), tools.call(readings())

    assert not first.success and first.error.message == TIMEOUT_MESSAGE
    assert first.error.code == "provider_error" and first.data is None
    assert second.success and second.data == clean.call(readings()).data
    assert tools.report.fired == ["timeout on get_readings call 1"]
    assert tools.report.retried == 1


def test_a_gap_drops_the_middle_third_of_the_range_from_the_answer_only():
    sim, clean = factory()
    tools = UnreliableProvider(clean, (Gap("get_readings", 1),))

    holed = tools.call(readings(low=300, high=599)).data
    whole = tools.call(readings(low=300, high=599)).data

    assert {row["tick"] for row in holed} == set(range(300, 400)) | set(range(500, 600))
    assert len(whole) == 300  # asking again gives everything
    assert tools.report.retried == 1
    assert len([r for r in sim.readings if r.machine_id == "CNC-01"]) >= 600


def history(machine=None):
    arguments = {} if machine is None else {"machine_id": machine}
    return ToolRequest(name="get_maintenance_history", arguments=arguments)


def test_a_stale_record_joins_the_history_of_its_machine_in_date_order():
    _, clean = factory()
    tools = UnreliableProvider(clean, (StaleRecord("CNC-02", BEFORE_RUN),))

    everything = tools.call(history()).data
    mine, other = tools.call(history("CNC-02")).data, tools.call(history("CNC-01"))

    stale = [r for r in everything if r["performed_at"] == BEFORE_RUN]
    assert len(stale) == 1 and stale[0]["machine_id"] == "CNC-02"
    assert "bearing replaced" in stale[0]["note"] and stale[0]["tick"] is None
    assert any(r["performed_at"] == BEFORE_RUN for r in mine)
    assert other.data == clean.call(history("CNC-01")).data
    assert tools.report.fired == ["stale maintenance record on CNC-02"]
    past = [r["performed_at"] for r in everything if r["tick"] is None]
    assert past == sorted(past)


def test_calls_off_the_schedule_pass_through_unchanged():
    _, clean = factory()
    tools = UnreliableProvider(clean, (Timeout("get_events", 3), Gap("get_events", 4)))
    request = ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 599})
    assert tools.call(request).data == clean.call(request).data
    assert tools.call(readings()).data == clean.call(readings()).data
    assert tools.report.fired == []


def test_a_gap_can_only_be_put_on_tools_with_ticked_rows():
    with pytest.raises(ValueError):
        Gap("get_sensor_trend")


def test_the_standard_set_has_a_stale_record_only_when_a_machine_was_named():
    with_machine = standard_hazards("CNC-03", BEFORE_RUN)
    assert StaleRecord("CNC-03", BEFORE_RUN) in with_machine
    assert not any(isinstance(h, StaleRecord) for h in standard_hazards(None, ""))


def test_an_episode_with_hazards_reports_them_and_repeats_exactly():
    def run():
        return run_episode(
            6,
            wear_policy(),
            fault="bearing_degradation",
            clock=lambda: 0.0,
            hazards=True,
        )

    result, again = run(), run()
    record = record_of(Case("seed-6/bearing", 6, "bearing_degradation"), "k", result)

    assert "timeout on get_sensor_summary call 1" in result.hazards.fired
    assert record.hazards_fired == result.hazards.fired
    assert record.hazards_retried == result.hazards.retried
    assert again.score == result.score and again.hazards == result.hazards
    failed = [d for d in result.state.decisions if d.error is not None]
    assert failed and failed[0].error.message == TIMEOUT_MESSAGE


def test_without_hazards_nothing_is_reported():
    result = run_episode(
        6, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0
    )
    record = record_of(Case("seed-6/bearing", 6, "bearing_degradation"), "k", result)
    assert result.hazards is None
    assert (record.hazards_fired, record.hazards_retried) == (None, None)
