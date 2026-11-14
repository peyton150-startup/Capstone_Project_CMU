"""The investigate compiler over the fixed triage plan's own questions.

What these tests prove, with no model:

- of every fixed-plan template (an alarm on each sensor, a stopped machine,
  failed inspections, anything else), only an alarm's Q1 compiles, because
  it is the only question with a measured predicate; the rest ask for a
  screening, events, settings or inspections and go to the model;
- Q1 compiles before any explanation is formed (investigate runs before
  hypothesize), which is where 147 of 184 compiler turns stood aside in the
  2026-11-14 live runs, and it compiles for hydraulic pressure too, since
  the alarm came from that sensor;
- the compiled read's window is the predicate's window exactly, and the
  predicate judges the read's answer (never "stale"), so the question
  closes on a measured verdict;
- a fixed-plan question is never compiled from its words (Q2's line
  screening was compiled as a sensor read in 7 of 14 live compiles), while
  a model's question still is;
- in the loop with TRIAGE_INVESTIGATE=on, Q1 is read without a decide
  question, and the model decides once it is settled.
"""

import pytest

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.evidence_tests import evaluate
from capstone.agent.investigate_compiler import compile_requests, escape_reason
from capstone.agent.loop import InvestigationDeps, run_inner_loop
from capstone.agent.state import Question
from capstone.agent.triage_plan import fixed_plan, fixed_predicates
from capstone.contracts.hypotheses import Hypothesis
from tests.helpers import FakeProvider, ScriptedPolicy, new_state

ALARM_TICK = 40
NOW = 45


def alarm(sensor, side="above", limit="4.50"):
    return DetectedAnomaly(
        tick=ALARM_TICK,
        machine_id="CNC-02",
        kind="alarm",
        description=f"alarm on CNC-02: {sensor} 9.99 u {side} {limit}",
    )


TEMPLATES = {
    "vibration alarm": alarm("vibration"),
    "following error alarm": alarm("following_error", limit="0.30"),
    "hydraulic pressure alarm": alarm("hydraulic_pressure", "below", "65.0"),
    "other sensor alarm": alarm("temperature", limit="80.0"),
    "stopped machine": DetectedAnomaly(
        tick=ALARM_TICK, machine_id="CNC-02", kind="status", description="stopped"
    ),
    "failed inspections": DetectedAnomaly(
        tick=ALARM_TICK, kind="inspection_failures", description="3 parts failed"
    ),
    "anything else": DetectedAnomaly(
        tick=ALARM_TICK, machine_id="CNC-02", kind="drift", description="odd"
    ),
}
ALARMS = [name for name in TEMPLATES if name.endswith("alarm")]


def planned(anomaly, *, explained=False):
    """A triage after the fixed plan, as the investigate stage sees it."""
    # Variables:
    #   explained: Whether hypothesize has formed an explanation yet; in the
    #     investigate stage it has not.
    state = new_state()
    state.anomaly = anomaly
    state.mode = "triage"
    state.last_tick = NOW
    state.triage_packet = EvidencePacket(
        machine_id="CNC-02",
        trigger_tick=ALARM_TICK,
        roster=("CNC-01", "CNC-02", "CNC-03"),
        roster_verified=True,
    )
    state.unanswered_questions = list(fixed_plan(anomaly))
    state.question_predicates.update(fixed_predicates(anomaly))
    state.fixed_plan_used = True
    if explained:
        state.hypotheses = [Hypothesis(id="H1", claim="a fault", confidence=0.5)]
    return state


@pytest.mark.parametrize("explained", [False, True])
@pytest.mark.parametrize("name", TEMPLATES)
def test_only_an_alarms_measured_question_compiles(name, explained):
    state = planned(TEMPLATES[name], explained=explained)
    ranked = compile_requests(state)
    if name in ALARMS:
        assert [(c.question_id, c.measured) for c in ranked] == [("Q1", True)]
        assert escape_reason(state, ranked) is None
    else:
        assert ranked == []
        assert escape_reason(state, ranked) == (
            "no_question_names_one_sensor_on_a_known_machine"
            if explained
            else "no_live_explanation"
        )


@pytest.mark.parametrize("name", ALARMS)
def test_the_compiled_read_is_the_predicates_window(name):
    state = planned(TEMPLATES[name])
    predicate = state.question_predicates["Q1"]
    (candidate,) = compile_requests(state)
    assert candidate.step().request.arguments == {
        "machine_id": predicate.machine_id,
        "sensor": predicate.sensor,
        "from_tick": predicate.from_tick,
        "to_tick": predicate.to_tick,
    }
    assert candidate.signals()["measured"] == 1


def test_a_settled_predicate_is_not_read_again():
    state = planned(TEMPLATES["vibration alarm"])
    run(state, [], answer={"sample_count": 12, "mean": 4.6})
    assert compile_requests(state) == []
    # Even if Q1 were reopened, the window was read: the duplicate guard holds.
    state.unanswered_questions.insert(0, fixed_plan(state.anomaly)[0])
    assert compile_requests(state) == []


def test_a_models_question_is_still_compiled_from_its_words():
    state = planned(TEMPLATES["stopped machine"], explained=True)
    state.unanswered_questions.append(
        Question(id="Q6", text="Is the temperature on CNC-03 rising?")
    )
    assert [c.root for c in compile_requests(state)] == ["CNC-03:temperature"]


def test_a_fixed_question_reworded_by_a_model_is_parsed_again():
    state = planned(TEMPLATES["vibration alarm"], explained=True)
    state.unanswered_questions[1] = Question(id="Q2", text="Vibration on CNC-03?")
    assert [c.root for c in compile_requests(state)] == [
        "CNC-02:vibration",
        "CNC-03:vibration",
    ]


def run(state, decisions, answer):
    """Run the investigate loop with TRIAGE_INVESTIGATE=on and a scripted model."""
    # Variables:
    #   answer: What the fake factory says to every read; the window comes
    #     from the request, as the real summary tool echoes it.
    provider = FakeProvider(lambda request: {**request.arguments, **answer}, tick=NOW)
    policy = ScriptedPolicy(list(decisions))
    deps = InvestigationDeps(
        provider=provider, policy=policy, clock=lambda: 0.0, triage_investigate="on"
    )
    run_inner_loop(state, deps, "investigate")
    return provider, policy


@pytest.mark.parametrize(("mean", "verdict"), [(4.6, "true"), (4.4, "false")])
def test_on_reads_q1_without_a_model_and_its_predicate_settles_it(mean, verdict):
    state = planned(TEMPLATES["vibration alarm"])
    provider, policy = run(state, [], answer={"sample_count": 12, "mean": mean})
    first = provider.calls[0]
    assert first.name == "get_sensor_summary"
    p = state.question_predicates["Q1"]
    assert (first.arguments["from_tick"], first.arguments["to_tick"]) == (
        p.from_tick,
        p.to_tick,
    )
    assert evaluate(p, state).verdict == verdict
    assert "Q1" not in {q.id for q in state.unanswered_questions}
    assert state.investigate_advice[0].outcome == "compiled"
    # With Q1 settled and no explanation formed, the model decides next.
    assert state.investigate_advice[1].outcome == "no_candidate"
    assert state.investigate_advice[1].reason == "no_live_explanation"
    assert len(policy.seen_states) == 1
