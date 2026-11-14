"""Block 5 of the 2026-11-13 triage schedule: what the conclusion is shown and timed.

What these tests prove, with no model:

- the TRIAGE CONCLUSION BRIEF names the live explanations that were tested
  and those that were not, each question predicate's verdict with its value
  and sample count, and the packet's missing channels, and says that
  untested, unsettled and missing evidence is unknown, never normal;
- it is bounded: past MAX_BRIEF_ITEMS an entry is counted, not named;
- only a triage's conclusion question shows it, only with
  TRIAGE_CONCLUDE_BRIEF on (the default), and a deep run's conclusion prompt
  is the same with the setting on or off;
- `conclude` records the conclusion model's seconds apart from the Python
  validation seconds on the injected clock, and both reach the triage
  metrics and the experiment's TriageRecord.
"""

import pytest

import capstone.agent.investigation as investigation
from capstone.agent.artifacts import AgentConclusion
from capstone.agent.conclude_brief import (
    MAX_BRIEF_ITEMS,
    brief_lines,
    explanations_tested,
    missing_channels,
    predicate_lines,
)
from capstone.agent.evidence_packet import EvidencePacket, PacketItem
from capstone.agent.loop import InvestigationDeps
from capstone.agent.model_policy import render
from capstone.agent.state import DecisionRecord, Predicate
from capstone.contracts.hypotheses import Hypothesis
from capstone.evaluation.triage_metrics import triage_metrics
from capstone.experiment import TriageRecord, triage_record
from capstone.settings import Settings
from tests.helpers import FakeProvider, ScriptedPolicy, new_state
from tests.test_model_policy import policy
from tests.test_triage import add_evidence, triage_then_deep
from tests.test_triage_evidence_tests import summary

CONCLUDED = {
    "diagnosis": "CNC-02 bearing wear",
    "confidence": 0.6,
    "recommendation": "escalate",
    "assessment": "unresolved",
    "unresolved_questions": ["is H2 ruled out?"],
}


def predicate(threshold=4.0, machine="CNC-02", sensor="vibration"):
    return Predicate(
        machine_id=machine,
        sensor=sensor,
        from_tick=100,
        to_tick=130,
        statistic="mean",
        comparison="above",
        threshold=threshold,
    )


def read_for(state, hypothesis_id, outcome="observed"):
    state.decisions.append(
        DecisionRecord(
            sequence=len(state.decisions) + 1,
            phase="test",
            information_needed="a read",
            tool="get_sensor_summary",
            arguments={"machine_id": "CNC-02", "sensor": "vibration"},
            outcome=outcome,
            hypothesis_id=hypothesis_id,
            confidence=0.5,
        )
    )


def missing(root, reason, source="live_sensor"):
    machine, _, sensor = root.partition(":")
    return PacketItem(
        machine_id=machine,
        sensor=sensor or None,
        physical_root=root if sensor else None,
        source_type=source,
        status="missing",
        missing_reason=reason,
    )


def briefed(*, packet=True):
    """A triage with H1 tested by a read, H2 untested, two predicates and a packet."""
    # Variables:
    #   packet: Whether Observe left a packet; without one, missing channels
    #     are said to be unrecorded.
    state = new_state()
    state.mode = "triage"
    state.triage_conclude_brief = True
    state.hypotheses = [
        Hypothesis(id="H1", claim="bearing wear on CNC-02", confidence=0.6),
        Hypothesis(id="H2", claim="a loose sensor mount", confidence=0.3),
    ]
    read_for(state, "H1")
    read_for(state, "H2", outcome="tool_error")  # a failed read tests nothing
    add_evidence(state, "E1", "simulator:get_sensor_summary", summary(4.6))
    state.question_predicates = {
        "Q1": predicate(),
        "Q2": predicate(machine="CNC-03", sensor="temperature"),
    }
    if packet:
        state.triage_packet = EvidencePacket(
            machine_id="CNC-02",
            trigger_tick=10,
            items=(
                missing("CNC-03:temperature", "tool_error"),
                missing("CNC-03:temperature", "tool_error"),
                missing(
                    "CNC-04:vibration", "absent_from_screening", "derived_screening"
                ),
                missing("CNC-02", "not a sensor", "status"),
            ),
        )
    return state


# --- the brief ----------------------------------------------------------------


