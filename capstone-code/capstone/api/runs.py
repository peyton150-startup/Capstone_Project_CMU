"""Opt-in, local-only simulator execution with durable status and safe event journal.

The worker calls the existing Pydantic Graph episode and ApprovalDesk. It never
receives, stores or serves simulator hidden truth. Pilot execution is impossible.
Web observers cannot block a watcher: stage snapshots use a bounded queue.
"""

from __future__ import annotations

import hashlib
import json
import queue
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from capstone.settings import Settings, get_settings
from capstone.triage_run_controls import (
    EffectiveTriageRun,
    TriageRunOptions,
    overridden_fields,
    resolve_triage_run,
)

RunState = Literal[
    "queued", "running", "awaiting_review", "completed", "failed", "interrupted"
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seed: int = Field(ge=0, le=1_000_000)
    kind: Literal["standard", "challenge"] = "standard"
    mode: Literal["triage", "deep"] = "triage"
    hazards: bool = False
    tree_of_thought: bool = False
    manual: Literal["none", "keyword", "neon"] = "none"
    # Validated request-specific settings; no environment or credential edits.
    triage_settings: TriageRunOptions | None = None
    # Optional optimistic concurrency token from the visible server preview.
    # Legacy clients may omit it; the UI always includes it.
    configuration_fingerprint: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{20}$"
    )
    _effective_triage: EffectiveTriageRun | None = PrivateAttr(default=None)


def public_run_configuration(
    request: RunRequest, settings: Settings, *,
    effective: EffectiveTriageRun | None = None,
) -> dict[str, Any]:
    """Pure, allowlisted resolution shared by preview, submit and worker."""
    applied = request.mode == "triage"
    if applied and effective is None:
        effective = resolve_triage_run(settings, request.triage_settings)
    desired = (
        {} if request.triage_settings is None
        else request.triage_settings.model_dump(exclude_none=True)
    )
    stages = (
        effective.stage_modes() if applied and effective
        else {"deep": "model-backed Graph", "triage": "not run"}
    )
    if applied:
        stages["manual"] = (
            "off" if request.manual == "none"
            else "dedicated lookup enabled" if settings.manual_step
            else "manual tool available; dedicated lookup off"
        )
        if (
            effective is not None
            and effective.investigate == "deterministic"
            and effective.hypothesize == "model"
            and request.tree_of_thought
        ):
            stages["test"] = "deterministic reads; possible model revaluation"
    body = {
        "schema_version": 1,
        "applied": applied,
        "run_inputs": {
            "seed": request.seed,
            "kind": request.kind,
            "mode": request.mode,
            "hazards": request.hazards,
            "tree_of_thought": request.tree_of_thought,
            "manual": request.manual,
        },
        "requested": desired,
        "effective_triage": (
            effective.model_dump(mode="json") if applied and effective else None
        ),
        "overridden": (
            list(overridden_fields(request.triage_settings, effective))
            if applied and effective else []
        ),
        "not_applied": sorted(desired) if not applied else [],
        "stages": stages,
        "configured_conclude_primary": (
            settings.triage_model or settings.conclude_model or settings.default_model
            if applied else settings.conclude_model or settings.default_model
        ),
        "model_attempts": (
            "Configured only; inspect run model-call audit for actual attempts"
        ),
        "scope": "simulator only; per-run; no controller operations",
    }
    # Digest is a stable, short correlation aid, never a credential.
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["fingerprint"] = hashlib.sha256(canonical.encode()).hexdigest()[:20]
    return body


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=200)


