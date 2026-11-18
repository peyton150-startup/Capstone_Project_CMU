"""Synthetic MTConnect qualification tests; not a Haas controller claim."""

from capstone.ingestion.channel_map import build_channel_map
from capstone.ingestion.qualified import qualify_numeric
from tests.test_channel_map import probe, record


def check(value="12", **kwargs):
    p = kwargs.pop("probe_xml", probe())
    return qualify_numeric(
        record("S1load", "SAMPLE", "Load", value, **kwargs),
        build_channel_map(p),
        authorized_item_ids=frozenset({"S1load"}),
    )


def test_good_numeric_sample_keeps_source_and_unit_lineage():
    outcome = check()
    assert outcome.accepted
    assert outcome.sample.value == 12
    assert outcome.sample.units == "PERCENT"
    assert len(outcome.sample.probe_sha256) == 64


def test_unavailable_is_not_zero():
    result = check(None)
    assert not result.accepted
    assert result.reason == "unavailable"


def test_nonfinite_never_reaches_detector():
    assert check("nan").reason == "nonfinite"
    assert check("inf").reason == "nonfinite"


def test_missing_unit_is_not_guessed():
    assert check(probe_xml=probe(load_units="")).reason == "unit_unstated"


def test_unmapped_and_wrong_signal_type_are_refused():
    mapped = build_channel_map(probe())
    assert (
        qualify_numeric(
            record("unknown", "SAMPLE", "Load", "1"),
            mapped,
            authorized_item_ids=frozenset({"unknown"}),
        ).reason == "unmapped"
    )
    assert check("12", sequence=0).reason == "invalid_sequence"


def test_source_authorization_gate_is_explicit():
    result = qualify_numeric(
        record("S1load", "SAMPLE", "Load"),
        build_channel_map(probe()),
        authorized_item_ids=frozenset(),
    )
    assert result.reason == "not_authorized"
