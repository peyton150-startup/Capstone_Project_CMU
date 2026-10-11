from uuid import UUID

import pytest
from pydantic import ValidationError

from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.investigations import (
    Investigation,
    investigation_id_for,
    run_id_for,
)
from capstone.contracts.observations import SensorObservation
from capstone.contracts.tools import ToolError, ToolResult


def test_ids_are_reproducible_and_separate_runs_and_investigations():
    run = run_id_for("experiment-42-repeat-1")
    assert isinstance(run, UUID)
    assert run == run_id_for("experiment-42-repeat-1")
    assert run != run_id_for("experiment-42-repeat-2")
    assert investigation_id_for(run, 1) == investigation_id_for(run, 1)
    assert investigation_id_for(run, 1) != investigation_id_for(run, 2)
    assert investigation_id_for(run, 1) != investigation_id_for(run_id_for("other"), 1)


@pytest.mark.parametrize("sequence", [0, -1, True])
def test_investigation_sequence_must_be_positive_integer(sequence):
    with pytest.raises(ValueError):
        investigation_id_for(run_id_for("run"), sequence)


def test_observation_rejects_hidden_or_unknown_fields():
    with pytest.raises(ValidationError):
        SensorObservation(
            tick=1,
            machine_id="CNC-01",
            sensor="vibration",
            value=2.0,
            unit="mm/s",
            bearing_health=0.3,
        )


def test_failed_tool_result_cannot_claim_success():
    with pytest.raises(ValidationError):
        ToolResult(
            success=True,
            tool="get_time",
            source="simulator",
            tick=0,
            timestamp="2026-01-05T06:00:00",
            error=ToolError(code="invalid_arguments", message="Invalid"),
        )


def test_research_artifacts_round_trip_with_evidence_references_and_ids():
    run = run_id_for("artifact-run")
    evidence = Evidence(
        id="e1",
        source_id="CNC-01/vibration",
        source_type="telemetry",
        content="Vibration rose over several readings",
        observed_tick=20,
    )
    hypothesis = Hypothesis(
        id="h1",
        claim="Possible bearing wear",
        confidence=0.6,
        supporting_evidence_ids=("e1",),
    )
    investigation = Investigation(
        run_id=run,
        investigation_id=investigation_id_for(run, 1),
        anomaly="Elevated vibration",
        evidence=(evidence,),
        hypotheses=(hypothesis,),
    )
    assert (
        Investigation.model_validate_json(investigation.model_dump_json())
        == investigation
    )
    assert investigation.hypotheses[0].supporting_evidence_ids == ("e1",)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan")])
def test_hypothesis_confidence_must_be_finite_and_in_range(confidence):
    with pytest.raises(ValidationError):
        Hypothesis(id="h1", claim="Possible wear", confidence=confidence)
