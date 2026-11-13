"""Block 4 of the 2026-11-13 triage schedule: the Investigate request compiler.

What these tests prove, with no model:

- the compiler turns an open question that names one sensor on a known
  machine into a bounded `get_sensor_summary` read, linked to the question,
  over the window before the alarm up to now;
- it names only machines on the packet's roster, never guesses between two
  sensors, skips sensors not every machine has, offers nothing once the
  research calls are spent, and never repeats a read already observed over
  a window that covers it (the duplicate guard);
- it ranks with no invented probabilities: rival separation, then a check
  that could tell against the favourite, signal trust, prior reads, cost,
  and a stable tie-break;
- "advisory" asks the model as before and records how its choice compares;
  "on" makes the compiled read without a decide question and falls back to
  the model when nothing compiles (the escape hatch); "off" and a deep run
  never use it;
- each turn is traced: the progress view prints it, the experiment record
  keeps it with the research-call count, and the report counts outcomes.
"""

import pytest

from capstone.agent.artifacts import TerminationReason
from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.investigate_compiler import (
    WINDOW_TICKS,
    agreement,
    compile_requests,
    escape_reason,
)
from capstone.agent.loop import InvestigationDeps, run_inner_loop
from capstone.agent.policy import Stop
from capstone.agent.state import DecisionRecord, InvestigateAdvice, Question
from capstone.contracts.hypotheses import Hypothesis
from capstone.progress import ProgressView, advice_line
from capstone.settings import Settings
from tests.helpers import FakeProvider, ScriptedPolicy, ask, new_state

NOW = 70  # the latest observed tick; the alarm fired at tick 10


def triage(*questions, roster=("CNC-01", "CNC-02", "CNC-03"), hypotheses=None):
    """A triage on CNC-02 with two live explanations, H1 leading."""
    # Variables:
    #   questions: The open questions the compiler reads.
    #   roster: The machines the packet verified; () for no packet.
    state = new_state()
    state.mode = "triage"
    state.last_tick = NOW
    if roster:
        state.triage_packet = EvidencePacket(
            machine_id="CNC-02", trigger_tick=10, roster=roster, roster_verified=True
        )
    state.hypotheses = (
        hypotheses
        if hypotheses is not None
        else [
            Hypothesis(
                id="H1", claim="the bearing on CNC-02 is wearing", confidence=0.6
            ),
            Hypothesis(id="H2", claim="a transient spike", confidence=0.3),
        ]
    )
    state.unanswered_questions = list(questions)
    return state


def question(qid, text, **fields):
    return Question(id=qid, text=text, **fields)


RIVAL = question(
    "Q1",
    "Is the vibration on CNC-02 still high after the spike?",
    distinguishes_hypothesis_ids=("H1", "H2"),
    signal_reliability="direct",
)


def roots(state):
    return [c.root for c in compile_requests(state)]


# --- compiling ----------------------------------------------------------------


def test_a_question_compiles_to_one_bounded_summary_read():
    (candidate,) = compile_requests(triage(RIVAL))
    step = candidate.step()
    assert step.request.name == "get_sensor_summary"
    assert step.request.arguments == {
        "machine_id": "CNC-02",
        "sensor": "vibration",
        "from_tick": 10 - WINDOW_TICKS if 10 > WINDOW_TICKS else 0,
        "to_tick": NOW,
    }
    assert step.question_id == "Q1"


def test_only_machines_on_the_roster_are_named():
    q = question("Q1", "Compare temperature on CNC-01 and CNC-07")
    assert roots(triage(q)) == ["CNC-01:temperature"]


def test_without_a_roster_only_the_alarmed_machine_is_known():
    q = question("Q1", "Is load rising on CNC-01 or CNC-02?")
    assert roots(triage(q, roster=())) == ["CNC-02:load"]


def test_a_partial_id_is_not_a_machine():
    q = question("Q1", "Is vibration high on CNC-021?")
    assert roots(triage(q)) == []


@pytest.mark.parametrize(
    "text",
    [
        "Do vibration and temperature both rise on CNC-02?",  # two sensors
        "Did anything change on CNC-02?",  # no sensor
        "Is hydraulic pressure falling on CNC-02?",  # not on every machine
    ],
)
def test_ambiguous_or_unsure_questions_compile_nothing(text):
    assert compile_requests(triage(question("Q1", text))) == []


def test_nothing_is_offered_once_the_research_calls_are_spent():
    state = triage(RIVAL)
    state.tool_call_count = state.budgets.max_tool_calls
    assert compile_requests(state) == []


def observed(state, machine, sensor, start, end):
    state.decisions.append(
        DecisionRecord(
            sequence=len(state.decisions) + 1,
            phase="investigate",
            information_needed="a read",
            tool="get_sensor_summary",
            arguments={
                "machine_id": machine,
                "sensor": sensor,
                "from_tick": start,
                "to_tick": end,
            },
            outcome="observed",
            confidence=0.5,
        )
    )


def test_a_read_already_observed_over_the_window_is_not_repeated():
    state = triage(RIVAL)
    observed(state, "CNC-02", "vibration", 0, NOW + 5)
    assert compile_requests(state) == []


