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
    assert lines[-2].startswith("CHECK: resolved")
    assert lines[-1].startswith("  calls: research ")


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
    heading = "  ruled out by tree-of-thought (contradicted by evidence):"
    assert lines.count(heading) == 1
    assert "    C3  a wrong speed setting  (rated impossible)" in lines


def test_deferred_candidates_are_set_aside_not_ruled_out():
    # Variables:
    #   ruled_out, set_aside: The two headings, each followed by its own candidates.
    from capstone.agent.state import PrunedCandidate
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.pruned_candidates = [
        PrunedCandidate(
            id="C1", claim="coolant", reason="rated low", status="deferred"
        ),
        PrunedCandidate(
            id="C2", claim="setting", reason="contradicted by E4", status="contradicted"
        ),
    ]
    ProgressView(lines.append)(state)
    ruled_out = lines.index(
        "  ruled out by tree-of-thought (contradicted by evidence):"
    )
    set_aside = lines.index("  set aside by tree-of-thought (deferred, not disproved):")
    assert lines[ruled_out + 1] == "    C2  setting  (contradicted by E4)"
    assert lines[set_aside + 1] == "    C1  coolant  (rated low)"


def test_a_blind_critique_is_marked_and_shows_which_label_was_which():
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.critique = CritiqueRecord(
        outcome="answered",
        result=critique_result("object", "H2"),
        shown_hypotheses=("H1", "H2", "H3"),
        seconds=4.0,
        blind=True,
        shown_order=("H3", "H1", "H2"),
    )
    ProgressView(lines.append)(state)
    at = next(i for i, line in enumerate(lines) if line.startswith("CRITIC ("))
    assert lines[at].startswith("CRITIC (answered, blind): favoured H2, object")
    assert lines[at + 1] == (
        "  shown as X1=H3, X2=H1, X3=H2; the agent's leader H1 was X2"
    )


def test_a_blind_critique_without_an_answer_is_still_marked_blind():
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.critique = CritiqueRecord(
        outcome="no_answer", shown_hypotheses=("H1",), seconds=40.0, blind=True
    )
    ProgressView(lines.append)(state)
    assert "CRITIC (no_answer, blind): no critique" in lines


def test_the_follow_up_says_what_it_did_and_how_the_leader_moved():
    from capstone.agent.artifacts import RecheckRecord
    from tests.helpers import new_state

    lines = []
    view = ProgressView(lines.append)
    state = new_state()
    state.recheck = RecheckRecord(
        outcome="observed",
        trigger="objection",
        question="The critic's check: the spindle temperature on CNC-02",
        tool="get_readings",
        evidence_id="E9",
        leading_before="H1",
        confidence_before=0.7,
        leading_after="H2",
        confidence_after=0.85,
    )
    view(state)
    view(state)
    at = lines.index("FOLLOW-UP (objection): observed, get_readings -> E9")
    assert lines[at + 1 : at + 3] == [
        "  question: The critic's check: the spindle temperature on CNC-02",
        "  leader before H1 0.70, after H2 0.85",
    ]
    assert sum(line.startswith("FOLLOW-UP") for line in lines) == 1


def test_a_skipped_follow_up_says_why():
    from capstone.agent.artifacts import RecheckRecord
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.recheck = RecheckRecord(outcome="skipped", reason="no tool calls left")
    ProgressView(lines.append)(state)
    assert "FOLLOW-UP skipped: no tool calls left" in lines


def test_a_follow_up_that_made_no_call_gives_its_outcome_and_reason():
    from capstone.agent.artifacts import RecheckRecord
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.recheck = RecheckRecord(
        outcome="already_answered",
        trigger="agreement",
        reason="the check was already made as E4",
    )
    ProgressView(lines.append)(state)
    at = lines.index("FOLLOW-UP (agreement): already answered")
    assert lines[at + 1] == "  why: the check was already made as E4"


def test_an_unresolved_conclusion_shows_what_is_open_and_the_next_check():
    from capstone.agent.artifacts import AgentConclusion
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.conclusion = AgentConclusion(
        diagnosis="Bearing wear on CNC-02, not yet confirmed",
        confidence=0.7,
        recommendation="escalate",
        assessment="unresolved",
        unresolved_questions=("is the temperature rising?", "is it the batch?"),
        next_check="read spindle temperature on CNC-02",
    )
    ProgressView(lines.append)(state)
    at = next(i for i, line in enumerate(lines) if line.startswith("CONCLUSION ("))
    assert lines[at + 1 : at + 4] == [
        "  assessment: unresolved",
        "  open: is the temperature rising?; is it the batch?",
        "  next check: read spindle temperature on CNC-02",
    ]


