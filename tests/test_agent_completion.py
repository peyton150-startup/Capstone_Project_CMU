import json

import pytest

from capstone.agent.artifacts import TerminationReason, VerificationCheck
from capstone.agent.completion import (
    AuditLog,
    AuditRecord,
    audit_record,
    complete,
    shared_verification,
)
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.contracts.tools import ToolRequest
from tests.helpers import FakeProvider, ScriptedPolicy, new_state
from tests.test_agent_verification import (
    PREDICTION,
    Factory,
    cite,
    investigate,
    policy,
)

HIDDEN_WORDS = ("bearing_health", "defect_risk", "standard_speed", "ground_truth")


def failed_at_every_stage():
    """An investigation in which the factory and the policy both gave nothing."""
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=FakeProvider(lambda request: "error"),
        policy=ScriptedPolicy([]),
        clock=lambda: 0.0,
    )
    return run_investigation(state, deps)


# Each way an investigation can end, by name.
ENDINGS = {
    "verified fix": lambda: investigate(policy())[0],
    "failed fix": lambda: investigate(policy(machine_id="CNC-01"))[0],
    "inconclusive check": lambda: investigate(policy(judge=cite("E2")))[0],
    "check not performed": lambda: investigate(policy(verify=()))[0],
    "rejected": lambda: investigate(policy(), "reject")[0],
    "no human answer": lambda: investigate(policy(), None)[0],
    "approved, not carried out": lambda: investigate(
        policy(), state=new_state(followup_tool_calls=2)
    )[0],
    "escalated": lambda: investigate(policy(recommendation="escalate"))[0],
    "no action, checked": lambda: investigate(
        policy(recommendation="no_action", judge=cite("E5", outcome="not_resolved"))
    )[0],
    "failed at every stage": failed_at_every_stage,
}


def sources(record, evidence_ids):
    by_id = {e.id: e.source_id.split(":")[1] for e in record.evidence}
    return [by_id[evidence_id] for evidence_id in evidence_ids]


def content(record, evidence_id):
    [evidence] = [e for e in record.evidence if e.id == evidence_id]
    return json.loads(evidence.content)


# --- a verified fix, field by field ----------------------------------------


def test_a_verified_fix_becomes_a_complete_shared_record():
    state = ENDINGS["verified fix"]()
    record = complete(state)
    assert isinstance(record, CompletedInvestigation)
    assert (record.run_id, record.investigation_id) == (
        state.run_id,
        state.investigation_id,
    )
    assert record.anomaly.model_dump() == {
        "summary": "High vibration",
        "symptoms": ("alarm",),
    }
    assert record.evidence == tuple(state.evidence)
    assert record.hypotheses == tuple(state.hypotheses)
    assert record.conclusion.model_dump() == {
        "diagnosis": "wear on CNC-02",
        "confidence": 0.95,
        "evidence_ids": ("E2", "E3"),
    }
    assert (record.iterations_used, record.tool_calls_used) == (
        state.iteration_count,
        state.tool_call_count,
    )
    assert record.termination_reason == "diagnosis_supported"


def test_the_action_cites_what_the_factory_reported_about_it():
    record = complete(ENDINGS["verified fix"]())
    action = record.proposed_action
    assert (action.action, action.machine_id) == ("replace_bearing", "CNC-02")
    assert action.reason == "vibration has climbed for hundreds of ticks"
    assert action.evidence_ids[:2] == ("E2", "E3")  # why it was wanted
    assert sources(record, action.evidence_ids[2:]) == [
        "propose_action",
        "get_proposals",
        "execute_action",
    ]


def test_a_resolved_check_is_verified_at_the_tick_it_was_made():
    state = ENDINGS["verified fix"]()
    check = complete(state).verification
    assert (check.status, check.outcome, check.observed_tick) == (
        "verified",
        "resolved",
        945,
    )
    assert check.evidence_ids == state.verification.evidence_ids
    assert PREDICTION in check.summary and "resolved" in check.summary


# --- an outcome is translated, never upgraded ------------------------------


