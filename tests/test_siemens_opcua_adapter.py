"""The read-only Siemens OPC UA collector, against a local mock server.

Nothing here contacts a real control. The mock is asyncua's own server on a
loopback port, so these tests show what the collector does with what a
server sends, not that a SINUMERIK sends it.
"""

import ast
import asyncio
import contextlib
import json
import logging
import math
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

pytest.importorskip("asyncua")

from asyncua import Server, ua  # noqa: E402

from capstone.ingestion import siemens_opcua_adapter as adapter  # noqa: E402
from capstone.ingestion.siemens_opcua_adapter import (  # noqa: E402
    SiemensOpcUaCollector,
    SiemensOpcUaConfig,
    SiemensOpcUaRefused,
    file_sink,
    load_config,
    main,
    missed_counters,
)
from capstone.ingestion.siemens_opcua_record import (  # noqa: E402
    NodeRef,
    OpcUaDataChange,
    OpcUaSessionMarker,
    continuous_runs,
    parse_opcua_line,
)

logging.getLogger("asyncua").setLevel(logging.CRITICAL)

SERVER_URI = "urn:test:mock-sinumerik"
NAMESPACE = "urn:test:nc"
SPEED = NodeRef(namespace_uri=NAMESPACE, identifier="/Channel/Spindle/actSpeed")
MODE = NodeRef(namespace_uri=NAMESPACE, identifier="/Bag/State/opMode")
SECRET = NodeRef(namespace_uri=NAMESPACE, identifier="/Plc/Secret")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def config(port: int, nodes=(SPEED, MODE), **over) -> SiemensOpcUaConfig:
    fields = {
        "endpoint_url": f"opc.tcp://127.0.0.1:{port}/mock",
        "expected_server_uri": SERVER_URI,
        "nodes": nodes,
        "publishing_interval_ms": 100,
        "allow_insecure_loopback": True,
        "watch_seconds": 0.1,
        "reconnect_seconds": 0.1,
        "heartbeat_seconds": 60,
    }
    fields.update(over)
    return SiemensOpcUaConfig(**fields)


@contextlib.asynccontextmanager
async def mock_server(port: int, uri: str = SERVER_URI, namespace: str = NAMESPACE):
    """A server with a speed, a mode and a node nobody approved."""
    server = Server()
    await server.init()
    server.set_endpoint(f"opc.tcp://127.0.0.1:{port}/mock")
    await server.set_application_uri(uri)
    index = await server.register_namespace(namespace)
    folder = await server.nodes.objects.add_object(index, "Machine")
    variables = {
        "speed": await folder.add_variable(
            ua.NodeId(SPEED.identifier, index), "speed", 1000.0
        ),
        "mode": await folder.add_variable(
            ua.NodeId(MODE.identifier, index), "mode", "AUTO"
        ),
        "secret": await folder.add_variable(
            ua.NodeId(SECRET.identifier, index), "secret", 42
        ),
    }
    async with server:
        yield variables


async def collect(cfg, during, lines=None):
    """Run a collector while `during(collector)` plays out, then stop it."""
    lines = [] if lines is None else lines
    collector = SiemensOpcUaCollector(cfg, lines.append)
    stop = asyncio.Event()
    task = asyncio.create_task(collector.run(stop))
    try:
        await during(collector)
    finally:
        stop.set()
        await asyncio.wait_for(task, 10)
    return lines, collector


async def until(condition, seconds: float = 20.0) -> None:
    """Wait for a condition, failing the test if it never holds."""
    for _ in range(int(seconds / 0.05)):
        if condition():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the condition never became true")


def values(lines, node=SPEED):
    return [
        line
        for line in lines
        if isinstance(line, OpcUaDataChange) and line.node == node
    ]


def events(lines):
    return [line.event for line in lines if isinstance(line, OpcUaSessionMarker)]


# --- the approved scope -------------------------------------------------------


def test_an_unencrypted_endpoint_is_refused_unless_it_is_local_and_allowed():
    with pytest.raises(ValidationError, match="unencrypted"):
        config(4840, endpoint_url="opc.tcp://192.168.1.20:4840")
    with pytest.raises(ValidationError, match="unencrypted"):
        config(4840, allow_insecure_loopback=False)
    assert config(4840, endpoint_url="opc.tcp://localhost:4840")


