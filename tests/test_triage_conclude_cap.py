"""The triage's conclusion cap (TRIAGE_CONCLUDE_CAP, 2026-11-14).

In a triage, the conclusion question gets at most the conclusion window
(TRIAGE_CONCLUDE_SECONDS), even when research ended early. Without it, an early
end handed the question all the time left (~86 s in the 2026-11-14 afternoon
runs), and Super 120B thought for most of it before being cut off. On by
default; off restores the old behaviour. A deep run is never capped.
"""

from capstone.agent.loop import seconds_left
from capstone.agent.state import TRIAGE_CONCLUDE_SECONDS, TRIAGE_SECONDS
from capstone.experiment import Case, run_experiment
from capstone.settings import Settings
from tests.test_episode import SEED, wear_policy
from tests.test_triage import ByMode, run, triage_then_deep
from tests.test_triage_hypothesis_reserve import TimeLimits


def conclude_limits(monkeypatch, cap, *, then_deep=False):
    """The time each conclusion question was given, triage and deep apart."""
    monkeypatch.setenv("TRIAGE_CONCLUDE_CAP", cap)
    triage_policy = TimeLimits(wear_policy("intervene"))
    deep_policy = TimeLimits(wear_policy())
    result = run(
        ByMode(triage_policy, deep_policy),
        monkeypatch,
        then_deep=then_deep,
        triage=True,
    )

    def concluded(policy):
        return [s for name, s in policy.given if name == "conclude"]

    return result, concluded(triage_policy), concluded(deep_policy)


def test_the_cap_is_on_by_default(monkeypatch):
    monkeypatch.delenv("TRIAGE_CONCLUDE_CAP", raising=False)
    assert Settings().triage_conclude_cap is True


def test_a_capped_conclusion_gets_only_the_conclusion_window(monkeypatch):
    # The clock never moves, so research "ends" with all 90 s still left.
    result, (given,), _ = conclude_limits(monkeypatch, "on")
    assert given == TRIAGE_CONCLUDE_SECONDS
    assert result.triage.triage_conclude_cap is True


def test_without_the_cap_the_conclusion_gets_all_the_time_left(monkeypatch):
    result, (given,), _ = conclude_limits(monkeypatch, "off")
    assert given == TRIAGE_SECONDS
    assert result.triage.conclusion_deadline is None


def test_the_deep_run_is_never_capped(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    result, _, deep = conclude_limits(monkeypatch, "on", then_deep=True)
    assert result.state is not result.triage
    assert result.state.triage_conclude_cap is False
    assert result.state.conclusion_deadline is None
    assert deep and deep[0] > TRIAGE_CONCLUDE_SECONDS


def test_the_capped_window_runs_down_from_when_the_question_was_asked(monkeypatch):
    # seconds_left reaches 0 at the conclusion deadline, so a model still
    # thinking then is out of time, not an outage.
    result, _, _ = conclude_limits(monkeypatch, "on")
    state = result.triage
    deadline = state.conclusion_deadline
    assert deadline is not None

    class Deps:
        clock = staticmethod(lambda: deadline - 5.0)

    assert seconds_left(state, Deps, research=False) == 5.0
    Deps.clock = staticmethod(lambda: deadline + 1.0)
    assert seconds_left(state, Deps, research=False) == 0.0


def test_the_triage_record_keeps_the_cap(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    monkeypatch.setenv("TRIAGE_CONCLUDE_CAP", "on")
    case = Case("bearing-6", SEED, "bearing_degradation")
    (record,) = run_experiment([case], triage_then_deep, name="cap", triage=True)
    assert record.triage.conclude_cap is True
