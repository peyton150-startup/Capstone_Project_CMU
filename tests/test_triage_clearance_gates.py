"""Block 5 clearance gates (2026-11-13): three more reasons a triage may not close a case.

`triage_clearance_gaps` already held a supported "nothing needs doing" open
when the triage formed no explanation or the screening left a machine
unscored (PR 246). Block 5 adds three, all triage-only and all in the safe
direction (they can only turn a clearance into an escalation):

- the answer must cite a measurement, not only a clock read or machine list;
- every machine on a gathered machine list must have a screening entry;
- the screening must be read at or after the alarm.

The Block 0 tests in `test_triage_safety_baseline.py` state the three rules;
these tests pin the edges, so a fix does not block a genuinely healthy case.
"""

from capstone.agent.investigation import latest_roster, unscored_machines
from capstone.contracts.provenance import ProvenanceReference
from tests.test_triage import add_evidence, clear, clearance_state, gap_kinds


def roster(state, *machines, evidence_id="E4"):
    add_evidence(
        state,
        evidence_id,
        "simulator:list_machines",
        [{"machine_id": m, "status": "running"} for m in machines],
    )


# --- a measurement must be cited -------------------------------------------


def test_citing_the_screening_counts_as_a_measurement():
    state = clearance_state()
    checked = clear(state, evidence_ids=("E2",))
    assert checked.recommendation == "no_action"
    assert gap_kinds(state) == []


def test_citing_only_the_machine_list_is_not_a_measurement():
    state = clearance_state()
    roster(state, "CNC-01", "CNC-02")
    checked = clear(state, evidence_ids=("E1", "E4"))
    assert checked.recommendation == "escalate"
    assert gap_kinds(state) == ["triage_no_measurement"]


def test_a_reading_that_is_not_from_the_factory_does_not_count():
    # A manual passage or a memory is general guidance or a past belief, not
    # a reading of this machine now: only observable evidence can count.
    state = clearance_state()
    add_evidence(state, "E5", "manual:search_manual", {"text": "normal is < 5 mm/s"})
    state.provenance[-1] = ProvenanceReference(
        evidence_id="E5",
        source_id="manual:search_manual",
        source_type="tool_result",
        origin="manual",
        observed_tick=10,
    )
    clear(state, evidence_ids=("E1", "E5"))
    assert gap_kinds(state) == ["triage_no_measurement"]


# --- every machine on the machine list must be screened ---------------------


def test_a_machine_list_that_matches_the_screening_adds_no_gap():
    state = clearance_state()
    roster(state, "CNC-01", "CNC-02")
    clear(state)
    assert gap_kinds(state) == []


def test_without_a_machine_list_only_the_screenings_own_machines_are_checked():
    # The triage need not gather the machine list; then nothing says a
    # machine is missing, and the check stays as it was before Block 5.
    state = clearance_state()
    assert latest_roster(state) is None
    clear(state)
    assert gap_kinds(state) == []


def test_the_newest_machine_list_is_the_one_used():
    state = clearance_state()
    roster(state, "CNC-01", "CNC-02", "CNC-03", evidence_id="E4")
    roster(state, "CNC-01", "CNC-02", evidence_id="E5")
    assert latest_roster(state) == ["CNC-01", "CNC-02"]


def test_missing_machines_follow_the_screenings_own_unscored_ones_without_repeats():
    state = clearance_state()
    machines = {"CNC-01": "not_running_yet", "CNC-02": {"vibration": [0.1, 0.0]}}
    assert unscored_machines(state, machines, ["CNC-01", "CNC-02", "CNC-03"]) == [
        "CNC-01",
        "CNC-03",
    ]


def test_the_gap_names_the_machine_the_screening_missed():
    state = clearance_state()
    roster(state, "CNC-01", "CNC-02", "CNC-03")
    checked = clear(state)
    assert gap_kinds(state) == ["triage_screening_gap"]
    assert "CNC-03" in checked.unresolved_questions[0]


# --- the screening must be read at or after the alarm -----------------------


def test_a_screening_read_at_the_alarms_tick_is_fresh_enough():
    state = clearance_state()
    assert state.anomaly.tick == 10  # the screening E2 was read at tick 10 too
    clear(state)
    assert gap_kinds(state) == []


def test_a_stale_screening_names_both_ticks():
    state = clearance_state()
    state.anomaly = state.anomaly.model_copy(update={"tick": 200})
    checked = clear(state)
    assert gap_kinds(state) == ["triage_screening_stale"]
    assert "tick 10" in checked.unresolved_questions[0]
    assert "tick 200" in checked.unresolved_questions[0]


def test_a_recorded_machine_has_no_screening_so_no_stale_or_roster_gap():
    state = clearance_state(screening=None)
    state.anomaly = state.anomaly.model_copy(update={"tick": 200})
    roster(state, "CNC-01", "CNC-02", "CNC-03")
    checked = clear(state, screening_available=False)
    assert checked.recommendation == "no_action"
    assert gap_kinds(state) == []


# --- unchanged elsewhere -----------------------------------------------------


def test_answers_that_clear_nothing_get_none_of_the_new_gaps():
    state = clearance_state()
    state.anomaly = state.anomaly.model_copy(update={"tick": 200})
    clear(state, recommendation="escalate", evidence_ids=("E1",))
    assert gap_kinds(state) == []


def test_a_deep_run_gets_none_of_the_new_gaps():
    state = clearance_state()
    state.mode = "deep"
    state.anomaly = state.anomaly.model_copy(update={"tick": 200})
    roster(state, "CNC-01", "CNC-02", "CNC-03")
    checked = clear(state, evidence_ids=("E1",))
    assert checked.recommendation == "no_action"
    assert gap_kinds(state) == []