def test_a_fix_that_did_not_work_is_recorded_as_failed():
    check = complete(ENDINGS["failed fix"]()).verification
    assert (check.status, check.outcome) == ("failed", "unresolved")


def test_an_inconclusive_check_stays_unverified():
    check = complete(ENDINGS["inconclusive check"]()).verification
    assert (check.status, check.outcome, check.observed_tick) == (
        "unverified",
        "unknown",
        945,
    )


@pytest.mark.parametrize(
    "ending",
    [
        "check not performed",
        "rejected",
        "no human answer",
        "approved, not carried out",
        "escalated",
        "failed at every stage",
    ],
)
def test_a_check_that_was_never_made_is_left_out(ending):
    assert complete(ENDINGS[ending]()).verification is None


def test_no_tick_is_invented_for_a_check_without_one():
    untimed = VerificationCheck(outcome="resolved", prediction="x")
    assert shared_verification(untimed) is None
    assert shared_verification(None) is None


# --- what became of the proposal can be read from the evidence -------------


def test_a_rejection_and_its_reason_are_in_the_record():
    record = complete(ENDINGS["rejected"]())
    action = record.proposed_action
    assert sources(record, action.evidence_ids[2:]) == [
        "propose_action",
        "get_proposals",
    ]
    [mine] = content(record, action.evidence_ids[-1])
    assert (mine["status"], mine["note"]) == ("rejected", "not yet")
    assert record.verification is None


def test_an_approval_that_was_never_carried_out_can_be_told_apart_from_a_fix():
    record = complete(ENDINGS["approved, not carried out"]())
    action = record.proposed_action
    reported = sources(record, action.evidence_ids[2:])
    assert reported == ["propose_action", "get_proposals"]  # no start of work
    [mine] = content(record, action.evidence_ids[-1])
    assert (mine["status"], mine["executed_tick"]) == ("approved", None)
    assert record.verification is None
    assert "execute_action" not in sources(record, [e.id for e in record.evidence])


def test_a_proposal_nobody_answered_is_shown_as_pending():
    record = complete(ENDINGS["no human answer"]())
    [mine] = content(record, record.proposed_action.evidence_ids[-1])
    assert mine["status"] == "pending"


@pytest.mark.parametrize("ending", ["escalated", "no action, checked"])
def test_no_action_is_recorded_when_none_was_wanted(ending):
    assert complete(ENDINGS[ending]()).proposed_action is None


def test_doing_nothing_and_checking_is_recorded_with_its_result():
    record = complete(ENDINGS["no action, checked"]())
    assert record.proposed_action is None
    assert (record.verification.status, record.verification.outcome) == (
        "failed",
        "unresolved",
    )


def test_a_failed_investigation_still_leaves_an_honest_record():
    record = complete(ENDINGS["failed at every stage"]())
    assert record.evidence == ()
    assert record.conclusion.model_dump() == {
        "diagnosis": "undetermined",
        "confidence": 0.0,
        "evidence_ids": (),
    }
    assert record.proposed_action is None and record.verification is None
    assert record.termination_reason == "no_useful_action"


# --- every ending ----------------------------------------------------------


@pytest.mark.parametrize("ending", ENDINGS)
def test_every_ending_produces_a_valid_record_that_cites_only_real_evidence(ending):
    state = ENDINGS[ending]()
    before = state.model_dump_json()
    record = complete(state)
    assert state.model_dump_json() == before  # working memory is not changed

    assert (
        CompletedInvestigation.model_validate_json(record.model_dump_json()) == record
    )
    gathered = {e.id for e in record.evidence}
    labelled = {p.evidence_id for p in state.provenance}
    cited = set(record.conclusion.evidence_ids)
    if record.proposed_action:
        cited |= set(record.proposed_action.evidence_ids)
    if record.verification:
        cited |= set(record.verification.evidence_ids)
    for hypothesis in record.hypotheses:
        cited |= set(hypothesis.supporting_evidence_ids)
        cited |= set(hypothesis.contradicting_evidence_ids)
    assert cited <= gathered == labelled
    assert record.termination_reason in {reason.value for reason in TerminationReason}
    text = record.model_dump_json().lower()
    assert not [word for word in HIDDEN_WORDS if word in text]


