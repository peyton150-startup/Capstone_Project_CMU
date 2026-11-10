"""Pilot preflight acceptance on synthetic fixtures, never a real shop controller."""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from capstone.ingestion.pilot_preflight import PilotPlan, check_pilot, main
from capstone.ingestion.visit_log import TechnicianEvent
from tests.test_channel_map import probe
from tests.test_replay_provider import T0, channel_map, obs


def approved_plan(**changes):
    """Human-filled example of a scoped, read-only shop authorization."""
    settings = dict(
        site_name="Fixture machine shop",
        visit_date="2026-11-12",
        shop_contact="example contact",
        machine_id="VF2",
        manufacturer="Fixture manufacturer",
        controller_model="Fixture controller",
        controller_software="Fixture revision",
        read_only_method="approved offline MTConnect fixture export",
        collection_scope="approved_pre_filtered_export",
        manager_approver="authorized manager",
        it_ot_approver="authorized OT contact",
        written_approval_reference="private signed-document location",
        capture_authorized=True,
        approved_data_item_ids=["exec", "S1load"],
        approved_poll_seconds=5.0,
        private_storage_location="private pilot folder outside checkout",
        retention_days=7,
        stop_and_delete_procedure="operator can disconnect and delete under agreement",
        event_log_owner="example technician",
        clocks_verified_by_human=True,
        normal_cycles_confirmed_by_technician=True,
    )
    settings.update(changes)
    return PilotPlan(**settings)


def sample():
    """One complete 60-second source-timed window and a technician entry."""
    lines = [
        obs(0, "exec", "ACTIVE", type_="Execution"),
        obs(0, "S1load", "10", type_="Load"),
        obs(60, "S1load", "20", type_="Load"),
    ]
    events = [
        TechnicianEvent(
            at=T0 + timedelta(seconds=30),
            event_type="tool_change",
            note="a tool change during the example cycle",
            logged_by="example technician",
        )
    ]
    return lines, events


def check(plan, **kwargs):
    lines, events = sample()
    return check_pilot(
        plan,
        stage="capture",
        probe_xml=probe(),
        channel_map=channel_map(),
        lines=lines,
        events=events,
        **kwargs,
    )


def test_discovery_refuses_to_invent_controller_or_visit_date():
    report = check_pilot(PilotPlan(), stage="discovery")
    assert not report.ready
    assert any("controller" in item for item in report.blocked)
    assert any("visit date" in item for item in report.blocked)


def test_authorized_capture_is_only_ready_when_probe_map_and_events_match():
    result = check(approved_plan())
    assert result.ready, result.blocked
    assert result.observations == 3
    assert result.mapped_channels > 0
    assert result.operator_events_matched == 1
    assert any(
        "does not establish access permission" in line for line in result.warnings
    )


def test_manager_or_it_approval_missing_blocks_even_a_good_capture():
    for missing in (
        {"manager_approver": None},
        {"it_ot_approver": None},
        {"written_approval_reference": None},
        {"capture_authorized": False},
    ):
        result = check(approved_plan(**missing))
        assert not result.ready


def test_unapproved_channel_is_rejected_instead_of_silently_ingested():
    lines, events = sample()
    lines.append(obs(120, "Xpos", "5", type_="Position"))
    report = check_pilot(
        approved_plan(),
        stage="capture",
        probe_xml=probe(),
        channel_map=channel_map(),
        lines=lines,
        events=events,
    )
    assert not report.ready
    assert any("not explicitly authorized" in item for item in report.blocked)


def test_probe_change_cannot_reuse_a_saved_map():
    lines, events = sample()
    report = check_pilot(
        approved_plan(),
        stage="capture",
        probe_xml=probe(load_units="AMPERE"),
        channel_map=channel_map(),
        lines=lines,
        events=events,
    )
    assert not report.ready
    assert any("probe/channel-map mismatch" in item for item in report.blocked)


def test_seven_day_work_needs_distinct_permission_and_operational_plan():
    lines, events = sample()
    report = check_pilot(
        approved_plan(),
        stage="week",
        probe_xml=probe(),
        channel_map=channel_map(),
        lines=lines,
        events=events,
    )
    assert not report.ready
    assert any("seven-day" in item for item in report.blocked)
    report = check_pilot(
        approved_plan(
            seven_day_capture_authorized=True,
            named_collector_restart_contact="example on-site person",
            disk_and_rotation_plan="verified storage and manual rotation",
        ),
        stage="week",
        probe_xml=probe(),
        channel_map=channel_map(),
        lines=lines,
        events=events,
    )
    assert report.ready
    assert any("NOT seven days of observed uptime" in item for item in report.warnings)


def test_private_template_starts_unapproved_and_does_not_overwrite():
    # The repository intentionally keeps pytest's tmp_path inside its checkout.
    # A real private plan must be created outside that checkout instead.
    with TemporaryDirectory() as directory:
        path = Path(directory) / "private-plan.json"
        assert main(["template", "--out", str(path)]) == 0
        plan = PilotPlan.model_validate_json(path.read_text(encoding="utf-8"))
        assert not plan.capture_authorized
        assert not plan.seven_day_capture_authorized
