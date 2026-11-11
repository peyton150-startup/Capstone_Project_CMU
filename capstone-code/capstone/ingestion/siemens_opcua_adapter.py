# The read-only Siemens OPC UA collector: subscribes to approved nodes only.
# Responsibility: turn a server's notifications into version 2 lines. It has
# no code path that writes to, calls, browses or transfers files from the
# server, and tests/test_siemens_opcua_adapter.py checks that in this source.
"""Collect approved SINUMERIK values over OPC UA, strictly read-only (S-0).

What the collector may do on the wire, and nothing else:

1. Ask the server for its endpoints, to check it is the approved server.
2. Open one session.
3. Read the server's namespace table, to turn each approved node's
   namespace URI into this session's index.
4. Create one subscription and monitor the approved nodes for data changes.
5. Close the session.

It never writes a value, calls a method, browses the address space, reads a
node that is not on the approved list, or transfers a file. The OPC UA
library can do all of those; this module does not use those calls, and a
test fails if one appears here.

It refuses to start (SiemensOpcUaRefused, nothing collected) when:

- the endpoint is not encrypted, unless it is a loopback address and the
  config says a local test server is allowed;
- the server's application URI is not the approved one;
- an approved node's namespace is not on the server;
- the server will not monitor an approved node.

A dropped connection is not a refusal: the collector writes a gap and a
`disconnected` marker, waits, and connects again under the next session
epoch. No value is carried across that break.

This module needs the `siemens` extra (asyncua). Nothing here has been run
against a SINUMERIK control; the tests use a local mock server.
"""

import argparse
import asyncio
import ipaddress
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from asyncua import Client, ua
from asyncua.common.subscription import Subscription
from asyncua.crypto import security_policies
from pydantic import BaseModel, ConfigDict, Field, model_validator

from capstone.ingestion.siemens_opcua_record import (
    NodeRef,
    OpcUaGap,
    OpcUaLine,
    OpcUaSessionMarker,
    data_change,
    to_json_line,
)

# OPC UA value types this collector stores; any other arrives as None.
STORED_TYPES = frozenset(
    {
        "Boolean",
        "SByte",
        "Byte",
        "Int16",
        "UInt16",
        "Int32",
        "UInt32",
        "Int64",
        "UInt64",
        "Float",
        "Double",
        "String",
    }
)

# Signed-and-encrypted policies only; the names are asyncua's classes.
POLICIES = {
    "Basic256Sha256": security_policies.SecurityPolicyBasic256Sha256,
    "Aes128_Sha256_RsaOaep": security_policies.SecurityPolicyAes128Sha256RsaOaep,
    "Aes256_Sha256_RsaPss": security_policies.SecurityPolicyAes256Sha256RsaPss,
}

IDENTIFIER_TYPES = {
    "String": "string",
    "Numeric": "numeric",
    "TwoByte": "numeric",
    "FourByte": "numeric",
    "Guid": "guid",
    "ByteString": "opaque",
}

# Notification counters wrap from this value back to 1.
SEQUENCE_MAX = 2**32 - 1

# What a broken connection can raise; anything else is a bug and propagates.
CONNECTION_ERRORS = (OSError, asyncio.TimeoutError, ua.UaError, ConnectionError)


class SiemensOpcUaRefused(Exception):
    """The collector will not collect from this server as configured."""


