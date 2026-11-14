"""A call refused as a repeat is shown back to the model (2026-11-14).

In the 2026-11-14 afternoon triage runs, research asked again for
`get_line_screening`, which the evidence packet had already read, until three
refused repeats ended research before hypothesize (22 of 26 triages). The
shared view now lists the calls refused as repeats, so the model can see that
the answer is already in the evidence.
"""

from capstone.agent.loop import call_signature, gather, record
from capstone.agent.model_policy import render
from capstone.agent.policy import CallTool
from capstone.contracts.tools import ToolRequest
from tests.helpers import new_state

HEADING = "REFUSED AS REPEATS"


def step(name, **arguments):
    return CallTool(
        information_needed="screen the line",
        request=ToolRequest(name=name, arguments=arguments),
    )


def refuse(state, call):
    record(
        state,
        "investigate",
        "repeated_call",
        information_needed=call.information_needed,
        step=call,
    )


def test_nothing_is_shown_before_a_repeat():
    assert HEADING not in render(new_state())


def test_a_refused_repeat_is_named_with_its_tick():
    state = new_state()
    state.last_tick = 920
    refuse(state, step("get_line_screening"))
    text = render(state)
    assert HEADING in text
    assert "- get_line_screening {} at tick 920" in text
    assert "already in the evidence" in text


def test_the_same_call_refused_twice_is_named_once():
    state = new_state()
    state.last_tick = 920
    refuse(state, step("get_line_screening"))
    refuse(state, step("get_line_screening"))
    assert render(state).count("- get_line_screening {}") == 1


def test_only_the_latest_three_refused_calls_are_shown():
    state = new_state()
    state.last_tick = 920
    for machine in ("CNC-01", "CNC-02", "CNC-03", "CNC-04"):
        refuse(state, step("get_machine_status", machine_id=machine))
    text = render(state)
    assert "CNC-01" not in text.split(HEADING)[1]
    assert all(m in text for m in ("CNC-02", "CNC-03", "CNC-04"))


def test_gather_records_a_repeat_that_the_view_then_shows():
    state = new_state()
    state.last_tick = 920
    call = step("get_line_screening")
    state.seen_calls.append(call_signature(call.request, state.last_tick))
    assert gather(state, None, "investigate", call) is None
    assert "- get_line_screening {} at tick 920" in render(state)
