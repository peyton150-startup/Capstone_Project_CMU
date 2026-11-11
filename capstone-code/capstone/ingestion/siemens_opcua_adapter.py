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

It refuses to start, or stops (SiemensOpcUaRefused, nothing more collected),
when:

- the endpoint is not encrypted, unless it is a loopback address and the
  config says a local test server is allowed;
- a certificate file is missing or cannot be loaded;
- the account's environment variables are not set;
- the server rejects the login (wrong user name or password) or the
  certificates (untrusted, expired, wrong policy). Trying again cannot fix
  these, and retrying a wrong password can lock the account;
- the server's application URI is not the approved one;
- an approved node's namespace is not on the server;
- the server will not monitor an approved node.

A dropped connection is not a refusal: the collector writes a gap and a
`disconnected` marker, waits, and connects again under the next session
epoch. No value is carried across that break.

Every connection attempt also goes to an audit trail
(`SiemensOpcUaAuditEntry`): when, which epoch, how far it got, how it ended
and why. The trail never holds the user name, the password or a
certificate's contents.

This module needs the `siemens` extra (asyncua). Nothing here has been run
against a SINUMERIK control; the tests use a fake client.
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
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

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

# Server answers that mean the account was rejected. Retrying cannot fix
# them, and repeated wrong passwords can lock the account, so they stop
# collection.
LOGIN_REFUSALS = frozenset(
    {
        "BadUserAccessDenied",
        "BadIdentityTokenInvalid",
        "BadIdentityTokenRejected",
        "BadUserSignatureInvalid",
    }
)

# Server answers that mean the certificates or security settings were
# rejected. These also stop collection: a person has to fix them.
SECURITY_REFUSALS = frozenset(
    {
        "BadApplicationSignatureInvalid",
        "BadCertificateChainIncomplete",
        "BadCertificateHostNameInvalid",
        "BadCertificateInvalid",
        "BadCertificateIssuerRevocationUnknown",
        "BadCertificateIssuerRevoked",
        "BadCertificateIssuerTimeInvalid",
        "BadCertificateIssuerUseNotAllowed",
        "BadCertificatePolicyCheckFailed",
        "BadCertificateRevocationUnknown",
        "BadCertificateRevoked",
        "BadCertificateTimeInvalid",
        "BadCertificateUntrusted",
        "BadCertificateUriInvalid",
        "BadCertificateUseNotAllowed",
        "BadNoValidCertificates",
        "BadNonceInvalid",
        "BadSecurityChecksFailed",
        "BadSecurityModeInsufficient",
        "BadSecurityModeRejected",
        "BadSecurityPolicyRejected",
    }
)

# How far a connection attempt got, for the audit trail.
Stage = Literal[
    "configure", "check_server", "connect", "resolve_nodes", "subscribe", "watch"
]

# How an attempt, or the whole collection, ended, for the audit trail.
Outcome = Literal[
    "connected", "closed", "lost", "failed", "refused", "error", "stopped"
]


class SiemensOpcUaRefused(Exception):
    """The collector will not collect from this server as configured."""


class SiemensOpcUaAuditEntry(BaseModel):
    """One entry in the collector's audit trail: an attempt and how it ended."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Variables:
    #   at: When this happened, by the collector's clock.
    #   session_epoch: The connection attempt's number (0 before the first).
    #   endpoint: The server's host and port only, never a user name.
    #   server_uri: The approved server's application URI.
    #   security_policy: The encryption policy, or "none" for a local test.
    #   login: "account" if a user name and password were configured, else
    #     "anonymous". Never the user name or password themselves.
    #   stage: How far the attempt got before it ended; None on the final
    #     `stopped` entry.
    #   outcome: connected (session open), closed (ended on request), lost
    #     (dropped after connecting; will retry), failed (could not connect;
    #     will retry), refused (will not retry), error (a bug in the
    #     collector), stopped (collection ended).
    #   reason: Why, in words or as the server's status name. Holds no secret.
    record_type: Literal["siemens_opcua_audit"] = "siemens_opcua_audit"
    at: AwareDatetime
    session_epoch: int = Field(ge=0)
    endpoint: str
    server_uri: str
    security_policy: str
    login: Literal["account", "anonymous"]
    stage: Stage | None = None
    outcome: Outcome
    reason: str | None = None


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
    #     this computer itself, for a local test server.
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


def status_name(code: int) -> str:
    """The OPC UA name of a status code, such as BadUserAccessDenied."""
    return ua.StatusCode(code).name


def refusal_for(error: BaseException) -> SiemensOpcUaRefused | None:
    """A refusal if the server rejected the login or certificates, else None."""
    # Variables:
    #   name: The status the server answered with, by name; it decides
    #     whether this is a refusal (stop) or a failure (retry).
    if not isinstance(error, ua.UaStatusCodeError):
        return None
    name = status_name(error.code)
    if name in LOGIN_REFUSALS:
        return SiemensOpcUaRefused(f"the server rejected the login ({name})")
    if name in SECURITY_REFUSALS:
        return SiemensOpcUaRefused(
            f"the server rejected the certificates or security settings ({name})"
        )
    return None


def failure_reason(error: BaseException) -> str:
    """Why a connection attempt failed, in words that hold no secret."""
    # Variables:
    #   kind: The exception's class name, the fallback when nothing more
    #     specific and safe is known.
    kind = type(error).__name__
    if isinstance(error, ua.UaStatusCodeError):
        return status_name(error.code)
    if isinstance(error, SiemensOpcUaRefused):
        return str(error)
    if isinstance(error, OSError) and error.strerror:
        return f"{kind}: {error.strerror}"
    if isinstance(error, ConnectionError) and error.args:
        return f"{kind}: {error.args[0]}"
    return kind


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


def counting_subscription(client: Client, params, handler) -> Subscription:
    """The real subscription, which reports each message's counter first."""
    return _CountingSubscription(client.uaclient, params, handler)


