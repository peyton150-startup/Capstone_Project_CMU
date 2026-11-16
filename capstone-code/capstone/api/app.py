"""Versioned, single-host FastAPI read models for the industrial frontend.

No controller or model is contacted by this module; all data comes from explicitly
configured local files. Pilot mode has no action, approval or evaluation routes.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import re
import threading
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from capstone.api.runs import RunRequest, ReviewDecision, SimulatorRuns

from capstone.api.config import UiConfig
from capstone.api.readers import (
    recent_lines,
    recorder_snapshot,
    mtconnect_snapshot,
    safe_evaluations,
    safe_scorecards,
    safe_memory_promotions,
    safe_investigation_detail,
    safe_investigations,
    signal_samples,
)

Workspace = Literal["simulator", "pilot"]

# Deliberate allowlist: nothing from the process environment is serialized by default.
PUBLIC_SETTING_NAMES = (
    "TRIAGE",
    "TRIAGE_SECONDS",
    "TRIAGE_PLAN",
    "TRIAGE_PACKET",
    "TRIAGE_INVESTIGATE",
    "TRIAGE_EVIDENCE_TESTS",
    "TRIAGE_THEN_DEEP",
    "STEP_QUESTIONS",
    "DECIDE_CALLS",
    "CRITIC",
    "CRITIC_BLIND",
    "CRITIC_FOLLOWUP",
    "MANUAL_STEP",
    "MEMORY_RETRIEVAL_MODE",
    "MIN_ACTION_CONFIDENCE",
    "MODEL_REQUEST_SECONDS",
)


def create_app(config: UiConfig | None = None) -> FastAPI:
    """Construct a read-only app; injected config keeps tests isolated."""
    # Variables:
    #   cfg: Immutable, validated server-side path and authentication authority.
    #   authorize: Bearer-token boundary for configured private data.
    cfg = config if config is not None else UiConfig.from_env()
    runner = SimulatorRuns(cfg.run_db) if cfg.runs_enabled and cfg.run_db is not None else None
    memory_instance = None  # Lazy server-owned service, never built on every poll.
    memory_lock = threading.Lock()
    app = FastAPI(
        title="Manufacturing Research Assistant | Industrial Console",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ],
        allow_methods=["GET"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
    )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        """Deny access if a configured private source requires a session token."""
        if cfg.token is None:
            return
        supplied = (authorization or "").removeprefix("Bearer ")
        if not any(hmac.compare_digest(supplied, key) for key in
                   (cfg.token, cfg.run_token, cfg.review_token, cfg.evaluator_token) if key):
            raise HTTPException(status_code=401, detail="Local session token required")

    Access = Depends(authorize)

    def require_role(authorization: str | None, role: Literal["operator", "reviewer"]) -> None:
        if runner is None:
            raise HTTPException(status_code=403, detail="Managed simulator execution is not configured")
        provided = (authorization or "").removeprefix("Bearer ")
        expected = cfg.run_token if role == "operator" else cfg.review_token
        if not expected or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail="Simulator role not authorized")

    def ensure_run(run_id: str) -> dict:
        if runner is None or not re.fullmatch(r"[a-f0-9-]{36}", run_id):
            raise HTTPException(status_code=404, detail="Run not found")
        run = runner.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    @app.get("/api/v1/health")
    def health() -> dict:
        return {
            "status": "api_available",
            "service": "industrial-console",
            "controller_connected": None,
        }

    @app.get("/api/v1/capabilities", dependencies=[Access])
    def capabilities() -> dict:
        return {
            "schema_version": 1,
            "workspaces": ["simulator", "pilot"],
            "sources": {
                "siemens_capture": cfg.capture is not None and cfg.capture.is_file(),
                "mtconnect_capture": cfg.mtconnect is not None and cfg.mtconnect.is_file(),
                "investigation_audit": cfg.investigations is not None
                and cfg.investigations.is_file(),
                "evaluations": cfg.evaluator
                and cfg.experiment is not None
                and cfg.experiment.is_file(),
            },
            "features": {
                "recording_view": cfg.capture is not None or cfg.mtconnect is not None,
                "investigation_history": cfg.investigations is not None,
                "evaluation_history": cfg.evaluator and cfg.experiment is not None,
                "simulation_run_launch": runner is not None,
                "simulation_approval": runner is not None,
                "manual_search": True,
                "episodic_memory": cfg.memory_enabled,
                "setting_changes": False,
                "siemens_live_subscription_confirmed": False,
            },
            "limits": [
                "pilot_read_only",
                "no_controller_commands",
                "no_unverified_diagnoses",
                "no_simulator_hidden_truth_in_investigations",
            ],
        }

    @app.get("/api/v1/overview", dependencies=[Access])
    def overview(workspace: Workspace = "simulator") -> dict:
        """No synthetic or inferred totals masquerading as shop measurements."""
        if workspace == "pilot":
            health_ = recorder_snapshot(cfg.capture, show_values=cfg.show_values)
            return {
                "workspace": workspace,
                "machines": 1 if cfg.capture and cfg.capture.is_file() else None,
                "incidents": None,
                "data_quality": None,
                "investigations": None,
                "recorder": health_.get("recorder"),
                "availability": health_["availability"],
            }
        investigations = safe_investigations(cfg.investigations)
        return {
            "workspace": workspace,
            "machines": None,
            "incidents": None,
            "data_quality": None,
            "investigations": len(investigations)
            if cfg.investigations is not None
            else None,
            "recorder": None,
            "availability": "available"
            if cfg.investigations and cfg.investigations.is_file()
            else "not_configured",
        }

    @app.get("/api/v1/machines", dependencies=[Access])
    def machines(workspace: Workspace = "simulator") -> dict:
        if workspace == "simulator":
            return {
                "availability": "not_configured",
                "items": [],
                "message": "Live simulator machine source is not connected to this API",
            }
        snap = recorder_snapshot(cfg.capture)
        if snap["availability"] != "available":
            return {
                "availability": snap["availability"],
                "items": [],
                "message": "No approved pilot recording available",
            }
        return {
            "availability": "available",
            "items": [
                {
                    "id": "authorized-cnc",
                    "name": cfg.machine_label,
                    "operating_state": "unknown",
                    "condition": "unknown",
                    "last_observed_at": snap["recorder"]["last_receive_at"],
                    "signal_count": len(snap["signals"]),
                }
            ],
        }

    @app.get("/api/v1/recordings", dependencies=[Access])
    def recordings() -> dict:
        siemens = recorder_snapshot(cfg.capture)
        legacy = mtconnect_snapshot(cfg.mtconnect)
        items = [x for x in (siemens["recorder"], legacy["recorder"]) if x is not None]
        return {"availability": "available" if items else "not_configured", "items": items}

    @app.get("/api/v1/recordings/mtconnect-local/health", dependencies=[Access])
    def mtconnect_health() -> dict:
        return mtconnect_snapshot(cfg.mtconnect, show_values=cfg.show_values)

    @app.get("/api/v1/recordings/siemens-local/health", dependencies=[Access])
    def recording_health() -> dict:
        return recorder_snapshot(cfg.capture, show_values=cfg.show_values)

    @app.get("/api/v1/recordings/siemens-local/events", dependencies=[Access])
    def recording_events() -> dict:
        snap = recorder_snapshot(cfg.capture)
        return {"availability": snap["availability"], "items": snap["events"]}

    @app.get("/api/v1/recordings/siemens-local/signals", dependencies=[Access])
    def recording_signals() -> dict:
        snap = recorder_snapshot(cfg.capture, show_values=cfg.show_values)
        return {"availability": snap["availability"], "items": snap["signals"]}

    @app.get("/api/v1/signals/{signal_id}/samples", dependencies=[Access])
    def samples(signal_id: str) -> dict:
        if len(signal_id) != 20 or any(
            ch not in "0123456789abcdef" for ch in signal_id
        ):
            raise HTTPException(status_code=404, detail="Unknown signal")
        snap = recorder_snapshot(cfg.capture)
        if not any(row["id"] == signal_id for row in snap["signals"]):
            raise HTTPException(status_code=404, detail="Unknown signal")
        return {
            "availability": snap["availability"],
            "window_scope": "bounded_recent_tail",
            "unit": None,
            "analysis_eligible": False,
            "items": signal_samples(
                cfg.capture, signal_id, show_values=cfg.show_values
            ),
        }

    @app.get("/api/v1/investigations", dependencies=[Access])
    def investigations(workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            return {"availability": "unsupported_for_pilot", "items": []}
        return {
            "availability": "available"
            if cfg.investigations and cfg.investigations.is_file()
            else "not_configured",
            "items": safe_investigations(cfg.investigations),
        }

    @app.get("/api/v1/investigations/{ident}", dependencies=[Access])
    def investigation(ident: str, workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot investigations require field acceptance"
            )
        result = safe_investigation_detail(cfg.investigations, ident)
        if result is None:
            raise HTTPException(
                status_code=404, detail="Investigation not found in configured audit"
            )
        return result

    def require_evaluator(authorization: str | None) -> None:
        # Legacy file-only evaluation requires CAPSTONE_UI_EVALUATOR plus local token.
        # With managed run roles, evaluator must have a distinct credential.
        if cfg.runs_enabled:
            provided = (authorization or "").removeprefix("Bearer ")
            if not cfg.evaluator_token or not hmac.compare_digest(provided, cfg.evaluator_token):
                raise HTTPException(status_code=403, detail="Evaluator role required")

    @app.get("/api/v1/evaluations", dependencies=[Access])
    def evaluations(workspace: Workspace = "simulator",
                    authorization: Annotated[str | None, Header()] = None) -> dict:
        if workspace != "simulator" or not cfg.evaluator:
            raise HTTPException(
                status_code=403, detail="Evaluator-only simulator records"
            )
        return {
            "availability": "available"
            if cfg.experiment and cfg.experiment.is_file()
            else "not_configured",
            "items": safe_evaluations(cfg.experiment),
        }

    @app.get("/api/v1/evaluations/scorecards", dependencies=[Access])
    def evaluation_scorecards(workspace: Workspace = "simulator",
                              authorization: Annotated[str | None, Header()] = None) -> dict:
        if workspace != "simulator" or not cfg.evaluator:
            raise HTTPException(status_code=403, detail="Evaluator-only simulator scorecards")
        require_evaluator(authorization)
        return {"availability": "available" if cfg.experiment and cfg.experiment.is_file()
                else "not_configured", "items": safe_scorecards(cfg.experiment)}

    @app.get("/api/v1/system", dependencies=[Access])
    def system() -> dict:
        snap = recorder_snapshot(cfg.capture)
        return {
            "api": "available",
            "simulation_worker": "enabled" if runner is not None else "not_integrated",
            "progress_stream": "enabled" if runner is not None else "not_integrated",
            "recorder_connection": snap["recorder"]["connection_state"]
            if snap["recorder"]
            else "not_configured",
            "recorder_sink": snap["recorder"]["sink_state"]
            if snap["recorder"]
            else "not_configured",
            "model_provider": "not_checked",
            "storage": "not_monitored",
        }

    @app.get("/api/v1/system/audit", dependencies=[Access])
    def system_audit() -> dict:
        """Return only safe lifecycle fields, not endpoint, account or error text."""
        items = []
        for line in recent_lines(cfg.audit, limit=200):
            try:
                import json

                raw = json.loads(line)
            except (ValueError, TypeError):
                continue
            if (
                isinstance(raw, dict)
                and raw.get("record_type") == "siemens_opcua_audit"
            ):
                items.append(
                    {
                        key: raw.get(key)
                        for key in ("at", "session_epoch", "stage", "outcome")
                    }
                )
        return {
            "availability": "available"
            if cfg.audit and cfg.audit.is_file()
            else "not_configured",
            "items": list(reversed(items)),
        }

    @app.get("/api/v1/settings/effective", dependencies=[Access])
    def settings_effective() -> dict:
        """A readonly whitelist; no API keys, certificates, filesystem paths or free text."""
        return {
            "editable": False,
            "items": [
                {
                    "name": name,
                    "value": os.environ.get(name),
                    "configured": name in os.environ,
                }
                for name in PUBLIC_SETTING_NAMES
            ],
        }

    @app.get("/api/v1/knowledge/manuals", dependencies=[Access])
    def search_simulator_manual(
        workspace: Workspace = "simulator",
        q: str | None = Query(default=None, max_length=120),
    ) -> dict:
        """Only simulator manual, checked for leaks; no OEM/pilot claims."""
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot manuals require OEM authorization")
        from capstone.manual.sections import load_manual
        from capstone.manual.index import KeywordManualSearch

        sections = load_manual()
        matches = (KeywordManualSearch(sections).search(q, limit=12)
                   if q and q.strip() else sections[:35])
        return {"availability": "available", "document_id": "SIM-CNC-001",
                "source_scope": "simulator_manual_only",
                "items": [{"citation": section.citation,
                           "section_id": section.section_id,
                           "title": section.title[:160],
                           "revision": section.revision,
                           "text": section.text[:1800]} for section in matches]}

    @app.get("/api/v1/knowledge/memories", dependencies=[Access])
    def simulator_memories(
        workspace: Workspace = "simulator",
        q: str | None = Query(default=None, max_length=120),
        limit: int = Query(default=20, ge=1, le=50),
    ) -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot memory not authorized")
        if not cfg.memory_enabled:
            return {"availability": "not_integrated", "items": []}
        from capstone.experiment import open_memory
        from capstone.memory.contracts import MemoryQuery

        nonlocal memory_instance
        try:
            if memory_instance is None:
                with memory_lock:
                    if memory_instance is None:
                        memory_instance = open_memory()
            memories = (memory_instance.search(q, limit=limit) if q and q.strip()
                        else memory_instance.retrieve(MemoryQuery(limit=limit)))
        except (Exception, SystemExit):
            raise HTTPException(status_code=503, detail="Approved memory store unavailable") from None
        safe = []
        for memory in memories:
            intervention = getattr(memory, "intervention", None)
            action = getattr(memory, "action", None)
            verification = getattr(memory, "verification", None)
            safe.append({
                "memory_id": str(memory.memory_id),
                "investigation_id": str(getattr(memory, "investigation_id", "") or ""),
                "category": memory.category[:128],
                "symptoms": [str(v)[:200] for v in memory.symptoms[:15]],
                "diagnosis": memory.diagnosis[:600],
                "action": action if isinstance(action, str) else
                    (intervention.action[:120] if intervention is not None else None),
                "outcome": memory.outcome,
                "lesson": memory.lesson[:600],
                "source_tick": memory.source_tick,
                "verification": getattr(verification, "status", None),
                "source": "simulator_episodic_memory",
            })
        return {"availability": "available", "items": safe}

    @app.get("/api/v1/knowledge/promotions", dependencies=[Access])
    def simulator_memory_promotions(
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        if workspace != "simulator" or not cfg.evaluator:
            raise HTTPException(status_code=403, detail="Evaluator-only promotion decisions")
        require_evaluator(authorization)
        return {"availability": "available" if cfg.experiment and cfg.experiment.is_file()
                else "not_configured", "items": safe_memory_promotions(cfg.experiment)}

    @app.get("/api/v1/knowledge", dependencies=[Access])
    def knowledge() -> dict:
        return {
            "availability": "not_integrated",
            "manuals": [],
            "memories": [],
            "message": "Existing manual and memory providers have no authorized UI read adapter yet",
        }


    @app.get("/api/v1/lab/runs", dependencies=[Access])
    def list_managed_runs(workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot cannot execute simulator runs")
        return {"availability": "available" if runner is not None else "not_integrated",
                "items": runner.list_runs() if runner is not None else []}

    @app.post("/api/v1/lab/runs", status_code=202)
    def start_simulator_run(
        request: RunRequest,
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot machine control is prohibited")
        require_role(authorization, "operator")
        if idempotency_key is None or not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", idempotency_key):
            raise HTTPException(status_code=422, detail="A unique 16-96 character Idempotency-Key is required")
        assert runner is not None
        try:
            return runner.submit(request, idempotency_key)
        except ValueError:
            raise HTTPException(status_code=409, detail="Idempotency key belongs to another request") from None
        except RuntimeError:
            raise HTTPException(status_code=409, detail="A simulator run is already active") from None

    @app.get("/api/v1/lab/runs/{run_id}", dependencies=[Access])
    def managed_run(run_id: str, workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot run access is prohibited")
        return ensure_run(run_id)

    @app.get("/api/v1/lab/runs/{run_id}/investigation", dependencies=[Access])
    def managed_run_investigation(run_id: str, workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot investigation access prohibited")
        run = ensure_run(run_id)
        assert runner is not None
        path = runner.investigation_audit_path(run_id)
        target = (run["snapshot"].get("investigation") or {}).get("investigation_id")
        if not isinstance(target, str):
            return {"availability": "not_recorded", "detail": None}
        return {"availability": "available" if (detail := safe_investigation_detail(path, target))
                else "not_recorded", "detail": detail}

    @app.get("/api/v1/lab/runs/{run_id}/triage", dependencies=[Access])
    def triage_result(run_id: str, workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot run access is prohibited")
        row = ensure_run(run_id)
        report = row["snapshot"].get("triage_report")
        return {"availability": "available" if report is not None else "not_recorded",
                "run_id": run_id, "report": report}

    @app.get("/api/v1/lab/runs/{run_id}/events", dependencies=[Access])
    async def run_events(
        run_id: str, workspace: Workspace = "simulator",
        since: int = Query(default=0, ge=0),
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot stream access is prohibited")
        ensure_run(run_id)
        cursor = since
        if last_event_id and re.fullmatch(r"[0-9]{1,12}", last_event_id):
            cursor = max(cursor, int(last_event_id))

        async def stream():
            nonlocal cursor
            yield "retry: 2000\n\n"
            while True:
                assert runner is not None
                events = await asyncio.to_thread(runner.events_since, run_id, cursor)
                for event in events:
                    cursor = event["seq"]
                    import json
                    payload = json.dumps(event["data"], separators=(",", ":"))
                    yield f"id: {cursor}\nevent: {event['event']}\ndata: {payload}\n\n"
                if not events:
                    yield ": keepalive\n\n"
                current = await asyncio.to_thread(runner.get, run_id)
                if current and current["state"] in {"completed", "failed", "interrupted"} and not events:
                    break
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/api/v1/simulator/reviews", dependencies=[Access])
    def pending_simulator_reviews(workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot approval is prohibited")
        return {"availability": "available" if runner is not None else "not_integrated",
                "items": runner.pending_reviews() if runner is not None else []}

    @app.post("/api/v1/simulator/reviews/{run_id}")
    def decide_simulator_review(
        run_id: str, decision: ReviewDecision,
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot approval is prohibited")
        require_role(authorization, "reviewer")
        ensure_run(run_id)
        assert runner is not None
        try:
            return runner.decide(run_id, decision)
        except LookupError:
            raise HTTPException(status_code=404, detail="Review request not found") from None
        except ValueError:
            raise HTTPException(status_code=409, detail="Review is no longer pending") from None

    return app


app = create_app()
