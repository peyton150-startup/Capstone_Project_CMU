"""Metadata logging stays opt-in and never serializes investigation payloads."""

import importlib
import json
import logging
from io import StringIO

import pytest
from pydantic import SecretStr

from capstone.observability import create_event_logger


def test_event_context_is_json_with_explicit_simulator_tick():
    stream = StringIO()
    logger = create_event_logger(stream)
    logger.log_event(
        "tool.completed",
        run_id="run-1",
        investigation_id="investigation-2",
        tick=42,
        tool="get_readings",
        success=True,
    )
    assert json.loads(stream.getvalue()) == {
        "event": "tool.completed",
        "run_id": "run-1",
        "investigation_id": "investigation-2",
        "tick": 42,
        "tool": "get_readings",
        "success": True,
    }


def test_missing_context_is_omitted_and_no_wall_clock_is_added():
    stream = StringIO()
    create_event_logger(stream).log_event("run.started")
    assert json.loads(stream.getvalue()) == {"event": "run.started"}


def test_secret_values_are_masked():
    stream = StringIO()
    create_event_logger(stream).log_event("run.started", run_id=SecretStr("password"))
    assert json.loads(stream.getvalue())["run_id"] == "[REDACTED]"
    assert "password" not in stream.getvalue()


@pytest.mark.parametrize("extra", ["password", "api_key", "reason", "result", "error"])
def test_unapproved_fields_are_rejected_without_logging_values(extra):
    stream = StringIO()
    with pytest.raises(TypeError) as caught:
        create_event_logger(stream).log_event("tool.failed", **{extra: "private-value"})
    assert "private-value" not in str(caught.value)
    assert stream.getvalue() == ""


@pytest.mark.parametrize(
    "value",
    [
        "postgresql://user:private-value@host/db",
        "password=private-value",
        "two\nlines",
        {},
    ],
)
def test_metadata_cannot_hold_raw_payloads_or_credentials(value):
    stream = StringIO()
    with pytest.raises(ValueError) as caught:
        create_event_logger(stream).log_event("tool.failed", tool=value)
    assert "private-value" not in str(caught.value)
    assert stream.getvalue() == ""


@pytest.mark.parametrize("tick", [-1, True, 1.5, "private-value"])
def test_invalid_ticks_are_rejected_without_emission(tick):
    stream = StringIO()
    with pytest.raises(ValueError):
        create_event_logger(stream).log_event("run.started", tick=tick)
    assert stream.getvalue() == ""


def test_success_requires_a_boolean():
    with pytest.raises(ValueError):
        create_event_logger(StringIO()).log_event("tool.completed", success="yes")


def test_import_and_creation_do_not_change_global_logging():
    root = logging.getLogger()
    before_handlers = list(root.handlers)
    before_level = root.level
    before_registry = dict(logging.Logger.manager.loggerDict)
    import capstone.observability as observability

    importlib.reload(observability)
    create_event_logger(StringIO())
    assert root.handlers == before_handlers
    assert root.level == before_level
    assert logging.Logger.manager.loggerDict == before_registry


def test_same_name_instances_are_isolated_and_calls_emit_once():
    first, second = StringIO(), StringIO()
    one = create_event_logger(first)
    two = create_event_logger(second)
    one.log_event("first.event")
    one.log_event("next.event")
    two.log_event("second.event")
    assert [json.loads(line)["event"] for line in first.getvalue().splitlines()] == [
        "first.event",
        "next.event",
    ]
    assert [json.loads(line)["event"] for line in second.getvalue().splitlines()] == [
        "second.event"
    ]
