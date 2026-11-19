"""Versioned, single-host FastAPI read models for the industrial frontend.

No controller or model is contacted by this module; all data comes from explicitly
configured local files. Pilot mode has no action, approval or evaluation routes.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import threading
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from capstone.api.access import roles_for
from capstone.api.config import UiConfig
from capstone.api.readers import (
    mtconnect_snapshot,
    project_operational_event,
    recent_lines,
    recorder_snapshot,
    safe_evaluations,
    safe_investigation_detail,
    safe_investigations,
    safe_memory_promotions,
    safe_scorecards,
    signal_samples,
)
from capstone.api.runs import (
    InvalidRunEnvironment,
    ReviewDecision,
    RunRequest,
    SimulatorRuns,
    StaleRunConfiguration,
    public_run_configuration,
)
from capstone.settings import get_settings
from capstone.triage_run_controls import resolve_triage_run

Workspace = Literal["simulator", "pilot"]

# Fixed 403 messages, each naming the token the action needs. The browser shows
# only these exact strings, so no other server detail reaches the page.
ROLE_DENIED = {
    "operator": "Starting a run needs the operator token (CAPSTONE_UI_RUN_TOKEN)",
    "reviewer": "Review decisions need the reviewer token (CAPSTONE_UI_REVIEW_TOKEN)",
    "evaluator": "Evaluation records need the evaluator token "
    "(CAPSTONE_UI_EVALUATOR_TOKEN)",
}

# Deliberate allowlist: nothing from the process environment is serialized by default.
PUBLIC_SETTING_FIELDS = {
    # Only explicitly reviewed, nonsecret scalar Settings fields are exposed.
    "TRIAGE": "triage",
    "TRIAGE_SECONDS": "triage_seconds",
    "TRIAGE_TOOL_CALLS": "triage_tool_calls",
    "TRIAGE_PLAN": "triage_plan",
    "TRIAGE_RUN_MODE": "triage_run_mode",
    "TRIAGE_HYPOTHESIZE": "triage_hypothesize",
    "TRIAGE_PACKET": "triage_packet",
    "TRIAGE_PACKET_PROMPT": "triage_packet_prompt",
    "TRIAGE_OBSERVE_CALLS": "triage_observe_calls",
    "TRIAGE_INVESTIGATE": "triage_investigate",
    "TRIAGE_EVIDENCE_TESTS": "triage_evidence_tests",
    "TRIAGE_CONCLUDE_BRIEF": "triage_conclude_brief",
    "TRIAGE_CONCLUDE_CAP": "triage_conclude_cap",
    "TRIAGE_HYPOTHESIS_SECONDS": "triage_hypothesis_seconds",
    "TRIAGE_THEN_DEEP": "triage_then_deep",
    "STEP_QUESTIONS": "step_questions",
    "DECIDE_CALLS": "decide_calls",
    "CRITIC": "critic",
    "CRITIC_BLIND": "critic_blind",
    "CRITIC_FOLLOWUP": "critic_followup",
    "MANUAL_STEP": "manual_step",
    "MEMORY_RETRIEVAL_MODE": "memory_retrieval_mode",
    "MIN_ACTION_CONFIDENCE": "min_action_confidence",
    "MODEL_REQUEST_SECONDS": "model_request_seconds",
}


def create_app(config: UiConfig | None = None) -> FastAPI:
    """Construct a read-only app; injected config keeps tests isolated."""
    # Variables:
    #   cfg: Immutable, validated server-side path and authentication authority.
    #   authorize: Bearer-token boundary for configured private data.
    #   require_role: Operator/reviewer check whose error names the token needed.
    cfg = config if config is not None else UiConfig.from_env()
    runner = None
    if cfg.runs_enabled:
        if cfg.run_backend == "hosted":
            from capstone.api.hosted_runs import HostedSimulatorRuns

            assert cfg.run_database_url is not None
            runner = HostedSimulatorRuns(cfg.run_database_url)
        elif cfg.run_backend == "postgres":
            from capstone.api.postgres_runs import PostgresSimulatorRuns

            assert cfg.run_database_url is not None and cfg.run_db is not None
            runner = PostgresSimulatorRuns(cfg.run_database_url, cfg.run_db.parent)
        else:
            assert cfg.run_db is not None
            runner = SimulatorRuns(cfg.run_db)
    memory_instance = None  # Lazy server-owned service, never built on every poll.
    memory_lock = threading.Lock()
    app = FastAPI(
        title="Manufacturing Research Assistant | Industrial Console",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.on_event("shutdown")
    def shutdown_runner() -> None:
        if runner is not None:
            runner.close()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
        ]
        + ([cfg.browser_origin] if cfg.browser_origin else []),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
        ],
        allow_credentials=False,
    )

    def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
        """Deny access if a configured private source requires a session token."""
        if cfg.token is None:
            return
        supplied = (authorization or "").removeprefix("Bearer ")
        if not any(
            hmac.compare_digest(supplied, key)
            for key in (cfg.token, cfg.run_token, cfg.review_token, cfg.evaluator_token)
            if key
        ):
            raise HTTPException(status_code=401, detail="Session token required")

    Access = Depends(authorize)

    def require_role(
        authorization: str | None, role: Literal["operator", "reviewer"]
    ) -> None:
        if runner is None:
            raise HTTPException(
                status_code=403, detail="Managed simulator execution is not configured"
            )
        # Variables:
        #   expected: The one token this action accepts; the viewer token and
        #     the other role's token are refused.
        provided = (authorization or "").removeprefix("Bearer ")
        expected = cfg.run_token if role == "operator" else cfg.review_token
        if not expected or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=403, detail=ROLE_DENIED[role])

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

    @app.get("/api/v1/access/whoami")
    def whoami(authorization: Annotated[str | None, Header()] = None) -> dict:
        """Name the roles the supplied token holds, never the tokens themselves."""
        # Variables:
        #   open: True when no viewer token is configured, so reads need none.
        #   roles: Every role whose configured token equals the supplied one.
        supplied = (authorization or "").removeprefix("Bearer ")
        return {
            "open": cfg.token is None,
            "roles": roles_for(supplied, cfg),
            "runs_enabled": runner is not None,
        }

    @app.get("/api/v1/ready")
    def readiness() -> dict:
        """Schema-aware HTTP readiness, not proof of worker availability."""
        if cfg.runs_enabled and cfg.run_backend == "hosted":
            try:
                if runner is None or not runner.ready():
                    raise RuntimeError("Hosted schema unavailable")
            except Exception:
                raise HTTPException(
                    status_code=503, detail="Hosted database unavailable"
                ) from None
        return {"status": "ready", "service": "fastapi"}

    @app.get("/api/v1/capabilities", dependencies=[Access])
    def capabilities() -> dict:
        return {
            "schema_version": 1,
            "workspaces": ["simulator", "pilot"],
            "sources": {
                "siemens_capture": cfg.capture is not None and cfg.capture.is_file(),
                "mtconnect_capture": cfg.mtconnect is not None
                and cfg.mtconnect.is_file(),
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
                "neon_manual_search": cfg.neon_manual_enabled,
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
        return {
            "availability": "available" if items else "not_configured",
            "items": items,
        }

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
            if not cfg.evaluator_token or not hmac.compare_digest(
                provided, cfg.evaluator_token
            ):
                raise HTTPException(status_code=403, detail=ROLE_DENIED["evaluator"])

    @app.get("/api/v1/evaluations", dependencies=[Access])
    def evaluations(
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        if workspace != "simulator" or not cfg.evaluator:
            raise HTTPException(
                status_code=403, detail="Evaluator-only simulator records"
            )
        require_evaluator(authorization)
        return {
            "availability": "available"
            if cfg.experiment and cfg.experiment.is_file()
            else "not_configured",
            "items": safe_evaluations(cfg.experiment),
        }

    @app.get("/api/v1/evaluations/scorecards", dependencies=[Access])
    def evaluation_scorecards(
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        if workspace != "simulator" or not cfg.evaluator:
            raise HTTPException(
                status_code=403, detail="Evaluator-only simulator scorecards"
            )
        require_evaluator(authorization)
        return {
            "availability": "available"
            if cfg.experiment and cfg.experiment.is_file()
            else "not_configured",
            "items": safe_scorecards(cfg.experiment),
        }

    @app.get("/api/v1/system", dependencies=[Access])
    def system() -> dict:
        snap = recorder_snapshot(cfg.capture)
        return {
            "api": "available",
            "simulation_worker": (
                "separate_worker_unverified"
                if cfg.run_backend == "hosted" and runner is not None
                else ("enabled" if runner is not None else "not_integrated")
            ),
            "run_queue": (
                runner.queue_metrics()
                if cfg.run_backend == "hosted" and runner is not None
                else None
            ),
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

    @app.get("/api/v1/system/integrations", dependencies=[Access])
    def integration_contracts() -> dict:
        """Report exact Pydantic source-contract coverage, not deployment health."""
        from capstone.api.integration_status import inspect_hosted_contracts

        return inspect_hosted_contracts().model_dump(mode="json")

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
        """Validated global scalars, including .env defaults; never credentials."""
        # Variables:
        #   settings: The validated Settings, so values shown match what a run
        #     would use, including .env defaults the process environment lacks.
        #   effective: The server's default triage profile after the
        #     deterministic switch is applied, shown as profile and stage modes.
        settings = get_settings()
        effective = resolve_triage_run(settings)
        return {
            "editable": False,
            "items": [
                {
                    "name": name,
                    "value": (
                        "on"
                        if value is True
                        else "off"
                        if value is False
                        else str(value)
                    ),
                    # Only process-level override marker; .env stays private.
                    "configured": name in os.environ,
                }
                for name, attr in PUBLIC_SETTING_FIELDS.items()
                for value in (getattr(settings, attr),)
            ],
            "triage_profile": effective.model_dump(mode="json"),
            "triage_stage_modes": effective.stage_modes(),
            "conclude": "model-backed",
        }

    @app.get("/api/v1/knowledge/manuals", dependencies=[Access])
    def search_simulator_manual(
        workspace: Workspace = "simulator",
        q: str | None = Query(default=None, max_length=120),
    ) -> dict:
        """Only simulator manual, checked for leaks; no OEM/pilot claims."""
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot manuals require OEM authorization"
            )
        if cfg.neon_manual_enabled:
            from capstone.manual.neon import open_neon_manual

            store = None
            try:
                store = open_neon_manual()
                matches = (
                    store.search(q, limit=5)
                    if q and q.strip()
                    else store.list_sections(limit=35)
                )
            except Exception:
                raise HTTPException(
                    status_code=503, detail="Approved manual store unavailable"
                ) from None
            finally:
                if store is not None:
                    store.close()
        else:
            from capstone.manual.index import KeywordManualSearch
            from capstone.manual.sections import load_manual

            sections = load_manual()
            matches = (
                KeywordManualSearch(sections).search(q, limit=12)
                if q and q.strip()
                else sections[:35]
            )
        return {
            "availability": "available",
            "document_id": "SIM-CNC-001",
            "source_scope": "simulator_manual_only",
            "backend": "neon" if cfg.neon_manual_enabled else "local",
            "items": [
                {
                    "citation": section.citation,
                    "section_id": section.section_id,
                    "title": section.title[:160],
                    "revision": section.revision,
                    "text": section.text[:1800],
                }
                for section in matches
            ],
        }

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
            memories = (
                memory_instance.search(q, limit=limit)
                if q and q.strip()
                else memory_instance.retrieve(MemoryQuery(limit=limit))
            )
        except (Exception, SystemExit):
            raise HTTPException(
                status_code=503, detail="Approved memory store unavailable"
            ) from None
        safe = []
        for memory in memories:
            intervention = getattr(memory, "intervention", None)
            action = getattr(memory, "action", None)
            verification = getattr(memory, "verification", None)
            safe.append(
                {
                    "memory_id": str(memory.memory_id),
                    "investigation_id": str(
                        getattr(memory, "investigation_id", "") or ""
                    ),
                    "category": memory.category[:128],
                    "symptoms": [str(v)[:200] for v in memory.symptoms[:15]],
                    "diagnosis": memory.diagnosis[:600],
                    "action": action
                    if isinstance(action, str)
                    else (
                        intervention.action[:120] if intervention is not None else None
                    ),
                    "outcome": memory.outcome,
                    "lesson": memory.lesson[:600],
                    "source_tick": memory.source_tick,
                    "verification": getattr(verification, "status", None),
                    "source": "simulator_episodic_memory",
                }
            )
        return {"availability": "available", "items": safe}

    @app.get("/api/v1/knowledge/promotions", dependencies=[Access])
    def simulator_memory_promotions(
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict:
        if workspace != "simulator" or not cfg.evaluator:
            raise HTTPException(
                status_code=403, detail="Evaluator-only promotion decisions"
            )
        require_evaluator(authorization)
        return {
            "availability": "available"
            if cfg.experiment and cfg.experiment.is_file()
            else "not_configured",
            "items": safe_memory_promotions(cfg.experiment),
        }

    @app.get("/api/v1/knowledge", dependencies=[Access])
    def knowledge() -> dict:
        return {
            "availability": "not_integrated",
            "manuals": [],
            "memories": [],
            "message": (
                "Existing manual and memory providers have no authorized "
                "UI read adapter yet"
            ),
        }

    @app.get("/api/v1/lab/runs", dependencies=[Access])
    def list_managed_runs(workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot cannot execute simulator runs"
            )
        return {
            "availability": "available" if runner is not None else "not_integrated",
            "items": runner.list_runs() if runner is not None else [],
        }

    @app.get("/api/v1/lab/runs/configuration", dependencies=[Access])
    def managed_run_configuration(workspace: Workspace = "simulator") -> dict:
        """Validated defaults for the per-run editor; not global env editing."""
        # Variables:
        #   effective: The same resolver a submitted run uses, applied to the
        #     server defaults, so the editor starts from what would really run.
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot configuration is read-only"
            )
        if runner is None:
            raise HTTPException(
                status_code=503, detail="Simulator runner is not configured"
            )
        # Use the exact resolver as a submitted run. Values are all allowlisted.
        effective = resolve_triage_run(get_settings())
        return {
            "schema_version": 1,
            "defaults": effective.model_dump(mode="json"),
            "editable_per_run": True,
            "global_environment_editable": False,
        }

    @app.post("/api/v1/lab/runs/preview", dependencies=[Access])
    def preview_simulator_run(
        request: RunRequest, workspace: Workspace = "simulator"
    ) -> dict:
        """Side-effect-free preflight: same typed resolver as submission."""
        # Variables:
        #   request: The proposed run; an incompatible stage combination is a
        #     422, so the operator fixes it before any run is admitted.
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot simulator runs prohibited"
            )
        if runner is None:
            raise HTTPException(
                status_code=503, detail="Simulator runner is not configured"
            )
        try:
            return public_run_configuration(request, get_settings())
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Incompatible triage settings"
            ) from None

    @app.post("/api/v1/lab/runs", status_code=202)
    def start_simulator_run(
        request: RunRequest,
        workspace: Workspace = "simulator",
        authorization: Annotated[str | None, Header()] = None,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> dict:
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot machine control is prohibited"
            )
        require_role(authorization, "operator")
        if request.manual == "neon" and not cfg.neon_manual_enabled:
            raise HTTPException(
                status_code=403, detail="Neon manual retrieval not configured"
            )
        if idempotency_key is None or not re.fullmatch(
            r"[A-Za-z0-9_-]{16,96}", idempotency_key
        ):
            raise HTTPException(
                status_code=422,
                detail="A unique 16-96 character Idempotency-Key is required",
            )
        # Refuse a 202 if the explicitly selected manual is not published.
        # The worker must never begin relying on an empty or broken knowledge store.
        if request.manual == "neon":
            from capstone.manual.neon import open_neon_manual

            knowledge = None
            try:
                knowledge = open_neon_manual()
                if not knowledge.list_sections(limit=1):
                    raise LookupError("No published simulator manual")
            except Exception:
                raise HTTPException(
                    status_code=503, detail="Approved manual store unavailable"
                ) from None
            finally:
                if knowledge is not None:
                    knowledge.close()
        assert runner is not None
        # Variables:
        #   preview: The effective configuration resolved now, before the
        #     durable submission lock, so bad settings are a 422 and a changed
        #     server default (fingerprint mismatch) is a 409, not a stale run.
        #   created: The admitted run; on the hosted backend its ID is logged
        #     as a structured event for the separate worker's operators.
        # Wrong stage combinations are invalid input, not an idempotency
        # conflict. Validate before touching the durable submission lock.
        try:
            preview = public_run_configuration(request, get_settings())
        except ValueError:
            raise HTTPException(
                status_code=422, detail="Incompatible triage settings"
            ) from None
        if (
            request.configuration_fingerprint is not None
            and request.configuration_fingerprint != preview["fingerprint"]
        ):
            raise HTTPException(
                status_code=409,
                detail="Settings changed after preview; review before starting",
            )
        try:
            created = runner.submit(request, idempotency_key)
            if cfg.run_backend == "hosted":
                logging.getLogger("capstone.api").info(
                    "%s",
                    json.dumps(
                        {
                            "service": "fastapi",
                            "event": "run_submitted",
                            "run_id": created["run_id"],
                        },
                        separators=(",", ":"),
                    ),
                )
            return created
        except InvalidRunEnvironment:
            # A server fault (bad build commit or triage env var on this host),
            # not the caller's idempotency key or an active run.
            raise HTTPException(
                status_code=503, detail="Server run configuration is invalid"
            ) from None
        except StaleRunConfiguration:
            raise HTTPException(
                status_code=409,
                detail="Settings changed after preview; validate again",
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="Idempotency key belongs to another request"
            ) from None
        except RuntimeError:
            raise HTTPException(
                status_code=409, detail="A simulator run is already active"
            ) from None

    @app.get("/api/v1/lab/runs/{run_id}", dependencies=[Access])
    def managed_run(run_id: str, workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot run access is prohibited"
            )
        return ensure_run(run_id)

    @app.get("/api/v1/lab/runs/{run_id}/model-calls", dependencies=[Access])
    def managed_run_model_calls(
        run_id: str, workspace: Workspace = "simulator"
    ) -> dict:
        """Read #297's strictly validated, durable model-attempt timeline."""
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot model telemetry unavailable"
            )
        ensure_run(run_id)
        assert runner is not None
        try:
            return runner.model_calls(run_id)
        except Exception:
            # No raw SQL/provider errors, prompts or credentials in HTTP.
            raise HTTPException(
                status_code=503, detail="Model-call journal unavailable"
            ) from None

    @app.get("/api/v1/lab/runs/{run_id}/investigation", dependencies=[Access])
    def managed_run_investigation(
        run_id: str,
        workspace: Workspace = "simulator",
        phase: Literal["final", "triage", "deep"] = "final",
    ) -> dict:
        """Retrieve one completed phase by server-owned investigation id only.

        The legacy no-phase route remains the final investigation. Never accept
        client-supplied audit paths, run internals, or arbitrary investigation IDs.
        """
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot investigation access prohibited"
            )
        run = ensure_run(run_id)
        snapshot = run["snapshot"]
        final = snapshot.get("investigation")
        final = final if isinstance(final, dict) else {}
        target = None
        if phase == "final":
            target = final.get("investigation_id")
        else:
            progress = snapshot.get("progress")
            stages = progress if isinstance(progress, dict) else {}
            stage = stages.get(phase)
            if isinstance(stage, dict) and stage.get("mode") == phase:
                target = stage.get("investigation_id")
            # Legacy or triage-only records can have a final stage but no
            # phase-specific progress map. Never infer an absent earlier phase.
            if not isinstance(target, str) and final.get("mode") == phase:
                target = final.get("investigation_id")
        if not isinstance(target, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            target,
        ):
            return {"availability": "not_recorded", "detail": None, "phase": phase}
        assert runner is not None
        if cfg.run_backend == "hosted":
            detail = runner.investigation_detail(run_id, target)
        else:
            detail = safe_investigation_detail(
                runner.investigation_audit_path(run_id), target
            )
        return {
            "availability": "available" if detail is not None else "not_recorded",
            "detail": detail,
            "phase": phase,
        }

    @app.get("/api/v1/lab/runs/{run_id}/observability", dependencies=[Access])
    def managed_run_observability(
        run_id: str, workspace: Workspace = "simulator"
    ) -> dict:
        """Expose a bounded allowlist of metadata, never raw audit or provider text."""
        # Variables:
        #   items: Each stored line re-projected by project_operational_event,
        #     the one allowlist shared by hosted and local runs.
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot diagnostics unavailable")
        ensure_run(run_id)
        assert runner is not None
        if cfg.run_backend == "hosted":
            items = runner.observability_items(run_id)
            return {
                "availability": "available" if items is not None else "not_recorded",
                "window_scope": "bounded_recent_tail",
                "items": items or [],
            }
        path = runner.investigation_event_path(run_id)
        if not path.is_file():
            return {"availability": "not_recorded", "items": []}
        import json

        items = []
        for line in recent_lines(path, limit=500):
            try:
                raw = json.loads(line)
            except (ValueError, TypeError):
                continue
            entry = project_operational_event(raw)
            if entry is not None:
                items.append(entry)
        return {
            "availability": "available",
            "window_scope": "bounded_recent_tail",
            "items": items,
        }

    @app.get("/api/v1/lab/runs/{run_id}/triage", dependencies=[Access])
    def triage_result(run_id: str, workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot run access is prohibited"
            )
        row = ensure_run(run_id)
        report = row["snapshot"].get("triage_report")
        return {
            "availability": "available" if report is not None else "not_recorded",
            "run_id": run_id,
            "report": report,
        }

    @app.get("/api/v1/lab/runs/{run_id}/events", dependencies=[Access])
    async def run_events(
        run_id: str,
        workspace: Workspace = "simulator",
        since: int = Query(default=0, ge=0),
        last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    ) -> StreamingResponse:
        if workspace != "simulator":
            raise HTTPException(
                status_code=403, detail="Pilot stream access is prohibited"
            )
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
                    # #297 model-call envelopes are a separate, revalidated
                    # endpoint. Do not stream private attempt metadata in SSE.
                    if event["event"].startswith("model."):
                        continue
                    import json

                    payload = json.dumps(event["data"], separators=(",", ":"))
                    yield f"id: {cursor}\nevent: {event['event']}\ndata: {payload}\n\n"
                if not events:
                    yield ": keepalive\n\n"
                current = await asyncio.to_thread(runner.get, run_id)
                if (
                    current
                    and current["state"]
                    in {
                        "completed",
                        "failed",
                        "interrupted",
                        "expired",
                    }
                    and not events
                ):
                    # A recovered terminal run need not have a terminal event.
                    # Explicitly end replay so browser reconnects can stop.
                    yield (
                        "event: stream.closed\n"
                        'data: {"reason":"terminal_replay_complete"}\n\n'
                    )
                    break
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/simulator/reviews", dependencies=[Access])
    def pending_simulator_reviews(workspace: Workspace = "simulator") -> dict:
        if workspace != "simulator":
            raise HTTPException(status_code=403, detail="Pilot approval is prohibited")
        return {
            "availability": "available" if runner is not None else "not_integrated",
            "items": runner.pending_reviews() if runner is not None else [],
        }

    @app.post("/api/v1/simulator/reviews/{run_id}")
    def decide_simulator_review(
        run_id: str,
        decision: ReviewDecision,
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
            raise HTTPException(
                status_code=404, detail="Review request not found"
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=409, detail="Review is no longer pending"
            ) from None

    return app


app = create_app()
