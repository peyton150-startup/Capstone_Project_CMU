"""The fixed triage plan (Block 1, TRIAGE_PLAN=fixed, 2026-11-13).

With TRIAGE_PLAN=fixed a triage takes its first questions from a table keyed
on what monitoring saw, with no model call; an alarm's first question also
carries a measured predicate, so it closes only on a "true" (sustained) or
"false" (a spike) verdict. Anything the table does not know gets a generic
list. The deep run always asks its own model plan.
"""

import pytest

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.triage_plan import (
    SUSTAIN_SAMPLES,
    SUSTAIN_TICKS,
    fixed_plan,
    fixed_predicates,
)
from capstone.experiment import Case, run_experiment
from tests.test_episode import SEED, wear_policy
from tests.test_triage import ByMode, run, triage_then_deep


def anomaly(kind="alarm", description=None, machine="CNC-02", tick=914):
    return DetectedAnomaly(
        tick=tick,
        machine_id=machine,
        kind=kind,
        description=description
        or f"alarm on {machine}: vibration 4.58 mm/s above 4.50",
    )


# --- the table ------------------------------------------------------------------


def test_a_vibration_alarm_gets_five_questions_on_its_own_machine_and_sensor():
    questions = fixed_plan(anomaly())
    assert [q.id for q in questions] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
    assert "CNC-02's vibration still above 4.50" in questions[0].text
    assert "spike" in questions[0].text  # sustained or transient
    assert "other machine" in questions[1].text  # this machine or the line
    assert "temperature and motor load" in questions[4].text
    assert [q.signal_reliability for q in questions] == [
        "direct",
        "direct",
        "indirect",
        "indirect",
        "indirect",
    ]
    assert all(q.hypothesis_id is None for q in questions)


@pytest.mark.parametrize(
    ("sensor", "side", "follow_up"),
    [
        ("following_error", "above", "following error rose"),
        ("hydraulic_pressure", "below", "hydraulic pressure fell"),
        ("temperature", "above", "other sensors move with its temperature"),
    ],
)
def test_each_alarm_sensor_gets_its_own_follow_up(sensor, side, follow_up):
    said = f"alarm on CNC-05: {sensor} 12.00 um {side} 10.00"
    questions = fixed_plan(anomaly(description=said, machine="CNC-05"))
    assert f"{sensor.replace('_', ' ')} still {side} 10.00" in questions[0].text
    assert follow_up in questions[-1].text


def test_failed_inspections_and_a_stopped_machine_get_their_own_lists():
    rejects = fixed_plan(
        anomaly(
            kind="inspection_failures",
            description="3 of the last 5 jobs failed inspection (jobs 11, 12, 13)",
            machine=None,
        )
    )
    assert "share one machine" in rejects[0].text
    assert "material batch" in rejects[1].text
    stopped = fixed_plan(anomaly(kind="status", description="CNC-02 machine stopped"))
    assert "CNC-02" in stopped[0].text
    assert "before it stopped" in stopped[0].text


def test_anything_else_gets_the_generic_list():
    for odd in (
        anomaly(kind="routine_check", description="routine check", machine=None),
        anomaly(description="alarm text in a format the table does not know"),
    ):
        questions = fixed_plan(odd)
        assert [q.id for q in questions] == ["Q1", "Q2", "Q3"]
        assert "line screening" in questions[0].text


def test_the_fixed_questions_name_no_cause_and_never_change():
    words = ("bearing", "leak", "wear", "worn", "wrong setting", "false alarm", "fault")
    for kind, said in (
        ("alarm", None),
        ("status", "CNC-02 machine stopped"),
        ("inspection_failures", "3 of the last 5 jobs failed inspection"),
        ("routine_check", "routine check"),
    ):
        made = fixed_plan(anomaly(kind=kind, description=said))
        assert made == fixed_plan(anomaly(kind=kind, description=said))
        for question in made:
            assert not any(word in question.text.lower() for word in words)


# --- the measured predicate -------------------------------------------------------


