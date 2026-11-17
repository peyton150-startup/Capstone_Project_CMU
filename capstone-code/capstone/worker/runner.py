"""Portless, single-claim Render worker; simulator and Graph never run in FastAPI."""

from __future__ import annotations

import json
import logging
import os
import queue
import signal
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from capstone.api.run_repository import (
    JobClaim, LostLease, ReviewProposal, RunExecutionConfig, RunRepository,
    StagePayload,
)
from capstone.api.runs import safe_stage

logger = logging.getLogger("capstone.worker")


def record(event: str, *, claim: JobClaim | None = None, **counts: int) -> None:
    """Only approved codes, UUID and numeric counters; never exception messages."""
    if event not in {
        "ready", "claimed", "finished", "failed", "lease_lost", "recovered",
        "review_requested", "review_decided", "poll_failed", "progress_dropped",
        "model_telemetry_unavailable", "model_telemetry_dropped",
    }:
        raise ValueError("Unknown worker event")
    body: dict[str, Any] = {"service": "agent_worker", "event": event}
    if claim is not None:
        body["run_id"] = str(claim.run_id)
        body["job_id"] = str(claim.job_id)
    for key in ("duration_ms", "count", "queue_wait_ms", "attempt"):
        value = counts.get(key)
        if type(value) is int and 0 <= value <= 1_000_000_000:
            body[key] = value
    logger.info("%s", json.dumps(body, sort_keys=True, separators=(",", ":")))


def check_strategy(config: RunExecutionConfig) -> None:
    """Refuse environment drift instead of executing different triage settings."""
    from capstone.settings import get_settings

    settings = get_settings()
    actual = RunExecutionConfig(
        triage_plan=settings.triage_plan,
        triage_investigate=settings.triage_investigate,
        triage_hypothesize=settings.triage_hypothesize,
        triage_evidence_tests=settings.triage_evidence_tests,
        source_revision=os.getenv("CAPSTONE_SOURCE_REVISION") or None,
    )
    if actual != config:
        raise RuntimeError("Worker configuration does not match submitted settings")