def test_the_same_run_twice_gives_the_same_record():
    first, second = (complete(ENDINGS["verified fix"]()) for _ in range(2))
    assert first.model_dump_json() == second.model_dump_json()


def test_an_investigation_that_has_not_finished_cannot_be_completed():
    with pytest.raises(ValueError, match="has not finished"):
        complete(new_state())


# --- the audit log ---------------------------------------------------------


def test_the_audit_record_holds_what_the_shared_record_leaves_out():
    state = ENDINGS["rejected"]()
    record = audit_record(state)
    assert record.completed == complete(state)
    assert record.provenance == tuple(state.provenance)
    assert record.proposal.status == "rejected" and record.proposal.proposal_id == 1
    assert record.anomaly.machine_id == "CNC-02" and record.anomaly.tick == 10
    assert record.conclusion.recommendation == "intervene"
    assert record.action_started_tick is None
    assert record.decisions == tuple(state.decisions)
    assert record.metrics == state.metrics()


def test_the_log_keeps_every_investigation_one_per_line(tmp_path):
    log = AuditLog(tmp_path / "investigations.jsonl")
    assert log.read() == ()
    records = [audit_record(ENDINGS[name]()) for name in ("verified fix", "rejected")]
    for record in records:
        log.append(record)
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(isinstance(json.loads(line), dict) for line in lines)
    assert log.read() == tuple(records)
    assert all(isinstance(record, AuditRecord) for record in log.read())


def test_the_log_is_only_ever_added_to(tmp_path):
    log = AuditLog(tmp_path / "investigations.jsonl")
    log.append(audit_record(ENDINGS["rejected"]()))
    first = log.path.read_text(encoding="utf-8")
    AuditLog(log.path).append(audit_record(ENDINGS["verified fix"]()))
    assert log.path.read_text(encoding="utf-8").startswith(first)
    assert len(log.read()) == 2


def test_a_rejection_note_is_kept_in_the_log_in_words(tmp_path):
    log = AuditLog(tmp_path / "investigations.jsonl")
    log.append(audit_record(ENDINGS["rejected"]()))
    assert "not yet" in log.path.read_text(encoding="utf-8")


def test_no_hidden_truth_is_written_to_the_log(tmp_path):
    log = AuditLog(tmp_path / "investigations.jsonl")
    for name in ("verified fix", "failed fix"):
        log.append(audit_record(ENDINGS[name]()))
    text = log.path.read_text(encoding="utf-8").lower()
    assert not [word for word in HIDDEN_WORDS if word in text]


def test_the_agent_has_no_tool_that_reads_the_log():
    provider = Factory().provider
    for name in ("read_audit_log", "get_audit_log", "search_incident_history"):
        result = provider.call(ToolRequest(name=name))
        assert not result.success and result.error.code == "unknown_tool"


def test_the_audit_record_keeps_what_tree_of_thought_ruled_out():
    from capstone.agent.state import PrunedCandidate

    state = ENDINGS["rejected"]()
    state.pruned_candidates = [
        PrunedCandidate(id="C3", claim="a wrong setting", reason="rated impossible")
    ]
    record = audit_record(state)
    assert record.pruned_candidates == tuple(state.pruned_candidates)
    assert "pruned" not in json.dumps(record.completed.model_dump(mode="json"))
    old = record.model_dump(mode="json")
    del old["pruned_candidates"]
    assert AuditRecord.model_validate(old).pruned_candidates == ()


def test_audit_without_memory_writes_the_record(tmp_path):
    from capstone.episode import run_episode
    from tests.test_episode import wear_policy

    log = AuditLog(tmp_path / "audit.jsonl")
    result = run_episode(
        6, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0, log=log
    )
    [record] = log.read()
    assert record.completed.investigation_id == result.state.investigation_id
    assert record.pruned_candidates == ()
