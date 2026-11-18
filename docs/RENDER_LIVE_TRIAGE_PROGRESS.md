# Render live simulator progress contract (stacked on PR #293)

## Actual deployment boundary

This patch extends the existing **single-owner** `SimulatorRuns` and `PostgresSimulatorRuns` FastAPI worker path. It does not turn PR #292's R1 queue into a running agent service. The future two-service Render model still requires R2–R5 from `docs/RENDER_FASTAPI_AGENT_WORKER_SPLIT.md`: a separate worker, lease-checked events, reviewer signaling, recovery and production rollout. Do not point the frontend at PR #292's `RunRepository` as a drop-in replacement for `SimulatorRuns`. Its independent `_EVENT_FIELDS` allowlist and worker-facing event contract must be versioned and brought into parity as part of the eventual worker integration.

## Source-to-screen map

`run_episode` -> existing Pydantic Graph watcher -> `SafeStageSnapshot` (Pydantic v2, extra forbidden) -> bounded in-memory queue -> atomic SQLite/PostgreSQL `run_events` + run `snapshot.progress` -> versioned FastAPI `/lab/runs/{id}` GET and authenticated SSE `/events` -> React `LiveProgress`.

The visible progress is *observations about execution*, never a diagnosis. Read-only source metadata only:

| Contract fields | Authorized source | UI |
| --- | --- | --- |
| investigation_id, mode, stage, termination_reason, conclusion_available | typed `InvestigationState` and enum | phase and stage status |
| iteration_count, remaining_iterations, tool_calls, remaining_tool_calls | state budget counters | decisions and budgets |
| evidence_count, hypothesis_count, answered_question_count, decision_count | lengths of state containers | progress summary |
| repeated_calls, failed_tool_calls, malformed_results, interpretation_failures, unproductive_steps | existing loop counters | failure accounting |
| followup_tool_calls, screening_tool_calls, observe_tool_calls | read-budget counters | evidence collection |
| last_observed_tick, observation_cutoff_tick, clock_verified | admitted source-time state | source horizon, never a reading |
| triage_requirement_total/satisfied/open, triage_question_gaps | qualified requirement results | coverage summary |
| requirement_statuses (max 32), requirement_statuses_truncated | allowlisted requirement IDs, fixed status enum, evidence-reference count | per-requirement review |
| triage_evidence_accepted/rejected | precommit qualification count | rejected versus admitted |
| triage_decide_reads/stops, triage_candidates, triage_test_requirements, triage_test_records, triage_trace_events, triage_logging_failures | existing typed trace and candidate collections | deterministic route |
| packet_roster_verified, packet_roster_size, packet_screened_machines, packet_missing_machines | bounded evidence-packet roster | line coverage |
| packet_calls_mandatory/optional/qualified/unavailable, packet_items_qualified/missing | packet call/item statuses | source availability |
| deep_recommended | code-gated triage routing flag | escalation suggestion |

If the state lacks a field in an older run, React renders it as unavailable rather than inventing a zero. Totals always include the entire state even where per-requirement statuses are capped.

## Privacy and security boundary

- The live projection is **constructed field by field**; `InvestigationState.model_dump()`, unknown event keys, tool arguments, raw evidence, question wording, free-text requirement reasons, model prompts, provider responses, simulator hidden truth, anomaly fault labels, configuration secrets and storage URLs are never included.
- A question ID must match a short Q/R/T numeric identifier. A requirement ID must match a fixed code-like `Q#:name` or `Q#:job:#` pattern, never a free-text token.
- The 16+ telemetry counters are numeric aggregates, not raw readings. `SafeStageSnapshot` rejects unapproved properties before journal insertion. The API authentication and evaluator-only scorecard separation remain unchanged.
- Existing *completed authorized audit* and triage-report views are separate from the live stream and retain their pre-existing content/role rules; do not treat this progress patch as general approval to publish audit text or private plant data.

## Recovery semantics

- `stage.updated` is written atomically with the per-phase snapshot under the run lock in SQLite or PostgreSQL; triage and deep are independently retained.
- The worker reconciles final phase snapshots from the actual returned Graph states, not the queue's last successful event. This makes the final view correct when intermediate updates are dropped.
- No late `stage.updated` can alter a terminal completed/failed/interrupted run. The publisher catches storage and validation errors without failing the episode and coalesces unchanged state.
- The writer's flush is bounded; the final event is still authoritative. Missing intermediate updates are counted in a `resync.required` event if the journal remains available.
- SSE replays events via monotonically increasing DB sequence and `since` or `Last-Event-ID`. Terminal replay emits `stream.closed` even after restart interruption (which may not have a terminal row) to stop endless browser reconnect attempts.
- UI backend-switch and credential isolation remain intact. React polls the durable run record as the authoritative source even when SSE is delayed or unavailable.

## Release checks

1. Test both pure triage and triage-then-deep against the same simulator seed, including unavailable channels and missing-data cases.
2. Inject a wrong/secret-bearing question ID and unexpected fields into a test watcher: none may enter the journal, SSE or React.
3. Persist triage and deep snapshots across review, final result, browser refresh and service restart. Check that late writes cannot regress final state.
4. Verify SSE cursor after 100+ events, reconnect after a dropped response, terminal replay and all three terminal states.
5. Run full pytest, Ruff, frontend build/tests, source-matched evaluator inventory/SNAP, and disposable PostgreSQL journal integration.
6. Separately confirm on Render that a **single owner** process with the approved PostgreSQL migration and access tokens is configured. No live Render deployment, production database mutation or Siemens ingestion is asserted by this patch.

## Pydantic framework decision

The code already uses `GraphBuilder` and typed state/deps; its watcher is the right capture point. Pydantic's current Graph Builder documentation explicitly notes that graph state persistence is **not** automatic in V2; this project must continue to own its transactional journal and replay contract. No new agent, tracing exporter, automatic OpenTelemetry prompt capture or model call is required for safe progress. A future R2 worker should reuse this Pydantic projection at the worker->repository boundary under lease fencing, with independent durable post-commit event emission.