class SecuritySettings(BaseModel):
    """The certificates for a signed and encrypted connection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   policy: The OPC UA security policy; every choice signs and encrypts.
    #   client_certificate, client_private_key: This collector's identity,
    #     issued for it by the shop.
    #   server_certificate: The approved server's certificate; a server
    #     presenting any other is not trusted.
    policy: Literal["Basic256Sha256", "Aes128_Sha256_RsaOaep", "Aes256_Sha256_RsaPss"]
    client_certificate: Path
    client_private_key: Path
    server_certificate: Path


class SiemensOpcUaConfig(BaseModel):
    """Which server, which nodes and how often: the approved scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   endpoint_url: The server's opc.tcp address, given by the shop.
    #   expected_server_uri: The approved server's application URI; the
    #     collector refuses a server that reports a different one.
    #   nodes: The approved nodes. Only these are ever monitored.
    #   publishing_interval_ms: How often the server may send changes. The
    #     server can revise it; this is a request, not a sampling guarantee.
    #   queue_size: How many changes per node the server keeps between sends.
    #   security: Certificates for an encrypted connection; None only for a
    #     local test server.
    #   username_env, password_env: Names of environment variables holding
    #     the read-only account; the values are never in this file or a log.
    #   allow_insecure_loopback: True to allow an unencrypted connection to
    #     this computer itself, for the mock server in tests.
    #   heartbeat_seconds: Write a heartbeat after this long with no value.
    #   watch_seconds: How often the connection is checked.
    #   reconnect_seconds: How long to wait before connecting again.
    #   max_sessions: Stop after this many connections; None means no limit.
    endpoint_url: str
    expected_server_uri: str = Field(min_length=1)
    nodes: tuple[NodeRef, ...] = Field(min_length=1)
    publishing_interval_ms: float = Field(default=1000.0, ge=100.0)
    queue_size: int = Field(default=10, ge=1)
    security: SecuritySettings | None = None
    username_env: str | None = None
    password_env: str | None = None
    allow_insecure_loopback: bool = False
    heartbeat_seconds: float = Field(default=60.0, gt=0)
    watch_seconds: float = Field(default=5.0, gt=0)
    reconnect_seconds: float = Field(default=5.0, ge=0)
    max_sessions: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def scope_is_safe(self):
        """Refuse a config that is not opc.tcp, not encrypted, or repeats a node."""
        # Variables:
        #   parts: The endpoint split into scheme and host.
        #   keys: Each node's identity, to find one listed twice.
        parts = urlsplit(self.endpoint_url)
        if parts.scheme != "opc.tcp" or not parts.hostname:
            raise ValueError("endpoint_url must be an opc.tcp:// address")
        if self.security is None and not (
            self.allow_insecure_loopback and is_loopback(parts.hostname)
        ):
            raise ValueError(
                "an unencrypted connection is only allowed to a loopback "
                "address with allow_insecure_loopback set"
            )
        keys = [node.key for node in self.nodes]
        if len(set(keys)) != len(keys):
            raise ValueError("a node is listed more than once")
        if (self.username_env is None) != (self.password_env is None):
            raise ValueError("username_env and password_env go together")
        return self


def is_loopback(host: str) -> bool:
    """True if the host can only be this computer."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def utc_now() -> datetime:
    """The collector's clock, in UTC."""
    return datetime.now(UTC)


def aware(stamp: datetime | None) -> datetime | None:
    """A server timestamp with its timezone; OPC UA times are UTC by definition."""
    if stamp is None or stamp.tzinfo is not None:
        return stamp
    return stamp.replace(tzinfo=UTC)


def missed_counters(previous: int | None, current: int) -> tuple[int, int] | None:
    """The notification counters skipped between two messages, or None."""
    # Variables:
    #   previous: The counter of the last message that carried values; None
    #     before the first.
    #   current: The counter of this message.
    #   expected: The counter that should follow previous (it wraps to 1).
    #   skipped: How many counters lie between expected and current, going
    #     forwards round the wrap. A huge number means current is behind
    #     previous (a repeated or late message), which is not a loss.
    if previous is None:
        return None
    expected = 1 if previous == SEQUENCE_MAX else previous + 1
    skipped = (current - expected) % SEQUENCE_MAX
    if skipped == 0 or skipped > SEQUENCE_MAX // 2:
        return None
    return (expected, SEQUENCE_MAX if current == 1 else current - 1)


def stored_value(variant) -> tuple[bool | int | float | str | None, str | None]:
    """A delivered value and its type name, or (None, None) if not stored."""
    # Variables:
    #   variant: The OPC UA Variant from the DataValue; None when the server
    #     sent no value.
    #   kind: Its type's name, kept only if this collector stores that type.
    if variant is None or variant.Value is None:
        return None, None
    kind = variant.VariantType.name
    if kind not in STORED_TYPES or isinstance(variant.Value, (list, tuple)):
        return None, None
    return variant.Value, kind


class _Handler:
    """Receives the subscription's callbacks and hands them to the collector."""

    def __init__(self, collector: "SiemensOpcUaCollector") -> None:
        self.collector = collector

    def datachange_notification(self, node, val, data) -> None:
        self.collector.on_value(node.nodeid, data.monitored_item.Value)

    def status_change_notification(self, status) -> None:
        self.collector.on_subscription_status(status)


