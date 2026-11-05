"""Tree-of-thought search improvements: reachability, retention, ranking, rotation,
reinstatement, adaptive branching and the second rating pass. Offline only:
fake clocks, scripted policies and fake models; no network and no keys."""

import pytest

from capstone.agent.artifacts import TerminationReason
from capstone.agent.loop import InvestigationDeps, held_for_hypotheses
from capstone.experiment import Case, run_experiment
from capstone.tree_reach import group_of, reach_of, summarize
from tests.helpers import ask, new_state
from tests.test_agent_investigation import fresh_state, investigate, stages, wear_policy


@pytest.fixture(autouse=True)
def two_questions_per_step(monkeypatch):
    """Scripted replies give separate interpret and decide answers."""
    monkeypatch.setenv("STEP_QUESTIONS", "2")


# --- reachability: the hypothesis reserve -------------------------------------


def slow_factory(now, seconds=40.0):
    """A factory where every call takes `seconds` on the fake clock."""

    def respond(request):
        now[0] += seconds
        return {"ok": True}

    return respond


def long_research():
    """Research that would go on until the time is up: six distinct look-ups."""
    return wear_policy(
        decisions={
            "investigate": [
                ask("get_sensor_summary", question_id="Q1", machine_id="CNC-02"),
                *[ask("get_events", from_tick=t, to_tick=t + 1) for t in range(5)],
            ],
            "test": [ask("get_readings", hypothesis_id="H1", machine_id="CNC-02")],
        }
    )


def run_long(reserve):
    now = [0.0]
    return investigate(
        long_research(),
        respond=slow_factory(now),
        clock=lambda: now[0],
        state=fresh_state(timeout_seconds=300.0, followup_seconds=60.0),
        hypothesis_seconds=reserve,
    )[0]


def test_without_a_reserve_long_research_skips_the_hypotheses():
    """The behaviour the audit found: research used every second, so the run
    went straight to the conclusion and never formed explanations."""
    state = run_long(0.0)
    assert "hypothesize" not in stages(state)
    assert state.hypothesis_reserve_used is None


def test_the_reserve_lets_the_hypothesize_question_be_asked():
    state = run_long(100.0)
    assert stages(state)[:5] == [
        "observe",
        "plan",
        "investigate",
        "hypothesize",
        "test",
    ]
    assert state.hypothesis_reserve_used is True
    # Research stopped early (three look-ups, not five), so the reserve was there.
    looked = [d for d in state.decisions if d.phase == "investigate" and d.tool]
    assert len(looked) == 3
    assert state.hypotheses  # the test stage ran on the explanation it formed


def test_a_reserve_that_was_not_needed_is_recorded_as_unused():
    state, _ = investigate(wear_policy(), hypothesis_seconds=50.0)
    assert state.hypothesis_reserve_used is False
    assert "hypothesize" in stages(state)


def test_the_reserve_is_held_only_before_the_hypothesize_question():
    deps = InvestigationDeps(
        provider=None, policy=wear_policy(), hypothesis_seconds=30.0
    )
    state = new_state()
    for stage, held in [
        ("plan", 30.0),
        ("investigate", 30.0),
        ("hypothesize", 0.0),
        ("test", 0.0),
        ("verify", 0.0),
    ]:
        state.stage = stage
        assert held_for_hypotheses(state, deps) == held


def test_a_negative_reserve_is_refused():
    with pytest.raises(ValueError):
        InvestigationDeps(provider=None, policy=wear_policy(), hypothesis_seconds=-1)


def test_a_reserve_that_leaves_no_research_time_is_refused(monkeypatch):
    from capstone.episode import run_episode
    from tests.test_known_answers import stand_in

    monkeypatch.setenv("HYPOTHESIS_RESERVE_SECONDS", "800")
    with pytest.raises(ValueError, match="HYPOTHESIS_RESERVE_SECONDS"):
        run_episode(6, stand_in(), fault="bearing_degradation", clock=lambda: 0.0)


# --- reachability: the measurement over saved records ---------------------------


def test_the_report_puts_a_tree_run_in_the_tree_group():
    from tests.test_model_policy import scripted_models
    from tests.test_tree_of_thought import as_tree

    case = [Case("bearing-6", 6, "bearing_degradation")]
    [record] = run_experiment(case, lambda: as_tree(scripted_models()), name="tot")
    assert group_of(record) == "tree"
    reach = reach_of(record)
    assert reach.scenario_id == "bearing-6"
    # Time before the tree is counted only for jobs asked before hypothesize.
    assert "conclude" not in reach.seconds_by_job
    summary = summarize([reach])
    assert summary["runs"] == 1 and summary["groups"]["tree"]["runs"] == 1


def test_the_report_groups_a_run_that_ended_before_the_question_by_its_reason():
    from tests.test_model_policy import scripted_models

    case = [Case("bearing-6", 6, "bearing_degradation")]
    [record] = run_experiment(case, scripted_models, name="plain")
    record = record.model_copy(
        update={
            "thoughts": [],
            "model_calls": record.model_calls.model_copy(
                update={
                    "details": tuple(
                        c for c in record.model_calls.details if c.job != "hypothesize"
                    )
                }
            ),
            "score": record.score.model_copy(update={"termination_reason": "timeout"}),
        }
    )
    assert group_of(record) == "before_timeout"


def test_the_report_reads_the_archived_pairs_as_the_audit_counted_them():
    """The 2026-11-05 audit, repeated from the saved records alone."""
    from pathlib import Path

    from capstone.tree_reach import read_all

    archive = Path(__file__).parents[1] / "docs/benchmarks/2026-11-01-tot13-pairs"
    paths = sorted(archive.glob("*/master-tot13-*.records.jsonl"))
    if not paths:
        pytest.skip("archive not present")
    groups = summarize([reach_of(r) for r in read_all(paths)])["groups"]
    assert {name: g["runs"] for name, g in groups.items()} == {
        "tree": 33,
        "no_answer": 3,
        "before_model_unavailable": 9,
        "before_timeout": 7,
    }


def test_the_stop_reason_for_a_timeout_is_still_timeout():
    """The reserve changes where the run goes after research, not why research
    stopped: the record still says the research ran out of time."""
    state = run_long(100.0)
    stopped = [
        d
        for d in state.decisions
        if d.phase == "investigate" and d.outcome == "stopped"
    ]
    assert stopped[-1].termination_reason is TerminationReason.TIMEOUT