def safe_hypothesis_progress(state: Any) -> dict[str, Any] | None:
    """Allowlisted typed compiler metadata; no prose or source payloads."""
    if state.mode != "triage":
        return None
    from capstone.agent.triage_hypothesize import TriageCandidate, TriageHypothesisTrace

    candidates = []
    for value in state.triage_candidates:
        if not isinstance(value, TriageCandidate):
            continue
        try:
            # Do not trust Pydantic instances produced by unchecked model_copy
            # updates or mutated nested references. Validate actual values.
            candidates.append(TriageCandidate.model_validate(value.model_dump()))
        except (TypeError, ValueError):
            continue
    last = None
    for value in reversed(state.triage_hypothesis_trace):
        if not isinstance(value, TriageHypothesisTrace):
            continue
        try:
            last = TriageHypothesisTrace.model_validate(value.model_dump())
            break
        except (TypeError, ValueError):
            continue
    return {
        "rule_version": None if last is None else last.rule_version,
        "last_action": None if last is None else last.action,
        "candidate_count": len(candidates),
        "candidates_truncated": len(candidates) > 12,
        "candidates": [
            {
                "id": c.id,
                "family": c.family,
                "status": c.status,
                "qualified_sources": len(c.observation_evidence_ids),
                "required_tests": len(c.discriminating_requirement_ids),
                "missing_tests": len(c.missing_requirement_ids),
                "unavailable_tests": len(c.unavailable_requirement_ids),
                "open_questions": len(c.open_question_ids),
            }
            for c in candidates[:12]
        ],
        "test_requirements": len(state.triage_test_requirement_ids),
        "trace_records": len(state.triage_hypothesis_trace),
        "logging_failures": state.triage_hypothesis_logging_failures,
    }


def safe_stage(state: Any) -> dict[str, Any]:
    """Immutable, bounded operational fields only; never entire InvestigationState."""
    reason = state.termination_reason
    return {
        "investigation_id": str(state.investigation_id),
        "mode": state.mode,
        "triage_run_mode": state.triage_run_mode if state.mode == "triage" else None,
        "stage": state.stage,
        "iteration_count": state.iteration_count,
        "tool_calls": state.tool_call_count,
        "evidence_count": len(state.evidence),
        "hypothesis_count": len(state.hypotheses),
        "unresolved_question_ids": [q.id for q in state.unanswered_questions[:25]],
        "termination_reason": None if reason is None else reason.value,
        "conclusion_available": state.conclusion is not None,
        "hypothesis_progress": safe_hypothesis_progress(state),
    }


