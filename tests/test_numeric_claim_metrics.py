"""A conclusion may cite the first and last reading of a window (2026-11-14).

In the 2026-11-14 live triage runs, two conclusions (KA-01 r2, KA-08 r2) were
refused because the model wrote `end_value`, a name the sensor summary and the
evidence brief show it, as a numeric-claim metric. The claim contract now
accepts `start_value` and `end_value`, and the verifier checks them against the
observed readings like every other metric.
"""

import pytest
from pydantic import ValidationError

from capstone.agent.evidence_brief import verify_numeric_claims
from capstone.contracts.hypotheses import Hypothesis, NumericClaim
from tests.helpers import new_state
from tests.test_reasoning_evidence import observed


def readings(state):
    """Two temperature readings on CNC-01: 70 F at tick 10, 72 F at tick 20."""
    observed(
        state,
        "get_readings",
        [
            {
                "machine_id": "CNC-01",
                "sensor": "temperature",
                "tick": tick,
                "value": value,
                "unit": "F",
            }
            for tick, value in [(10, 70), (20, 72)]
        ],
    )


def claim(metric, value, **extra):
    return NumericClaim(
        evidence_id="E1",
        machine_id="CNC-01",
        sensor="temperature",
        metric=metric,
        value=value,
        unit="F",
        **extra,
    )


def test_a_hypothesis_citing_end_value_is_accepted():
    hypothesis = Hypothesis.model_validate(
        {
            "id": "H1",
            "claim": "temperature rose",
            "confidence": 0.6,
            "numeric_claims": [
                {
                    "evidence_id": "E1",
                    "sensor": "temperature",
                    "metric": "end_value",
                    "value": 72,
                }
            ],
        }
    )
    assert hypothesis.numeric_claims[0].metric == "end_value"


def test_an_unknown_metric_is_still_refused():
    with pytest.raises(ValidationError):
        claim("median", 71)


def test_start_and_end_values_are_checked_against_raw_readings():
    state = new_state()
    readings(state)
    assert verify_numeric_claims(state, (claim("start_value", 70),)) == ()
    assert verify_numeric_claims(state, (claim("end_value", 72),)) == ()
    with pytest.raises(ValueError, match="observed arithmetic"):
        verify_numeric_claims(state, (claim("end_value", 70),))


def test_end_value_follows_the_claimed_window():
    state = new_state()
    readings(state)
    early = claim("end_value", 70, from_tick=0, to_tick=15)
    assert verify_numeric_claims(state, (early,)) == ()


def test_end_value_is_checked_against_a_sensor_summary():
    state = new_state()
    observed(
        state,
        "get_sensor_summary",
        {
            "machine_id": "CNC-01",
            "sensor": "temperature",
            "from_tick": 10,
            "to_tick": 20,
            "sample_count": 2,
            "unit": "F",
            "start_value": 70.0,
            "end_value": 72.0,
            "minimum": 70.0,
            "maximum": 72.0,
            "mean": 71.0,
            "delta": 2.0,
        },
    )
    summary = claim("end_value", 72, from_tick=10, to_tick=20)
    assert verify_numeric_claims(state, (summary,)) == ()
    with pytest.raises(ValueError, match="observed arithmetic"):
        verify_numeric_claims(state, (summary.model_copy(update={"value": 80}),))