def test_a_narrower_earlier_read_does_not_block_a_new_window():
    # The packet's window up to the alarm does not cover the window up to now.
    state = triage(RIVAL)
    observed(state, "CNC-02", "vibration", 0, 10)
    (candidate,) = compile_requests(state)
    assert candidate.prior_reads == 1


def test_two_questions_about_one_read_offer_it_once():
    again = question("Q2", "Vibration on CNC-02 since the alarm?")
    assert roots(triage(RIVAL, again)) == ["CNC-02:vibration"]


# --- ranking --------------------------------------------------------------------


def test_a_rival_separating_question_ranks_first():
    side = question("Q0", "Is temperature normal on CNC-01?", hypothesis_id="H1")
    assert roots(triage(side, RIVAL))[0] == "CNC-02:vibration"


def test_a_check_that_could_tell_against_the_favourite_ranks_next():
    about_h2 = question("Q1", "Load on CNC-01?", hypothesis_id="H2")
    about_h1 = question("Q2", "Load on CNC-03?", hypothesis_id="H1")
    assert roots(triage(about_h2, about_h1)) == ["CNC-03:load", "CNC-01:load"]


def test_trust_then_prior_reads_then_cost_break_the_rest():
    indirect = question("Q1", "Power on CNC-01?", signal_reliability="indirect")
    direct = question("Q2", "Power on CNC-03?", signal_reliability="direct")
    assert roots(triage(indirect, direct)) == ["CNC-03:power", "CNC-01:power"]
    state = triage(
        question("Q1", "Load on CNC-01?"),
        question("Q2", "Load on CNC-03?", estimated_calls=2),
        question("Q3", "Load on CNC-02?"),
    )
    observed(state, "CNC-01", "load", 0, 5)
    assert roots(state) == ["CNC-02:load", "CNC-03:load", "CNC-01:load"]


def test_ties_break_by_question_order_then_machine_and_never_vary():
    q = question("Q1", "Is temperature high on CNC-03 or CNC-01?")
    state = triage(q)
    first = roots(state)
    assert first == ["CNC-01:temperature", "CNC-03:temperature"]
    assert all(roots(state) == first for _ in range(5))


# --- the escape hatch and agreement -------------------------------------------


def test_the_model_decides_when_causality_is_unclear():
    assert escape_reason(triage(RIVAL, hypotheses=[]), []) == "no_live_explanation"
    assert escape_reason(triage(), []) == "no_open_question"
    vague = triage(question("Q1", "What else is going on?"))
    assert escape_reason(vague, compile_requests(vague)) == (
        "no_question_names_one_sensor_on_a_known_machine"
    )
    assert escape_reason(triage(RIVAL), compile_requests(triage(RIVAL))) is None


def test_agreement_names_how_the_model_choice_compares():
    (choice,) = compile_requests(triage(RIVAL))
    assert agreement(choice, choice.step()) == "same_request"
    readings = ask(
        "get_readings", machine_id="CNC-02", sensor="vibration", from_tick=0, to_tick=9
    )
    assert agreement(choice, readings) == "same_target"
    assert agreement(choice, ask("get_events", from_tick=0, to_tick=9)) == "different"
    assert agreement(choice, Stop(reason=TerminationReason.EVIDENCE_SUFFICIENT)) == (
        "model_stopped"
    )
    assert agreement(choice, None) == "model_failed"


# --- in the loop ------------------------------------------------------------------


def loop(state, mode, decisions=()):
    """Run the investigate loop once with a scripted model; return what ran."""
    # Variables:
    #   provider: The fake factory, which records every request it was sent.
    #   policy: The scripted model; `seen_states` counts its decide questions.
    provider = FakeProvider(lambda request: {"sample_count": 12, "mean": 4.6})
    policy = ScriptedPolicy(list(decisions))
    deps = InvestigationDeps(
        provider=provider,
        policy=policy,
        clock=lambda: 0.0,
        triage_investigate=mode,
    )
    run_inner_loop(state, deps, "investigate")
    return provider, policy


EVENTS = ask("get_events", from_tick=0, to_tick=10)


def test_advisory_asks_the_model_and_records_the_comparison():
    state = triage(RIVAL)
    provider, policy = loop(state, "advisory", [EVENTS])
    assert [c.name for c in provider.calls] == ["get_events"]  # the model's read
    first = state.investigate_advice[0]
    assert first.mode == "advisory" and first.outcome == "different"
    assert first.root == "CNC-02:vibration" and first.model_tool == "get_events"
    assert first.signals["rivals_separated"] == 2


def test_on_makes_the_compiled_read_without_a_decide_question():
    state = triage(RIVAL)
    provider, policy = loop(state, "on")
    assert provider.calls[0].name == "get_sensor_summary"
    assert provider.calls[0].arguments["machine_id"] == "CNC-02"
    first = state.investigate_advice[0]
    assert first.outcome == "compiled" and first.model_tool is None
    read = next(d for d in state.decisions if d.tool == "get_sensor_summary")
    assert read.question_id == "Q1"
    # The model was first asked only after the compiled read: once its
    # question is answered, nothing compiles and the model decides.
    assert len(policy.seen_states) == 1
    assert policy.seen_states[0].tool_call_count == 1
    assert state.investigate_advice[-1].outcome == "no_candidate"


