"""Strict Haas sequence metadata is optional for legacy MTConnect tests."""

import pytest

from capstone.ingestion.mtconnect import validate_streams_metadata
from tests.test_mtconnect_ingestion import FakeAgent, collector, parse, streams


@pytest.mark.parametrize(
    "xml",
    [
        streams("", first=0, last=0, nxt=1),
        streams("", first=2, last=0, nxt=1),
        streams("", first=1, last=3, nxt=5),
        streams("", instance="", first=1, last=1, nxt=2),
    ],
)
def test_strict_header_rejects_missing_or_inconsistent_sequences(xml):
    with pytest.raises(ValueError):
        validate_streams_metadata(parse(xml))


def test_legacy_parser_still_preserves_existing_fixture_contract():
    # Valid XML remains parseable independently of the stricter Haas profile.
    assert parse(streams("", first=0, last=0, nxt=1)).next_sequence == 1


def test_hardening_rejects_stalled_pagination_without_infinite_catchup():
    agent = FakeAgent(
        streams("", nxt=5, last=4),
        streams("", nxt=5, first=1, last=8),
    )
    c = collector(agent, strict_headers=True)
    c.poll()
    with pytest.raises(ValueError, match="did not advance"):
        c.poll()