def test_a_config_that_is_not_opc_tcp_or_repeats_a_node_is_refused():
    with pytest.raises(ValidationError, match="opc.tcp"):
        config(4840, endpoint_url="http://127.0.0.1:4840")
    with pytest.raises(ValidationError, match="more than once"):
        config(4840, nodes=(SPEED, SPEED))
    with pytest.raises(ValidationError, match="at least 1"):
        config(4840, nodes=())
    with pytest.raises(ValidationError, match="go together"):
        config(4840, username_env="OPCUA_USER")


def test_the_config_has_no_field_for_a_password_or_user_name():
    names = set(SiemensOpcUaConfig.model_fields)
    assert {"username_env", "password_env"} <= names
    assert not names & {"username", "password", "user"}


# --- the read-only boundary ---------------------------------------------------

FORBIDDEN = {
    "write_value",
    "write_values",
    "write_attribute",
    "write_params",
    "write",
    "set_value",
    "set_writable",
    "call_method",
    "call",
    "add_nodes",
    "delete_nodes",
    "add_references",
    "delete_references",
    "browse",
    "browse_nodes",
    "get_children",
    "get_child",
    "get_referenced_nodes",
    "translate_browsepaths",
    "read_raw_history",
    "history_read",
    "import_xml",
    "export_xml",
    "register_nodes",
    "read_value",
    "read_values",
    "read_attribute",
}


def test_the_adapter_source_has_no_write_call_browse_or_direct_read():
    """The library can write and call; this module must never use those."""
    tree = ast.parse(Path(adapter.__file__).read_text(encoding="utf-8"))
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} | {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    # `write` is the collector's own method for the sink and the file handle.
    assert used & (FORBIDDEN - {"write"}) == set()
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "write"
    ]
    owners = {ast.unparse(node.value) for node in writes}
    assert owners <= {"self", "out"}


def test_the_collector_has_no_method_that_changes_the_server():
    public = {name for name in dir(SiemensOpcUaCollector) if not name.startswith("_")}
    assert not public & FORBIDDEN - {"write"}


# --- collecting ---------------------------------------------------------------


def test_values_arrive_typed_with_status_clocks_and_connection():
    async def scenario():
        port = free_port()
        async with mock_server(port) as variables:

            async def during(collector):
                await until(lambda: collector.last_seq is not None)
                await variables["speed"].write_value(1200.5)
                await until(lambda: len(values(lines)) >= 2)

            lines = []
            return await collect(config(port), during, lines)

    lines, _ = asyncio.run(scenario())
    assert events(lines)[0] == "connected" and events(lines)[-1] == "stopped"
    first, second = values(lines)[:2]
    assert (first.value, second.value) == (1000.0, 1200.5)
    assert first.value_type == "Double" and first.status.severity == "good"
    assert first.server_uri == SERVER_URI and first.session_epoch == 1
    assert first.source_timestamp.tzinfo is not None
    assert first.received_at.tzinfo is not None
    assert first.subscription_id is not None
    assert second.notification_seq > first.notification_seq
    mode = values(lines, MODE)[0]
    assert mode.value == "AUTO" and mode.value_type == "String"
    assert mode.number() is None
    # Every line survives the trip to a file and back.
    for line in lines:
        assert parse_opcua_line(line.model_dump_json()) == line


def test_a_node_that_was_not_approved_is_never_collected():
    async def scenario():
        port = free_port()
        async with mock_server(port) as variables:

            async def during(collector):
                await until(lambda: collector.last_seq is not None)
                await variables["secret"].write_value(43)
                await variables["speed"].write_value(1100.0)
                await until(lambda: len(values(lines)) >= 2)

            lines = []
            return await collect(config(port), during, lines)

    lines, collector = asyncio.run(scenario())
    assert values(lines, SECRET) == []
    assert collector.dropped == 0
    assert SECRET.identifier not in json.dumps(
        [json.loads(x.model_dump_json()) for x in lines]
    )


