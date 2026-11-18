# PR B — Qualified signal identity → deterministic real-data detector (P0-07–11)

**DEPENDENCY: PR A → PR #307.** Branch based on PR A, not main. **DRAFT, DO NOT MERGE.** Initial commit documents work only; actual quality and detector claims require tests and approved field fixtures.

## Problem / current repo
`capstone/ingestion/channel_map.py` builds probe-hashed manual map but legacy `ToolSensor` has one type/machine. `record.py.number()` permits nonfinite floats; `providers/replay.py._rows` and `_visible` require end-to-end quality/order audit. `tools/screening.py` uses simulator healthy_reference.json (running_load=15), **not a qualified Haas baseline**. PR #195/198/199/200 discuss planned CPU detector; do not pretend it's live. `agent/monitor.py` monitors simulated events, not MTConnect.

## Implementation tasks
- [ ] Re-inspect #307 + PR A current code/contract and docs before each small commit, specifically ingestion record/quality/time_stats/channel_map, replay provider, screening, incident context and triage.
- [ ] Pydantic v2 frozen typed `SourceIdentity`/`QualifiedObservation`/`SignalCatalogEntry`/`QualityVerdict`, with source URI fingerprint, machine, component, axis/spindle, dataItemId, unit/nativeScale, mapping revision, source timestamp, receive timestamp, quality/coverage, epoch and provenance. Explicit unknown/missing.
- [ ] Reject NaN/inf, invalid clock/negative gap/unknown units, conflicting probe, stale/unavailable/out-of-order data before use; never normalize UNAVAILABLE to zero. Maintain old record serialization with versioned compatibility.
- [ ] Replace ID-only channel aggregation where necessary with machine/source/component identity; support independent duplicate sensor categories on different axes (no silent collapse). Calibrate units/conversion ONLY with validated probe and technician sign-off.
- [ ] Pydantic typed `DetectorConfig` and `DetectorAssessment`: model-free and local CPU; per-machine versioned, fault-free reference; eligible operational states, warmup windows, persistence/hysteresis, min samples, abstain/unknown. Do not reuse simulator thresholds. No LLM calls on stream.
- [ ] Derive bounded `IncidentTrigger` from approved anomaly/Condition events with evidence IDs and as-known cutoff; do not claim alarm always identifies the faulty machine. Preserve multi-machine context.
- [ ] Safe counts, latency and rejection logs: source_epoch, signal/mapping/calibration identifiers, eligible/missing/invalid samples, severity, trigger/clear, suppressed reason; no raw machining payloads.
- [ ] Offline fixtures/test matrix: available/unavailable, duplicate axes, units, legacy timestamps, out-of-order, gaps/reconnect, idle/warmup, normal vs calibrated anomaly, no baseline, false positives; simulator unaffected.

## Pydantic AI maximization without misuse
Use Pydantic BaseModel/validators/Settings for all contract boundaries; reuse existing Graph/Pydantic typed tool schemas; optional Pydantic Logfire/OTel spans at the boundary. **Do not use `pydantic_ai.Agent` for numeric anomaly detection**, as it would make a deterministic safety gate probabilistic.
Pydantic docs: https://pydantic.dev/docs/validation/latest/concepts/models/ and https://pydantic.dev/docs/ai/production/observability/ .

## Micro-loop and merge requirements
For each small change: write/extend test → compare against #307 + A versions → read current relevant Pydantic docs → minimal implementation → lint/pytest → trace/log/privacy check → commit → repeat. Preserve Siemens/simulator provenance and source-matched evaluation inventories. Do not merge until A and #307 are green/final and approved.
**Handoff:** inspect `docs/haas_vf4/PR_B_SIGNALS_DETECTOR.md`, #307, PR A and this branch.
