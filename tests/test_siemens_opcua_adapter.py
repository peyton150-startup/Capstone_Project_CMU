"""The read-only Siemens OPC UA collector, against an in-memory fake client.

No server is started. The fake client and subscription below stand in for
asyncua's, so each test runs in milliseconds and can play a server that
rejects the password or the certificates. These tests therefore show what
the collector does with what a client reports, not that a SINUMERIK, or
asyncua on the wire, reports it.
"""

import ast
import asyncio
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

pytest.importorskip("asyncua")

from asyncua import ua  # noqa: E402

from capstone.ingestion import siemens_opcua_adapter as adapter  # noqa: E402
from capstone.ingestion.siemens_opcua_adapter import (  # noqa: E402
    POLICIES,
    SecuritySettings,
    SiemensOpcUaCollector,
    SiemensOpcUaConfig,
    SiemensOpcUaRefused,
    failure_reason,
    file_sink,
    load_config,
    main,
    missed_counters,
    read_audit,
    refusal_for,
)
from capstone.ingestion.siemens_opcua_record import (  # noqa: E402
    NodeRef,
    OpcUaDataChange,
    OpcUaSessionMarker,
    continuous_runs,
    parse_opcua_line,
)

SERVER_URI = "urn:test:mock-sinumerik"
NAMESPACE = "urn:test:nc"
SPEED = NodeRef(namespace_uri=NAMESPACE, identifier="/Channel/Spindle/actSpeed")
MODE = NodeRef(namespace_uri=NAMESPACE, identifier="/Bag/State/opMode")
SECRET = NodeRef(namespace_uri=NAMESPACE, identifier="/Plc/Secret")
STAMP = datetime(2026, 11, 11, 15, 0, 0)  # naive, as asyncua delivers them
USER, PASSWORD = "operator-7", "hunter2-not-a-real-password"


# --- the fake client ----------------------------------------------------------


class FakeServer:
    """What the fake clients talk to: one scriptable server shared by them."""

    def __init__(self, uri=SERVER_URI, namespace=NAMESPACE):
        self.uri = uri
        self.namespaces = ["http://opcfoundation.org/UA/", namespace]
        self.known = {SPEED.identifier, MODE.identifier, SECRET.identifier}
        self.endpoint_errors: list[BaseException] = []
        self.connect_errors: list[BaseException] = []
        self.namespace_error: BaseException | None = None
        self.alive = True
        self.clients: list[FakeClient] = []
        self.subscriptions: list[FakeSubscription] = []


class FakeClient:
    """Records what the collector asks of it; answers from the FakeServer."""

    def __init__(self, server: FakeServer, url: str):
        self.server = server
        self.url = url
        self.security = None
        self.user = None
        self.password = None
        self.opened = False
        self.disconnects = 0
        server.clients.append(self)

    async def set_security(self, policy, cert, key, server_certificate=None, mode=None):
        self.security = SimpleNamespace(
            policy=policy, cert=cert, key=key, server=server_certificate, mode=mode
        )

    def set_user(self, user):
        self.user = user

    def set_password(self, password):
        self.password = password

    async def connect_and_get_server_endpoints(self):
        if self.server.endpoint_errors:
            raise self.server.endpoint_errors.pop(0)
        return [SimpleNamespace(Server=SimpleNamespace(ApplicationUri=self.server.uri))]

    async def connect(self):
        if self.server.connect_errors:
            raise self.server.connect_errors.pop(0)
        self.opened = True

    async def get_namespace_array(self):
        if self.server.namespace_error:
            raise self.server.namespace_error
        return list(self.server.namespaces)

    def get_node(self, node_id):
        return SimpleNamespace(nodeid=node_id)

    async def check_connection(self):
        if not self.server.alive:
            raise ConnectionError("connection closed")

    async def disconnect(self):
        self.disconnects += 1
        self.opened = False


