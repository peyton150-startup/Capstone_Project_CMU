# Read-only collection of real machine telemetry (MTConnect), kept apart from the agent.
# Responsibility: fetch, normalize and store observations; never write to a machine.
"""Read-only telemetry ingestion.

The collector reads an MTConnect agent (for example a Haas NGC control) with
HTTP GET only, turns each observation into a `TelemetryRecord`, and appends the
records to a JSONL file. It runs as its own process:

    uv run python -m capstone.ingestion --url http://<agent-host>:8082 --out telemetry.jsonl

The research agent does not read these records yet. See the
"Haas live-telemetry collection" plan in docs/MVP_SCOPE.md.
"""

from capstone.ingestion.collector import MTConnectCollector, PollResult, run_collector
from capstone.ingestion.mtconnect import MTConnectError, StreamsDocument, parse_streams
from capstone.ingestion.record import TelemetryRecord

__all__ = [
    "MTConnectCollector",
    "MTConnectError",
    "PollResult",
    "StreamsDocument",
    "TelemetryRecord",
    "parse_streams",
    "run_collector",
]
