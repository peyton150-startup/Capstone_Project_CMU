# PR C — Real-machine qualified read-only triage tools (P0-12–14)

**DEPENDENCY: PR B → PR A → PR #307**, stacked branch; **DRAFT**. Do not merge independently. Initial change contains a durable scope/acceptance contract.

## Current code + overlapping work
`recorded_investigation.py` creates replay catalog; `providers/replay.py` supports get_time, list_machines and numeric reads/summary/trend, refuses get_events/get_settings/get_line_screening/get_job_history/get_inspections/maintenance. `triage_decide.py` `READ_ONLY` includes event/maintenance/settings/job/inspection/summary, so a VF-4 recording cannot satisfy most deterministic fixed requirements. `agent/investigation.py` Observe correctly skips simulator screening in replay. PR #307 incorporates #299/#301/#306 and preserves #296 Decide trace and #297 model-call telemetry. **Never overwrite those implementations.**

## Implementation tasks
- [ ] Refresh PR #307 head and actual merged `TRIAGE_RUN_MODE=deterministic` effective settings; use its `GraphBuilder`/`StepContext` stages and typed `FactoryProvider`, NOT a second orchestrator.
- [ ] Build a capability registry from Pydantic-validated source+map+capture+quality, per machine/sensor/cutoff, no unsupported tools offered, and no source/epoch/window cross-talk.
- [ ] Build qualified MTConnect Events and Conditions → `get_events` using declared mapping, alarm activation/clear/unknown semantics and ID/time provenance. **Do not synthesize** `get_settings`, inspection/job/maintenance history or line peers if source lacks them; optional qualified records from separate authorized shop exports.
- [ ] Wire validated real detector results → a typed incident → fixed Plan/Observe → deterministic Investigate/Decide/Hypothesize/Test → **model-only Conclude**. Triage remains read-only; no propose/execute on CNC.
- [ ] Enforce quality, completeness, source/clock checks before evidence commit and before each tool; partial/missing/cutoff must never count as proof of normality. Avoid the simulator's numeric sensor shortcuts and false `down/idle` labels.
- [ ] Reuse Pydantic model validation (strict instrumented contracts), FactoryProvider/tool_spec, `triage_evidence_validation.py`, `triage_trace.py`, and PR #307's authoritative effective run settings/ModelPolicy; a new PydanticAI Agent only for justified model-facing Conclude integration after parity tests, never for deterministic reads.
- [ ] Logging/observability: `capture_session_id → incident_id → run_id → investigation_id → evidence_id`; selected tool, source, cutoff, capability denial, evidence quality, phase duration, model Conclude usage/errors. Redact credentials, filenames, program/alarm text and telemetry values; preserve #296/#297 journal scopes.
- [ ] Tests: stable deterministic read choices, event conversion/unknown state, explicit unsupported capability, future/late data denial, verified clock, multi-axis source collision, no-controller-write, model only Conclude, custom/deep parity, #307 API/worker nonregression.

## Repeatable micro-loop
For every unit: test → read #307 and A/B code → reread current Pydantic Graph/Agent Function Tools/dependencies/validators docs → minimal implementation → validate source/tool trace + focused tests → record evidence and repeat. Relevant docs: https://pydantic.dev/docs/ai/graph/graph/ and https://pydantic.dev/docs/ai/tools-toolsets/tools/ .
Acceptance requires safe full source→tool→conclusion replay and no false root-cause or no-action clearance from absent evidence. No actual VF-4 control access.
**Handoff:** read `docs/haas_vf4/PR_C_TRIAGE_TOOLS.md`, #307, A/B and PR C branch.