class _CountingSubscription(Subscription):
    """A subscription that tells the collector each message's counter first."""

    async def publish_callback(self, publish_result) -> None:
        # Variables:
        #   message: One publish message: a counter and its notifications.
        #   has_values: True if it carries data changes. A keep-alive or a
        #     status change does not use up a counter that values would.
        message = publish_result.NotificationMessage
        has_values = any(
            isinstance(item, ua.DataChangeNotification)
            for item in message.NotificationData or []
        )
        self._handler.collector.on_message(
            publish_result.SubscriptionId, message.SequenceNumber, has_values
        )
        await super().publish_callback(publish_result)


class SiemensOpcUaCollector:
    """Monitors the approved nodes and writes version 2 lines to a sink."""

    def __init__(
        self,
        config: SiemensOpcUaConfig,
        sink: Callable[[OpcUaLine], None],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        # Variables:
        #   sink: Called with each line, in order; it stores the line.
        #   clock: The collector's clock; tests pass a fixed one.
        #   epoch: The current connection's number, from 1.
        #   refs: This session's (namespace index, identifier) to approved
        #     node; a notification for anything else is dropped and counted.
        #   subscription_id, last_seq: The subscription and the counter of
        #     its last message that carried data.
        #   last_received_at, last_written_at: When the last value arrived
        #     and when the last line was written (for heartbeats).
        #   lost: Why the subscription was lost, once the server says so.
        #   dropped, unsupported: Counts of notifications for unknown nodes
        #     and of values whose type is not stored.
        self.config = config
        self.sink = sink
        self.clock = clock
        self.epoch = 0
        self.refs: dict[tuple[int, object], NodeRef] = {}
        self.subscription_id: int | None = None
        self.last_seq: int | None = None
        self.last_received_at: datetime | None = None
        self.last_written_at: datetime | None = None
        self.lost: str | None = None
        self.dropped = 0
        self.unsupported = 0

    # --- writing lines ------------------------------------------------------

    def write(self, line: OpcUaLine) -> None:
        """Send one line to the sink and note when."""
        self.sink(line)
        self.last_written_at = self.clock()

    def mark(self, event: str, reason: str | None = None, gap: OpcUaGap | None = None):
        """Write a session marker for the current epoch."""
        self.write(
            OpcUaSessionMarker(
                server_uri=self.config.expected_server_uri,
                event=event,
                at=self.clock(),
                session_epoch=self.epoch,
                reason=reason,
                gap=gap,
            )
        )

    # --- callbacks from the subscription -------------------------------------

    def on_message(self, subscription_id: int, seq: int, has_data: bool) -> None:
        """Note a message's counter; write a gap if counters were skipped."""
        # Variables:
        #   has_data: True only for a message that carries values; a
        #     keep-alive or status change is not counted.
        #   missed: The first and last counters skipped, if any.
        self.subscription_id = subscription_id
        if not has_data:
            return
        missed = missed_counters(self.last_seq, seq)
        if missed:
            self.mark(
                "gap",
                gap=OpcUaGap(
                    cause="notification_missed",
                    subscription_id=subscription_id,
                    lost_from_seq=missed[0],
                    lost_to_seq=missed[1],
                    last_received_at=self.last_received_at,
                ),
            )
        self.last_seq = seq

    def on_value(self, node_id, data_value) -> None:
        """Write one delivered value as a record, with a gap first on overflow."""
        # Variables:
        #   node_id: The session's id for the node the value came from.
        #   data_value: The server's DataValue: value, status, timestamps.
        #   ref: The approved node it maps to; None means it is not ours.
        #   value, kind: The value and type to store, or None for a type
        #     this collector does not store.
        ref = self.refs.get((node_id.NamespaceIndex, node_id.Identifier))
        if ref is None:
            self.dropped += 1
            return
        value, kind = stored_value(data_value.Value)
        if kind is None and data_value.Value is not None:
            if data_value.Value.Value is not None:
                self.unsupported += 1
        status = data_value.StatusCode
        received_at = self.clock()
        record = data_change(
            server_uri=self.config.expected_server_uri,
            node=ref,
            value=value,
            value_type=kind,
            status_code=0 if status is None else status.value,
            status_name=None if status is None else status.name,
            source_timestamp=aware(data_value.SourceTimestamp),
            server_timestamp=aware(data_value.ServerTimestamp),
            received_at=received_at,
            session_epoch=self.epoch,
            subscription_id=self.subscription_id,
            notification_seq=self.last_seq,
        )
        if record.status.overflow:
            self.mark(
                "gap",
                gap=OpcUaGap(
                    cause="queue_overflow",
                    subscription_id=self.subscription_id,
                    node=ref,
                    last_received_at=self.last_received_at,
                ),
            )
        self.write(record)
        self.last_received_at = received_at

    def on_subscription_status(self, status) -> None:
        """Remember that the server ended or changed the subscription."""
        self.lost = f"subscription status {getattr(status, 'Status', status)}"

    # --- one session -----------------------------------------------------------

    async def configure(self, client: Client) -> None:
        """Set the client's encryption and account from the config."""
        # Variables:
        #   security: The certificates; None only for an allowed local server.
        #   user, password: The read-only account, read from the environment
        #     at this moment and passed straight to the client.
        security = self.config.security
        if security is not None:
            await client.set_security(
                POLICIES[security.policy],
                security.client_certificate,
                security.client_private_key,
                server_certificate=str(security.server_certificate),
                mode=ua.MessageSecurityMode.SignAndEncrypt,
            )
        if self.config.username_env:
            user = os.environ.get(self.config.username_env)
            password = os.environ.get(self.config.password_env)
            if not user or not password:
                raise SiemensOpcUaRefused(
                    "the account's environment variables are not set"
                )
            client.set_user(user)
            client.set_password(password)

    async def check_server(self, client: Client) -> None:
        """Refuse a server whose application URI is not the approved one."""
        # Variables:
        #   reported: The application URIs the server's endpoints give.
        endpoints = await client.connect_and_get_server_endpoints()
        reported = {endpoint.Server.ApplicationUri for endpoint in endpoints}
        if self.config.expected_server_uri not in reported:
            raise SiemensOpcUaRefused(
                f"the server reports {sorted(reported)}, not the approved "
                f"{self.config.expected_server_uri!r}"
            )

    async def resolve_nodes(self, client: Client) -> list:
        """The approved nodes as this session's node objects; fills self.refs."""
        # Variables:
        #   namespaces: The server's namespace table; a URI's position is
        #     its index in this session only.
        #   missing: Approved namespace URIs the server does not have.
        #   node_id: One approved node's id in this session.
        namespaces = list(await client.get_namespace_array())
        missing = sorted({n.namespace_uri for n in self.config.nodes} - set(namespaces))
        if missing:
            raise SiemensOpcUaRefused(f"the server has no namespace {missing}")
        self.refs = {}
        nodes = []
        for ref in self.config.nodes:
            node_id = session_node_id(ref, namespaces.index(ref.namespace_uri))
            self.refs[(node_id.NamespaceIndex, node_id.Identifier)] = ref
            nodes.append(client.get_node(node_id))
        return nodes

    async def subscribe(self, client: Client, nodes: list) -> None:
        """Create the subscription and monitor the approved nodes."""
        # Variables:
        #   params: The requested publishing rate and lifetime; the server
        #     may revise them.
        #   handles: Per node, a handle on success or a StatusCode on refusal.
        #   refused: The approved nodes the server would not monitor.
        params = ua.CreateSubscriptionParameters()
        params.RequestedPublishingInterval = self.config.publishing_interval_ms
        params.RequestedLifetimeCount = 10000
        params.RequestedMaxKeepAliveCount = 10
        params.MaxNotificationsPerPublish = 10000
        params.PublishingEnabled = True
        params.Priority = 0
        subscription = _CountingSubscription(client.uaclient, params, _Handler(self))
        await subscription.init()
        handles = await subscription.subscribe_data_change(
            nodes, queuesize=self.config.queue_size
        )
        refused = [
            f"{ref.identifier} ({handle.name})"
            for ref, handle in zip(self.config.nodes, handles, strict=True)
            if isinstance(handle, ua.StatusCode)
        ]
        if refused:
            raise SiemensOpcUaRefused(f"the server will not monitor {refused}")

    async def watch(self, client: Client, stop: asyncio.Event) -> None:
        """Stay connected until asked to stop; raise if the connection is lost."""
        # Variables:
        #   quiet: Seconds since the last line was written; a heartbeat is
        #     written when it passes the configured limit.
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), self.config.watch_seconds)
            except asyncio.TimeoutError:
                pass
            if stop.is_set():
                return
            await client.check_connection()
            if self.lost:
                raise ConnectionError(self.lost)
            quiet = (self.clock() - self.last_written_at).total_seconds()
            if quiet >= self.config.heartbeat_seconds:
                self.mark("heartbeat")

    async def session(self, stop: asyncio.Event) -> None:
        """One connection: check, connect, subscribe, watch, close."""
        # Variables:
        #   client: The OPC UA client for this connection only.
        #   connected: True once the `connected` marker is written, so a
        #     later failure is recorded as a loss of collected time.
        client = Client(self.config.endpoint_url)
        self.subscription_id = None
        self.last_seq = None
        self.lost = None
        connected = False
        await self.configure(client)
        await self.check_server(client)
        await client.connect()
        try:
            nodes = await self.resolve_nodes(client)
            self.mark("connected")
            connected = True
            await self.subscribe(client, nodes)
            await self.watch(client, stop)
        except CONNECTION_ERRORS as error:
            if connected:
                self.mark(
                    "gap",
                    gap=OpcUaGap(
                        cause="session_lost",
                        subscription_id=self.subscription_id,
                        last_received_at=self.last_received_at,
                    ),
                )
                self.mark("disconnected", reason=type(error).__name__)
            raise
        finally:
            try:
                await client.disconnect()
            except CONNECTION_ERRORS:
                pass

    async def run(self, stop: asyncio.Event) -> None:
        """Collect until asked to stop, reconnecting after a lost connection."""
        # Variables:
        #   stop: Set by the caller to end collection cleanly.
        #   reason: Why collection ended, written on the `stopped` marker.
        reason = "stop requested"
        while not stop.is_set():
            self.epoch += 1
            try:
                await self.session(stop)
            except SiemensOpcUaRefused as error:
                self.mark("stopped", reason=f"refused: {error}")
                raise
            except CONNECTION_ERRORS:
                pass
            if stop.is_set():
                break
            if self.config.max_sessions and self.epoch >= self.config.max_sessions:
                reason = "session limit reached"
                break
            try:
                await asyncio.wait_for(stop.wait(), self.config.reconnect_seconds)
            except asyncio.TimeoutError:
                pass
        self.mark("stopped", reason=reason)