class SiemensOpcUaCollector:
    """Monitors the approved nodes and writes version 2 lines to a sink."""

    def __init__(
        self,
        config: SiemensOpcUaConfig,
        sink: Callable[[OpcUaLine], None],
        clock: Callable[[], datetime] = utc_now,
        audit: Callable[[SiemensOpcUaAuditEntry], None] | None = None,
        client_factory: Callable[[str], Client] = Client,
        subscription_factory: Callable[..., Subscription] = counting_subscription,
    ) -> None:
        # Variables:
        #   sink: Called with each line, in order; it stores the line.
        #   clock: The collector's clock; tests pass a fixed one.
        #   audit: Called with each audit entry; None keeps no trail.
        #   client_factory: Makes the OPC UA client for one connection; tests
        #     pass a fake so no server is needed.
        #   subscription_factory: Makes the subscription on a client; tests
        #     pass a fake.
        #   epoch: The current connection's number, from 1.
        #   stage: How far the current attempt has got, for the audit trail.
        #   connected: True once the current session wrote `connected`.
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
        self.audit = audit
        self.client_factory = client_factory
        self.subscription_factory = subscription_factory
        self.epoch = 0
        self.stage: Stage | None = None
        self.connected = False
        self.refs: dict[tuple[int, object], NodeRef] = {}
        self.subscription_id: int | None = None
        self.last_seq: int | None = None
        self.last_received_at: datetime | None = None
        self.last_written_at: datetime | None = None
        self.lost: str | None = None
        self.dropped = 0
        self.unsupported = 0

    # --- writing lines and the audit trail -------------------------------------

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

    def trail(self, outcome: Outcome, reason: str | None = None) -> None:
        """Add one entry to the audit trail, with any secret blanked out."""
        # Variables:
        #   secrets: The account's current values, if set, removed from the
        #     reason in case a library ever echoes them.
        #   parts: The endpoint split up, so only host and port are kept.
        if self.audit is None:
            return
        secrets = [
            os.environ.get(name) or ""
            for name in (self.config.username_env, self.config.password_env)
            if name
        ]
        for secret in secrets:
            if reason and secret:
                reason = reason.replace(secret, "[REDACTED]")
        parts = urlsplit(self.config.endpoint_url)
        security = self.config.security
        self.audit(
            SiemensOpcUaAuditEntry(
                at=self.clock(),
                session_epoch=self.epoch,
                endpoint=f"{parts.hostname}:{parts.port or 4840}",
                server_uri=self.config.expected_server_uri,
                security_policy="none" if security is None else security.policy,
                login="account" if self.config.username_env else "anonymous",
                stage=None if outcome == "stopped" else self.stage,
                outcome=outcome,
                reason=reason,
            )
        )

    def stopped(self, reason: str) -> None:
        """Write the final `stopped` marker and its audit entry."""
        self.mark("stopped", reason=reason)
        self.trail("stopped", reason)

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
        # Variables:
        #   code: The status the server gave, named (such as BadTimeout) so
        #     the `disconnected` marker and audit trail can say why.
        code = getattr(status, "Status", None)
        name = code.name if isinstance(code, ua.StatusCode) else str(status)
        self.lost = f"subscription status {name}"

    # --- one session -----------------------------------------------------------

    async def configure(self, client: Client) -> None:
        """Set the client's encryption and account from the config."""
        # Variables:
        #   security: The certificates; None only for an allowed local server.
        #   files: Each certificate file and what it is, checked before the
        #     client sees them so a missing one gives a clear refusal.
        #   user, password: The read-only account, read from the environment
        #     at this moment and passed straight to the client.
        security = self.config.security
        if security is not None:
            files = (
                ("client certificate", security.client_certificate),
                ("client private key", security.client_private_key),
                ("server certificate", security.server_certificate),
            )
            for label, path in files:
                if not path.is_file():
                    raise SiemensOpcUaRefused(
                        f"the {label} file {path.name} is missing"
                    )
            try:
                await client.set_security(
                    POLICIES[security.policy],
                    str(security.client_certificate),
                    str(security.client_private_key),
                    server_certificate=str(security.server_certificate),
                    mode=ua.MessageSecurityMode.SignAndEncrypt,
                )
            except (OSError, ValueError, TypeError) as error:
                raise SiemensOpcUaRefused(
                    f"the certificates could not be loaded ({type(error).__name__})"
                ) from error
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
        subscription = self.subscription_factory(client, params, _Handler(self))
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
        #   opened: True once client.connect() succeeded, so the session is
        #     closed at the end; a failed connect leaves nothing to close.
        #   self.stage: How far this attempt got, for the audit trail.
        #   self.connected: True once the `connected` marker is written, so a
        #     later failure is recorded as a loss of collected time.
        #   refusal: Set when the server rejected the login or certificates;
        #     raised in place of the server's error so collection stops.
        client = self.client_factory(self.config.endpoint_url)
        self.subscription_id = None
        self.last_seq = None
        self.lost = None
        self.connected = False
        opened = False
        try:
            self.stage = "configure"
            await self.configure(client)
            self.stage = "check_server"
            await self.check_server(client)
            self.stage = "connect"
            await client.connect()
            opened = True
            self.stage = "resolve_nodes"
            nodes = await self.resolve_nodes(client)
            self.mark("connected")
            self.connected = True
            self.trail("connected")
            self.stage = "subscribe"
            await self.subscribe(client, nodes)
            self.stage = "watch"
            await self.watch(client, stop)
        except CONNECTION_ERRORS as error:
            refusal = refusal_for(error)
            if refusal is not None:
                raise refusal from error
            if self.connected:
                self.mark(
                    "gap",
                    gap=OpcUaGap(
                        cause="session_lost",
                        subscription_id=self.subscription_id,
                        last_received_at=self.last_received_at,
                    ),
                )
                self.mark("disconnected", reason=failure_reason(error))
            raise
        finally:
            if opened:
                try:
                    await client.disconnect()
                except CONNECTION_ERRORS:
                    pass

    async def run(self, stop: asyncio.Event) -> None:
        """Collect until asked to stop, reconnecting after a lost connection."""
        # Variables:
        #   stop: Set by the caller to end collection cleanly.
        #   reason: Why collection ended, on the `stopped` marker and in the
        #     audit trail.
        #   self.connected: Read after a failed session, to tell a lost
        #     connection (it had connected) from a failed attempt.
        reason = "stop requested"
        while not stop.is_set():
            self.epoch += 1
            self.stage = None
            try:
                await self.session(stop)
            except SiemensOpcUaRefused as error:
                self.trail("refused", str(error))
                self.stopped(f"refused: {error}")
                raise
            except CONNECTION_ERRORS as error:
                outcome = "lost" if self.connected else "failed"
                self.trail(outcome, failure_reason(error))
            except Exception as error:
                self.trail("error", type(error).__name__)
                self.stopped(f"error: {type(error).__name__}")
                raise
            else:
                self.trail("closed", "stop requested")
            if stop.is_set():
                break
            if self.config.max_sessions and self.epoch >= self.config.max_sessions:
                reason = "session limit reached"
                break
            try:
                await asyncio.wait_for(stop.wait(), self.config.reconnect_seconds)
            except asyncio.TimeoutError:
                pass
        self.stopped(reason)


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