def test_a_bad_value_and_a_nan_are_stored_but_are_never_numbers():
    async def scenario():
        port = free_port()
        async with mock_server(port) as variables:

            async def during(collector):
                await until(lambda: collector.last_seq is not None)
                await variables["speed"].write_value(
                    ua.DataValue(
                        ua.Variant(0.0, ua.VariantType.Double),
                        ua.StatusCode(ua.StatusCodes.BadNoCommunication),
                    )
                )
                await until(lambda: len(values(lines)) >= 2)
                await variables["speed"].write_value(
                    ua.DataValue(ua.Variant(math.nan, ua.VariantType.Double))
                )
                await until(lambda: len(values(lines)) >= 3)

            lines = []
            return await collect(config(port), during, lines)

    lines, _ = asyncio.run(scenario())
    _, bad, nan = values(lines)[:3]
    assert bad.status.severity == "bad" and bad.status.name == "BadNoCommunication"
    assert bad.number() is None and bad.number(allow_uncertain=True) is None
    assert nan.value is None and nan.non_finite == "nan" and nan.number() is None


def test_a_value_type_that_is_not_stored_arrives_as_none_and_is_counted():
    async def scenario():
        port = free_port()
        async with mock_server(port) as variables:

            async def during(collector):
                await until(lambda: collector.last_seq is not None)
                await variables["speed"].write_value(
                    ua.DataValue(ua.Variant([1.0, 2.0], ua.VariantType.Double))
                )
                await until(lambda: collector.unsupported >= 1)

            return await collect(config(port), during)

    lines, collector = asyncio.run(scenario())
    last = values(lines)[-1]
    assert last.value is None and last.value_type is None
    assert collector.unsupported == 1


# --- refusing -----------------------------------------------------------------


def refused(cfg_changes=None, **server):
    """Run against a mock that should be refused; return the error and lines."""

    async def scenario():
        port = free_port()
        lines = []
        async with mock_server(port, **server):
            collector = SiemensOpcUaCollector(
                config(port, **(cfg_changes or {})), lines.append
            )
            with pytest.raises(SiemensOpcUaRefused) as caught:
                await asyncio.wait_for(collector.run(asyncio.Event()), 10)
        return str(caught.value), lines

    return asyncio.run(scenario())


def test_a_server_with_the_wrong_application_uri_is_refused_before_a_session():
    message, lines = refused(uri="urn:test:some-other-server")
    assert "not the approved" in message
    assert events(lines) == ["stopped"]
    assert lines[0].reason.startswith("refused:")
    assert values(lines) == []


def test_a_missing_namespace_is_refused():
    message, lines = refused(namespace="urn:test:renamed")
    assert "no namespace" in message and NAMESPACE in message
    assert events(lines) == ["stopped"] and values(lines) == []


def test_a_node_the_server_will_not_monitor_is_refused_by_name():
    ghost = NodeRef(namespace_uri=NAMESPACE, identifier="/Channel/Nope")
    message, lines = refused({"nodes": (SPEED, ghost)})
    assert "/Channel/Nope" in message and "BadNodeIdUnknown" in message
    assert events(lines) == ["connected", "stopped"]


def test_an_account_whose_environment_variables_are_unset_is_refused(monkeypatch):
    monkeypatch.delenv("TEST_OPCUA_USER", raising=False)
    monkeypatch.delenv("TEST_OPCUA_PASSWORD", raising=False)
    message, lines = refused(
        {"username_env": "TEST_OPCUA_USER", "password_env": "TEST_OPCUA_PASSWORD"}
    )
    assert "environment variables" in message
    assert events(lines) == ["stopped"]


# --- losing the connection ----------------------------------------------------


