"""Triage stage metrics (2026-11-13): where a triage spent its model questions.

The A0 baseline could not split model time by stage, because a question was
recorded only by its job and "decide" runs in both investigate and test.
These tests check that each model question now carries its stage and mode,
that the first hypothesis is timed on the run's own clock, and that the
experiment record and report sum them up per stage.
"""

import pytest

from capstone.agent.artifacts import AgentConclusion
from capstone.agent.loop import apply_interpretation
from capstone.agent.model_policy import ModelCall
from capstone.agent.policy import Interpretation
from capstone.agent.state import DecisionRecord
from capstone.contracts.hypotheses import Hypothesis
from capstone.evaluation.triage_metrics import triage_metrics
from capstone.experiment import Case, format_triage_stages, report, run_experiment
from capstone.providers.chat import Attempt
from tests.helpers import new_state
from tests.test_episode import SEED
from tests.test_model_policy import policy
from tests.test_triage import triage_then_deep

H1 = Hypothesis(id="H1", claim="the bearing is wearing", confidence=0.6)
H2 = Hypothesis(id="H2", claim="a transient spike", confidence=0.3)


# --- each model question carries its stage and mode -------------------------


@pytest.mark.parametrize("mode", ["triage", "deep"])
def test_a_model_question_records_the_stage_and_mode_it_was_asked_in(mode):
    agent = policy(plan=[{"questions": [{"id": "Q1", "text": "When did it start?"}]}])
    state = new_state()
    state.mode, state.stage = mode, "plan"
    agent.plan(state)
    assert (agent.calls[-1].stage, agent.calls[-1].mode) == ("plan", mode)


def test_a_call_from_an_old_record_still_loads_without_stage_or_mode():
    old = ModelCall.model_validate({"job": "decide", "outcome": "answered"})
    assert old.stage is None and old.mode is None


# --- the first hypothesis is timed on the run's clock -----------------------


def started_state(at=100.0):
    state = new_state()
    state.started_at = at
    return state


def test_the_first_hypotheses_record_the_seconds_since_the_run_started():
    state = started_state()
    apply_interpretation(state, Interpretation(hypotheses=(H1,)), now=137.5)
    assert state.first_hypothesis_seconds == 37.5


def test_a_later_revision_does_not_move_the_first_hypothesis_time():
    state = started_state()
    apply_interpretation(state, Interpretation(hypotheses=(H1,)), now=120.0)
    apply_interpretation(state, Interpretation(hypotheses=(H1, H2)), now=150.0)
    assert state.first_hypothesis_seconds == 20.0


def test_no_hypotheses_or_no_clock_reading_records_nothing():
    state = started_state()
    apply_interpretation(state, Interpretation(hypotheses=()), now=120.0)
    apply_interpretation(state, Interpretation(hypotheses=(H1,)))
    assert state.first_hypothesis_seconds is None


# --- the metrics of one finished triage --------------------------------------


def asked(stage, seconds, *, mode="triage", models=("primary",), answered="primary"):
    """One model question, answered by `answered` after trying `models` in turn."""
    return ModelCall(
        job="decide",
        outcome="answered",
        answered_by=answered,
        attempts=tuple(
            Attempt(model=m, outcome="answered", seconds=seconds) for m in models
        ),
        stage=stage,
        mode=mode,
    )


def read(sequence, outcome, hypothesis_id=None):
    return DecisionRecord(
        sequence=sequence,
        phase="investigate",
        information_needed="a reading",
        tool="get_sensor_summary",
        outcome=outcome,
        hypothesis_id=hypothesis_id,
        confidence=0.5,
    )


def finished_triage():
    """A triage with two hypotheses, five reads and a conclusion on H1."""
    # Variables:
    #   state: The finished triage: H1 concluded on, H2 tested by one read,
    #     one read uninterpreted, one failed and one skipped as a repeat.
    state = new_state()
    state.mode = "triage"
    state.first_hypothesis_seconds = 41.0
    state.hypotheses = [H1, H2]
    state.decisions = [
        read(1, "observed"),
        read(2, "observed", "H2"),
        read(3, "uninterpreted"),
        read(4, "tool_error"),
        read(5, "repeated_call"),
    ]
    state.conclusion = AgentConclusion(
        diagnosis="bearing wear",
        confidence=0.6,
        recommendation="escalate",
        hypothesis_id="H1",
        assessment="unresolved",
        unresolved_questions=("Is CNC-07 vibrating too?", "Did the spike pass?"),
    )
    return state


def test_model_questions_and_seconds_are_summed_by_stage():
    calls = [
        asked("plan", 31.0),
        asked("investigate", 9.0),
        asked("investigate", 12.0),
        asked("decide", 14.0),
    ]
    metrics = triage_metrics(finished_triage(), calls)
    assert metrics.calls_by_stage == {"decide": 1, "investigate": 2, "plan": 1}
    assert metrics.model_seconds_by_stage == {
        "decide": 14.0,
        "investigate": 21.0,
        "plan": 31.0,
    }


def test_a_following_deep_runs_questions_are_left_out():
    calls = [asked("plan", 10.0), asked("plan", 50.0, mode="deep")]
    metrics = triage_metrics(finished_triage(), calls)
    assert metrics.calls_by_stage == {"plan": 1}
    assert metrics.model_seconds_by_stage == {"plan": 10.0}


def test_every_attempt_counts_and_a_fallback_answer_is_counted():
    calls = [asked("plan", 20.0, models=("primary", "backup"), answered="backup")]
    metrics = triage_metrics(finished_triage(), calls)
    assert metrics.model_seconds_by_stage == {"plan": 40.0}
    assert metrics.fallback_answers == 1


def test_calls_from_before_stages_were_kept_count_as_unknown():
    old = ModelCall(job="plan", outcome="answered", answered_by="primary")
    metrics = triage_metrics(finished_triage(), [old])
    assert metrics.calls_by_stage == {"unknown": 1}


def test_hypotheses_reads_and_unknowns_come_from_the_finished_state():
    metrics = triage_metrics(finished_triage(), [])
    assert metrics.first_hypothesis_seconds == 41.0
    assert metrics.final_hypotheses == 2
    assert metrics.hypotheses_tested == 1 and metrics.rival_tested is True
    assert (
        metrics.reads_observed,
        metrics.reads_uninterpreted,
        metrics.reads_failed,
        metrics.reads_repeated,
    ) == (2, 1, 1, 1)
    assert metrics.unknowns_reported == 2


def test_no_rival_is_named_when_the_conclusion_chose_no_hypothesis():
    state = finished_triage()
    state.conclusion = state.conclusion.model_copy(update={"hypothesis_id": None})
    assert triage_metrics(state, []).rival_tested is False


# --- the experiment record and report ----------------------------------------


def test_an_experiment_records_the_triage_metrics_and_reports_them(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "on")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="metrics", triage=True)
    metrics = record.triage.metrics
    assert metrics is not None
    # A scripted policy asks no model, so there are no model questions to sum.
    assert metrics.calls_by_stage == {}
    assert metrics.first_hypothesis_seconds is not None
    assert metrics.reads_observed > 0
    line = format_triage_stages([record])
    assert line.startswith("triage stages: model questions none; ")
    assert "first hypothesis in 1/1" in line
    assert line in report([record], {})


def test_records_without_triage_metrics_have_no_stage_line():
    assert format_triage_stages([]) is None