def test_a_conclusion_without_an_assessment_prints_none():
    from capstone.agent.artifacts import AgentConclusion
    from tests.helpers import new_state

    lines = []
    state = new_state()
    state.conclusion = AgentConclusion(
        diagnosis="Bearing wear", confidence=0.9, recommendation="intervene"
    )
    ProgressView(lines.append)(state)
    assert not any(line.startswith("  assessment:") for line in lines)


def test_the_calls_line_keeps_the_three_allowances_apart():
    from capstone.agent.artifacts import AgentConclusion
    from capstone.progress import calls_line
    from tests.helpers import new_state

    state = new_state()
    state.tool_call_count = 9
    state.followup_tool_calls_used = 2
    state.critic_tool_calls_used = 1
    assert calls_line(state) == (
        "  calls: research 6/20, critic check 1/1, after the action 2/14"
    )
    state.conclusion = AgentConclusion(
        diagnosis="Bearing wear", confidence=0.9, recommendation="intervene"
    )
    lines = []
    ProgressView(lines.append)(state)
    at = next(i for i, line in enumerate(lines) if line.startswith("CONCLUSION ("))
    assert lines[at + 1] == calls_line(state)


def manual_state(decision_fields, content=None):
    """A state holding one search_manual step and, if given, its answer."""
    from capstone.contracts.evidence import Evidence
    from tests.helpers import new_state

    state = new_state()
    if content is not None:
        state.evidence.append(
            Evidence(
                id="E1", source_id="manual", source_type="document", content=content
            )
        )
    step = decision(tool="search_manual", arguments={"text": "vibration"})
    return state, step.model_copy(update=decision_fields)


def test_a_manual_search_says_it_answered_and_which_sections():
    state, step = manual_state(
        {"phase": "observe", "evidence_ids": ("E1",)},
        content='[{"section": "§2.7"}, {"section": "§3.1"}]',
    )
    assert step_line(step, state)[-1] == (
        "       manual (manual step): answered, sections §2.7, §3.1"
    )


def test_a_manual_search_with_no_match_and_a_failed_one():
    state, step = manual_state({"evidence_ids": ("E1",)}, content="[]")
    assert step_line(step, state)[-1] == (
        "       manual (agent's search): answered, sections no section matched"
    )
    error = ToolError(code="provider_error", message="The manual is unavailable.")
    state, step = manual_state({"outcome": "tool_error", "error": error})
    lines = step_line(step, state)
    assert lines[0].endswith("-> failed: The manual is unavailable.")
    assert lines[-1] == "       manual (agent's search): failed"


def test_other_tools_get_no_manual_line():
    state = run().state
    first = state.decisions[0]
    assert not any("manual (" in line for line in step_line(first, state))


class Settings:
    """Just the fields run_header reads."""

    def __init__(self, **fields):
        base = dict(
            critic=True,
            critic_blind=False,
            critic_followup=True,
            manual_step=True,
            embedding_model="nvidia/llama-3.2-nv-embedqa-1b-v2",
        )
        self.__dict__.update(base | fields)


def test_the_run_header_names_the_critic_treatment():
    from capstone.progress import run_header

    anchored = run_header(Settings(), manual="semantic", tree_of_thought=True)
    assert anchored == [
        "RUN: critic anchored, follow-up on; manual by meaning "
        "(nvidia/llama-3.2-nv-embedqa-1b-v2), manual step on",
        "RUN: tree-of-thought on; hazards off",
    ]
    blind = run_header(Settings(critic_blind=True), manual=None, hazards="blackout")
    assert blind[0].startswith("RUN: critic blind, follow-up on; no manual")
    assert blind[1] == "RUN: tree-of-thought off; hazards blackout"
    off = run_header(Settings(critic=False), manual="keyword", hazards=True)
    assert off == [
        "RUN: critic off; manual by keyword, manual step on",
        "RUN: tree-of-thought off; hazards standard",
    ]


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
