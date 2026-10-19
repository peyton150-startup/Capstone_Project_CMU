"""The maintenance history from before the run, and the tool that shows it."""

import pytest

from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.simulator.line import build_line
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.errors import ToolInputError
from capstone.tools.observation import ObservationTools
from tests.helpers import approve_and_run
from tests.test_observation_tools import HIDDEN_WORDS


def history(seed, **options):
    return build_line(seed, **options).state.maintenance_history


def test_every_machine_has_one_to_four_past_records_before_the_start():
    sim = build_line(3)
    records = sim.state.maintenance_history
    start = sim.clock.time_at(0)
    for machine_id in sim.state.machines:
        mine = [r for r in records if r.machine_id == machine_id]
        assert 1 <= len(mine) <= 4
    assert all(r.performed_at < start for r in records)
    assert records == sorted(records, key=lambda r: (r.performed_at, r.machine_id))


def test_the_same_seed_gives_the_same_history_and_another_seed_another():
    assert history(5) == history(5)
    assert history(5) != history(6)


@pytest.mark.parametrize("seed", [1, 6, 9])
def test_the_history_is_the_same_whatever_the_fault(seed):
    """Drawn before the fault and never from it: it cannot point at the cause."""
    histories = [
        build_scenario(seed, fault=fault).state.maintenance_history for fault in FAULTS
    ]
    assert all(h == histories[0] for h in histories)


def test_no_history_names_a_hidden_mechanism():
    text = " ".join(
        f"{r.kind} {r.note}" for seed in range(40) for r in history(seed)
    ).lower()
    assert not [word for word in HIDDEN_WORDS if word in text]


def test_the_tool_shows_past_records_then_this_runs_maintenance():
    sim = build_scenario(6, fault="bearing_degradation")
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    act.wait(10)
    proposal = act.propose_action("CNC-02", "replace_bearing", "vibration rising")
    approve_and_run(desk, act, proposal["id"])
    act.wait(60)
    rows = look.get_maintenance_history("CNC-02")
    past = [r for r in rows if r["tick"] is None]
    during = [r for r in rows if r["tick"] is not None]
    assert past and len(during) == 2  # started, then finished with a finding
    assert rows == past + during
    assert all(r["machine_id"] == "CNC-02" for r in rows)
    assert {r["machine_id"] for r in look.get_maintenance_history()} == set(
        sim.state.machines
    )
    with pytest.raises(ToolInputError):
        look.get_maintenance_history("CNC-99")


def test_the_provider_offers_it_with_checked_arguments():
    sim = build_scenario(6, fault="bearing_degradation")
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    factory = SimulatorFactoryProvider(look, act)
    result = factory.call(
        ToolRequest(name="get_maintenance_history", arguments={"machine_id": "CNC-01"})
    )
    assert result.success and result.data == look.get_maintenance_history("CNC-01")
    refused = factory.call(
        ToolRequest(name="get_maintenance_history", arguments={"machine": "CNC-01"})
    )
    assert not refused.success and refused.error.code == "invalid_arguments"
