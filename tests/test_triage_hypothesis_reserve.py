"""The triage's own hypothesis reserve (TRIAGE_HYPOTHESIS_SECONDS, 2026-11-14).

In a triage, research before the hypothesize question stops this many seconds
before the conclusion's time begins, so a triage that researches until its
time is up still asks for explanations. On (25 s) by default until the
developer's tests decide; 0 turns it off. The deep run keeps its own reserve
(HYPOTHESIS_RESERVE_SECONDS).
"""

import pytest

from capstone.agent.state import (
    TRIAGE_CONCLUDE_SECONDS,
    TRIAGE_SECONDS,
    triage_budgets,
    triage_hypothesis_reserve,
)
from capstone.experiment import Case, run_experiment
from capstone.settings import Settings
from tests.test_episode import SEED, wear_policy
from tests.test_triage import ByMode, run, triage_then_deep

RESEARCH = TRIAGE_SECONDS - TRIAGE_CONCLUDE_SECONDS  # 70 s in a 90 s triage


class TimeLimits:
    """A scripted policy that notes the time each question was given."""

    def __init__(self, inner):
        self.inner = inner
        self.given = []

    def __getattr__(self, name):
        method = getattr(self.inner, name)
        if not callable(method):
            return method

        def call(state, *args, **kwargs):
            self.given.append((name, state.seconds_for_question))
            return method(state, *args, **kwargs)

        return call


def ticking(step):
    """A clock that moves `step` seconds every time it is read."""
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock


# --- the setting and its cap -------------------------------------------------------


def test_the_reserve_is_on_by_default(monkeypatch):
    monkeypatch.delenv("TRIAGE_HYPOTHESIS_SECONDS", raising=False)
    assert Settings().triage_hypothesis_seconds == 25.0


def test_the_reserve_fits_the_triage_window():
    assert triage_hypothesis_reserve(25.0, triage_budgets()) == 25.0
    # An 8 s triage keeps 2 s for the conclusion: research has 6, so the
    # reserve is at most half of it.
    assert triage_hypothesis_reserve(25.0, triage_budgets(seconds=8)) == 3.0
    assert triage_hypothesis_reserve(0.0, triage_budgets()) == 0.0


def test_a_negative_reserve_is_refused(monkeypatch):
    monkeypatch.setenv("TRIAGE_HYPOTHESIS_SECONDS", "-1")
    with pytest.raises(ValueError):
        Settings()


# --- what the questions are given -------------------------------------------------


def limits(monkeypatch, reserve):
    """The time limit of each triage question, with a clock that never moves."""
    monkeypatch.setenv("TRIAGE_HYPOTHESIS_SECONDS", reserve)
    policy = TimeLimits(wear_policy("intervene"))
    result = run(
        ByMode(policy, wear_policy()), monkeypatch, then_deep=False, triage=True
    )
    return result.triage, policy.given


def split_at_hypothesize(given):
    """The decide time limits before the hypothesize question, and after it."""
    names = [name for name, _ in given]
    cut = names.index("hypothesize")
    before = [s for name, s in given[:cut] if name == "decide"]
    after = [s for name, s in given[cut:] if name == "decide"]
    return before, after


def test_research_questions_stop_short_of_the_reserve(monkeypatch):
    first, given = limits(monkeypatch, "25")
    assert first.triage_hypothesis_seconds == 25.0
    before, _ = split_at_hypothesize(given)
    assert before and all(s == RESEARCH - 25.0 for s in before)


def test_the_hypothesize_question_and_the_tests_after_it_get_it_back(monkeypatch):
    _, given = limits(monkeypatch, "25")
    (hypothesize,) = [s for name, s in given if name == "hypothesize"]
    assert hypothesize == RESEARCH
    _, after = split_at_hypothesize(given)
    assert after and all(s == RESEARCH for s in after)


def test_with_the_reserve_off_research_keeps_all_its_time(monkeypatch):
    first, given = limits(monkeypatch, "0")
    assert first.triage_hypothesis_seconds == 0.0
    assert all(s == RESEARCH for name, s in given if name == "decide")
    assert first.hypothesis_reserve_used is None


def test_the_conclusion_keeps_its_own_time(monkeypatch):
    _, given = limits(monkeypatch, "25")
    (conclude,) = [s for name, s in given if name == "conclude"]
    assert conclude == TRIAGE_SECONDS


# --- when time runs out -------------------------------------------------------------


def test_research_stopped_by_the_reserve_still_asks_for_explanations(monkeypatch):
    monkeypatch.setenv("TRIAGE_HYPOTHESIS_SECONDS", "25")
    result = run(
        triage_then_deep(),
        monkeypatch,
        then_deep=False,
        triage=True,
        clock=ticking(6.0),
    )
    first = result.triage
    assert first.hypothesis_reserve_used is True
    assert any(d.phase == "hypothesize" for d in first.decisions)
    assert first.hypotheses


def test_without_the_reserve_the_same_run_records_no_reserve(monkeypatch):
    monkeypatch.setenv("TRIAGE_HYPOTHESIS_SECONDS", "0")
    result = run(
        triage_then_deep(),
        monkeypatch,
        then_deep=False,
        triage=True,
        clock=ticking(6.0),
    )
    assert result.triage.hypothesis_reserve_used is None


# --- the deep run and the record -----------------------------------------------------


def test_the_deep_run_does_not_take_the_triage_reserve(monkeypatch):
    monkeypatch.setenv("TRIAGE_HYPOTHESIS_SECONDS", "25")
    monkeypatch.delenv("HYPOTHESIS_RESERVE_SECONDS", raising=False)
    result = run(triage_then_deep(), monkeypatch, then_deep=True, triage=True)
    assert result.state is not result.triage
    assert result.state.triage_hypothesis_seconds == 0.0
    assert result.state.hypothesis_reserve_used is None


def test_the_triage_record_keeps_the_reserve(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    monkeypatch.setenv("TRIAGE_HYPOTHESIS_SECONDS", "25")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="reserve", triage=True)
    assert record.triage.hypothesis_reserve_seconds == 25.0
    assert record.triage.hypothesis_reserve_used is False  # time never ran out