def test_on_falls_back_to_the_model_when_nothing_compiles():
    state = triage(question("Q1", "What else is going on?"))
    provider, policy = loop(state, "on", [EVENTS])
    assert [c.name for c in provider.calls] == ["get_events"]
    assert state.investigate_advice[0].outcome == "no_candidate"
    assert state.investigate_advice[0].reason == (
        "no_question_names_one_sensor_on_a_known_machine"
    )


def test_a_failed_model_answer_is_recorded():
    state = triage(RIVAL)

    def broken(_state):
        raise ValueError("not a decision")

    loop(state, "advisory", [broken])
    assert state.investigate_advice[0].outcome == "model_failed"


@pytest.mark.parametrize(("mode", "kind"), [("off", "triage"), ("on", "deep")])
def test_off_and_deep_never_use_the_compiler(mode, kind):
    state = triage(RIVAL)
    state.mode = kind
    provider, _ = loop(state, mode, [EVENTS])
    assert [c.name for c in provider.calls] == ["get_events"]
    assert state.investigate_advice == []


# --- the setting and the traces -------------------------------------------------


def test_the_setting_is_advisory_by_default(monkeypatch):
    monkeypatch.delenv("TRIAGE_INVESTIGATE", raising=False)
    assert Settings(_env_file=None).triage_investigate == "advisory"
    monkeypatch.setenv("TRIAGE_INVESTIGATE", "on")
    assert Settings(_env_file=None).triage_investigate == "on"
    assert InvestigationDeps(provider=None, policy=None).triage_investigate == "off"


def test_the_progress_view_prints_each_turn_once():
    state = triage(RIVAL)
    lines = []
    view = ProgressView(lines.append)
    state.investigate_advice.append(
        InvestigateAdvice(
            mode="advisory",
            phase="investigate",
            iteration=1,
            candidates=1,
            question_id="Q1",
            tool="get_sensor_summary",
            root="CNC-02:vibration",
            from_tick=0,
            to_tick=NOW,
            model_tool="get_events",
            outcome="different",
        )
    )
    view(state)
    view(state)
    shown = [line for line in lines if line.startswith("INVESTIGATE")]
    assert shown == [advice_line(state.investigate_advice[0])]
    assert shown[0] == (
        "INVESTIGATE advisory investigate (decide): 1 candidate(s); compiled "
        "get_sensor_summary CNC-02:vibration t=0-70 for Q1; model get_events; "
        "different"
    )


def triaged(monkeypatch, mode):
    from capstone.experiment import Case, run_experiment
    from tests.test_episode import SEED
    from tests.test_triage import triage_then_deep

    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    monkeypatch.setenv("TRIAGE_INVESTIGATE", mode)
    (record,) = run_experiment(
        [Case("bearing-6", SEED, "bearing_degradation")],
        triage_then_deep,
        name="investigate",
        clock=lambda: 0.0,
        triage=True,
    )
    return record


def test_a_triage_record_keeps_the_advice_and_the_research_count(monkeypatch):
    from capstone.experiment import format_investigate, report

    record = triaged(monkeypatch, "advisory")
    triage_record = record.triage
    assert triage_record.investigate_advice is not None
    # The line screening has its own allowance: one call more than research.
    assert triage_record.tool_calls == triage_record.research_tool_calls + 1
    assert triage_record.research_tool_calls <= 6
    # The scripted triage has no explanation at first and no open question in
    # Test, so each turn records why the model decided (the escape hatch).
    assert triage_record.investigate_advice
    assert {a.outcome for a in triage_record.investigate_advice} == {"no_candidate"}
    line = format_investigate([record])
    assert line.startswith("investigate compiler (advisory): ")
    assert line in report([record], {})


def test_the_report_counts_each_outcome():
    from capstone.experiment import format_investigate

    def advice(outcome):
        return InvestigateAdvice(
            mode="on", phase="investigate", iteration=1, candidates=1, outcome=outcome
        )

    class Triage:
        investigate_advice = [
            advice("compiled"),
            advice("compiled"),
            advice("same_request"),
            advice("different"),
            advice("no_candidate"),
        ]

    class Record:
        triage = Triage()

    line = format_investigate([Record()])
    assert line == (
        "investigate compiler (on): 5 turn(s); decide replaced 2; model agreed "
        "1 of 2 compared (1 same read, 0 same sensor); different 1, model "
        "stopped 0, model failed 0; no candidate 1"
    )
    assert format_investigate([]) is None


def test_a_deep_episode_is_unchanged_by_the_setting(monkeypatch):
    from capstone.episode import run_episode
    from tests.test_episode import SEED, wear_policy

    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.delenv("TRIAGE", raising=False)

    def run(mode):
        monkeypatch.setenv("TRIAGE_INVESTIGATE", mode)
        return run_episode(
            SEED, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0
        ).state

    off, on = run("off"), run("on")
    assert on.mode == "deep" and on.investigate_advice == []
    assert on.model_dump() == off.model_dump()
