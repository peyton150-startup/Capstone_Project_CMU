"""Approved Haas transport must remain rate-bounded while catching up."""

from datetime import UTC, datetime
from types import SimpleNamespace

from capstone.ingestion.collector import PollResult, run_collector


def test_catchup_cannot_bypass_shop_approved_polling_interval(tmp_path):
    polls = []
    sleeps = []

    def poll():
        polls.append(1)
        return PollResult(more_waiting=True)

    collector = SimpleNamespace(
        base_url="http://approved:8082/VF-4",
        now=lambda: datetime(2026, 11, 18, tzinfo=UTC),
        poll=poll,
    )
    written = run_collector(
        collector,
        tmp_path / "approved.jsonl",
        interval=5.0,
        max_polls=3,
        sleep=sleeps.append,
        enforce_poll_interval=True,
    )
    assert written == 0
    assert len(polls) == 3
    assert sleeps == [5.0, 5.0, 5.0]