def execute_claim(
    repository: RunRepository, claim: JobClaim, owner: str,
    *, stop: threading.Event | None = None,
    heartbeat_seconds: int = 10, review_seconds: int = 240,
) -> None:
    """Heartbeat during model I/O, persist approval, audit, events and outcome."""
    # Variables:
    #   lost: Sticky fencing failure that forbids actions and terminal writes.
    #   updates: Bounded nonblocking queue for validated UI stage projections.
    #   finished: Stops observer/heartbeat threads after the episode ends.
    if not 1 <= heartbeat_seconds <= 20:
        raise ValueError("Invalid heartbeat interval")
    stop = stop or threading.Event()
    lost, finished = threading.Event(), threading.Event()
    updates: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=128)
    missed = [0]
    # #297 owns the sanitized ModelCall and Attempt schema; this worker owns
    # only the cross-process journal adapter. No second telemetry projector.
    policy_holder: list[Any] = [None]
    persisted_calls = [0]
    telemetry_failures = [0]
    monitor_enabled = [False]
    started = time.monotonic()

    def emit_model(event_name: str, payload: dict[str, Any]) -> None:
        if not monitor_enabled[0]:
            return
        try:
            repository.publish_model_event(claim, owner, event_name, payload)
        except LostLease:
            lost.set()
            raise
        except Exception:
            telemetry_failures[0] += 1

    def flush_model_calls() -> None:
        if not monitor_enabled[0] or policy_holder[0] is None:
            return
        from capstone.api.model_calls import project_model_call

        calls = getattr(policy_holder[0], "calls", ()) or ()
        while persisted_calls[0] < len(calls):
            index = persisted_calls[0]
            try:
                safe = project_model_call(calls[index], index + 1)
                repository.publish_model_event(claim, owner, "model.call", safe)
            except LostLease:
                lost.set()
                raise
            except Exception:
                telemetry_failures[0] += 1
                return  # Retry on next stage or finalization without advancing.
            persisted_calls[0] += 1

    def finish_model_monitor() -> None:
        if monitor_enabled[0]:
            calls = getattr(policy_holder[0], "calls", ()) or ()
            emit_model("model.monitor.finished", {
                "schema_version": 1,
                "questions_seen": min(len(calls), 100_000),
                "questions_persisted": min(persisted_calls[0], 100_000),
                "write_failures": min(telemetry_failures[0], 100_000),
                "complete": len(calls) == persisted_calls[0],
            })
        if telemetry_failures[0]:
            record("model_telemetry_dropped", claim=claim,
                   count=min(telemetry_failures[0], 1_000_000))

    def alive() -> None:
        if lost.is_set() or stop.is_set():
            raise LostLease("Worker authority ended")
        if not repository.heartbeat(claim, owner, lease_seconds=60):
            lost.set()
            raise LostLease("Expired worker lease")

    def heartbeat() -> None:
        while not finished.wait(heartbeat_seconds):
            try:
                if not repository.heartbeat(claim, owner, lease_seconds=60):
                    lost.set()
                    record("lease_lost", claim=claim)
                    return
            except Exception:
                lost.set()
                record("lease_lost", claim=claim)
                return

    def watch(state: Any) -> None:
        try:
            flush_model_calls()
            safe = StagePayload.model_validate(
                safe_stage(state)
            ).model_dump(mode="json")
            updates.put_nowait(safe)
        except (ValueError, queue.Full):
            missed[0] += 1

    def write_updates() -> None:
        while True:
            try:
                safe = updates.get(timeout=0.5)
            except queue.Empty:
                if finished.is_set():
                    return
                continue
            try:
                if safe is None:
                    return
                if not lost.is_set():
                    repository.publish_progress(claim, owner, safe)
            except LostLease:
                lost.set()
            except Exception:
                missed[0] += 1
            finally:
                updates.task_done()

    def approver(proposal: Any) -> tuple[bool, str]:
        alive()
        safe = ReviewProposal(
            proposal_id=int(proposal.proposal_id),
            machine_id=str(proposal.machine_id)[:80],
            action=str(proposal.action)[:160],
            reason=str(proposal.reason)[:600],
            predicted_effect=str(getattr(proposal, "predicted_effect", "") or "")[:600],
        )
        repository.request_review(claim, owner, safe, timeout_seconds=review_seconds)
        record("review_requested", claim=claim)
        deadline = time.monotonic() + review_seconds
        status = "pending"
        while time.monotonic() < deadline:
            alive()
            status = repository.review_status(claim, owner, safe.proposal_id)
            if status != "pending":
                break
            stop.wait(1)
        alive()
        if status == "pending":
            status = repository.review_status(claim, owner, safe.proposal_id)
        repository.resume_review(claim, owner)
        record("review_decided", claim=claim)
        if status == "approve":
            alive()  # The last check before simulator-side authorization.
            return True, "approved by authorized reviewer"
        return False, "rejected or review expired"

    beats = threading.Thread(target=heartbeat, daemon=True, name="hosted-lease")
    writer = threading.Thread(target=write_updates, daemon=True, name="hosted-progress")
    beats.start()
    writer.start()
    try:
        check_strategy(claim.effective_config)
        # #297 lands independently. Until its module is integrated, do not
        # fabricate model-call data or block the existing Graph workflow.
        try:
            from capstone.api.model_calls import SafeModelCall  # noqa: F401
        except ImportError:
            record("model_telemetry_unavailable", claim=claim)
        else:
            monitor_enabled[0] = True
            emit_model("model.monitor", {"schema_version": 1})
        from capstone.agent.completion import AuditLog
        from capstone.episode import run_episode
        from capstone.experiment import model_policy_factory, open_manual
        from capstone.observability import EventLogger

        with tempfile.TemporaryDirectory(prefix="capstone-worker-") as root:
            audit = Path(root) / "audit.jsonl"
            trace = Path(root) / "trace.jsonl"
            manual = (
                open_manual(claim.request.manual)
                if claim.request.manual != "none" else None
            )
            try:
                policy = model_policy_factory(
                    with_recall=False, with_manual=manual is not None,
                    tree_of_thought=claim.request.tree_of_thought,
                )()
            except Exception as exc:
                from capstone.providers.chat import ModelError

                missing = (
                    isinstance(exc, ModelError)
                    and str(exc).startswith("set ")
                    and "_API_KEY" in str(exc)
                )
                emit_model("model.config", {
                    "schema_version": 1,
                    "outcome": "missing_credentials" if missing else "invalid_configuration",
                })
                raise
            policy_holder[0] = policy
            emit_model("model.config", {"schema_version": 1, "outcome": "configured"})
            with trace.open("w", encoding="utf-8") as stream:
                stream.write('{"event":"worker.started"}\n')
                result = run_episode(
                    claim.request.seed, policy, kind=claim.request.kind,
                    triage=claim.request.mode == "triage",
                    hazards=claim.request.hazards, manual=manual, watch=watch,
                    log=AuditLog(audit), event_logger=EventLogger(
                        stream, name="hosted-" + str(claim.run_id)
                    ), approver=approver, run_key="hosted/" + str(claim.run_id),
                )
            alive()
            flush_model_calls()
            finish_model_monitor()
            # Audit and safe trace must be committed before completed status.
            repository.store_artifacts(
                claim, owner,
                {"audit": audit.read_bytes(), "observability": trace.read_bytes()},
            )
            final = StagePayload.model_validate(
                safe_stage(result.state)
            ).model_dump(mode="json")
            triage = result.triage or (
                result.state if result.state.mode == "triage" else None
            )
            report = (
                triage.triage_report.model_dump(mode="json")
                if triage is not None and triage.triage_report is not None else None
            )
            finished.set()
            writer.join(timeout=5)
            alive()
            if missed[0]:
                # Optional observer failures must not fail the investigation.
                try:
                    repository.publish_resync(
                        claim, owner, min(missed[0], 1_000_000)
                    )
                except LostLease:
                    raise
                except Exception:
                    record("progress_dropped", claim=claim, count=missed[0])
            repository.publish_progress(claim, owner, final)
            repository.transition(
                claim, owner, "completed", "run.completed", {
                    "status": "completed", "mode": claim.request.mode,
                    "investigation": final, "triage_report": report,
                    "diagnosis": (
                        result.state.conclusion.diagnosis[:1000]
                        if result.state.conclusion is not None else None
                    ),
                    "recommendation": (
                        result.state.conclusion.recommendation
                        if result.state.conclusion is not None else None
                    ),
                    "action_executed": result.state.action_started_tick is not None,
                    "verification_outcome": (
                        result.state.verification.outcome
                        if result.state.verification is not None else None
                    ),
                    "deep_ran": (
                        result.triage is not None and result.state is not result.triage
                    ),
                    "review_count": len(result.desk.proposals()),
                },
            )
        record("finished", claim=claim,
               duration_ms=int((time.monotonic() - started) * 1000))
        if missed[0]:
            record("progress_dropped", claim=claim, count=missed[0])
    except LostLease:
        record("lease_lost", claim=claim)
        # Expiry recovery interrupts the run; never automatically rerun it.
    except Exception as error:
        record("failed", claim=claim)
        try:
            flush_model_calls()
            finish_model_monitor()
        except LostLease:
            pass
        except Exception:
            pass
        try:
            if not lost.is_set() and not stop.is_set():
                repository.transition(claim, owner, "failed", "run.failed", {
                    "status": "failed", "mode": claim.request.mode,
                    "error_class": type(error).__name__[:80],
                })
        except Exception:
            pass  # Never expose provider/SQL errors or overwrite another lease.
    finally:
        finished.set()
        try:
            updates.put_nowait(None)
        except queue.Full:
            pass
        writer.join(timeout=5)
        beats.join(timeout=heartbeat_seconds + 1)


