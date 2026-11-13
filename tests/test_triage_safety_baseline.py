"""Block 0 of the 2026-11-13 triage schedule: frozen safety expectations.

`docs/2026-11-13-schedule.md`, Block 0, asks for the triage safety rules to be
written as tests *before* the five triage feature branches change any code,
and for deep mode to be pinned so those branches can prove they left it alone.

Two kinds of test live here:

- **Triage safety expectations** (TRI-02, TRI-03, TRI-04, TRI-22, TRI-33).
  Each states what a safe triage must do. The ones main does not meet yet are
  marked `xfail(strict=True)`: they fail today, as recorded, and the strict
  mark turns CI red the moment a fix makes one pass, so the fixing branch must
  remove the mark and the test becomes a normal guard. Their `reason` names
  the branch expected to fix them.
- **Deep-mode pins.** The same inputs in deep mode, and one scripted deep
  episode, with today's results written down. The schedule forbids the triage
  branches from changing deep behaviour; if one of these fails, a branch
  changed deep mode and must either undo that or get the developer's explicit
  decision.

Frozen baseline: main `0b0d3c4` (2026-11-13). See
`docs/benchmarks/2026-11-13-triage-block0-freeze.md`.
"""

import pytest

from capstone.agent.investigation import needs_deep_run
from capstone.agent.loop import InvestigationDeps, diagnosis_supported
from capstone.agent.state import Question
from capstone.contracts.hypotheses import Hypothesis
from capstone.episode import run_episode
from tests.helpers import FakeProvider, ScriptedPolicy, new_state
from tests.test_episode import SEED, wear_policy
from tests.test_triage import add_evidence, clear, clearance_state, gap_kinds

CONCLUDE_BRANCH = "feature/triage-conclusion-gates"
# feature/triage-evidence-tests (Block 3) fixed TRI-03, TRI-04 and the KA-09
# rival-question clearance; their marks were removed there.


def deps(**changes):
    """Default investigation settings, as the loop uses them."""
    return InvestigationDeps(
        provider=FakeProvider(), policy=ScriptedPolicy(), **changes
    )


def is_cleared(conclusion):
    """True when the checked answer closes the case with no deep run."""
    return (
        conclusion.assessment == "supported"
        and conclusion.recommendation == "no_action"
        and not needs_deep_run(conclusion)
    )


# --- Conclusion: when may a triage say "supported, nothing needs doing"? -----


@pytest.mark.xfail(
    strict=True,
    reason=f"TRI-02: a timestamp is not proof of health; fix in {CONCLUDE_BRANCH}",
)
def test_a_triage_cannot_clear_on_a_timestamp_alone():
    # E1 is `get_time`: observable, so today's "cites no observable
    # evidence" gap does not fire, and the alarm is cleared on a clock read.
    state = clearance_state()
    checked = clear(state, evidence_ids=("E1",))
    assert not is_cleared(checked)


def test_a_triage_citing_a_full_screening_may_still_clear():
    # The control for the test above: a cited, complete screening is a real
    # observation of the line, so a genuinely healthy case can still close.
    state = clearance_state()
    checked = clear(state, evidence_ids=("E2",))
    assert is_cleared(checked)


@pytest.mark.xfail(
    strict=True,
    reason=f"TRI-22/TRI-33: screening checked against no roster; fix in {CONCLUDE_BRANCH}",
)
def test_a_triage_cannot_clear_when_the_screening_omits_a_machine_on_the_roster():
    # The line has three machines (`list_machines`), the screening lists two.
    # `unscored_machines` only sees machines the screening itself names, so a
    # machine missing from it entirely is never counted as unscored.
    state = clearance_state()
    add_evidence(
        state,
        "E3",
        "simulator:list_machines",
        [{"machine_id": m} for m in ("CNC-01", "CNC-02", "CNC-03")],
    )
    checked = clear(state, evidence_ids=("E2",))
    assert not is_cleared(checked)


@pytest.mark.xfail(
    strict=True,
    reason=f"TRI-21/TRI-33: screening age is not checked; fix in {CONCLUDE_BRANCH}",
)
def test_a_triage_cannot_clear_on_a_screening_read_before_the_alarm():
    # The screening (E2) was read at tick 10; the alarm being cleared fired at
    # tick 200. A screening from before the alarm cannot show the line after it.
    state = clearance_state()
    state.anomaly = state.anomaly.model_copy(update={"tick": 200})
    state.last_tick = 200
    checked = clear(state, evidence_ids=("E2",))
    assert not is_cleared(checked)


def ka09_like_state():
    """A KA-09-style triage: a leading "transient" and an untested rival.

    The rival-separating question names both explanations but has no primary
    `hypothesis_id`, the shape TRI-03 says today's checks miss.
    """
    # Variables:
    #   state: The triage, with a full screening (E2) so only the open rival
    #     question stands between this answer and clearance.
    state = clearance_state()
    state.hypotheses = [
        Hypothesis(id="H1", claim="a transient spike on CNC-02", confidence=0.85),
        Hypothesis(id="H2", claim="a fault elsewhere on the line", confidence=0.4),
    ]
    state.unanswered_questions = [
        Question(
            id="Q1",
            text="Is the vibration only on CNC-02, or on other machines too?",
            hypothesis_id=None,
            distinguishes_hypothesis_ids=("H1", "H2"),
        )
    ]
    return state