def audit_file(path: Path) -> Callable[[SiemensOpcUaAuditEntry], None]:
    """An audit trail that appends each entry to a JSONL file and flushes it."""

    def write(entry: SiemensOpcUaAuditEntry) -> None:
        with path.open("a", encoding="utf-8") as out:
            out.write(entry.model_dump_json() + "\n")
            out.flush()

    return write


def read_audit(path: Path) -> list[SiemensOpcUaAuditEntry]:
    """The audit trail from a file, oldest first."""
    return [
        SiemensOpcUaAuditEntry.model_validate_json(text)
        for text in path.read_text(encoding="utf-8").splitlines()
        if text
    ]


def main(argv: list[str] | None = None) -> int:
    """Collect from the configured server into a JSONL file until Ctrl+C."""
    # Variables:
    #   args.config: The approved scope (server, nodes, certificates).
    #   args.out: The capture file; lines are appended, never overwritten.
    #   trail: The audit file: --audit, or the capture file's name ending in
    #     .audit.jsonl, so every run leaves a trail.
    #   Exit code: 0 when collection ended normally; 2 when the config is
    #     unreadable or the collector refused, since a person must fix it.
    parser = argparse.ArgumentParser(
        prog="python -m capstone.ingestion.siemens_opcua_adapter"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit", type=Path, default=None)
    args = parser.parse_args(argv)
    trail = args.audit or args.out.with_name(args.out.stem + ".audit.jsonl")
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as error:
        print(f"config: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    collector = SiemensOpcUaCollector(
        config, file_sink(args.out), audit=audit_file(trail)
    )

    async def collect() -> None:
        await collector.run(asyncio.Event())

    try:
        asyncio.run(collect())
    except SiemensOpcUaRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        collector.stopped("interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