class FakeSubscription:
    """Monitors whatever the server knows; tests push messages through it."""

    def __init__(self, server: FakeServer, params, handler):
        self.server = server
        self.params = params
        self.handler = handler
        self.nodes = []

    async def init(self):
        self.server.subscriptions.append(self)
        self.id = len(self.server.subscriptions)

    async def subscribe_data_change(self, nodes, queuesize):
        self.nodes = nodes
        return [
            index
            if node.nodeid.Identifier in self.server.known
            else ua.StatusCode(ua.StatusCodes.BadNodeIdUnknown)
            for index, node in enumerate(nodes, 1)
        ]

    def publish(self, seq, *changes):
        """Deliver one message: its counter, then each (node, DataValue)."""
        collector = self.handler.collector
        collector.on_message(self.id, seq, bool(changes))
        for ref, data_value in changes:
            node = SimpleNamespace(nodeid=ua.NodeId(ref.identifier, 1))
            item = SimpleNamespace(monitored_item=SimpleNamespace(Value=data_value))
            self.handler.datachange_notification(node, None, item)


def double(value, status=0):
    return ua.DataValue(
        ua.Variant(value, ua.VariantType.Double),
        ua.StatusCode(status),
        SourceTimestamp=STAMP,
        ServerTimestamp=STAMP,
    )


def config(port: int = 4840, nodes=(SPEED, MODE), **over) -> SiemensOpcUaConfig:
    fields = {
        "endpoint_url": f"opc.tcp://127.0.0.1:{port}/mock",
        "expected_server_uri": SERVER_URI,
        "nodes": nodes,
        "publishing_interval_ms": 100,
        "allow_insecure_loopback": True,
        "watch_seconds": 0.01,
        "reconnect_seconds": 0,
        "heartbeat_seconds": 60,
    }
    fields.update(over)
    return SiemensOpcUaConfig(**fields)


def collector_for(server, cfg, lines, audit=None):
    return SiemensOpcUaCollector(
        cfg,
        lines.append,
        audit=None if audit is None else audit.append,
        client_factory=lambda url: FakeClient(server, url),
        subscription_factory=lambda client, params, handler: FakeSubscription(
            server, params, handler
        ),
    )


async def until(condition, seconds: float = 5.0) -> None:
    """Wait for a condition, failing the test if it never holds."""
    for _ in range(int(seconds / 0.005)):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the condition never became true")


async def nothing(server) -> None:
    """A scenario where the server sends nothing."""


def collect(during=nothing, server=None, cfg=None):
    """Run a collector while `during(server)` plays out, then stop it."""
    server = server or FakeServer()
    lines, audit = [], []
    collector = collector_for(server, cfg or config(), lines, audit)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(collector.run(stop))
        try:
            await until(lambda: server.subscriptions)
            await during(server)
        finally:
            stop.set()
            await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    return lines, audit, collector


def refused(server=None, cfg=None):
    """Run a collector that should refuse; return the error, lines and trail."""
    server = server or FakeServer()
    lines, audit = [], []
    collector = collector_for(server, cfg or config(), lines, audit)
    with pytest.raises(SiemensOpcUaRefused) as caught:
        asyncio.run(asyncio.wait_for(collector.run(asyncio.Event()), 5))
    return str(caught.value), lines, audit


def values(lines, node=SPEED):
    return [
        line
        for line in lines
        if isinstance(line, OpcUaDataChange) and line.node == node
    ]


def events(lines):
    return [line.event for line in lines if isinstance(line, OpcUaSessionMarker)]


def outcomes(audit):
    return [entry.outcome for entry in audit]


def dumped(*groups) -> str:
    return "\n".join(item.model_dump_json() for group in groups for item in group)


# --- the approved scope -------------------------------------------------------


def test_an_unencrypted_endpoint_is_refused_unless_it_is_local_and_allowed():
    with pytest.raises(ValidationError, match="unencrypted"):
        config(endpoint_url="opc.tcp://192.168.1.20:4840")
    with pytest.raises(ValidationError, match="unencrypted"):
        config(allow_insecure_loopback=False)
    assert config(endpoint_url="opc.tcp://localhost:4840")


