"""Compiled reads back to back, with no model question in between (audit #4).

With TRIAGE_INVESTIGATE=on the compiler picks a triage's next read, but each
read used to be followed by a model question: with STEP_QUESTIONS=1,
interpret_and_decide, whose proposed next step then ran ahead of the
compiler's; with STEP_QUESTIONS=2, the standalone interpret question. In the
2026-11-15 Lightning `all` arm, 23 of 69 research turns came from such a
model step. Now a compiled read that another compiled read follows asks no
model; the last compiled read is interpreted as before, and the model takes
over from there.
"""

import pytest

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.loop import InvestigationDeps, run_inner_loop
from capstone.agent.policy import Interpretation, InterpretedStep
from capstone.agent.triage_plan import fixed_plan, fixed_predicates
from tests.helpers import FakeProvider, ScriptedPolicy, ask, new_state

ALARM_TICK = 40
NOW = 45
ALARM = DetectedAnomaly(
    tick=ALARM_TICK,
    machine_id="CNC-02",
    kind="alarm",
    description="alarm on CNC-02: vibration 9.99 u above 4.50",
)
# What a model would propose after a read: a read of its own choosing.
MODEL_STEP = ask(
    "get_readings", machine_id="CNC-03", sensor="temperature", from_tick=0, to_tick=NOW
)
COMPILED = ["get_sensor_summary", "get_events", "get_settings", "get_sensor_summary"]


class Model(ScriptedPolicy):
    """A scripted model that, like a real one, proposes a next step with every
    reading, and counts how often it is asked to read a result."""

    def __init__(self):
        super().__init__()
        self.read_and_decided = 0
        self.read_only = 0

    def interpret_and_decide(self, state, phase, step, evidence):
        self.read_and_decided += 1
        return InterpretedStep(interpretation=Interpretation(), decision=MODEL_STEP)

    def interpret(self, state, step, evidence):
        self.read_only += 1
        return Interpretation()


def triage(mode="triage", **budgets):
    """A triage after the fixed plan, as the investigate stage sees it."""
    state = new_state(**budgets)
    state.anomaly = ALARM
    state.mode = mode
    state.last_tick = NOW
    state.triage_packet = EvidencePacket(
        machine_id="CNC-02",
        trigger_tick=ALARM_TICK,
        roster=("CNC-01", "CNC-02", "CNC-03"),
        roster_verified=True,
    )
    state.unanswered_questions = list(fixed_plan(ALARM))
    state.question_predicates.update(fixed_predicates(ALARM))
    state.fixed_plan_used = True
    return state


def deps_for(model, provider, *, step_questions=1, investigate="on"):
    return InvestigationDeps(
        provider=provider,
        policy=model,
        clock=lambda: 0.0,
        triage_investigate=investigate,
        step_questions=step_questions,
    )


def run(state, *, step_questions=1, investigate="on"):
    provider = FakeProvider(
        lambda request: {**request.arguments, "sample_count": 12, "mean": 4.6},
        tick=NOW,
    )
    model = Model()
    deps = deps_for(
        model, provider, step_questions=step_questions, investigate=investigate
    )
    run_inner_loop(state, deps, "investigate")
    return [c.name for c in provider.calls], model


def test_the_models_next_step_no_longer_runs_ahead_of_the_compiler():
    state = triage()
    calls, model = run(state)
    # Every compiled read first; only then the model's own proposal.
    assert calls[:4] == COMPILED
    assert calls[4] == "get_readings"
    # The model read just the last compiled result, and decided from there.
    assert model.read_and_decided >= 1
    assert state.compiled_reads_uninterpreted == 3
    assert [a.outcome for a in state.investigate_advice[:4]] == ["compiled"] * 4


def test_with_two_questions_per_step_only_the_last_compiled_read_is_interpreted():
    state = triage()
    calls, model = run(state, step_questions=2)
    assert calls[:4] == COMPILED
    assert model.read_only == 1  # the 4th compiled read, not the first three
    assert state.compiled_reads_uninterpreted == 3


def test_every_compiled_read_still_answers_its_question():
    state = triage()
    run(state)
    assert {"Q1", "Q3", "Q4", "Q5"} <= set(state.answers)
    assert [q.id for q in state.unanswered_questions] == ["Q2"]
    assert len(state.evidence) >= 4  # all kept for hypothesize and conclude


def test_the_last_read_the_budget_allows_is_interpreted():
    # Two research calls: Q1, then Q3 with no call left for a third read, so
    # Q3's result is read by the model and nothing more is compiled.
    state = triage(max_tool_calls=2)
    calls, model = run(state)
    assert calls == COMPILED[:2]
    assert state.compiled_reads_uninterpreted == 1
    assert model.read_and_decided == 1


@pytest.mark.parametrize("investigate", ["advisory", "off"])
def test_without_the_compiler_in_charge_every_read_is_interpreted(investigate):
    state = triage()
    model = Model()
    model.decisions = [MODEL_STEP, MODEL_STEP]
    provider = FakeProvider(lambda request: {"rows": []}, tick=NOW)
    run_inner_loop(
        state, deps_for(model, provider, investigate=investigate), "investigate"
    )
    assert state.compiled_reads_uninterpreted == 0
    assert model.read_and_decided == len(provider.calls)


def test_a_deep_run_is_unchanged():
    state = triage(mode="deep")
    model = Model()
    model.decisions = [MODEL_STEP]
    provider = FakeProvider(lambda request: {"rows": []}, tick=NOW)
    run_inner_loop(state, deps_for(model, provider), "investigate")
    assert state.compiled_reads_uninterpreted == 0
    assert state.investigate_advice == []
    assert model.read_and_decided == len(provider.calls) >= 1
