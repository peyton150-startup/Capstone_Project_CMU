"""Qualified control-state events, without synthesizing job history."""

from capstone.ingestion.channel_map import build_channel_map
from capstone.ingestion.mtconnect_events import qualify_event
from tests.test_channel_map import probe, record

MAP = build_channel_map(probe())
PERMITTED = frozenset({"exec", "S1temp"})


def admit(item, category, type_, value, *, approved=PERMITTED):
    return qualify_event(
        record(item, category, type_, value),
        MAP,
        approved_item_ids=approved,
        tick=42,
    )


def test_approved_fault_is_an_alarm_with_source_lineage():
    verdict = admit("S1temp", "CONDITION", "TEMPERATURE", "FAULT")
    assert verdict.reason is None
    assert verdict.value.event.kind == "alarm"
    assert verdict.value.source_epoch == "1"
    assert verdict.value.event.tick == 42
    assert verdict.value.event.job_id is None


def test_normal_condition_means_cleared_not_fault():
    verdict = admit("S1temp", "CONDITION", "TEMPERATURE", "NORMAL")
    assert verdict.value.event.kind == "condition_clear"


def test_execution_is_a_state_event_not_a_root_cause():
    verdict = admit("exec", "EVENT", "Execution", "ACTIVE")
    assert verdict.value.event.kind == "status"
    assert verdict.value.event.message == "MTConnect execution ACTIVE"


def test_unknown_execution_and_condition_states_are_never_invented():
    assert admit("exec", "EVENT", "Execution", "DIAGNOSTIC").reason == "unknown_state"
    assert (
        admit("S1temp", "CONDITION", "TEMPERATURE", "OTHER").reason
        == "unknown_state"
    )


def test_unapproved_controller_channel_is_refused():
    assert (
        admit("S1temp", "CONDITION", "TEMPERATURE", "FAULT", approved=frozenset()).reason
        == "not_authorized"
    )