def test_a_config_that_is_not_opc_tcp_or_repeats_a_node_is_refused():
    with pytest.raises(ValidationError, match="opc.tcp"):
        config(endpoint_url="http://127.0.0.1:4840")
    with pytest.raises(ValidationError, match="more than once"):
        config(nodes=(SPEED, SPEED))
    with pytest.raises(ValidationError, match="at least 1"):
        config(nodes=())
    with pytest.raises(ValidationError, match="go together"):
        config(username_env="OPCUA_USER")


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
    async def during(server):
        sub = server.subscriptions[0]
        sub.publish(1, (SPEED, double(1000.0)))
        sub.publish(
            2, (SPEED, double(1200.5)), (MODE, ua.DataValue(ua.Variant("AUTO")))
        )

    lines, audit, _ = collect(during)
    assert events(lines)[0] == "connected" and events(lines)[-1] == "stopped"
    first, second = values(lines)
    assert (first.value, second.value) == (1000.0, 1200.5)
    assert first.value_type == "Double" and first.status.severity == "good"
    assert first.server_uri == SERVER_URI and first.session_epoch == 1
    assert first.source_timestamp.tzinfo is not None
    assert first.received_at.tzinfo is not None
    assert first.subscription_id == 1
    assert (first.notification_seq, second.notification_seq) == (1, 2)
    mode = values(lines, MODE)[0]
    assert mode.value == "AUTO" and mode.value_type == "String"
    assert mode.number() is None
    # Every line survives the trip to a file and back.
    for line in lines:
        assert parse_opcua_line(line.model_dump_json()) == line
    assert outcomes(audit) == ["connected", "closed", "stopped"]
    assert audit[0].stage == "resolve_nodes" and audit[-1].stage is None


def test_only_the_approved_nodes_are_handed_to_the_subscription():
    server = FakeServer()
    collect(server=server)
    monitored = {node.nodeid.Identifier for node in server.subscriptions[0].nodes}
    assert monitored == {SPEED.identifier, MODE.identifier}


def test_a_value_for_a_node_that_was_not_approved_is_never_written():
    async def during(server):
        server.subscriptions[0].publish(
            1, (SECRET, double(43.0)), (SPEED, double(1100.0))
        )

    lines, _, collector = collect(during)
    assert values(lines, SECRET) == [] and len(values(lines)) == 1
    assert collector.dropped == 1
    assert SECRET.identifier not in dumped(lines)


def test_a_bad_value_and_a_nan_are_stored_but_are_never_numbers():
    async def during(server):
        sub = server.subscriptions[0]
        sub.publish(1, (SPEED, double(0.0, ua.StatusCodes.BadNoCommunication)))
        sub.publish(2, (SPEED, double(math.nan)))

    lines, _, _ = collect(during)
    bad, nan = values(lines)
    assert bad.status.severity == "bad" and bad.status.name == "BadNoCommunication"
    assert bad.number() is None and bad.number(allow_uncertain=True) is None
    assert nan.value is None and nan.non_finite == "nan" and nan.number() is None


def test_a_value_type_that_is_not_stored_arrives_as_none_and_is_counted():
    async def during(server):
        array = ua.DataValue(ua.Variant([1.0, 2.0], ua.VariantType.Double))
        server.subscriptions[0].publish(1, (SPEED, array))

    lines, _, collector = collect(during)
    (last,) = values(lines)
    assert last.value is None and last.value_type is None
    assert collector.unsupported == 1


# --- refusing the server or its scope -----------------------------------------


def test_a_server_with_the_wrong_application_uri_is_refused_before_a_session():
    server = FakeServer(uri="urn:test:some-other-server")
    message, lines, audit = refused(server)
    assert "not the approved" in message
    assert events(lines) == ["stopped"] and lines[0].reason.startswith("refused:")
    assert values(lines) == [] and not server.clients[0].opened
    assert outcomes(audit) == ["refused", "stopped"]
    assert audit[0].stage == "check_server"


def test_a_missing_namespace_is_refused():
    message, lines, audit = refused(FakeServer(namespace="urn:test:renamed"))
    assert "no namespace" in message and NAMESPACE in message
    assert events(lines) == ["stopped"] and values(lines) == []
    assert audit[0].stage == "resolve_nodes"


def test_a_node_the_server_will_not_monitor_is_refused_by_name():
    ghost = NodeRef(namespace_uri=NAMESPACE, identifier="/Channel/Nope")
    server = FakeServer()
    message, lines, audit = refused(server, config(nodes=(SPEED, ghost)))
    assert "/Channel/Nope" in message and "BadNodeIdUnknown" in message
    assert events(lines) == ["connected", "stopped"]
    assert outcomes(audit) == ["connected", "refused", "stopped"]
    assert server.clients[0].disconnects == 1