def test_tested_and_untested_explanations_are_named_apart():
    state = briefed()
    state.hypotheses[1] = state.hypotheses[1].model_copy(
        update={"contradicting_evidence_ids": ()}
    )
    tested, untested = explanations_tested(state)
    assert tested == [
        "H1 (1 read(s) aimed at it, 0 supporting and 0 contradicting evidence item(s))"
    ]
    assert untested == ["H2"]


def test_linked_evidence_alone_counts_as_tested():
    state = briefed()
    state.hypotheses[1] = state.hypotheses[1].model_copy(
        update={"contradicting_evidence_ids": ("E1",)}
    )
    tested, untested = explanations_tested(state)
    assert [t.split()[0] for t in tested] == ["H1", "H2"] and untested == []


def test_each_predicate_shows_its_verdict_value_and_samples():
    entries = predicate_lines(briefed())
    assert entries[0] == (
        "Q1: mean of vibration on CNC-02, ticks 100-130, above 4: "
        "true (value 4.6 from 20 sample(s); E1)"
    )
    # Nothing measured CNC-03's temperature: unavailable, with the reason.
    assert entries[1].endswith(
        "unavailable (no observed reading of CNC-03:temperature)"
    )


def test_missing_channels_are_physical_named_once_with_their_reason():
    assert missing_channels(briefed()) == [
        "CNC-03:temperature (tool_error)",
        "CNC-04:vibration (absent_from_screening)",
    ]
    assert missing_channels(briefed(packet=False)) == []


def test_the_brief_never_turns_missing_or_untested_into_normal():
    text = "\n".join(brief_lines(briefed()))
    assert text.startswith("TRIAGE CONCLUSION BRIEF (")
    assert "not a diagnosis" in text
    assert (
        "Explanations not tested: H2. An untested explanation is not ruled out." in text
    )
    assert "insufficient, stale or unavailable is unknown, not normal" in text
    assert "it is not known to be normal" in text
    # Identifiers and verdicts only: no claim text, no record text.
    assert "bearing wear" not in text and "loose" not in text

    bare = "\n".join(brief_lines(briefed(packet=False)))
    assert "Missing channels: not recorded (no evidence packet)" in bare
    assert "unknown, not normal" in bare


def test_a_brief_with_nothing_to_report_says_so():
    state = new_state()
    state.mode = "triage"
    text = "\n".join(brief_lines(state))
    assert "Explanations tested: none." in text
    assert "Explanations not tested: none." in text
    assert "Measured checks: none attached to a question." in text


def test_the_brief_is_bounded():
    state = briefed()
    state.decisions = []  # nothing tested, so all 20 are listed as untested
    state.hypotheses = [
        Hypothesis(id=f"H{i}", claim="x", confidence=0.1) for i in range(20)
    ]
    state.question_predicates = {f"Q{i:02}": predicate() for i in range(20)}
    lines = brief_lines(state)
    untested = next(line for line in lines if line.startswith("Explanations not"))
    assert f"H{MAX_BRIEF_ITEMS - 1}; and 12 more" in untested
    assert f"H{MAX_BRIEF_ITEMS}" not in untested.split("; and")[0]
    checks = next(line for line in lines if line.startswith("Measured checks"))
    assert checks.count(": mean of vibration") == MAX_BRIEF_ITEMS
    assert "and 12 more" in checks


# --- the conclusion prompt ----------------------------------------------------


def conclusion_prompt(state):
    agent = policy(conclude=[{"conclusion": CONCLUDED}])
    agent.conclude(state)
    return agent.clients["conclude"].asked[0][1]


def test_only_the_triage_conclusion_question_shows_the_brief():
    state = briefed()
    prompt = conclusion_prompt(state)
    assert "TRIAGE CONCLUSION BRIEF" in prompt
    # Every other question's shared view stays as it was.
    assert "TRIAGE CONCLUSION BRIEF" not in render(state)


def test_turning_the_brief_off_restores_the_old_prompt():
    on = briefed()
    off = briefed()
    off.triage_conclude_brief = False
    shown = conclusion_prompt(on)
    old = conclusion_prompt(off)
    assert "TRIAGE CONCLUSION BRIEF" not in old
    assert old == render(off)
    assert shown.startswith(render(on)) and shown != old


def test_a_deep_conclusion_prompt_is_unchanged_by_the_setting():
    deep = briefed()
    deep.mode = "deep"
    flagged = conclusion_prompt(deep)
    deep.triage_conclude_brief = False
    assert flagged == conclusion_prompt(deep)
    assert "TRIAGE CONCLUSION BRIEF" not in flagged


