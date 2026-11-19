"""Qualified real-data screening is deterministic and never fabricates causes."""

from datetime import UTC, datetime, timedelta

from capstone.ingestion.qualified import QualifiedNumericObservation
from capstone.ingestion.real_detector import (
    CalibratedSignalBaseline,
    assess_calibrated_window,
)


def baseline():
    return CalibratedSignalBaseline(
        calibration_id="manual-approved-calibration-v1",
        machine_id="VF4",
        data_item_id="load-1",
        unit="PERCENT",
        mapping_revision="a" * 64,
        median=20.0,
        robust_spread=4.0,
        score_threshold=3.0,
        min_samples=3,
        min_span_seconds=10,
    )


def samples(value=20.0):
    t = datetime(2026, 11, 18, tzinfo=UTC)
    return [
        QualifiedNumericObservation(
            source="approved-agent",
            instance_id="17000000",
            device="VF4",
            component="S1",
            data_item_id="load-1",
            sequence=i + 1,
            timestamp=t + timedelta(seconds=i * 10),
            received_at=t + timedelta(seconds=i * 10 + 1),
            value=value,
            units="PERCENT",
            probe_sha256="a" * 64,
        )
        for i in range(3)
    ]


def test_calibrated_running_deviation_is_a_score_not_a_diagnosis():
    outcome = assess_calibrated_window(
        baseline(), samples(40), operating_state="running"
    )
    assert outcome.status == "scored"
    assert outcome.threshold_exceeded
    assert outcome.robust_score == 5
    assert not hasattr(outcome, "root_cause")


def test_normal_running_readings_do_not_trigger():
    outcome = assess_calibrated_window(baseline(), samples(), operating_state="running")
    assert outcome.status == "scored"
    assert not outcome.threshold_exceeded


def test_idle_and_unknown_states_are_unscorable():
    for state in ("not_running", "unknown"):
        outcome = assess_calibrated_window(
            baseline(), samples(99), operating_state=state
        )
        assert outcome.status == "unscorable"
        assert not outcome.threshold_exceeded


def test_mixed_provenance_is_unscorable():
    rows = samples(99)
    rows[1] = rows[1].model_copy(update={"instance_id": "different-epoch"})
    result = assess_calibrated_window(baseline(), rows, operating_state="running")
    assert result.reason == "different_source_epoch"


def test_lost_order_and_missing_coverage_never_claim_deviation():
    rows = samples(99)
    rows[1] = rows[1].model_copy(update={"sequence": 1})
    assert (
        assess_calibrated_window(baseline(), rows, operating_state="running").reason
        == "out_of_order"
    )
    assert (
        assess_calibrated_window(
            baseline(), samples(99)[:2], operating_state="running"
        ).reason
        == "too_few_samples"
    )
