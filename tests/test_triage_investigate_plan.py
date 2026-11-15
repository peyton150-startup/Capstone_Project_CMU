"""The investigate compiler over the fixed triage plan's own questions.

What these tests prove, with no model:

- of every fixed-plan template (an alarm on each sensor, a stopped machine,
  failed inspections, anything else), an alarm's Q1 compiles from its
  measured predicate, and each question the plan's table names a read for
  (`planned_reads`: events, settings, inspections, service records, an
  alarm's follow-up sensor) compiles to that read, before any explanation
  too; a question with no single read (the screening, which machines failed
  jobs passed through) still goes to the model. In the 2026-11-15 Lightning
  runs the compiler stood aside 30 times for want of a sensor question, and
  `get_settings` was never called in 52 triages;
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
- in the loop with TRIAGE_INVESTIGATE=on, Q1 and then every planned read
  is made without a decide question, and the model decides once they are
  answered.
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


# What each template compiles to, best first: (question, tool, root).
COMPILED = {
    "vibration alarm": [
        ("Q1", "get_sensor_summary", "CNC-02:vibration"),
        ("Q3", "get_events", "CNC-02:get_events"),
        ("Q4", "get_settings", "line:get_settings"),
        ("Q5", "get_sensor_summary", "CNC-02:temperature"),
    ],
    "following error alarm": [
        ("Q1", "get_sensor_summary", "CNC-02:following_error"),
        ("Q3", "get_events", "CNC-02:get_events"),
        ("Q4", "get_settings", "line:get_settings"),
        ("Q5", "get_inspections", "line:get_inspections"),
    ],
    "hydraulic pressure alarm": [
        ("Q1", "get_sensor_summary", "CNC-02:hydraulic_pressure"),
        ("Q3", "get_events", "CNC-02:get_events"),
        ("Q4", "get_settings", "line:get_settings"),
        ("Q5", "get_inspections", "line:get_inspections"),
    ],
    "other sensor alarm": [
        ("Q1", "get_sensor_summary", "CNC-02:temperature"),
        ("Q3", "get_events", "CNC-02:get_events"),
        ("Q4", "get_settings", "line:get_settings"),
    ],
    "stopped machine": [
        ("Q1", "get_events", "CNC-02:get_events"),
        ("Q4", "get_maintenance_history", "CNC-02:get_maintenance_history"),
    ],
    "failed inspections": [
        ("Q2", "get_inspections", "line:get_inspections"),
        ("Q3", "get_settings", "line:get_settings"),
        ("Q5", "get_events", "line:get_events"),
    ],
    "anything else": [
        ("Q2", "get_events", "line:get_events"),
        ("Q3", "get_inspections", "line:get_inspections"),
    ],
}


@pytest.mark.parametrize("explained", [False, True])
@pytest.mark.parametrize("name", TEMPLATES)
def test_each_template_compiles_its_measured_and_planned_reads(name, explained):
    state = planned(TEMPLATES[name], explained=explained)
    ranked = compile_requests(state)
    assert [(c.question_id, c.tool, c.root) for c in ranked] == COMPILED[name]
    assert all(c.measured != c.planned for c in ranked)  # the plan chose each
    assert escape_reason(state, ranked) is None  # with or without an explanation


def test_planned_reads_take_the_alarm_window_or_none():
    state = planned(TEMPLATES["vibration alarm"])
    args = {c.question_id: c.step().request.arguments for c in compile_requests(state)}
    window = {"from_tick": max(0, ALARM_TICK - 60), "to_tick": NOW}
    assert args["Q3"] == {"machine_id": "CNC-02", **window}
    assert args["Q4"] == {}  # settings: every machine, now
    assert args["Q5"] == {"machine_id": "CNC-02", "sensor": "temperature", **window}
    assert all(c.step().question_id == c.question_id for c in compile_requests(state))


def test_a_planned_read_on_an_unknown_machine_is_not_compiled():
    state = planned(TEMPLATES["vibration alarm"])
    state.triage_packet = state.triage_packet.model_copy(update={"roster": ("CNC-01",)})
    # Q1's predicate and Q3/Q5 name CNC-02; only the line-wide settings remain.
    assert [c.question_id for c in compile_requests(state)] == ["Q4"]


def test_a_planned_read_already_made_is_not_offered_again():
    state = planned(TEMPLATES["vibration alarm"])
    run(state, [], answer={"sample_count": 12, "mean": 4.6})
    calls = [c for c in compile_requests(state) if c.tool == "get_settings"]
    assert calls == []
    # Even with Q4 reopened, the same settings read was made: not offered.
    state.unanswered_questions.append(fixed_plan(state.anomaly)[3])
    assert [c for c in compile_requests(state) if c.question_id == "Q4"] == []


@pytest.mark.parametrize("name", ALARMS)
def test_the_compiled_read_is_the_predicates_window(name):
    state = planned(TEMPLATES[name])
    predicate = state.question_predicates["Q1"]
    candidate = compile_requests(state)[0]
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
    assert "Q1" not in {c.question_id for c in compile_requests(state)}
    # Even if Q1 were reopened, the window was read: the duplicate guard holds.
    state.unanswered_questions.insert(0, fixed_plan(state.anomaly)[0])
    assert "Q1" not in {c.question_id for c in compile_requests(state)}


def test_a_models_question_is_still_compiled_from_its_words():
    state = planned(TEMPLATES["stopped machine"], explained=True)
    state.unanswered_questions.append(
        Question(id="Q6", text="Is the temperature on CNC-03 rising?")
    )
    (parsed,) = [c for c in compile_requests(state) if c.question_id == "Q6"]
    assert parsed.root == "CNC-03:temperature"
    assert not parsed.measured and not parsed.planned


def test_a_fixed_question_reworded_by_a_model_is_parsed_again():
    state = planned(TEMPLATES["vibration alarm"], explained=True)
    state.unanswered_questions[1] = Question(id="Q2", text="Vibration on CNC-03?")
    ranked = compile_requests(state)
    assert ranked[0].root == "CNC-02:vibration"  # Q1, its predicate's read
    # The reworded Q2 is a model's question now: parsed from its words, and
    # ranked by its own (unknown) reliability, after the plan's reads.
    (parsed,) = [c for c in ranked if c.question_id == "Q2"]
    assert parsed.root == "CNC-03:vibration"
    assert not parsed.measured and not parsed.planned


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
    # Then the planned reads, in rank order, with no model asked.
    assert [c.name for c in provider.calls] == [
        "get_sensor_summary",
        "get_events",
        "get_settings",
        "get_sensor_summary",
    ]
    assert [a.outcome for a in state.investigate_advice[:4]] == ["compiled"] * 4
    # Only the screening question (no single read) is left, so the model,
    # asked once, decides next.
    assert [q.id for q in state.unanswered_questions] == ["Q2"]
    assert state.investigate_advice[4].outcome == "no_candidate"
    assert state.investigate_advice[4].reason == "no_live_explanation"
    assert len(policy.seen_states) == 1


# --- with Observe's reads kept off research (PR 274) ----------------------------


@pytest.mark.parametrize("observe", ["shared", "separate"])
def test_a_triage_episode_reads_the_plans_records_when_research_has_the_calls(
    monkeypatch, observe
):
    """Both fixes together, in a real episode: with TRIAGE_OBSERVE_CALLS=separate
    research has room for the plan's record reads, which the compiler makes."""
    from tests.test_episode import wear_policy
    from tests.test_triage import ByMode
    from tests.test_triage import run as run_episode_triage

    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    monkeypatch.setenv("TRIAGE_INVESTIGATE", "on")
    monkeypatch.setenv("TRIAGE_OBSERVE_CALLS", observe)
    result = run_episode_triage(
        ByMode(wear_policy("intervene"), wear_policy()),
        monkeypatch,
        then_deep=False,
        triage=True,
    )
    triage = result.triage
    compiled = [a.tool for a in triage.investigate_advice if a.outcome == "compiled"]
    research = [
        d.tool for d in triage.decisions if d.phase != "observe" and d.tool is not None
    ]
    open_ids = [q.id for q in triage.unanswered_questions]
    assert {"get_events", "get_settings"} <= set(compiled)
    assert "get_settings" in research
    if observe == "separate":
        # Every plan question was answered within research's six calls.
        assert open_ids == []
    else:
        # Observe's reads used research calls, so the follow-up was never read.
        assert open_ids == ["Q5"]
    assert triage.research_tool_calls <= triage.budgets.max_tool_calls
    assert len(compiled) <= triage.budgets.max_tool_calls
