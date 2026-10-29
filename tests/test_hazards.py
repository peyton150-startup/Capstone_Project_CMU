"""Unreliable tools: each fault fires on schedule, is recoverable, and leaves reality alone."""

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.episode import run_episode
from capstone.experiment import Case, record_of
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.providers.hazards import (
    BLACKOUT_STREAM,
    BLACKOUT_TICKS,
    TIMEOUT_MESSAGE,
    Blackout,
    Gap,
    StaleRecord,
    Timeout,
    UnreliableProvider,
    blackout_hazards,
    standard_hazards,
)
from capstone.simulator.generator import build_scenario
from capstone.simulator.rng import RandomSource
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
    assert (record.hazards_blocked, record.blackout_recovered) == (None, None)


# --- a dead sensor feed, for a seeded while ------------------------------------


def wait(ticks):
    return ToolRequest(name="wait", arguments={"ticks": ticks})


def test_a_blackout_refuses_the_machine_s_sensors_until_its_end_tick():
    sim, clean = factory()
    tick = sim.clock.tick
    tools = UnreliableProvider(clean, (Blackout("CNC-01", tick + 20),))

    first, again = tools.call(readings()), tools.call(readings())

    for refused in (first, again):  # asking again does not help: time must pass
        assert not refused.success and refused.data is None
        assert refused.error.code == "provider_error"
        assert refused.error.message == "The sensor feed for CNC-01 is not responding."
    assert str(tick + 20) not in first.error.message  # never says when it ends
    assert tools.report.fired == [f"blackout on CNC-01 until tick {tick + 20}"]
    assert tools.report.blocked == 2
    assert tools.report.blackout_recovered is False


def test_a_blackout_leaves_other_machines_and_other_tools_alone():
    sim, clean = factory()
    tools = UnreliableProvider(clean, (Blackout("CNC-01", sim.clock.tick + 20),))
    events = ToolRequest(name="get_events", arguments={"from_tick": 0, "to_tick": 599})

    assert tools.call(readings("CNC-02")).data == clean.call(readings("CNC-02")).data
    assert tools.call(events).data == clean.call(events).data
    assert tools.report.fired == [] and tools.report.blocked == 0


def test_after_waiting_past_the_end_the_feed_answers_and_recovery_is_kept():
    sim, clean = factory()
    tools = UnreliableProvider(clean, (Blackout("CNC-01", sim.clock.tick + 20),))
    assert not tools.call(readings()).success

    assert tools.call(wait(19)).success
    assert not tools.call(readings()).success  # one tick short
    assert tools.call(wait(1)).success
    back = tools.call(readings())

    assert back.success and back.data == clean.call(readings()).data
    assert tools.report.blackout_recovered is True
    assert tools.report.blocked == 2


def test_a_feed_that_was_never_refused_is_not_a_recovery():
    sim, clean = factory()
    tools = UnreliableProvider(clean, (Blackout("CNC-01", sim.clock.tick + 20),))
    tools.call(wait(30))
    assert tools.call(readings()).success
    assert tools.report.blackout_recovered is False
    assert tools.report.fired == []


def test_a_blackout_does_not_touch_the_factory():
    sim, clean = factory()
    before = len(sim.readings)
    tools = UnreliableProvider(clean, (Blackout("CNC-01", sim.clock.tick + 20),))
    tools.call(readings())
    assert len(sim.readings) == before and sim.clock.tick == sim.clock.tick


def test_the_length_is_seeded_and_within_the_range():
    low, high = BLACKOUT_TICKS
    ends = []
    for seed in range(20):
        [hazard] = blackout_hazards(
            "CNC-02", 100, RandomSource(seed).stream(BLACKOUT_STREAM)
        )
        [same] = blackout_hazards(
            "CNC-02", 100, RandomSource(seed).stream(BLACKOUT_STREAM)
        )
        assert hazard == same  # the same seed, the same blackout
        assert 100 + low <= hazard.until_tick <= 100 + high
        ends.append(hazard.until_tick)
    assert len(set(ends)) > 1  # different seeds, different lengths


def test_no_machine_named_means_no_blackout():
    assert blackout_hazards(None, 0, RandomSource(1).stream(BLACKOUT_STREAM)) == ()


def test_an_episode_with_a_blackout_reports_it_and_repeats_exactly():
    def run(hazards):
        return run_episode(
            6,
            wear_policy(),
            fault="bearing_degradation",
            clock=lambda: 0.0,
            hazards=hazards,
        )

    result, again, plain = run("blackout"), run("blackout"), run(False)
    record = record_of(Case("seed-6/bearing", 6, "bearing_degradation"), "k", result)

    machine = result.state.anomaly.machine_id
    assert result.hazards.fired[0].startswith(f"blackout on {machine} until tick ")
    assert record.hazards_blocked == result.hazards.blocked > 0
    assert record.blackout_recovered is False  # the scripted policy never waits
    assert again.score == result.score and again.hazards == result.hazards
    # Drawing the length uses its own stream: the factory is the same world.
    assert plain.state.anomaly == result.state.anomaly
    assert plain.score.true_fault == result.score.true_fault
    refused = [d for d in result.state.decisions if d.error is not None]
    assert refused and "not responding" in refused[0].error.message