class SimulatorRuns:
    """Single-host runner; SQLite recovers status but never resumes an approval.

    At most one active episode per local service. SQLite carries events/snapshots
    across browser reconnects. An API process restart fails interrupted runs.
    """

    def __init__(self, database: Path, *, approval_timeout_seconds: float = 240):
        self.database = database
        self.artifact_root = database.parent
        self.approval_timeout_seconds = approval_timeout_seconds
        self.lock = threading.RLock()
        self.waiters: dict[tuple[str, int], threading.Event] = {}
        self.active: set[str] = set()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._initialize_store()

    def _initialize_store(self) -> None:
        """Create or recover the local journal; remote stores override this."""
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, request_key TEXT UNIQUE,
                    requested TEXT NOT NULL, state TEXT NOT NULL,
                    snapshot TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL, seq INTEGER NOT NULL,
                    event TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY (run_id, seq)
                );
                CREATE TABLE IF NOT EXISTS run_reviews (
                    run_id TEXT NOT NULL, proposal_id INTEGER NOT NULL,
                    status TEXT NOT NULL, details TEXT NOT NULL,
                    PRIMARY KEY (run_id, proposal_id)
                );
            """)
            db.execute(
                "UPDATE runs SET state='interrupted', updated_at=? "
                "WHERE state IN ('queued', 'running', 'awaiting_review')",
                (utc_now(),),
            )
            db.execute("UPDATE run_reviews SET status='expired' WHERE status='pending'")

    @contextmanager
    def _db(self):
        con = sqlite3.connect(str(self.database), timeout=5)
        con.execute("PRAGMA busy_timeout=5000")
        try:
            with con:
                yield con
        finally:
            con.close()

    def investigation_audit_path(self, run_id: str) -> Path:
        """Private, server-owned path derived from an existing UUID run id."""
        if str(uuid.UUID(run_id)) != run_id:
            raise ValueError("Invalid run identifier")
        return self.artifact_root / "simulator-investigations" / (run_id + ".jsonl")

    def investigation_event_path(self, run_id: str) -> Path:
        """Server-owned safe operational event log, separate from private audits."""
        return self.investigation_audit_path(run_id).with_suffix(".events.jsonl")

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self.lock, self._db() as db:
            row = db.execute(
                "SELECT run_id, requested, state, snapshot, created_at, updated_at "
                "FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "requested": json.loads(row[1]),
            "state": row[2],
            "snapshot": json.loads(row[3]),
            "created_at": row[4],
            "updated_at": row[5],
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock, self._db() as db:
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT run_id FROM runs ORDER BY created_at DESC LIMIT ?",
                    (min(limit, 100),),
                ).fetchall()
            ]
        return [r for id_ in ids if (r := self.get(id_)) is not None]

    def events_since(
        self, run_id: str, seq: int, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        if self.get(run_id) is None:
            return []
        with self.lock, self._db() as db:
            rows = db.execute(
                "SELECT seq, event, payload FROM run_events WHERE run_id=? AND seq>? "
                "ORDER BY seq LIMIT ?",
                (run_id, seq, min(limit, 100)),
            ).fetchall()
        return [
            {"seq": n, "event": name, "data": json.loads(payload)}
            for n, name, payload in rows
        ]

    def _lock_event_sequence(self, db: Any, run_id: str) -> None:
        """SQLite uses its existing transaction lock; remote stores may lock a row."""

    def _lock_submission(self, db: Any) -> None:
        """Remote stores may enforce cross-process admission before insertion."""

    def _store_has_active_run(self, db: Any) -> bool:
        """Local admission is guarded by the process lock and restart recovery."""
        return False

    def _persist_artifacts(self, run_id: str) -> None:
        """SQLite keeps the original private JSONL files locally."""

    def close(self) -> None:
        """Local SQLite connections are closed after each transaction."""

    def _emit(
        self,
        run_id: str,
        event: str,
        payload: dict[str, Any],
        *,
        state: RunState | None = None,
    ) -> None:
        with self.lock, self._db() as db:
            self._lock_event_sequence(db, run_id)
            next_seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO run_events VALUES(?,?,?,?,?)",
                (run_id, next_seq, event, json.dumps(payload), utc_now()),
            )
            if state is not None:
                db.execute(
                    "UPDATE runs SET state=?, snapshot=?, updated_at=? WHERE run_id=?",
                    (state, json.dumps(payload), utc_now(), run_id),
                )
            else:
                db.execute(
                    "UPDATE runs SET snapshot=?, updated_at=? WHERE run_id=?",
                    (json.dumps(payload), utc_now(), run_id),
                )

    def submit(self, request: RunRequest, request_key: str) -> dict[str, Any]:
        """At most one active episode; freeze its effective settings at admission."""
        settings = get_settings()
        effective = (
            resolve_triage_run(settings, request.triage_settings)
            if request.mode == "triage" else None
        )
        request._effective_triage = effective
        configuration = public_run_configuration(
            request, settings, effective=effective
        )
        if (
            request.configuration_fingerprint is not None
            and request.configuration_fingerprint != configuration["fingerprint"]
        ):
            raise ValueError("preview fingerprint does not match effective settings")
        # Stored alongside the request for durable replay and UI inspection.
        # Do not reconstruct effective settings from a future process environment.
        serialized = json.dumps(
            {
                **request.model_dump(mode="json"),
                "effective_configuration": configuration,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.lock:
            with self._db() as db:
                self._lock_submission(db)
                existing = db.execute(
                    "SELECT run_id, requested FROM runs WHERE request_key=?",
                    (request_key,),
                ).fetchone()
                if existing:
                    if existing[1] != serialized:
                        raise ValueError(
                            "idempotency key reused for different settings"
                        )
                    return self.get(existing[0])
                if self.active or self._store_has_active_run(db):
                    raise RuntimeError("one simulator run is already active")
                id_ = str(uuid.uuid4())
                initial = {
                    "stage": None,
                    "mode": request.mode,
                    "status": "queued",
                    "configuration_fingerprint": configuration["fingerprint"],
                }
                db.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                    (
                        id_,
                        request_key,
                        serialized,
                        "queued",
                        json.dumps(initial),
                        utc_now(),
                        utc_now(),
                    ),
                )
            self.active.add(id_)
        threading.Thread(
            target=self._execute,
            args=(id_, request),
            daemon=True,
            name="simulator-run-" + id_[:8],
        ).start()
        return self.get(id_)

    def pending_reviews(self) -> list[dict[str, Any]]:
        with self.lock, self._db() as db:
            rows = db.execute(
                "SELECT run_id, proposal_id, details FROM run_reviews WHERE status='pending' "
                "ORDER BY run_id LIMIT 50",
            ).fetchall()
        return [{"run_id": r[0], "proposal_id": r[1], **json.loads(r[2])} for r in rows]

    def decide(self, run_id: str, decision: ReviewDecision) -> dict[str, Any]:
        key = (run_id, decision.proposal_id)
        with self.lock:
            with self._db() as db:
                row = db.execute(
                    "SELECT status FROM run_reviews WHERE run_id=? AND proposal_id=?",
                    key,
                ).fetchone()
                if row is None:
                    raise LookupError("review request not found")
                if row[0] != "pending" or key not in self.waiters:
                    raise ValueError("review is not pending")
                details = json.loads(
                    db.execute(
                        "SELECT details FROM run_reviews WHERE run_id=? AND proposal_id=?",
                        key,
                    ).fetchone()[0]
                )
                details["note"] = decision.note
                db.execute(
                    "UPDATE run_reviews SET status=?, details=? "
                    "WHERE run_id=? AND proposal_id=? AND status='pending'",
                    (decision.decision, json.dumps(details), *key),
                )
            # Record the decision before waking the episode. Otherwise the
            # worker may finish and a late review event can regress the run
            # from completed back to running.
            self._emit(
                run_id,
                "review.decided",
                {
                    "proposal_id": decision.proposal_id,
                    "decision": decision.decision,
                    "status": "decided_not_executed",
                    "mode": "deep",
                },
                state="running",
            )
            self.waiters[key].set()
        return {
            "run_id": run_id,
            "proposal_id": decision.proposal_id,
            "decision": decision.decision,
        }

    def _await_review(self, run_id: str, proposal: Any) -> tuple[bool, str]:
        """Called only from episode worker, never the HTTP request thread."""
        id_ = int(proposal.proposal_id)
        key = (run_id, id_)
        fields = {
            "proposal_id": id_,
            "machine_id": str(proposal.machine_id)[:80],
            "action": str(proposal.action)[:160],
            "reason": str(proposal.reason)[:600],
            "predicted_effect": str(getattr(proposal, "predicted_effect", "") or "")[
                :600
            ],
            "note": "",
        }
        waiter = threading.Event()
        with self.lock:
            with self._db() as db:
                db.execute(
                    "INSERT INTO run_reviews VALUES(?,?,?,?)",
                    (run_id, id_, "pending", json.dumps(fields)),
                )
            self.waiters[key] = waiter
        self._emit(run_id, "review.requested", fields, state="awaiting_review")
        accepted = waiter.wait(self.approval_timeout_seconds)
        with self.lock:
            with self._db() as db:
                row = db.execute(
                    "SELECT status, details FROM run_reviews WHERE run_id=? AND proposal_id=?",
                    key,
                ).fetchone()
                if not accepted and row and row[0] == "pending":
                    db.execute(
                        "UPDATE run_reviews SET status='expired' "
                        "WHERE run_id=? AND proposal_id=? AND status='pending'",
                        key,
                    )
            self.waiters.pop(key, None)
        status = row[0] if row else "expired"
        if status == "pending":
            status = "expired"
        # A committed approval is not enough to resume an episode: the
        # in-process reviewer waiter must also have received the signal.
        # If event delivery failed after the DB update, fail closed rather
        # than treating a stale "approve" as permission to act.
        if status == "approve" and accepted:
            return True, json.loads(row[1]).get(
                "note", ""
            ) or "approved by simulator reviewer"
        if status == "approve":
            return False, "review notification not confirmed"
        return False, "review timed out" if status == "expired" else (
            json.loads(row[1]).get("note", "") or "rejected by simulator reviewer"
        )

    def _execute(self, run_id: str, request: RunRequest) -> None:
        progress: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
        missed = [0]

        def watch(state: Any) -> None:
            try:
                progress.put_nowait(safe_stage(state))
            except queue.Full:
                missed[0] += 1

        def publish() -> None:
            while True:
                row = progress.get()
                try:
                    if row is None:
                        return
                    try:
                        self._emit(run_id, "stage.updated", row)
                    except (OSError, sqlite3.Error, RuntimeError):
                        # Observer storage must never crash or block the agent.
                        missed[0] += 1
                finally:
                    progress.task_done()

        writer = threading.Thread(
            target=publish, name="run-events-" + run_id[:8], daemon=True
        )
        writer.start()
        manual = None
        try:
            submitted = self.get(run_id)
            configuration = (
                None if submitted is None
                else submitted["requested"].get("effective_configuration")
            )
            self._emit(
                run_id,
                "run.started",
                {
                    "status": "running",
                    "mode": request.mode,
                    "configuration_fingerprint": (
                        None if configuration is None
                        else configuration.get("fingerprint")
                    ),
                },
                state="running",
            )
            from capstone.agent.completion import AuditLog
            from capstone.episode import run_episode
            from capstone.experiment import model_policy_factory, open_manual
            from capstone.observability import EventLogger

            audit_path = self.investigation_audit_path(run_id)
            audit_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            manual = open_manual(request.manual) if request.manual != "none" else None
            policy = model_policy_factory(
                with_recall=False,
                with_manual=manual is not None,
                tree_of_thought=request.tree_of_thought,
            )()
            # Keep structured operational metadata in a separate private file.
            # EventLogger rejects free text, evidence, provider secrets and
            # unvalidated metadata; it is not the investigator's audit.
            with self.investigation_event_path(run_id).open(
                "a", encoding="utf-8"
            ) as event_stream:
                result = run_episode(
                    request.seed,
                    policy,
                    kind=request.kind,
                    triage=request.mode == "triage",
                    triage_configuration=request._effective_triage,
                    hazards=request.hazards,
                    manual=manual,
                    watch=watch,
                    log=AuditLog(audit_path),
                    event_logger=EventLogger(event_stream, name="ui-" + run_id),
                    approver=lambda proposal: self._await_review(run_id, proposal),
                    run_key="ui/" + run_id,
                )
            progress.join()
            if missed[0]:
                self._emit(
                    run_id,
                    "resync.required",
                    {
                        "dropped_ui_updates": missed[0],
                        "mode": request.mode,
                    },
                )
            triage = (
                result.triage
                if result.triage is not None
                else (result.state if result.state.mode == "triage" else None)
            )
            report = (
                None
                if triage is None or triage.triage_report is None
                else (triage.triage_report.model_dump(mode="json"))
            )
            # A completed run must have a durable audit before it can report
            # success on a hosted backend; SQLite's artifact hook is a no-op.
            self._persist_artifacts(run_id)
            # The immutable submission manifest is the source of truth for
            # effective settings, including after browser reconnection.
            persisted = self.get(run_id)
            configuration = (
                None if persisted is None
                else persisted["requested"].get("effective_configuration")
            )
            final = {
                "status": "completed",
                "mode": request.mode,
                "effective_configuration": configuration,
                "investigation": safe_stage(result.state),
                "triage_report": report,
                "diagnosis": None
                if result.state.conclusion is None
                else result.state.conclusion.diagnosis[:1000],
                "recommendation": None
                if result.state.conclusion is None
                else result.state.conclusion.recommendation,
                "action_executed": result.state.action_started_tick is not None,
                "verification_outcome": None
                if result.state.verification is None
                else result.state.verification.outcome,
                "deep_ran": result.triage is not None
                and result.state is not result.triage,
                "review_count": len(result.desk.proposals()),
            }
            self._emit(run_id, "run.completed", final, state="completed")
        except Exception as error:
            # Never persist exception messages: providers may include private details.
            try:
                self._emit(
                    run_id,
                    "run.failed",
                    {
                        "status": "failed",
                        "error_class": type(error).__name__,
                        "mode": request.mode,
                    },
                    state="failed",
                )
            except Exception:
                # An interrupted run is marked by the next exclusive owner.
                pass
        finally:
            if manual is not None and hasattr(manual, "close"):
                try:
                    manual.close()
                except Exception:
                    pass  # Cleanup failure must not change the recorded outcome.
            try:
                progress.put(None, timeout=2)
            except queue.Full:
                pass
            with self.lock:
                self.active.discard(run_id)
