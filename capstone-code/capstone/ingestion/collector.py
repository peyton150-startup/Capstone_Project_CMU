# Polls one MTConnect agent read-only and appends what it reports to a JSONL file.
# Responsibility: request order, sequence tracking and recovery; never write to a machine.
"""A bounded-rate, read-only MTConnect polling collector.

Request order (MTConnect REST protocol):

1. GET /current once: the latest value of every data item, and nextSequence.
2. GET /sample?from=<nextSequence>&count=<count> repeatedly: everything new
   since the last request, in sequence order.

Recovery:
- OUT_OF_RANGE (we asked for data the agent no longer holds) or a changed
  instanceId (the agent restarted and its sequences started again): go back
  to step 1 and report a gap. Data lost in between is not invented.
- Network or parse failure: report it and try again on the next poll.

Only HTTP GET is ever sent. The collector does not choose what the machine
exposes; save /probe once (`--save-probe`) to see the machine's capability list.
"""

import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TextIO

from capstone.ingestion.mtconnect import MTConnectError, parse_streams
from capstone.ingestion.record import CollectorMarker, Line, TelemetryRecord

# The fastest a collector may poll. Real machines are shared production
# equipment; agree the actual rate with the shop before running.
MIN_INTERVAL_SECONDS = 1.0
# The most bytes read from one response, so a broken agent cannot exhaust memory.
MAX_RESPONSE_BYTES = 20_000_000
REQUEST_TIMEOUT_SECONDS = 10.0

Fetch = Callable[[str], str]