# --- the login ----------------------------------------------------------------

ACCOUNT = {"username_env": "TEST_OPCUA_USER", "password_env": "TEST_OPCUA_PASSWORD"}


@pytest.fixture
def account(monkeypatch):
    monkeypatch.setenv("TEST_OPCUA_USER", USER)
    monkeypatch.setenv("TEST_OPCUA_PASSWORD", PASSWORD)


def test_the_account_is_read_from_the_environment_and_given_to_the_client(account):
    server = FakeServer()
    lines, audit, _ = collect(server=server, cfg=config(**ACCOUNT))
    client = server.clients[0]
    assert (client.user, client.password) == (USER, PASSWORD)
    assert events(lines)[0] == "connected"
    assert {entry.login for entry in audit} == {"account"}
    assert USER not in dumped(lines, audit) and PASSWORD not in dumped(lines, audit)


def test_an_account_whose_environment_variables_are_unset_is_refused(monkeypatch):
    monkeypatch.delenv("TEST_OPCUA_USER", raising=False)
    monkeypatch.delenv("TEST_OPCUA_PASSWORD", raising=False)
    server = FakeServer()
    message, lines, audit = refused(server, config(**ACCOUNT))
    assert "environment variables" in message
    assert events(lines) == ["stopped"]
    assert audit[0].stage == "configure" and server.clients[0].user is None


def test_a_wrong_password_stops_after_one_attempt_and_says_why(account):
    server = FakeServer()
    server.connect_errors = [ua.UaStatusCodeError(ua.StatusCodes.BadUserAccessDenied)]
    message, lines, audit = refused(server, config(**ACCOUNT))
    assert message == "the server rejected the login (BadUserAccessDenied)"
    assert len(server.clients) == 1  # no retry that could lock the account
    assert events(lines) == ["stopped"]
    assert lines[0].reason == f"refused: {message}"
    assert outcomes(audit) == ["refused", "stopped"]
    assert audit[0].stage == "connect" and "BadUserAccessDenied" in audit[0].reason
    assert USER not in dumped(lines, audit) and PASSWORD not in dumped(lines, audit)


def test_a_rejected_identity_token_also_stops():
    for name in ("BadIdentityTokenInvalid", "BadIdentityTokenRejected"):
        error = ua.UaStatusCodeError(getattr(ua.StatusCodes, name))
        assert str(refusal_for(error)) == f"the server rejected the login ({name})"


def test_a_secret_echoed_in_an_error_is_blanked_in_the_audit_trail(account):
    server = FakeServer()
    server.connect_errors = [ConnectionError(f"bad login {USER}:{PASSWORD}")]
    lines, audit = [], []
    collector = collector_for(server, config(max_sessions=1, **ACCOUNT), lines, audit)
    asyncio.run(collector.run(asyncio.Event()))
    assert audit[0].outcome == "failed"
    assert "[REDACTED]" in audit[0].reason
    assert USER not in dumped(audit) and PASSWORD not in dumped(audit)


# --- encryption ---------------------------------------------------------------


@pytest.fixture
def certificates(tmp_path):
    """Three placeholder files where the shop's certificates would be."""
    files = {}
    for name in ("client.der", "client.pem", "server.der"):
        files[name] = tmp_path / name
        files[name].write_bytes(b"placeholder")
    return SecuritySettings(
        policy="Basic256Sha256",
        client_certificate=files["client.der"],
        client_private_key=files["client.pem"],
        server_certificate=files["server.der"],
    )


def encrypted(certificates, port: int = 4840) -> SiemensOpcUaConfig:
    return config(port, security=certificates, allow_insecure_loopback=False)


def test_an_encrypted_connection_gives_the_client_the_policy_and_certificates(
    certificates,
):
    server = FakeServer()
    lines, audit, _ = collect(server=server, cfg=encrypted(certificates))
    given = server.clients[0].security
    assert given.policy is POLICIES["Basic256Sha256"]
    assert given.mode == ua.MessageSecurityMode.SignAndEncrypt
    assert given.cert == str(certificates.client_certificate)
    assert given.key == str(certificates.client_private_key)
    assert given.server == str(certificates.server_certificate)
    assert events(lines)[0] == "connected"
    assert {entry.security_policy for entry in audit} == {"Basic256Sha256"}
    assert "placeholder" not in dumped(lines, audit)


