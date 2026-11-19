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
        admit("S1temp", "CONDITION", "TEMPERATURE", "OTHER").reason == "unknown_state"
    )


def test_unapproved_controller_channel_is_refused():
    assert (
        admit(
            "S1temp", "CONDITION", "TEMPERATURE", "FAULT", approved=frozenset()
        ).reason
        == "not_authorized"
    )


def test_warning_and_fault_are_both_alarms_with_their_own_severity():
    warning = admit("S1temp", "CONDITION", "TEMPERATURE", "WARNING").value.event
    fault = admit("S1temp", "CONDITION", "TEMPERATURE", "FAULT").value.event
    normal = admit("S1temp", "CONDITION", "TEMPERATURE", "NORMAL").value.event
    assert (warning.kind, warning.severity) == ("alarm", "warning")
    assert (fault.kind, fault.severity) == ("alarm", "fault")
    assert normal.severity is None
    assert admit("exec", "EVENT", "Execution", "ACTIVE").value.event.severity is None


def test_an_unavailable_execution_is_refused_before_its_value_is_read():
    from capstone.ingestion.channel_map import disagreement

    unavailable = record("exec", "EVENT", "Execution", value=None)
    assert disagreement(MAP.entry_for(unavailable), unavailable) is None
    assert admit("exec", "EVENT", "Execution", None).reason == "unknown_state"