def test_the_setting_is_on_by_default_and_off_turns_it_off(monkeypatch):
    monkeypatch.delenv("TRIAGE_CONCLUDE_BRIEF", raising=False)
    assert Settings(_env_file=None).triage_conclude_brief is True
    monkeypatch.setenv("TRIAGE_CONCLUDE_BRIEF", "off")
    assert Settings(_env_file=None).triage_conclude_brief is False


def test_a_triage_episode_sets_the_brief_but_its_deep_run_does_not(monkeypatch):
    from capstone.episode import run_episode
    from tests.test_episode import SEED

    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE", "on")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "on")
    monkeypatch.delenv("TRIAGE_CONCLUDE_BRIEF", raising=False)
    result = run_episode(
        SEED,
        triage_then_deep("intervene"),
        fault="bearing_degradation",
        clock=lambda: 0.0,
    )
    assert result.triage.triage_conclude_brief is True
    assert result.state.mode == "deep" and not result.state.triage_conclude_brief
    record = triage_record(result)
    assert record.conclude_brief is True


# --- timing -------------------------------------------------------------------


class Clock:
    """An injected clock that only moves when a step says so."""

    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def timed_conclude(monkeypatch, *, mode="triage", fails=False):
    """Run `conclude` with the model taking 7 s and each Python check 1 s."""
    # Variables:
    #   clock: Moved 7 s by the model, 1 s by check_conclusion, 1 s by
    #     needs_deep_run and 1 s by the triage report.
    clock = Clock()

    def model(state):
        clock.now += 7.0
        if fails:
            raise ValueError("the model gave no usable conclusion")
        return AgentConclusion(**CONCLUDED), None

    def slow(original):
        def wrapped(*args, **kwargs):
            clock.now += 1.0
            return original(*args, **kwargs)

        return wrapped

    for name in ("check_conclusion", "needs_deep_run", "build_triage_report"):
        monkeypatch.setattr(investigation, name, slow(getattr(investigation, name)))
    state = new_state()
    state.mode = mode
    state.started_at = clock.now
    deps = InvestigationDeps(
        FakeProvider(), ScriptedPolicy(conclude=model), clock=clock
    )
    investigation.conclude(state, deps)
    return state


def test_conclude_times_the_model_apart_from_the_python_checks(monkeypatch):
    state = timed_conclude(monkeypatch)
    assert state.conclude_model_seconds == pytest.approx(7.0)
    assert state.conclude_check_seconds == pytest.approx(3.0)
    metrics = triage_metrics(state, ())
    assert metrics.conclude_model_seconds == pytest.approx(7.0)
    assert metrics.conclude_check_seconds == pytest.approx(3.0)


def test_a_deep_conclusion_has_no_triage_report_time(monkeypatch):
    state = timed_conclude(monkeypatch, mode="deep")
    assert state.conclude_model_seconds == pytest.approx(7.0)
    assert state.conclude_check_seconds == pytest.approx(1.0)  # check_conclusion


def test_a_failed_model_answer_still_records_its_time(monkeypatch):
    state = timed_conclude(monkeypatch, fails=True)
    assert state.conclusion_rejected
    assert state.conclude_model_seconds == pytest.approx(7.0)
    # No answer to check; the triage's verdict rule and report still ran.
    assert state.conclude_check_seconds == pytest.approx(2.0)


def test_the_triage_record_keeps_both_times(monkeypatch):
    from capstone.episode import run_episode
    from tests.test_episode import SEED

    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("TRIAGE", "on")
    monkeypatch.setenv("TRIAGE_THEN_DEEP", "off")
    result = run_episode(
        SEED,
        triage_then_deep("escalate"),
        fault="bearing_degradation",
        clock=lambda: 0.0,
    )
    record = triage_record(result)
    assert record.conclude_model_seconds == 0.0
    assert record.conclude_check_seconds == 0.0
    assert record.metrics.conclude_model_seconds == 0.0
    # Records from before these were kept still load.
    old = record.model_dump()
    for key in ("conclude_model_seconds", "conclude_check_seconds", "conclude_brief"):
        del old[key]
    restored = TriageRecord.model_validate(old)
    assert restored.conclude_model_seconds is None and restored.conclude_brief is None