def test_a_missing_certificate_file_is_refused_before_the_client_sees_it(
    certificates,
):
    certificates.server_certificate.unlink()
    server = FakeServer()
    message, lines, audit = refused(server, encrypted(certificates))
    assert message == "the server certificate file server.der is missing"
    assert server.clients[0].security is None
    assert events(lines) == ["stopped"]
    assert outcomes(audit) == ["refused", "stopped"]
    assert audit[0].stage == "configure"


def test_a_certificate_that_cannot_be_loaded_is_refused(certificates):
    class BrokenClient(FakeClient):
        async def set_security(self, *args, **kwargs):
            raise ValueError("Could not deserialize key data")

    server = FakeServer()
    collector = collector_for(server, encrypted(certificates), [], [])
    collector.client_factory = lambda url: BrokenClient(server, url)
    with pytest.raises(
        SiemensOpcUaRefused, match=r"could not be loaded \(ValueError\)"
    ):
        asyncio.run(collector.run(asyncio.Event()))


def test_a_certificate_the_server_rejects_stops_collection(certificates):
    server = FakeServer()
    server.connect_errors = [
        ua.UaStatusCodeError(ua.StatusCodes.BadCertificateUntrusted)
    ]
    message, _, audit = refused(server, encrypted(certificates))
    assert "certificates" in message and "BadCertificateUntrusted" in message
    assert len(server.clients) == 1
    assert audit[0].outcome == "refused" and audit[0].stage == "connect"


def test_every_refusal_code_exists_in_asyncua_and_refuses():
    for name in adapter.LOGIN_REFUSALS | adapter.SECURITY_REFUSALS:
        code = getattr(ua.StatusCodes, name)
        assert refusal_for(ua.UaStatusCodeError(code)) is not None


# --- failing, losing and reconnecting -----------------------------------------


def test_a_failed_attempt_is_recorded_with_its_reason_and_retried():
    server = FakeServer()
    server.endpoint_errors = [ConnectionRefusedError(10061, "connection refused")]
    server.connect_errors = [ua.UaStatusCodeError(ua.StatusCodes.BadTooManySessions)]

    async def during(server):
        server.subscriptions[0].publish(1, (SPEED, double(5.0)))

    lines, audit, _ = collect(during, server)
    assert outcomes(audit)[:3] == ["failed", "failed", "connected"]
    assert audit[0].stage == "check_server"
    assert audit[0].reason == "ConnectionRefusedError: connection refused"
    assert audit[1].stage == "connect" and audit[1].reason == "BadTooManySessions"
    # A failed attempt never connected, so it leaves no gap in the capture.
    assert events(lines) == ["connected", "stopped"]
    assert values(lines)[0].session_epoch == 3


def test_a_lost_connection_writes_a_gap_and_reconnects_under_a_new_epoch():
    async def during(server):
        server.subscriptions[0].publish(1, (SPEED, double(1000.0)))
        server.alive = False
        await until(lambda: len(server.clients) >= 2)
        server.alive = True
        await until(lambda: len(server.subscriptions) >= 2)
        server.subscriptions[1].publish(1, (SPEED, double(900.0)))

    lines, audit, _ = collect(during)
    kinds = events(lines)
    lost = kinds.index("gap")
    assert kinds[lost : lost + 2] == ["gap", "disconnected"]
    gap = next(line for line in lines if getattr(line, "gap", None))
    assert gap.gap.cause == "session_lost" and gap.gap.last_received_at is not None
    disconnected = next(
        line for line in lines if getattr(line, "event", None) == "disconnected"
    )
    assert disconnected.reason == "ConnectionError: connection closed"
    assert kinds.count("connected") == 2 and kinds[-1] == "stopped"
    assert [record.session_epoch for record in values(lines)] == [1, 2]
    for run in continuous_runs(lines):
        assert len({record.session_epoch for record in run}) == 1
    lost_entry = next(entry for entry in audit if entry.outcome == "lost")
    assert lost_entry.stage == "watch" and "connection closed" in lost_entry.reason


