# Optional JSON event logging for safe operational details.
# Responsibility: log checked identifiers and ticks, never evidence or secrets.
"""Opt-in JSON event logging for safe operational metadata.

Callers supply correlation IDs and simulation ticks. Observations, conclusions,
action reasons, exception text and arbitrary extra fields are deliberately absent
from the API. Event names and IDs must be identifiers, never free-form text.
"""

import json
import logging
import re
from math import isfinite
from collections.abc import Mapping
from typing import TextIO

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _safe_identifier(value: object, field: str) -> str:
    """Mask secret wrappers or validate metadata without echoing rejected values."""
    # Recognize Pydantic secret wrappers without requiring it for this module.
    if type(value).__name__ in {"SecretStr", "SecretBytes"} and callable(
        getattr(value, "get_secret_value", None)
    ):
        return "[REDACTED]"
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field} must be an identifier of at most 128 characters")
    return value


class EventLogger:
    """An isolated standard-library logger with one JSON-line stream handler."""

    def __init__(self, stream: TextIO, *, name: str = "capstone") -> None:
        # Construct directly: getLogger() would mutate the process-wide registry
        # and cause independent callers using the same name to share handlers.
        self._logger = logging.Logger(name, level=logging.INFO)
        self._logger.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)

    def log_event(
        self,
        event: str,
        *,
        run_id: str | None = None,
        investigation_id: str | None = None,
        tick: int | None = None,
        tool: str | None = None,
        success: bool | None = None,
        counts: Mapping[str, int] | None = None,
        sequence: int | None = None,
        phase: str | None = None,
        status: str | None = None,
        reason_code: str | None = None,
        evidence_id: str | None = None,
        cutoff_tick: int | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Emit one event; omitted context stays absent and no clock is inferred.

        Only the listed metadata fields can be logged. Store rich investigation
        records elsewhere, behind their own evidence and secret boundaries.
        """
        # Variables:
        #   event: A short identifier naming what happened, never free text.
        #   metadata: The only fields that are logged, each checked as an identifier or
        #     number.
        #   counts: Optional named tallies (for example how many calls failed); each
        #     key is checked as an identifier and each value as a nonnegative integer,
        #     so no evidence text can be logged through it.
        metadata: dict[str, str | int | bool | dict[str, int]] = {
            "event": _safe_identifier(event, "event")
        }
        for field, value in (
            ("run_id", run_id),
            ("investigation_id", investigation_id),
            ("tool", tool),
            ("phase", phase),
            ("status", status),
            ("reason_code", reason_code),
            ("evidence_id", evidence_id),
        ):
            if value is not None:
                metadata[field] = _safe_identifier(value, field)
        if tick is not None:
            if type(tick) is not int or tick < 0:
                raise ValueError("tick must be a nonnegative integer")
            metadata["tick"] = tick
        for field, value in (
            ("sequence", sequence),
            ("cutoff_tick", cutoff_tick),
        ):
            if value is not None:
                if type(value) is not int or value < (1 if field == "sequence" else 0):
                    raise ValueError(f"{field} must be a nonnegative integer")
                metadata[field] = value
        if duration_ms is not None:
            if type(duration_ms) not in (float, int) or not isfinite(duration_ms) or duration_ms < 0:
                raise ValueError("duration_ms must be a finite nonnegative number")
            metadata["duration_ms"] = round(duration_ms, 3)
        if success is not None:
            if type(success) is not bool:
                raise ValueError("success must be a boolean")
            metadata["success"] = success
        if counts is not None:
            checked: dict[str, int] = {}
            for key, value in counts.items():
                if type(value) is not int or value < 0:
                    raise ValueError("counts must be nonnegative integers")
                checked[_safe_identifier(key, "counts key")] = value
            metadata["counts"] = checked
        self._logger.info(json.dumps(metadata, separators=(",", ":")))


def create_event_logger(stream: TextIO, *, name: str = "capstone") -> EventLogger:
    """Create an opt-in logger; never configure the root or close caller streams."""
    return EventLogger(stream, name=name)
