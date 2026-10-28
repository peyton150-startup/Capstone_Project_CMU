"""The live progress view: a watcher hooked into the loop, and the terminal
view built on it. Scripted policies only; no network."""

import pytest

from capstone.agent.artifacts import CritiqueRecord
from capstone.agent.state import DecisionRecord, InvestigationState
from capstone.contracts.tools import ToolError
from capstone.episode import run_episode
from capstone.progress import ProgressView, main, shorten, step_line, watch_episode
from tests.helpers import critique_result
from tests.test_episode import MACHINE, SEED, wear_policy


def run(**options):
    return run_episode(
        SEED, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0, **options
    )


def test_the_watcher_sees_the_run_grow_and_ends_with_the_final_state():
    seen = []
    result = run(watch=seen.append)
    assert len(seen) > 3
    assert all(isinstance(state, InvestigationState) for state in seen)
    counts = [len(state.decisions) for state in seen]
    assert counts == sorted(counts)  # shown as it happens, never going back
    assert seen[-1].decisions == result.state.decisions
    assert seen[-1].verification == result.state.verification


def test_a_watcher_gets_copies_and_cannot_change_the_run():
    plain = run()

    def meddle(state):
        state.decisions.clear()
        state.hypotheses.clear()
        state.conclusion = None

    watched = run(watch=meddle)
    assert watched.state.decisions == plain.state.decisions
    assert watched.state.conclusion == plain.state.conclusion
    assert watched.score == plain.score


def test_a_failing_watcher_is_ignored_and_the_run_is_unchanged(caplog):
    plain = run()

    def broken(state):
        raise RuntimeError("display fault quoting E3 content")

    watched = run(watch=broken)
    assert watched.state.decisions == plain.state.decisions
    assert watched.score == plain.score
    assert "watcher failed" in caplog.text
    assert "E3 content" not in caplog.text  # the exception text is never logged


def test_the_view_prints_each_step_once_and_in_order():
    lines = []
    result = run(watch=ProgressView(lines.append))
    steps = [line for line in lines if line.startswith("#")]
    numbers = [int(line[1:].split()[0]) for line in steps]
    assert numbers == list(range(1, len(result.state.decisions) + 1))
    assert lines[0].startswith("anomaly at t=") and MACHINE in lines[0]
    assert any(line.startswith("CONCLUSION (") for line in lines)
    assert any(line.startswith("  beliefs:") for line in lines)
    assert lines[-1].startswith("CHECK: resolved")


def test_the_proposal_is_on_screen_before_the_human_is_asked():
    lines = []

    def approver(proposal):
        assert any(line.startswith("PROPOSAL ") for line in lines)
        return True, "approved"

    run(watch=ProgressView(lines.append), approver=approver)


def test_the_same_state_twice_prints_nothing_new():
    seen = []
    run(watch=seen.append)
    lines = []
    view = ProgressView(lines.append)
    view(seen[-1])
    printed = len(lines)
    view(seen[-1])
    assert len(lines) == printed


def test_the_truth_is_printed_only_after_every_step():
    lines = []
    watch_episode(
        SEED, wear_policy(), write=lines.append, fault="bearing_degradation",
        clock=lambda: 0.0,
    )  # fmt: skip
    heading = lines.index("--- after the run: the truth (the agent never saw this) ---")
    assert all(
        not line.startswith(("#", "CHECK", "PROPOSAL")) for line in lines[heading:]
    )
    assert any("true cause: bearing_degradation" in line for line in lines[heading:])
    # The truth's own words appear nowhere before its heading.
    assert not any("true cause" in line for line in lines[:heading])


def decision(**fields):
    base = dict(
        sequence=4,
        phase="investigate",
        tick=300,
        information_needed="the vibration trend",
        tool="get_sensor_history",
        arguments={"machine_id": "CNC-02"},
        outcome="observed",
        confidence=0.5,
    )
    return DecisionRecord(**(base | fields))


def test_step_lines_say_what_came_of_each_kind_of_step():
    state = run().state
    skipped = step_line(decision(outcome="repeated_call"), state)
    assert skipped[0].endswith("-> skipped: already asked at this tick")
    error = ToolError(code="invalid_arguments", message="Recall failed.")
    failed = step_line(decision(outcome="tool_error", error=error), state)
    assert failed[0].endswith("-> failed: Recall failed.")
    first = state.decisions[0]
    assert step_line(first, state)[0].startswith("#1   ")


def test_shorten_keeps_one_line_and_cuts_long_text():
    assert shorten("a\n  b") == "a b"
    assert shorten("x" * 200, 20) == "x" * 17 + "..."


def test_the_command_refuses_an_unknown_fault():
    with pytest.raises(SystemExit):
        main(["--seed", "1", "--fault", "no_such_fault"])


def test_critic_line_printed_once():
    seen = []
    run(watch=seen.append)
    state = seen[-1].model_copy(deep=True)
    state.critique = CritiqueRecord(
        outcome="answered",
        result=critique_result("object", "H1"),
        shown_hypotheses=("H1",),
        seconds=3.0,
    )
    lines = []
    view = ProgressView(lines.append)
    view(state)
    view(state)
    critic_lines = [line for line in lines if line.startswith("CRITIC (")]
    assert critic_lines == [
        "CRITIC (answered): favoured H1, object, check: get_readings on CNC-02"
    ]


def test_critic_line_without_an_answer():
    seen = []
    run(watch=seen.append)
    state = seen[-1].model_copy(deep=True)
    state.critique = CritiqueRecord(
        outcome="no_answer", shown_hypotheses=("H1",), seconds=40.0
    )
    lines = []
    ProgressView(lines.append)(state)
    assert "CRITIC (no_answer): no critique" in lines
