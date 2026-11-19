# PR D — Field acceptance, reliability and observability (P0-15/16, P1-01–10)

**DEPENDENCY: PR C → PR B → PR A → PR #307.** **DRAFT, NOT READY TO MERGE.** Initial commit is the acceptance implementation contract, not evidence of a live successful VF-4 pilot.

## Scope
End-to-end offline replay and field-readiness verification for Haas VF-4 NGC, plus operational alerting, tracing and recovery. Preserve Render's two-service deployment and #307 worker/journal contract; do not route CNC traffic to hosted API. Read-only, shop-authorized, on-site laptop is the only initial collector.

## Implementation tasks
- [ ] Pydantic `FieldAcceptanceManifest`/`ReadinessReport` and staged fail-closed gates: consent/approved host, controller generation+firmware, endpoint, device identity, probe hash, item scope, sample freshness, calibration, safety, retention/egress, technician sign-off.
- [ ] Offline fixture corpus: actual documented Haas-shaped MTConnect XML + anonymized approved on-machine samples when acquired; ensure source/version/provenance and any licensing rights; no invented data.
- [ ] Replay complete GET /probe → current → sample → JSONL+checkpoint → channel map → qualified signals → detector → incident → Graph tool calls → model Conclude (mocked in CI); assert errors, unknowns, no future leakage, no CNC writes.
- [ ] Explicit negative scenarios: proxy/redirect/host mismatch, malformed XML/header/sequence/response size, timeout, disconnect, duplicate, restart, buffer loss, sink full, partial corrupt line, stale, UNAVAILABLE, wrong scale, false anomaly, model failure, worker restart, absent capability.
- [ ] Structured safe EventLogger/OTel/optional Logfire spans: `capture_session_id → incident_id → run_id → investigation_id → evidence_id`; counters for bytes, rate, gaps, rejections, qualified windows, alerts, tool failures, Conclude outcomes. **No raw responses, prompts, programs, secrets, alarm text, or telemetry values in logs.** Trace attributes are bounded-cardinality; versioned private diagnostic artifacts separate from public API.
- [ ] Health/readiness and operator report: blocked/degraded/qualified, reason codes, collector/clock/storage/calibration status. 24h simulated soak/recovery scenario with bounded storage and restart, plus longer shop-approved pilot only after signoff.
- [ ] PydanticAI/Graph docs alignment for all typed boundaries, graph transitions and possible optional Agent/RunContext only for justified model-facing code; reuse existing Settings and publisher, no redundant framework wrappers.
- [ ] Run Ruff, focused tests, full pytest, Siemens/OEM and render API/worker tests, frontend privacy tests, offline SNAP and source-matched inventory rebuild. Record actual logs/workflow URLs; never claim green from static review.
- [ ] Before ready/merge, verify all dependency PRs accepted and final #307 head integrated, replay/soak passed, exact machine configuration and technician approval evidenced. P0 field compatibility remains UNKNOWN until physical visit.

## Iterative implementation rule
Write smallest failing test → inspect #307 + A/B/C files and dependencies → check official Haas/Pydantic docs → minimal code → focused test → inspect safe logs → repeat. Cite documentation:
- https://www.haascnc.com/service/online-manuals/next-gen-control-electrical---service-manual/ngc---machine-data-collection.html
- https://pydantic.dev/docs/ai/production/observability/
- https://pydantic.dev/docs/ai/graph/graph/

**Handoff:** read `docs/haas_vf4/PR_D_ACCEPTANCE_OBSERVABILITY.md`, PR #307 and preceding A/B/C. Never merge all stacked PRs as independent unrebased diffs.