def test_a_bug_in_the_collector_stops_it_and_is_recorded():
    server = FakeServer()
    server.namespace_error = RuntimeError("boom")
    lines, audit = [], []
    collector = collector_for(server, config(), lines, audit)
    with pytest.raises(RuntimeError):
        asyncio.run(collector.run(asyncio.Event()))
    assert lines[-1].reason == "error: RuntimeError"
    assert outcomes(audit) == ["error", "stopped"]
    assert server.clients[0].disconnects == 1


def test_failure_reasons_name_the_cause_without_the_text_of_unknown_errors():
    assert failure_reason(asyncio.TimeoutError()) == "TimeoutError"
    assert failure_reason(OSError(5, "Access is denied")) == "OSError: Access is denied"
    assert failure_reason(RuntimeError("anything")) == "RuntimeError"
    status = ua.UaStatusCodeError(ua.StatusCodes.BadServerHalted)
    assert failure_reason(status) == "BadServerHalted"
    assert refusal_for(status) is None


# --- the command line (the real asyncua client, but no server) ----------------


def test_main_with_no_server_records_the_failure_and_stops_at_the_limit(tmp_path):
    cfg = tmp_path / "config.json"
    out = tmp_path / "capture.jsonl"
    # Nothing listens on loopback port 9, so the connection is refused.
    cfg.write_text(config(9, max_sessions=1).model_dump_json(), encoding="utf-8")
    assert load_config(cfg).max_sessions == 1
    assert main(["--config", str(cfg), "--out", str(out)]) == 0
    written = [parse_opcua_line(text) for text in out.read_text("utf-8").splitlines()]
    assert events(written) == ["stopped"]
    assert written[0].reason == "session limit reached"
    trail = read_audit(tmp_path / "capture.audit.jsonl")
    assert outcomes(trail) == ["failed", "stopped"]
    assert trail[0].stage == "check_server" and trail[0].reason


def test_main_exits_2_on_a_missing_certificate_and_writes_the_trail(
    tmp_path, certificates
):
    certificates.client_private_key.unlink()
    cfg = tmp_path / "config.json"
    out = tmp_path / "capture.jsonl"
    audit = tmp_path / "audit" / "trail.jsonl"
    audit.parent.mkdir()
    cfg.write_text(encrypted(certificates, 9).model_dump_json(), encoding="utf-8")
    code = main(["--config", str(cfg), "--out", str(out), "--audit", str(audit)])
    assert code == 2
    written = [parse_opcua_line(text) for text in out.read_text("utf-8").splitlines()]
    assert written[0].reason == (
        "refused: the client private key file client.pem is missing"
    )
    assert outcomes(read_audit(audit)) == ["refused", "stopped"]


def test_main_exits_2_on_a_config_it_cannot_read(tmp_path, capsys):
    out = tmp_path / "capture.jsonl"
    assert main(["--config", str(tmp_path / "nope.json"), "--out", str(out)]) == 2
    assert "config:" in capsys.readouterr().err
    assert not out.exists()


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
    collector = SiemensOpcUaCollector(config(), lines.append, clock=lambda: fixed)
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


def test_the_real_subscription_counts_only_messages_that_carry_values():
    """asyncua's own Subscription class, fed messages directly: no server."""

    async def scenario():
        collector, _ = offline_collector()
        quiet = SimpleNamespace(on_notification=lambda *args: None)
        subscription = adapter._CountingSubscription(
            SimpleNamespace(observer=quiet),
            ua.CreateSubscriptionParameters(),
            adapter._Handler(collector),
        )
        status = ua.StatusChangeNotification(
            Status=ua.StatusCode(ua.StatusCodes.BadTimeout)
        )
        for seq, data in ((4, [status]), (5, [ua.DataChangeNotification()])):
            await subscription.publish_callback(
                ua.PublishResult(
                    SubscriptionId=3,
                    NotificationMessage=ua.NotificationMessage(
                        SequenceNumber=seq, NotificationData=data
                    ),
                )
            )
            await asyncio.sleep(0)
        return collector

    collector = asyncio.run(scenario())
    assert collector.subscription_id == 3
    assert collector.last_seq == 5  # the status change at 4 was not counted
    assert collector.lost and "BadTimeout" in collector.lost


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
    assert json.loads(out.read_text("utf-8").splitlines()[0])["event"] == "connected"