def session_node_id(ref: NodeRef, index: int):
    """An approved node's id for this session, from its namespace's index."""
    # Variables:
    #   ref: The approved node, named by namespace URI.
    #   index: That namespace's position in this session's table.
    if ref.identifier_type == "numeric":
        return ua.NodeId(int(ref.identifier), index)
    if ref.identifier_type == "string":
        return ua.NodeId(ref.identifier, index)
    raise SiemensOpcUaRefused(
        f"{ref.identifier_type} node identifiers are not supported yet"
    )


def load_config(path: Path) -> SiemensOpcUaConfig:
    """Read the approved scope from a JSON file."""
    return SiemensOpcUaConfig.model_validate_json(path.read_text(encoding="utf-8"))


def file_sink(path: Path) -> Callable[[OpcUaLine], None]:
    """A sink that appends each line to a JSONL file and flushes it."""

    def write(line: OpcUaLine) -> None:
        with path.open("a", encoding="utf-8") as out:
            out.write(to_json_line(line) + "\n")
            out.flush()

    return write


def main(argv: list[str] | None = None) -> int:
    """Collect from the configured server into a JSONL file until Ctrl+C."""
    # Variables:
    #   args.config: The approved scope (server, nodes, certificates).
    #   args.out: The capture file; lines are appended, never overwritten.
    parser = argparse.ArgumentParser(
        prog="python -m capstone.ingestion.siemens_opcua_adapter"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    collector = SiemensOpcUaCollector(load_config(args.config), file_sink(args.out))

    async def collect() -> None:
        await collector.run(asyncio.Event())

    try:
        asyncio.run(collect())
    except SiemensOpcUaRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        collector.mark("stopped", reason="interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