def test_a_triage_cannot_clear_while_a_rival_separating_question_is_open():
    state = ka09_like_state()
    checked = clear(state, evidence_ids=("E2",))
    assert not is_cleared(checked)


# --- Test stage: when is the leading explanation "supported"? ---------------


def supported_state(mode, *, second, question=None):
    """A leading explanation with two observed supporters, E2 and `second`.

    `second` is ("get_readings", "vibration") for a second view of the same
    sensor, or ("get_sensor_summary", "temperature") for a different sensor.
    """
    # Variables:
    #   state: A run whose leading explanation H1 is confident (0.95) and backed
    #     by E2 (CNC-02 vibration summary) and E3 (`second`).
    #   question: An optional open question left on the run.
    state = new_state()
    state.mode = mode
    add_evidence(
        state,
        "E2",
        "simulator:get_sensor_summary",
        {"machine_id": "CNC-02", "sensor": "vibration", "mean": 4.6},
    )
    tool, sensor = second
    add_evidence(
        state,
        "E3",
        f"simulator:{tool}",
        {"machine_id": "CNC-02", "sensor": sensor, "values": [4.5, 4.6, 4.7]},
    )
    state.hypotheses = [
        Hypothesis(
            id="H1",
            claim="the bearing on CNC-02 is wearing",
            confidence=0.95,
            supporting_evidence_ids=("E2", "E3"),
        ),
        Hypothesis(id="H2", claim="a transient spike", confidence=0.2),
    ]
    if question is not None:
        state.unanswered_questions = [question]
    return state


RIVAL_QUESTION = Question(
    id="Q1",
    text="Did the vibration settle after the spike?",
    hypothesis_id=None,
    distinguishes_hypothesis_ids=("H1", "H2"),
)
SAME_SENSOR = ("get_readings", "vibration")
OTHER_SENSOR = ("get_sensor_summary", "temperature")


def test_two_different_sensors_support_a_triage_diagnosis():
    # The control: two physical sources, no open question. Must stay True so
    # the fixes below do not block a genuinely supported diagnosis.
    state = supported_state("triage", second=OTHER_SENSOR)
    assert diagnosis_supported(state, deps()) is True


def test_an_open_rival_question_keeps_a_triage_diagnosis_unsupported():
    state = supported_state("triage", second=OTHER_SENSOR, question=RIVAL_QUESTION)
    assert diagnosis_supported(state, deps()) is False


def test_two_views_of_one_sensor_do_not_support_a_triage_diagnosis():
    # E2 summarises CNC-02 vibration and E3 is its raw readings: one physical
    # source, which today counts as the two supporters the bar asks for.
    state = supported_state("triage", second=SAME_SENSOR)
    assert diagnosis_supported(state, deps()) is False


# --- Deep mode is pinned: the triage branches must not change it -----------


def test_deep_mode_still_counts_an_open_rival_question_as_today():
    # Today, in deep mode, a rival question with no primary hypothesis does
    # not block support. Pinned, not endorsed: the schedule keeps deep mode
    # unchanged, so changing this needs the developer's explicit decision.
    state = supported_state("deep", second=OTHER_SENSOR, question=RIVAL_QUESTION)
    assert diagnosis_supported(state, deps()) is True


def test_deep_mode_still_counts_two_views_of_one_sensor_as_today():
    state = supported_state("deep", second=SAME_SENSOR)
    assert diagnosis_supported(state, deps()) is True


def test_deep_mode_conclusion_check_is_unchanged_for_the_ka09_shape():
    state = ka09_like_state()
    state.mode = "deep"
    checked = clear(state, evidence_ids=("E1",))
    assert is_cleared(checked)
    assert gap_kinds(state) == []


# The stages and tool calls of one scripted deep episode (seed 6, bearing wear
# on CNC-02), recorded on main 0b0d3c4. Any change to deep routing, budgets or
# stage order shows up here.
DEEP_STEPS = [
    ("observe", "get_time"),
    ("observe", "get_line_screening"),
    ("plan", None),
    ("investigate", "get_sensor_summary"),
    ("investigate", None),
    ("hypothesize", None),
    ("test", "get_sensor_trend"),
    ("test", None),
    ("decide", None),
    ("propose", "propose_action"),
    ("propose", "get_proposals"),
    ("execute", "execute_action"),
    ("execute", "wait"),
    ("verify", "wait"),
    ("verify", "get_sensor_summary"),
    ("verify", None),
    ("verify", None),
]


def test_a_scripted_deep_episode_takes_the_same_path_as_on_the_frozen_main():
    result = run_episode(
        SEED, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0
    )
    state = result.state
    assert state.mode == "deep"
    assert [(d.phase, d.tool) for d in state.decisions] == DEEP_STEPS
    assert state.termination_reason == "diagnosis_supported"
    assert state.conclusion.recommendation == "intervene"
    assert state.conclusion.evidence_ids == ("E3", "E4")
    assert result.score.resolved is True
    assert result.score.tool_calls == 10
    assert result.score.ticks_elapsed == 345
