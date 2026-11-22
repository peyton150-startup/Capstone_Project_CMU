# Batch integration compatibility gates (PRs #300, #299, #301, #306, #298, #302, #303, #305)

This branch starts at main after squash-merging #296 and #297. Treat their implementations as authoritative, not as files to replace with older stacked versions.

## Merge order and conflict handling

Integrate changes in the listed order. Compare each PR's merge base and diff against current main before applying; do not blindly copy whole files from stale stacked heads. Reconcile overlapping edits in `capstone/api/runs.py`, `frontend/src/pages/managed.tsx`, `frontend/src/types.ts`, and the investigation state/loop/completion modules. Preserve source identity and provenance for any journal and audit event.

## PydanticAI and Pydantic Graph acceptance

- Validate Graph state/node transitions and checkpoint/recovery using the actual Pydantic Graph types and state model. Do not duplicate state transitions in API or worker layers.
- Validate agent dependencies, structured outputs, tool registration, and model-selection settings using the actual PydanticAI interfaces in this repository.
- One deterministic-triage override must govern Plan, Decide, Hypothesize, Test and Investigate, while Conclude stays model-driven. Validate the effective configuration in both API and worker.
- Keep #296 chronological Decide audit records and #297 sanitized model-call telemetry intact. Correlate run ID, phase, model-call ID and timestamps across API, durable journal and frontend without exposing secrets, raw prompts, or hidden simulator truth.
- Test idempotency, authorization, bounded event streaming, worker restart/recovery and duplicate-execution prevention for local and Render deployments.
- Read-only Siemens/OEM interfaces must remain read-only; tests must use simulations, never live controllers.

## Validation before merging into main

Run Ruff and focused triage/Graph/API/telemetry/frontend tests after each conflict cluster. Run full pytest, React/API privacy, disposable PostgreSQL/TLS and Siemens/OEM contract workflows on the final integrated head. Rebuild all four evaluator inventory/matrix files only from genuine JUnit and coverage evidence; require source-matched hashes and passing offline SNAP. Do not ignore failures other than specifically identified Vercel rate limiting. Merge only a validated integration PR, and account for each original PR explicitly.
