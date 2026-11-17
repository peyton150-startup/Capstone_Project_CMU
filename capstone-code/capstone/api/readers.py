"""Bounded, honest adapters for existing v2 capture and offline run artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from capstone.ingestion.siemens_opcua_record import (
    OpcUaDataChange,
    OpcUaSessionMarker,
    parse_opcua_line,
)

MAX_TAIL_BYTES = 2_000_000
MAX_LINES = 3500


def recent_lines(path: Path | None, *, limit: int = MAX_LINES) -> list[str]:
    """Read only complete lines from the end of an approved private artifact."""
    # Variables:
    #   start: Byte offset for a bounded tail; the first partial line is discarded.
    #   raw: File tail ending at its final newline, excluding incomplete writes.
    if path is None or not path.is_file():
        return []
    with path.open("rb") as handle:
        size = handle.seek(0, 2)
        start = max(0, size - MAX_TAIL_BYTES)
        handle.seek(start)
        raw = handle.read(MAX_TAIL_BYTES)
    if start:
        pos = raw.find(b"\n")
        raw = raw[pos + 1 :] if pos >= 0 else b""
    end = raw.rfind(b"\n")
    if end < 0:
        return []
    return [
        line.decode("utf-8", errors="replace")
        for line in raw[: end + 1].splitlines()[-limit:]
        if line
    ]


def capture_records(
    path: Path | None,
) -> tuple[list[OpcUaDataChange | OpcUaSessionMarker], int]:
    """Validate actual Siemens v2 records; never treat MTConnect as OPC UA."""
    # Variables:
    #   records: Pydantic validated data changes and session markers.
    #   invalid: Bad or truncated records in the bounded tail.
    records: list[OpcUaDataChange | OpcUaSessionMarker] = []
    invalid = 0
    for line in recent_lines(path):
        try:
            records.append(parse_opcua_line(line))
        except (ValueError, TypeError):
            invalid += 1
    return records, invalid


def signal_id(server_uri: str, namespace_uri: str, kind: str, identifier: str) -> str:
    """Stable opaque id; browser never needs raw OPC UA topology."""
    return hashlib.sha256(
        json.dumps([server_uri, namespace_uri, kind, identifier]).encode("utf-8")
    ).hexdigest()[:20]


def iso_age(at: str | None, now: datetime) -> float | None:
    """UTC age in seconds; unknown timestamps remain unknown."""
    if not at:
        return None
    try:
        stamp = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        elapsed = (now - stamp).total_seconds()
        # A future collector clock must not make a stale or invalid recording
        # look live. Allow only a small clock/rounding tolerance.
        if elapsed < -5.0:
            return None
        return max(0.0, elapsed)
    except ValueError:
        return None


def recorder_snapshot(
    path: Path | None, *, show_values: bool = False
) -> dict[str, Any]:
    """Summarize a bounded window, not falsely claim whole-session coverage.

    Signals are identified by server and OPC UA node, never display label.
    Native Good is not equivalent to eligible for a specific analysis.
    """
    # Variables:
    #   counts: Severity totals over the bounded tail, not the whole recording.
    #   last_event: Most recent explicit collector state event.
    #   signals: Most recent validated value per physical source identity.
    #   now: Current UTC clock for conservative 'unknown' session freshness.
    if path is None:
        return {
            "availability": "not_configured",
            "message": "No approved Siemens capture configured",
            "recorder": None,
            "signals": [],
            "events": [],
        }
    records, invalid = capture_records(path)
    counts: Counter[str] = Counter()
    signals: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    latest_receive: str | None = None
    latest_good_numeric: str | None = None
    last_event: dict[str, Any] | None = None
    session_epoch: int | None = None
    subscribed_epoch: int | None = None
    for record in records:
        if isinstance(record, OpcUaSessionMarker):
            marker = {
                "event": record.event,
                "at": record.at.isoformat(),
                "epoch": record.session_epoch,
            }
            events.append(marker)
            last_event = marker
            session_epoch = record.session_epoch
            if record.event == "subscribed":
                subscribed_epoch = record.session_epoch
            if record.event in ("disconnected", "stopped", "gap"):
                subscribed_epoch = None
            if record.event == "gap":
                counts["gaps"] += 1
            if record.event == "connected":
                counts["connections"] += 1
            continue
        counts["received"] += 1
        counts[record.status.severity] += 1
        if record.status.overflow:
            counts["overflow"] += 1
        if record.non_finite or record.value_type is None:
            counts["unsupported"] += 1
        sid = signal_id(
            record.server_uri,
            record.node.namespace_uri,
            record.node.identifier_type,
            record.node.identifier,
        )
        latest_receive = max(latest_receive or "", record.received_at.isoformat())
        if record.number() is not None:
            latest_good_numeric = max(
                latest_good_numeric or "", record.received_at.isoformat()
            )
        signals[sid] = {
            "id": sid,
            "label": "Signal " + sid[:7],
            "unit": None,
            "mapped": False,
            "analysis_eligible": False,
            "value": record.value if show_values else None,
            "value_available": show_values and record.value is not None,
            "quality": record.status.severity,
            "status_code": record.status.code,
            "received_at": record.received_at.isoformat(),
            "source_timestamp": record.source_timestamp.isoformat()
            if record.source_timestamp
            else None,
            "server_timestamp": record.server_timestamp.isoformat()
            if record.server_timestamp
            else None,
            "session_epoch": record.session_epoch,
            "freshness": "unknown",
            "reason": "Physical mapping, unit and update policy not yet field-verified",
        }
        session_epoch = record.session_epoch
    for item in signals.values():
        item["last_received_age_s"] = iso_age(item["received_at"], now)
    age = iso_age(last_event["at"], now) if last_event else None
    connected = bool(
        last_event
        and last_event["event"] in ("connected", "subscribed", "heartbeat")
        and (
            (age is not None and age <= 90)
            or (receive_age := iso_age(latest_receive, now)) is not None
            and receive_age <= 90
        )
    )
    if last_event and last_event["event"] in ("stopped", "disconnected"):
        connection = "disconnected"
    elif connected:
        connection = "connected"
    else:
        connection = "unknown"
    receive_age = iso_age(latest_receive, now)
    measured = (
        "received_recently"
        if receive_age is not None and receive_age <= 120
        else ("stale_or_none" if latest_receive else "none")
    )
    size = path.stat().st_size if path.is_file() else 0
    # Disk availability is observed independently; it does not prove a durable flush.
    try:
        disk_free = shutil.disk_usage(path.parent).free if path.is_file() else None
    except OSError:
        disk_free = None
    subscribed = bool(
        connected and subscribed_epoch is not None and subscribed_epoch == session_epoch
    )
    return {
        "availability": "available" if path.is_file() else "file_missing",
        "message": None if path.is_file() else "Configured capture file is not present",
        "recorder": {
            "id": "siemens-local",
            "source": "Siemens OPC UA v2",
            "process_state": "unknown",  # No process supervisor is integrated.
            "connection_state": connection,
            "subscription_state": "confirmed" if subscribed else "unconfirmed",
            "measurement_state": measured,
            "last_receive_at": latest_receive,
            "last_good_numeric_at": latest_good_numeric,
            "session_epoch": session_epoch,
            "window_scope": "bounded_recent_tail",
            "received": counts["received"],
            "good": counts["good"],
            "uncertain": counts["uncertain"],
            "bad": counts["bad"],
            "overflow": counts["overflow"],
            "gaps": counts["gaps"],
            "reconnections": max(0, counts["connections"] - 1),
            "unsupported": counts["unsupported"],
            "invalid_lines": invalid,
            "analysis_eligible": None,  # Cannot establish mapping and quality gate.
            "output_bytes": size,
            "sink_state": "unknown",  # A growing file is not proof of durable storage.
            "disk_free_bytes": disk_free,
        },
        "signals": sorted(signals.values(), key=lambda x: x["label"]),
        "events": list(reversed(events[-120:])),
    }


def signal_samples(
    path: Path | None, requested: str, *, show_values: bool
) -> list[dict[str, Any]]:
    """Return bounded real samples; never interpolate missing data."""
    records, _ = capture_records(path)
    samples: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, OpcUaDataChange):
            continue
        sid = signal_id(
            record.server_uri,
            record.node.namespace_uri,
            record.node.identifier_type,
            record.node.identifier,
        )
        if sid != requested:
            continue
        value = record.number()
        samples.append(
            {
                "at": record.source_timestamp.isoformat()
                if record.source_timestamp
                else record.received_at.isoformat(),
                "received_at": record.received_at.isoformat(),
                "value": value if show_values else None,
                "quality": record.status.severity,
                "epoch": record.session_epoch,
            }
        )
    return samples[-600:]


def safe_investigations(path: Path | None) -> list[dict[str, Any]]:
    """Whitelist completed-investigation fields; never return arbitrary audit JSON."""
    out: list[dict[str, Any]] = []
    for line in recent_lines(path, limit=300):
        try:
            raw = json.loads(line)
        except (ValueError, TypeError):
            continue
        completed = raw.get("completed", raw) if isinstance(raw, dict) else {}
        if not isinstance(completed, dict):
            continue
        id_ = completed.get("investigation_id")
        if not isinstance(id_, str):
            continue
        anomaly = completed.get("anomaly") or {}
        conclusion = completed.get("conclusion") or {}
        if not isinstance(anomaly, dict) or not isinstance(conclusion, dict):
            continue
        evidence = completed.get("evidence") or []
        hypotheses = completed.get("hypotheses") or []
        out.append(
            {
                "id": id_,
                "run_id": completed.get("run_id"),
                "summary": str(anomaly.get("summary") or "No summary")[:600],
                "symptoms": [
                    str(x)[:250] for x in (anomaly.get("symptoms") or [])[:20]
                ],
                "diagnosis": str(conclusion.get("diagnosis") or "")[:1200],
                "model_confidence": conclusion.get("confidence"),
                "termination_reason": completed.get("termination_reason"),
                "evidence_count": len(evidence),
                "hypothesis_count": len(hypotheses),
                "tool_calls": completed.get("tool_calls_used"),
                "iterations": completed.get("iterations_used"),
                "verification": (completed.get("verification") or {}).get("status")
                if isinstance(completed.get("verification"), dict)
                else None,
            }
        )
    return list(reversed(out))


def safe_investigation_detail(path: Path | None, ident: str) -> dict[str, Any] | None:
    """Project only explicitly permitted evidence and hypothesis attributes."""
    if not ident or len(ident) > 100:
        return None
    for line in reversed(recent_lines(path, limit=300)):
        try:
            raw = json.loads(line)
        except (ValueError, TypeError):
            continue
        completed = raw.get("completed", raw) if isinstance(raw, dict) else {}
        if (
            not isinstance(completed, dict)
            or completed.get("investigation_id") != ident
        ):
            continue
        summary = next((x for x in safe_investigations(path) if x["id"] == ident), None)
        if summary is None:
            return None
        evidence = []
        for e in (completed.get("evidence") or [])[:100]:
            if not isinstance(e, dict):
                continue
            evidence.append(
                {
                    k: e.get(k)
                    for k in (
                        "id",
                        "source_id",
                        "source_type",
                        "content",
                        "observed_at",
                        "observed_tick",
                    )
                }
            )
        hypotheses = []
        for h in (completed.get("hypotheses") or [])[:20]:
            if not isinstance(h, dict):
                continue
            hypotheses.append(
                {
                    k: h.get(k)
                    for k in (
                        "id",
                        "description",
                        "claim",
                        "status",
                        "confidence",
                        "supporting_evidence_ids",
                        "contradicting_evidence_ids",
                        "unexplained_evidence_ids",
                        "discriminating_check",
                    )
                }
            )
        # The audit includes private arguments and free-text thoughts. The
        # UI receives only decision outcomes and source-linked IDs.
        decisions = []
        for decision in (raw.get("decisions") or [])[:250]:
            if not isinstance(decision, dict):
                continue
            decisions.append(
                {
                    key: decision.get(key)
                    for key in (
                        "sequence",
                        "agent",
                        "phase",
                        "tick",
                        "tool",
                        "outcome",
                        "question_id",
                        "hypothesis_id",
                        "evidence_ids",
                        "batch",
                        "batch_position",
                        "termination_reason",
                    )
                }
            )
        metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
        public_metrics = {
            key: metrics.get(key)
            for key in (
                "iterations",
                "tool_calls",
                "repeated_calls",
                "failed_tool_calls",
                "malformed_results",
                "interpretation_failures",
                "hypothesis_revisions",
            )
        }
        pruned = []
        for candidate in (raw.get("pruned_candidates") or [])[:50]:
            if isinstance(candidate, dict):
                pruned.append(
                    {
                        key: candidate.get(key)
                        for key in (
                            "id",
                            "status",
                            "confidence",
                            "supporting_evidence_ids",
                            "contradicting_evidence_ids",
                        )
                    }
                )
        proposal = completed.get("proposed_action")
        verification = completed.get("verification")
        runtime_conclusion = raw.get("conclusion") or {}
        if not isinstance(runtime_conclusion, dict):
            runtime_conclusion = {}
        completed_conclusion = completed.get("conclusion") or {}
        if not isinstance(completed_conclusion, dict):
            completed_conclusion = {}
        proposal_record = raw.get("proposal") or {}
        if not isinstance(proposal_record, dict):
            proposal_record = {}

        def limited_text(value: Any, limit: int = 500) -> str | None:
            return value[:limit] if isinstance(value, str) else None

        def limited_strings(
            values: Any, *, count: int = 40, length: int = 160
        ) -> list[str]:
            if not isinstance(values, (list, tuple)):
                return []
            return [
                value[:length]
                for value in values[:count]
                if isinstance(value, str)
            ]

        def observed_tick(value: Any) -> int | None:
            return value if type(value) is int and value >= 0 else None

        status = proposal_record.get("status")
        if status not in ("pending", "approved", "rejected", "not_submitted"):
            status = None
        proposal_id = proposal_record.get("proposal_id")
        return {
            **summary,
            "conclusion_detail": {
                "assessment": runtime_conclusion.get("assessment")
                if runtime_conclusion.get("assessment") in ("supported", "unresolved")
                else None,
                "hypothesis_id": limited_text(
                    runtime_conclusion.get("hypothesis_id"), 80
                ),
                "evidence_ids": limited_strings(
                    completed_conclusion.get("evidence_ids"), length=80
                ),
                "unresolved_questions": limited_strings(
                    runtime_conclusion.get("unresolved_questions"),
                    count=20,
                    length=250,
                ),
                "next_check": limited_text(runtime_conclusion.get("next_check")),
                "action_rationale": limited_text(
                    runtime_conclusion.get("action_rationale")
                ),
            },
            "proposal_status": status,
            "proposal_id": (
                proposal_id
                if type(proposal_id) is int and proposal_id > 0
                else None
            ),
            "action_started_tick": observed_tick(raw.get("action_started_tick")),
            "action_finish_tick": observed_tick(raw.get("action_finish_tick")),
            "evidence": evidence,
            "hypotheses": hypotheses,
            "decision_trace": decisions,
            "reasoning_metrics": public_metrics,
            "pruned_candidates": pruned,
            "proposed_action": {
                k: proposal.get(k)
                for k in ("action", "machine_id", "reason", "evidence_ids")
            }
            if isinstance(proposal, dict)
            else None,
            "verification_detail": {
                k: verification.get(k)
                for k in (
                    "status",
                    "outcome",
                    "summary",
                    "evidence_ids",
                    "observed_tick",
                )
            }
            if isinstance(verification, dict)
            else None,
        }
    return None


def safe_evaluations(path: Path | None) -> list[dict[str, Any]]:
    """Deliberately omit whole Score and all simulator hidden-truth fields."""
    out: list[dict[str, Any]] = []
    for line in recent_lines(path, limit=300):
        try:
            raw = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("run_key"), str):
            continue
        out.append(
            {
                "id": raw["run_key"][:100],
                "scenario": raw.get("scenario_id"),
                "seed": raw.get("seed"),
                "conclusion": raw.get("conclusion"),
                "assessment": raw.get("assessment"),
                "recommendation": raw.get("recommendation"),
                "verification": raw.get("verification"),
                "wall_seconds": raw.get("wall_seconds"),
                "model_questions": (raw.get("model_calls") or {}).get("questions")
                if isinstance(raw.get("model_calls"), dict)
                else None,
                "tool_count": len(raw.get("tools_used") or []),
            }
        )
    return list(reversed(out))


def safe_scorecards(path: Path | None) -> list[dict[str, Any]]:
    """Evaluator-only aggregate-safe score projection; never expose true_fault.

    Score contains hidden simulator labels. We select correctness flags and
    counts explicitly instead of serializing Score or ExperimentRecord.
    Missing labels stay None; never coerce an unjudged case to a failure.
    """
    rows: list[dict[str, Any]] = []
    booleans = (
        "fault_correct",
        "target_correct",
        "action_correct",
        "recommendation_correct",
        "resolved",
    )
    nonnegative = (
        "tool_calls",
        "ticks_elapsed",
        "iterations",
        "causes_found",
        "wrong_causes",
        "causes_resolved",
    )
    for line in recent_lines(path, limit=300):
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict) or not isinstance(record.get("run_key"), str):
            continue
        score = record.get("score")
        if not isinstance(score, dict):
            continue
        row = {"id": record["run_key"][:100]}
        # Validate primitive types before projecting. Never echo arbitrary text.
        row.update(
            {
                key: score.get(key) if isinstance(score.get(key), bool) else None
                for key in booleans
            }
        )
        row.update(
            {
                key: score.get(key)
                if type(score.get(key)) is int and score[key] >= 0
                else None
                for key in nonnegative
            }
        )
        relevant = score.get("relevant_evidence")
        collected = score.get("relevant_evidence_collected")
        row["relevant_evidence_count"] = (
            len(relevant) if isinstance(relevant, list) else None
        )
        row["evidence_collected_count"] = (
            len(collected) if isinstance(collected, list) else None
        )
        row["judged"] = row["fault_correct"] is not None
        rows.append(row)
    return list(reversed(rows))


def mtconnect_snapshot(
    path: Path | None, *, show_values: bool = False
) -> dict[str, Any]:
    """Separate MTConnect v1 projection; never parse legacy rows as Siemens v2.

    MTConnect provides availability and conditions, NOT OPC UA StatusCode Good.
    A receipt or recent heartbeat does not certify physical controller health.
    """
    import math

    from capstone.ingestion.record import CollectorMarker, TelemetryRecord, parse_line

    if path is None:
        return {
            "availability": "not_configured",
            "recorder": None,
            "signals": [],
            "events": [],
        }
    if not path.is_file():
        return {
            "availability": "file_missing",
            "recorder": None,
            "signals": [],
            "events": [],
        }
    signals: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    received = available = unavailable = invalid = gaps = 0
    last: str | None = None
    last_marker: str | None = None
    last_marker_at: str | None = None
    last_instance: str | None = None
    for line in recent_lines(path):
        try:
            record = parse_line(line)
        except (ValueError, TypeError):
            invalid += 1
            continue
        if isinstance(record, CollectorMarker):
            if record.event == "gap":
                gaps += 1
            last_marker = record.event
            last_marker_at = record.at.isoformat()
            events.append(
                {
                    "event": record.event,
                    "at": last_marker_at,
                    "reason_code": "collector" if record.event != "gap" else "data_gap",
                }
            )
            continue
        assert isinstance(record, TelemetryRecord)
        received += 1
        if record.available:
            available += 1
        else:
            unavailable += 1
        at = record.received_at.isoformat()
        last = max(last or at, at)
        last_instance = record.instance_id
        sid = hashlib.sha256(
            json.dumps(
                [record.source, record.device, record.component, record.data_item_id],
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:20]
        numeric = record.number() if record.category == "SAMPLE" else None
        if numeric is not None and not math.isfinite(numeric):
            numeric = None
        signals[sid] = {
            "id": sid,
            "label": (record.name or record.type)[:100],
            "machine": record.device[:100],
            "component": record.component[:100],
            "category": record.category,
            "value": (
                numeric
                if record.category == "SAMPLE"
                else (record.value[:200] if record.value is not None else None)
            )
            if show_values and record.available
            else None,
            "value_available": bool(show_values and record.available),
            "quality": "available" if record.available else "unavailable",
            "unit": None,
            "analysis_eligible": False,
            "received_at": at,
            "source_timestamp": record.source_timestamp.isoformat(),
            "freshness": "unknown",
            "reason": "MTConnect availability is not a machine-approved analysis gate",
        }
    age = iso_age(last, datetime.now(timezone.utc))
    connection = "disconnected" if last_marker == "stopped" else "unknown"
    measurement = (
        "received_recently"
        if age is not None and age <= 120
        else ("stale_or_none" if last is not None else "none")
    )
    return {
        "availability": "available",
        "recorder": {
            "id": "mtconnect-local",
            "source": "MTConnect v1",
            "process_state": "unknown",
            "connection_state": connection,
            "subscription_state": "not_applicable",
            "measurement_state": measurement,
            "last_receive_at": last,
            "last_collector_marker_at": last_marker_at,
            "last_instance_known": last_instance is not None,
            "received": received,
            "available": available,
            "unavailable": unavailable,
            "gaps": gaps,
            "invalid_lines": invalid,
            "quality_scheme": "mtconnect_availability_not_opcua_statuscode",
            "window_scope": "bounded_recent_tail",
            "output_bytes": path.stat().st_size,
            "analysis_eligible": None,
            "sink_state": "unknown",
        },
        "signals": sorted(
            signals.values(), key=lambda row: (row["machine"], row["label"])
        ),
        "events": list(reversed(events[-120:])),
    }


def safe_memory_promotions(path: Path | None) -> list[dict[str, Any]]:
    """Read-only evaluator projection; promotion correctness never proves eligibility."""
    out: list[dict[str, Any]] = []
    for line in recent_lines(path, limit=300):
        try:
            raw = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("run_key"), str):
            continue
        promotion = raw.get("memory_promotion")
        if not isinstance(promotion, dict):
            continue
        out.append(
            {
                "run_key": raw["run_key"][:100],
                "investigation_id": str(promotion.get("investigation_id") or "")[:100],
                "accepted": promotion.get("accepted")
                if isinstance(promotion.get("accepted"), bool)
                else None,
                "stored": promotion.get("stored")
                if isinstance(promotion.get("stored"), bool)
                else None,
                "policy_version": str(promotion.get("policy_version") or "")[:80],
                "reasons_count": len(promotion["reasons"])
                if isinstance(promotion.get("reasons"), list)
                else None,
            }
        )
    return list(reversed(out))