def test_an_alarm_first_question_carries_a_sustained_reading_predicate():
    ((qid, predicate),) = fixed_predicates(anomaly()).items()
    assert qid == "Q1"
    assert predicate.machine_id == "CNC-02"
    assert predicate.sensor == "vibration"
    assert predicate.from_tick == 914 - SUSTAIN_TICKS
    assert predicate.to_tick == 914 + SUSTAIN_TICKS
    assert predicate.statistic == "mean"
    assert predicate.comparison == "above"
    assert predicate.threshold == 4.50
    assert predicate.min_samples == SUSTAIN_SAMPLES


def test_a_low_side_alarm_compares_below_and_an_early_alarm_starts_at_zero():
    said = "alarm on CNC-05: hydraulic_pressure 61.20 bar below 65.00"
    predicates = fixed_predicates(anomaly(description=said, machine="CNC-05", tick=5))
    predicate = predicates["Q1"]
    assert predicate.comparison == "below" and predicate.threshold == 65.0
    assert predicate.from_tick == 0


@pytest.mark.parametrize(
    "odd",
    [
        anomaly(kind="status", description="CNC-02 machine stopped"),
        anomaly(description="alarm text in a format the table does not know"),
        anomaly(description="alarm on CNC-02: vibration 4.58 mm/s above high"),
        anomaly(machine=None, description="alarm on CNC-02: vibration 4 mm/s above 4"),
    ],
)
def test_only_a_readable_alarm_on_a_named_machine_gets_a_predicate(odd):
    assert fixed_predicates(odd) == {}


# --- in a triage ---------------------------------------------------------------------


class CountsPlans:
    """A scripted policy that counts its plan questions and keeps the open
    questions the first research question saw."""

    def __init__(self, inner):
        self.inner = inner
        self.planned = 0
        self.first_seen = None

    def __getattr__(self, name):
        method = getattr(self.inner, name)
        if not callable(method):
            return method

        def call(state, *args, **kwargs):
            if self.first_seen is None and state.stage == "investigate":
                self.first_seen = [(q.id, q.text) for q in state.unanswered_questions]
            return method(state, *args, **kwargs)

        return call

    def plan(self, state, *args, **kwargs):
        self.planned += 1
        return self.inner.plan(state, *args, **kwargs)


def test_a_fixed_plan_triage_asks_no_plan_question(monkeypatch):
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    triage, deep = CountsPlans(wear_policy("intervene")), CountsPlans(wear_policy())
    result = run(ByMode(triage, deep), monkeypatch, triage=True)
    assert triage.planned == 0  # the table answered for the triage
    assert result.triage.fixed_plan_used is True
    assert [qid for qid, _ in triage.first_seen] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
    assert "vibration still above" in triage.first_seen[0][1]
    assert set(result.triage.question_predicates) == {"Q1"}
    assert deep.planned == 1  # the deep run still asks its own plan
    assert result.state.fixed_plan_used is False
    assert result.state.triage_fixed_plan is False


def test_by_default_the_triage_still_asks_the_model_to_plan(monkeypatch):
    monkeypatch.delenv("TRIAGE_PLAN", raising=False)
    triage = CountsPlans(wear_policy("intervene"))
    result = run(
        ByMode(triage, wear_policy()), monkeypatch, then_deep=False, triage=True
    )
    assert triage.planned == 1
    assert result.triage.fixed_plan_used is False
    assert result.triage.question_predicates == {}


def test_a_deep_only_run_ignores_the_fixed_plan_setting(monkeypatch):
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    monkeypatch.delenv("TRIAGE", raising=False)
    policy = CountsPlans(wear_policy())
    result = run(policy, monkeypatch)
    assert result.triage is None
    assert policy.planned == 1 and result.state.fixed_plan_used is False


def test_the_same_seed_gives_the_same_fixed_plan_triage(monkeypatch):
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")

    def once():
        policy = ByMode(wear_policy("intervene"), wear_policy())
        first = run(policy, monkeypatch, then_deep=False, triage=True).triage
        return first.question_predicates, first.evidence, first.conclusion

    assert once() == once()


def test_the_triage_record_says_the_plan_was_fixed(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="fixed", triage=True)
    assert record.triage.fixed_plan is True


def test_an_unknown_plan_setting_is_refused(monkeypatch):
    from capstone.settings import Settings

    monkeypatch.setenv("TRIAGE_PLAN", "llm")
    with pytest.raises(ValueError):
        Settings()