def http_get(url: str) -> str:
    """GET a URL and return the body, including the body of an HTTP error.

    MTConnect agents answer a bad request (e.g. OUT_OF_RANGE) with HTTP 400 and
    an MTConnectError document, so the error body must be read, not dropped.
    """
    # Variables:
    #   url: The full agent address for one request, e.g. .../sample?from=5.
    #   request: A GET request asking for XML; no other method is ever built.
    #   body: An HTTP error's content; returned if it is an MTConnect error
    #     document, otherwise the HTTP error is raised again.
    request = urllib.request.Request(
        url, method="GET", headers={"Accept": "application/xml"}
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            return response.read(MAX_RESPONSE_BYTES).decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        if "MTConnectError" in body:
            return body
        raise


def utc_now() -> datetime:
    """The current time in UTC (the collector's receive clock)."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class PollResult:
    """What one poll produced."""

    # Variables:
    #   records: New observations, in sequence order, never repeated.
    #   gap: True when data may have been lost (buffer overrun or agent restart).
    #   more_waiting: True when the agent holds more than one request returned,
    #     so the caller should poll again without waiting.
    records: list[TelemetryRecord] = field(default_factory=list)
    gap: bool = False
    more_waiting: bool = False


class MTConnectCollector:
    """Tracks where it is in one agent's sequence and fetches what is new."""

    def __init__(
        self,
        base_url: str,
        *,
        device: str | None = None,
        count: int = 1000,
        fetch: Fetch = http_get,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        # Variables:
        #   base_url: The agent's address, e.g. http://192.168.1.20:8082.
        #   device: Restricts requests to one machine on an agent that serves
        #     several (/<device>/current); None means every device.
        #   count: The most observations one /sample request may return.
        #   fetch: Gets a URL's body; replaced by a fake in tests.
        #   now: The receive clock, also used to time start/stop markers;
        #     replaced by a fixed clock in tests.
        #   _next: The sequence the next /sample starts from; None means "start
        #     again from /current".
        #   _instance_id: The agent run we are following; a change means restart.
        if count < 1:
            raise ValueError("count must be at least 1")
        self.base_url = base_url.rstrip("/")
        self.device = device
        self.count = count
        self._fetch = fetch
        self.now = now
        self._next: int | None = None
        self._instance_id: str | None = None

    def _url(self, request: str) -> str:
        """The URL for a request, scoped to the device if one was chosen."""
        # Variables:
        #   request: The MTConnect request and its query, e.g. "current" or
        #     "sample?from=5&count=1000".
        #   prefix: The agent's address, plus "/<device>" when one was chosen.
        prefix = f"{self.base_url}/{self.device}" if self.device else self.base_url
        return f"{prefix}/{request}"

    def probe(self) -> str:
        """The agent's /probe document: which data items this machine exposes."""
        return self._fetch(self._url("probe"))

    def poll(self) -> PollResult:
        """Fetch what is new since the last poll.

        Raises on network or parse failure; the caller decides to retry.
        """
        # Variables:
        #   starting: True for the first request, or after a gap or restart.
        #   requested_from: The sequence we asked /sample to start from.
        #   url: /current when starting, else /sample from requested_from.
        #   document: The parsed reply: its header numbers and its records.
        #   restarted: True when the agent's instanceId changed since the last
        #     poll, meaning its sequence numbers started again.
        #   records: The reply's records, minus any already written.
        #   gap: True when data may have been lost: a restart, or the agent's
        #     oldest held sequence is past where we asked to start.
        starting = self._next is None
        requested_from = self._next
        url = (
            self._url("current")
            if starting
            else self._url(f"sample?from={requested_from}&count={self.count}")
        )
        try:
            document = parse_streams(
                self._fetch(url), source=self.base_url, received_at=self.now()
            )
        except MTConnectError as error:
            if "OUT_OF_RANGE" in error.codes:
                self._next = None
                return PollResult(gap=True)
            raise

        restarted = (
            self._instance_id is not None and document.instance_id != self._instance_id
        )
        self._instance_id = document.instance_id
        if restarted and not starting:
            # Sequences from the old run mean nothing in the new one.
            self._next = None
            return PollResult(gap=True)

        self._next = document.next_sequence
        records = document.records
        if not starting:
            records = [r for r in records if r.sequence >= (requested_from or 0)]
        gap = restarted or (
            not starting and (requested_from or 0) < document.first_sequence
        )
        return PollResult(
            records=records,
            gap=gap,
            more_waiting=not starting
            and document.next_sequence <= document.last_sequence,
        )


def append_jsonl(path: Path, records: list[Line]) -> None:
    """Append records or markers to a JSONL file, one per line, flushed at once."""
    # Variables:
    #   path: The telemetry file; created if missing, never overwritten.
    #   records: Observations and markers to append, in the order given.
    if not records:
        return
    with path.open("a", encoding="utf-8") as sink:
        for record in records:
            sink.write(record.model_dump_json() + "\n")
        sink.flush()


def run_collector(
    collector: MTConnectCollector,
    out: Path,
    *,
    interval: float,
    max_polls: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    log: TextIO | None = None,
) -> int:
    """Poll until max_polls (or forever), writing records; returns records written.

    Failures are reported and retried; one bad response never stops collection.
    A `started` marker is written first. A `stopped` marker is written only
    when collection ends on purpose: the poll limit, or Ctrl+C (which is then
    not re-raised). Any other exception ends it without a marker, so a crash
    stays visible in the file.
    """
    # Variables:
    #   collector: The agent reader; keeps its place in the agent's sequence.
    #   out: The JSONL file every record and marker is appended to.
    #   interval: Seconds between polls; never below MIN_INTERVAL_SECONDS.
    #   max_polls: Stop after this many polls; None runs until interrupted.
    #   sleep: Waits between polls; replaced by a fake clock in tests.
    #   log: Where failures and gaps are reported; None means standard error.
    #   polls: Polls made so far, compared with max_polls.
    #   result: One poll's records and its gap and more_waiting flags.
    #   written: Records appended so far, returned for the caller's summary.
    #   reason: Why collection ended on purpose, written into the stop marker.
    if interval < MIN_INTERVAL_SECONDS:
        raise ValueError(f"interval must be at least {MIN_INTERVAL_SECONDS} s")
    written = 0
    polls = 0
    append_jsonl(out, [_marker(collector, "started")])
    try:
        while max_polls is None or polls < max_polls:
            polls += 1
            try:
                result = collector.poll()
            except (OSError, ET.ParseError, ValueError, MTConnectError) as error:
                print(
                    f"poll failed, retrying: {type(error).__name__}: {error}",
                    file=log or sys.stderr,
                )
                sleep(interval)
                continue
            append_jsonl(out, result.records)
            written += len(result.records)
            if result.gap:
                print(
                    "gap: some observations were lost; restarted from /current",
                    file=log or sys.stderr,
                )
            if not result.more_waiting:
                sleep(interval)
        reason = "poll limit reached"
    except KeyboardInterrupt:
        reason = "interrupted"
    append_jsonl(out, [_marker(collector, "stopped", reason)])
    return written


def _marker(
    collector: MTConnectCollector,
    event: Literal["started", "stopped"],
    reason: str | None = None,
) -> CollectorMarker:
    """A start or stop marker for this collector, timed on its clock."""
    # Variables:
    #   event: "started" or "stopped".
    #   reason: Why it stopped (e.g. "interrupted"); None for a start.
    return CollectorMarker(
        source=collector.base_url, event=event, at=collector.now(), reason=reason
    )
