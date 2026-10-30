"""The live progress view: a watcher hooked into the loop, and the terminal
view built on it. Scripted policies only; no network."""

import pytest

from capstone.agent.artifacts import CritiqueRecord, CritiqueResult, Objection
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


def test_critic_detail_lines_say_why_how_sure_and_who_answered():
    seen = []
    run(watch=seen.append)
    state = seen[-1].model_copy(deep=True)
    state.critique = CritiqueRecord(
        outcome="answered",
        result=CritiqueResult(
            favoured="H1",
            why="the readings rise steadily",
            discriminating_check="get_readings on CNC-02",
            objections=(
                Objection(
                    kind="missing_evidence", text="one reading", evidence_ids=("E1",)
                ),
                Objection(kind="alternative", text="fits wear too"),
            ),
            verdict="object",
            favoured_confidence=0.65,
            supports_action=False,
        ),
        shown_hypotheses=("H1", "H2"),
        seconds=8.24,
        answered_by="mistral/ministral-14b-2512",
    )
    lines = []
    ProgressView(lines.append)(state)
    at = next(i for i, line in enumerate(lines) if line.startswith("CRITIC ("))
    assert lines[at + 1 : at + 3] == [
        "  why: the readings rise steadily",
        "  confidence 0.65, supports action: no, objections: "
        "missing_evidence, alternative; mistral/ministral-14b-2512 in 8.2 s",
    ]


def test_critic_detail_with_no_objections_and_no_model_name():
    seen = []
    run(watch=seen.append)
    state = seen[-1].model_copy(deep=True)
    state.critique = CritiqueRecord(
        outcome="answered",
        result=critique_result("no_objection", "H1"),
        shown_hypotheses=("H1",),
        seconds=3.0,
    )
    lines = []
    ProgressView(lines.append)(state)
    assert (
        "  confidence 0.60, supports action: no, objections: none; "
        "unknown model in 3.0 s"
    ) in lines


def test_critic_without_an_answer_still_says_how_long_it_tried():
    seen = []
    run(watch=seen.append)
    state = seen[-1].model_copy(deep=True)
    state.critique = CritiqueRecord(
        outcome="no_answer", shown_hypotheses=("H1",), seconds=40.04
    )
    lines = []
    ProgressView(lines.append)(state)
    at = lines.index("CRITIC (no_answer): no critique")
    assert lines[at + 1] == "  tried for 40.0 s"


def test_terminal_progress_uses_color_without_changing_text(monkeypatch):
    # Variables:
    #   terminal: An interactive stream that captures the displayed text.
    #   output: Captured text, checked with and without ANSI colors.
    import io
    import re
    import sys

    from capstone.progress import print_progress

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    terminal = Terminal()
    monkeypatch.setattr(sys, "stdout", terminal)
    monkeypatch.delenv("NO_COLOR", raising=False)
    for line in (
        "  beliefs:",
        "    H1 0.90  bearing",
        "#1   observe     get_time()",
        "#2   investigate get_readings()",
        "CRITIC (ok): favoured H1",
    ):
        print_progress(line)
    output = terminal.getvalue()
    assert "\x1b[95mCRITIC (ok): favoured H1\x1b[0m" in output
    assert re.sub(r"\x1b\[[0-9;]*m", "", output).splitlines() == [
        "  beliefs:",
        "    H1 0.90  bearing",
        "#1   observe     get_time()",
        "#2   investigate get_readings()",
        "CRITIC (ok): favoured H1",
    ]


def test_redirected_progress_stays_plain(monkeypatch):
    # Variables:
    #   output: A redirected stream that must not contain color codes.
    import io
    import sys

    from capstone.progress import print_progress

    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    print_progress("  beliefs:")
    assert output.getvalue() == "  beliefs:\n"


def test_no_color_environment_keeps_terminal_plain(monkeypatch):
    # Variables:
    #   output: An interactive stream with colors disabled by the environment.
    import io
    import sys

    from capstone.progress import print_progress

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    output = Terminal()
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setenv("NO_COLOR", "1")
    print_progress("CRITIC (ok): favoured H1")
    assert output.getvalue() == "CRITIC (ok): favoured H1\n"


def test_the_view_prints_what_tree_of_thought_ruled_out_once():
    from capstone.agent.state import PrunedCandidate
    from tests.helpers import new_state

    lines = []
    view = ProgressView(lines.append)
    state = new_state()
    state.pruned_candidates = [
        PrunedCandidate(
            id="C3",
            claim="a wrong speed setting",
            reason="rated impossible",
            status="contradicted",
        )
    ]
    view(state)
    view(state)
    assert lines.count("  ruled out by tree-of-thought:") == 1
    assert "    C3  a wrong speed setting  (contradicted: rated impossible)" in lines


def test_the_view_says_when_the_verdict_does_not_match_the_pick():
    from tests.helpers import new_state

    lines = []
    view = ProgressView(lines.append)
    state = new_state()
    state.critique = CritiqueRecord(
        outcome="answered",
        result=critique_result("object", favoured="H1"),
        shown_hypotheses=("H1",),
        seconds=5.0,
        verdict_mismatch="object while favouring the leading H1, with no contradiction or alternative raised",
    )
    view(state)
    assert any(
        line.startswith("  verdict does not match the pick: object") for line in lines
    )
