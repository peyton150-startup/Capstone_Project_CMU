"""The fixed plan's line-screening questions, closed from the packet's screening.

With TRIAGE_PLAN=fixed and TRIAGE_PACKET on, Observe has already read
`get_line_screening` before the plan is made. The fixed plan still asked
"Does the line screening show any other machine with unusual readings?", and
nothing closed that question from the read already held, so in the
2026-11-14 afternoon live runs research asked for the screening again 59
times and the refused repeats ended research before hypothesize in 22 of 26
triages. The plan stage now closes those questions with the screening
evidence, but only when the screening scored every machine on the roster: a
missing or unscored machine keeps the question open (unknown, never normal).
The deep run is unchanged.
"""

import pytest

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.evidence_packet import EvidencePacket, PacketCall, PacketItem
from capstone.agent.triage_plan import (
    fixed_plan,
    is_screening_question,
    screening_answer,
)
from tests.helpers import ask
from tests.test_episode import wear_policy
from tests.test_triage import ByMode, run


def anomaly(kind="alarm", description=None, machine="CNC-02"):
    return DetectedAnomaly(
        tick=914,
        machine_id=machine,
        kind=kind,
        description=description
        or f"alarm on {machine}: vibration 4.58 mm/s above 4.50",
    )


# --- which questions are about the screening --------------------------------------


@pytest.mark.parametrize(
    ("kind", "description", "ids"),
    [
        ("alarm", None, ["Q2"]),
        ("status", "CNC-02 machine stopped", ["Q3"]),
        ("inspection_failures", "3 of the last 5 jobs failed inspection", ["Q4"]),
        ("routine_check", "routine check", ["Q1"]),
    ],
)
def test_each_fixed_list_has_one_screening_question(kind, description, ids):
    questions = fixed_plan(anomaly(kind=kind, description=description))
    assert [q.id for q in questions if is_screening_question(q)] == ids


# --- when the screening answers them -------------------------------------------------


def scored(machine, sensors=("vibration", "temperature")):
    return [
        PacketItem(
            machine_id=machine,
            sensor=sensor,
            physical_root=f"{machine}:{sensor}",
            source_type="derived_screening",
            status="qualified",
            evidence_id="E2",
            scores=(0.4, 0.5),
        )
        for sensor in sensors
    ]


def packet(*, roster=("CNC-01", "CNC-02"), items=None, absent=(), screened=True):
    calls = [PacketCall(tool="get_time", role="mandatory", outcome="observed")]
    calls.append(
        PacketCall(
            tool="get_line_screening",
            role="mandatory",
            outcome="observed",
            qualified=True,
            evidence_id="E2",
        )
        if screened
        else PacketCall(
            tool="get_line_screening",
            role="mandatory",
            outcome="skipped_unavailable",
            reason="no_verified_healthy_reference",
        )
    )
    if items is None:
        items = [item for machine in roster for item in scored(machine)]
    return EvidencePacket(
        machine_id="CNC-02",
        trigger_tick=914,
        roster=roster,
        roster_verified=bool(roster),
        screened_machines=roster,
        absent_from_screening=absent,
        items=tuple(items),
        calls=tuple(calls),
    )


def test_a_screening_of_every_roster_machine_answers_with_its_evidence():
    assert screening_answer(packet()) == ("E2", "every roster machine scored")


def test_no_packet_answers_nothing():
    evidence_id, reason = screening_answer(None)
    assert evidence_id is None and reason == "no_packet"


def test_a_machine_absent_from_the_screening_stays_unknown():
    roster = ("CNC-01", "CNC-02", "CNC-03")
    items = scored("CNC-01") + scored("CNC-02")
    items.append(
        PacketItem(
            machine_id="CNC-03",
            source_type="derived_screening",
            status="missing",
            missing_reason="absent_from_screening",
        )
    )
    evidence_id, reason = screening_answer(
        packet(roster=roster, items=items, absent=("CNC-03",))
    )
    assert evidence_id is None and reason == "unscored: CNC-03"