def test_a_lost_connection_writes_a_gap_and_reconnects_under_a_new_epoch():
    async def scenario():
        port = free_port()
        lines = []
        collector = SiemensOpcUaCollector(config(port), lines.append)
        stop = asyncio.Event()
        async with mock_server(port):
            task = asyncio.create_task(collector.run(stop))
            await until(lambda: len(values(lines)) >= 1)
        await until(lambda: "disconnected" in events(lines), 15)
        async with mock_server(port) as variables:
            await until(lambda: collector.epoch >= 2 and collector.last_seq, 15)
            await variables["speed"].write_value(900.0)
            await until(lambda: values(lines)[-1].value == 900.0)
            stop.set()
            await asyncio.wait_for(task, 10)
        return lines

    lines = asyncio.run(scenario())
    kinds = events(lines)
    lost = kinds.index("gap")
    assert kinds[lost : lost + 2] == ["gap", "disconnected"]
    gap = next(line for line in lines if getattr(line, "gap", None))
    assert gap.gap.cause == "session_lost" and gap.gap.last_received_at is not None
    assert kinds.count("connected") >= 2 and kinds[-1] == "stopped"
    epochs = {record.session_epoch for record in values(lines)}
    assert 1 in epochs and max(epochs) >= 2
    for run in continuous_runs(lines):
        assert len({record.session_epoch for record in run}) == 1


def test_a_server_that_is_not_there_ends_at_the_session_limit(tmp_path):
    cfg = tmp_path / "config.json"
    out = tmp_path / "capture.jsonl"
    cfg.write_text(
        config(free_port(), max_sessions=1).model_dump_json(), encoding="utf-8"
    )
    assert load_config(cfg).max_sessions == 1
    assert main(["--config", str(cfg), "--out", str(out)]) == 0
    written = [parse_opcua_line(text) for text in out.read_text("utf-8").splitlines()]
    assert events(written) == ["stopped"]
    assert written[0].reason == "session limit reached"


# --- counters, overflow and the file ------------------------------------------


def test_missed_counters_names_what_was_skipped_and_wraps():
    assert missed_counters(None, 7) is None
    assert missed_counters(4, 5) is None
    assert missed_counters(4, 8) == (5, 7)
    assert missed_counters(2**32 - 1, 1) is None
    assert missed_counters(2**32 - 1, 3) == (1, 2)
    assert missed_counters(2**32 - 2, 1) == (2**32 - 1, 2**32 - 1)
    # A repeated or late message is behind the last one: not a loss.
    assert missed_counters(5, 5) is None
    assert missed_counters(5, 2) is None


def offline_collector():
    lines = []
    fixed = datetime(2026, 11, 11, 15, 0, 0, tzinfo=UTC)
    collector = SiemensOpcUaCollector(config(4840), lines.append, clock=lambda: fixed)
    collector.epoch = 1
    collector.refs = {(2, SPEED.identifier): SPEED}
    return collector, lines


def test_a_skipped_counter_writes_a_gap_and_a_keep_alive_does_not():
    collector, lines = offline_collector()
    collector.on_message(7, 1, True)
    collector.on_message(7, 2, False)
    collector.on_message(7, 2, True)
    assert lines == []
    collector.on_message(7, 5, True)
    (gap,) = lines
    assert gap.gap.cause == "notification_missed"
    assert (gap.gap.lost_from_seq, gap.gap.lost_to_seq) == (3, 4)


def test_an_overflow_status_writes_a_gap_for_that_node_before_the_value():
    collector, lines = offline_collector()
    collector.on_message(7, 1, True)
    collector.on_value(
        ua.NodeId(SPEED.identifier, 2),
        ua.DataValue(ua.Variant(5.0, ua.VariantType.Double), ua.StatusCode(0x00000480)),
    )
    gap, record = lines
    assert gap.gap.cause == "queue_overflow" and gap.gap.node == SPEED
    assert record.value == 5.0 and record.status.overflow


def test_a_notification_for_an_unknown_node_is_dropped_and_counted():
    collector, lines = offline_collector()
    collector.on_value(
        ua.NodeId("/Somewhere/Else", 2),
        ua.DataValue(ua.Variant(1.0, ua.VariantType.Double)),
    )
    assert lines == [] and collector.dropped == 1


def test_the_file_sink_appends_one_parseable_line_each(tmp_path):
    out = tmp_path / "capture.jsonl"
    sink = file_sink(out)
    collector, lines = offline_collector()
    collector.sink = sink
    collector.mark("connected")
    collector.mark("stopped", reason="test")
    parsed = [parse_opcua_line(text) for text in out.read_text("utf-8").splitlines()]
    assert events(parsed) == ["connected", "stopped"]
