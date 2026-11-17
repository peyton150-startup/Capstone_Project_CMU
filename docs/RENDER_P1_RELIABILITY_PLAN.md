# P1 two-Render-service reliability plan

Draft. This PR stacks on P0 #302, which stacks on #298. Keep the existing Pydantic Graph, PostgreSQL queue and source-owned #293/#294/#296/#297 telemetry contracts.

## Code changes
- Final stage is persisted atomically with the completed terminal transition; a late watcher must never regress the result.
- Preserve triage/deep/live safe progress when an expired worker claim transitions to interrupted.
- Match immutable worker execution settings and Render build revision before a queued job is claimed. Refuse incompatible jobs without changing their status or replaying actions.
- Add durable idle/busy worker heartbeats via a small private PostgreSQL table and schema migration; report liveness separately from the web service's DB-only readiness.
- Produce allowlisted correlated operational logs: service/run/job, queue latency, attempt, duration, reason code, dropped progress reasons, lease recovery, worker health; never prompts/provider errors or ground truth.
- Tests cover producer/consumer order, interruption preservation, revised queue filtering, active/idle liveness, privacy and negative cases.

## Safety and gates
Do not reimplement the #300 frontend lifecycle, #297 model UI, #296 Decide tool selection, #295/#299/#301 deterministic logic. Do not deploy, merge or alter Render production. Run disposable PostgreSQL, CI+SNAP, two-process manual/review/reconnect and Render staging tests before promotion.