def test_a_machine_with_one_unscored_sensor_stays_unknown():
    items = scored("CNC-01") + scored("CNC-02", ("vibration",))
    items.append(
        PacketItem(
            machine_id="CNC-02",
            sensor="temperature",
            physical_root="CNC-02:temperature",
            source_type="derived_screening",
            status="missing",
            missing_reason="not_running",
        )
    )
    evidence_id, reason = screening_answer(packet(items=items))
    assert evidence_id is None and reason == "unscored: CNC-02"


def test_a_machine_down_for_the_whole_window_stays_unknown():
    items = scored("CNC-01") + [
        PacketItem(
            machine_id="CNC-02",
            source_type="derived_screening",
            status="missing",
            missing_reason="not_running",
        )
    ]
    evidence_id, reason = screening_answer(packet(items=items))
    assert evidence_id is None and reason == "unscored: CNC-02"


def test_without_a_roster_the_coverage_cannot_be_known():
    evidence_id, reason = screening_answer(packet(roster=(), items=scored("CNC-02")))
    assert evidence_id is None and reason == "roster_unverified"


def test_without_a_screening_there_is_nothing_to_answer_with():
    evidence_id, reason = screening_answer(packet(screened=False, items=()))
    assert evidence_id is None and reason == "no_screening"


# --- in a triage ---------------------------------------------------------------------


class ChasesScreening:
    """A scripted triage policy that, as the live model did, asks for the line
    screening whenever a question about it is still open."""

    def __init__(self, inner):
        self.inner = inner
        self.chased = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def decide(self, state, phase):
        screening = [q for q in state.unanswered_questions if is_screening_question(q)]
        if phase == "investigate" and screening:
            self.chased += 1
            return ask("get_line_screening", question_id=screening[0].id)
        return self.inner.decide(state, phase)


def triage(monkeypatch, packet_setting="on"):
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    monkeypatch.setenv("TRIAGE_PACKET", packet_setting)
    policy = ChasesScreening(wear_policy("intervene"))
    result = run(
        ByMode(policy, wear_policy()), monkeypatch, then_deep=False, triage=True
    )
    return result.triage, policy


def screening_reads(state):
    return [d for d in state.decisions if d.tool == "get_line_screening"]


def test_a_packet_triage_does_not_ask_for_the_screening_again(monkeypatch):
    first, policy = triage(monkeypatch)
    assert policy.chased == 0
    (read,) = screening_reads(first)  # Observe's own read, and no other
    assert read.phase == "observe"
    assert first.repeated_calls == 0
    assert first.answers["Q2"] == list(read.evidence_ids)
    assert "Q2" not in [q.id for q in first.unanswered_questions]


def test_a_packet_triage_still_reaches_hypothesize(monkeypatch):
    first, _ = triage(monkeypatch)
    assert any(d.phase == "hypothesize" for d in first.decisions)
    assert first.hypotheses


def test_the_closing_is_recorded_with_the_screening_evidence(monkeypatch):
    first, _ = triage(monkeypatch)
    (record,) = [r for r in first.triage_test_records if r.stage == "plan"]
    assert record.kind == "question_closed"
    assert record.question_ids == ("Q2",)
    assert record.evidence_ids == tuple(first.answers["Q2"])
    assert record.reason == "every roster machine scored"


def test_without_the_packet_the_question_stays_open_and_is_asked_again(monkeypatch):
    first, policy = triage(monkeypatch, packet_setting="off")
    assert policy.chased > 0
    assert first.repeated_calls > 0  # the read is refused as a repeat
    assert [r for r in first.triage_test_records if r.stage == "plan"] == []


def test_the_deep_run_plans_and_answers_as_before(monkeypatch):
    monkeypatch.setenv("TRIAGE_PLAN", "fixed")
    monkeypatch.setenv("TRIAGE_PACKET", "on")
    result = run(
        ByMode(ChasesScreening(wear_policy("intervene")), wear_policy()),
        monkeypatch,
        then_deep=True,
        triage=True,
    )
    deep = result.state
    assert deep.mode == "deep" and deep.triage_packet is None
    assert [r for r in deep.triage_test_records if r.stage == "plan"] == []
