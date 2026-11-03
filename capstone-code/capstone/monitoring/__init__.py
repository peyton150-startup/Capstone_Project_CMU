# Deterministic monitoring of collected telemetry, run as its own process.
# Responsibility: read records the collector stored and raise alerts; no LLM, no machine access.
"""Deterministic telemetry monitor.

Reads the JSONL file the collector writes (a separate process, so a monitor
crash never stops collection) and writes alerts to another JSONL file:

    uv run python -m capstone.monitoring --input telemetry.jsonl --alerts alerts.jsonl --follow

Plain deterministic code: no model or agent monitors. The same records
always give the same alerts. The research agent does not read them yet.
"""

from capstone.monitoring.monitor import Alert, Monitor, Threshold
from capstone.monitoring.runner import JsonlFollower, replay

__all__ = ["Alert", "JsonlFollower", "Monitor", "Threshold", "replay"]