def serve_worker(
    repository: RunRepository, *, stop: threading.Event | None = None,
    poll_seconds: float = 1.5, max_jobs: int | None = None,
) -> None:
    """One active run per process; DB SKIP LOCKED prevents duplicate claims."""
    if not 0.2 <= poll_seconds <= 30:
        raise ValueError("Invalid polling interval")
    stop = stop or threading.Event()
    owner = "worker:" + uuid.uuid4().hex
    completed, failures = 0, 0
    if not repository.ready():
        raise RuntimeError("Hosted database not migrated")
    record("ready")
    while not stop.is_set():
        try:
            recovered = repository.recover_expired()
            if recovered:
                record("recovered", count=len(recovered))
            claim = repository.claim(owner)
            failures = 0
        except Exception:
            failures += 1
            record("poll_failed")
            stop.wait(min(30, 2 ** min(5, failures)))
            continue
        if claim is None:
            stop.wait(poll_seconds)
            continue
        record(
            "claimed", claim=claim,
            queue_wait_ms=claim.queue_wait_ms, attempt=claim.attempt,
        )
        execute_claim(repository, claim, owner, stop=stop)
        completed += 1
        if max_jobs is not None and completed >= max_jobs:
            return


def main() -> None:
    """Explicitly opted-in Render background worker; does not expose a port."""
    if os.getenv("CAPSTONE_WORKER_ENABLED") != "1":
        raise RuntimeError("CAPSTONE_WORKER_ENABLED=1 must be set")
    database_url = os.getenv("CAPSTONE_UI_RUN_DATABASE_URL") or ""
    if not database_url:
        raise RuntimeError("Missing private hosted PostgreSQL URL")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stop = threading.Event()

    def signal_stop(_signum: int, _frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    repository = RunRepository(database_url)
    try:
        serve_worker(repository, stop=stop)
    finally:
        repository.close()
