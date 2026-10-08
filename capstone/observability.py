"""Opt-in JSON event logging for safe operational metadata.

Callers supply correlation IDs and simulation ticks. Observations, conclusions,
action reasons, exception text and arbitrary extra fields are deliberately absent
from the API. Event names and IDs must be identifiers, never free-form text.
"""

import json
import logging
import re
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
    ) -> None:
        """Emit one event; omitted context stays absent and no clock is inferred.

        Only the listed metadata fields can be logged. Store rich investigation
        records elsewhere, behind their own evidence and secret boundaries.
        """
        metadata: dict[str, str | int | bool] = {
            "event": _safe_identifier(event, "event")
        }
        for field, value in (
            ("run_id", run_id),
            ("investigation_id", investigation_id),
            ("tool", tool),
        ):
            if value is not None:
                metadata[field] = _safe_identifier(value, field)
        if tick is not None:
            if type(tick) is not int or tick < 0:
                raise ValueError("tick must be a nonnegative integer")
            metadata["tick"] = tick
        if success is not None:
            if type(success) is not bool:
                raise ValueError("success must be a boolean")
            metadata["success"] = success
        self._logger.info(json.dumps(metadata, separators=(",", ":")))


def create_event_logger(stream: TextIO, *, name: str = "capstone") -> EventLogger:
    """Create an opt-in logger; never configure the root or close caller streams."""
    return EventLogger(stream, name=name)
