"""Pilot acceptance is conservative; all test probes and captures are synthetic."""

from datetime import timedelta

import pytest

from capstone.ingestion.pilot_acceptance import (
    PilotManifest,
    assess_pilot,
    main,
)
from capstone.ingestion.visit_log import TechnicianEvent
from tests.test_channel_map import probe
from tests.test_replay_provider import T0, capture, channel_map, obs


def approved():
    """One synthetic machine with documented fields, access and shop review."""
    # Variables:
    #   approved_channels: IDs that hypothetical IT/OT permission expressly covers.
    return PilotManifest(
        facility="Example test shop",
        machine_label="VF2",
        manufacturer="Example",
        machine_model="Example CNC",
        controller="Example controller",
        controller_revision="1.0",
        access_method="mtconnect",
        owner_approved=True,
        it_ot_approved=True,
        authorization_reference="/private/permission-record",
        approved_channels=["exec", "S1load", "Xpos"],
        approved_poll_seconds=5,
        data_storage_location="shop-approved local drive",
        retention_days=7,
        revocation_contact="approved shop contact",
        clock_alignment_confirmed=True,
        normal_cycles_confirmed=3,
        no_production_impact_confirmed=True,
        collection_gaps_reviewed=True,
        continued_collection_approved=True,
        continued_collection_until="approved private date",
    )


def evidence():
    """A capture and technician note whose timestamps match one covered run."""
    # Variables:
    #   records: The replay test capture, correcting Xpos to its probe-defined type.
    #   events: Operator note attached to one time covered by the capture.
    records = [
        obs(599, "Xpos", "1.5", type_="Position")
        if getattr(row, "data_item_id", None) == "Xpos"
        else row
        for row in capture()
    ]
    events = [
        TechnicianEvent(
            at=T0 + timedelta(seconds=120),
            event_type="program_change",
            note="Start normal program",
            logged_by="test operator",
        )
    ]
    return dict(probe=probe(), mapping=channel_map(), capture=records, events=events)


def test_an_unknown_controller_is_a_blocker_not_a_default_to_haas():
    report = assess_pilot(PilotManifest())
    assert report.status == "blocked"
    assert any("controller" in reason for reason in report.blockers)
    assert any("access method is unknown" in reason for reason in report.blockers)


def test_missing_capture_does_not_become_a_verified_visit():
    report = assess_pilot(approved())
    assert report.status == "pending_capture"
    assert "not yet verified" in " ".join(report.blockers)


def test_validated_probe_map_capture_operator_note_and_permission_are_required():
    report = assess_pilot(approved(), **evidence())
    assert report.status == "capture_verified"
    assert report.blockers == []
    assert report.observations > 0
    assert report.mapped_channels_with_values >= 1
    assert report.event_entries_covered == 1
    assert report.gap_markers == 1


def test_no_future_collection_permission_is_not_accepted():
    manifest = approved().model_copy(update={"continued_collection_approved": False})
    report = assess_pilot(manifest, **evidence())
    assert report.status == "pending_capture"
    assert any("permission" in reason for reason in report.blockers)


def test_gaps_must_be_reviewed():
    manifest = approved().model_copy(update={"collection_gaps_reviewed": False})
    report = assess_pilot(manifest, **evidence())
    assert report.status == "pending_capture"
    assert any("data gaps" in reason for reason in report.blockers)


def test_a_non_mtconnect_controller_is_not_faked_as_supported():
    manifest = approved().model_copy(
        update={"access_method": "approved_offline_export"}
    )
    report = assess_pilot(manifest, **evidence())
    assert report.status == "pending_capture"
    assert any("adapter" in reason for reason in report.blockers)


def test_cli_private_template_has_no_pretend_authorization(tmp_path):
    path = tmp_path / "manifest.json"
    assert main(["template", "--out", str(path)]) == 0
    plan = PilotManifest.model_validate_json(path.read_text())
    assert plan.controller is None
    assert plan.owner_approved is False
    assert plan.continued_collection_approved is False


def test_cli_reports_blockers_without_live_network_or_a_model(tmp_path):
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "acceptance.json"
    manifest.write_text(PilotManifest().model_dump_json())
    assert main(["check", "--manifest", str(manifest), "--out", str(output)]) == 1
    assert '"status": "blocked"' in output.read_text()


def test_cli_refuses_an_output_inside_a_git_checkout(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    with pytest.raises(SystemExit) as error:
        main(["template", "--out", str(repo / "pilot.json")])
    assert error.value.code == 2
    assert "inside the git checkout" in capsys.readouterr().err

def test_an_extra_unapproved_channel_blocks_acceptance():
    plan = approved().model_copy(update={"approved_channels": ["S1load"]})
    report = assess_pilot(plan, **evidence())
    assert report.status == "pending_capture"
    assert any("outside the approved field list" in x for x in report.blockers)
