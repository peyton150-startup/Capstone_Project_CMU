# Manufacturing Research Assistant — Industrial Console

React 19 + TypeScript + Vite with a loopback-only FastAPI service and the existing Python simulator. The design uses industrial HMI conventions (neutral backgrounds, explicit alarms and evidence-first diagnostics); it is not a controller HMI or a Siemens product.

## What works on this branch

| Workspace | Supported source and behavior | Remaining limitations |
| --- | --- | --- |
| Home / Overview | Spacious routes, industrial themes, source-aware unavailable states | No measured multi-machine live incident stream |
| Investigations / triage / deep / review | Approved completed-audit projections; managed run diagnosis, evidence, hypotheses, decision trace, persisted triage report and simulator review desk | No unapproved real-machine diagnosis; missing model answers may not yield a complete audit |
| Machines / signals | Siemens OPC UA v2 capture and separately identified MTConnect v1 observations, bounded charts and status quality | Units, physical mapping and eligibility require field verification |
| Recordings / quality / sessions | Versioned local capture parser, session epochs, subscription marker, quality and gap reporting | Recorder process supervision, durable sink confirmation and complete session indexing not verified |
| Experiment lab / runs | Role-gated simulator launch, SQLite status journal, progress SSE, resumable cursor, approval bridge, operational diagnostics | No proof of physical machine action; live provider workflow needs end-to-end tests |
| Evaluation / comparison | Evaluator-only projected scorecards, cautious comparison on matched inputs | Full scored traces, calibration and performance parity not established |
| Manuals / memory | Simulator manual search and opt-in authorized episodic memory search | No OEM manual, pilot memory promotion or verified field learning |
| Engineering / audit / settings | Source-bound service status, curated collector audit, read-only setting allowlist | Validated per-run configuration editing, full worker and sink health remain future work |

**Source boundaries:** Synthetic preview is opt-in and labeled. Simulator hidden truth is not sent to investigator endpoints. Confidence is a model assessment, not verified fault probability. A Siemens OPC UA connection does not prove a valid subscription or qualified sensor measurement. Missing data must not be interpreted as a healthy machine.

**Pilot safety:** The Prestige pilot is read-only. React/FastAPI cannot start or stop physical Siemens recordings, call OPC UA methods, write to a CNC, reset faults, acknowledge alarms, or approve physical machine interventions. Data collection is a separate approved local operation.

## Local PowerShell setup

Prerequisites: `uv`, the repository's pinned Python version, and Node.js 22. Run from the repository root:

1. `uv sync --locked --all-extras`
2. `uv pip install --python .venv/Scripts/python.exe -r frontend/requirements-api.txt`
3. `cd frontend; npm install; cd ..`
4. Set only authorized server-owned source paths, for example:
   `$env:CAPSTONE_UI_CAPTURE = "C:\\PrestigePilot\\capture-001.jsonl"` and
   `$env:CAPSTONE_UI_INVESTIGATIONS = "C:\\ApprovedPrivate\\audit.jsonl"`.
   Optional: `CAPSTONE_UI_MTCONNECT`, `CAPSTONE_UI_CAPTURE_AUDIT`, `CAPSTONE_UI_EXPERIMENTS`.
5. For private source access, set `CAPSTONE_UI_TOKEN` to a random secret of at least 24 characters. `CAPSTONE_UI_SHOW_VALUES=1` is a separate permission to show permitted numeric values.

Managed **simulator-only** execution is opt-in. Set `CAPSTONE_UI_SIM_RUNS=1`, an absolute `CAPSTONE_UI_RUN_DB` path, and three distinct secrets of at least 24 characters: `CAPSTONE_UI_TOKEN` (read), `CAPSTONE_UI_RUN_TOKEN` (submit), and `CAPSTONE_UI_REVIEW_TOKEN` (approve/reject). Submit and review credentials are not interchangeable. When `CAPSTONE_UI_EVALUATOR=1` is enabled alongside managed runs, configure a fourth distinct `CAPSTONE_UI_EVALUATOR_TOKEN` for scorecards and evaluation records. Local users enter the role-specific token in the browser Access dialog; it is held in memory only.

Start API: `uv run --no-sync python -m capstone.api` (127.0.0.1:8000). Start frontend separately: `cd frontend; npm run dev` (127.0.0.1:5173).

Never expose the API or Vite server on an external factory-network interface. Never commit private capture files, secrets or model-provider request logs. The local runner uses the server's model settings; UI selection is not permission to override an in-flight episode.

## Technical detail and operational diagnostics

- Run status and run progress are persisted in a SQLite journal; event IDs support SSE reconnect. The client stops reconnecting on a terminal event.
- The Python episode's completed audit is kept in a private, per-run JSONL file and **only strict selected fields** are projected to the frontend. It does not return the simulator or full `EpisodeResult`.
- Safe operational event metadata is recorded separately from the audit and shown through `GET /api/v1/lab/runs/{run_id}/observability`. The endpoint allowlists event names, identifiers, counters and non-sensitive tick/boolean fields. It does not return provider prompts, error messages, evidence text, arguments or credentials.
- Approving a proposal records permission only. The simulator's existing `ApprovalDesk` independently controls execution and subsequent verification.
- Collector process liveness, confirmed sink durability and physical Siemens field acceptance cannot be inferred from existing JSONL. They remain unknown/unverified without instrumentation.

## Checks

- `cd frontend; npm run build; npm test`
- `uv run --no-sync pytest tests/test_web_api.py tests/test_web_runs.py` (after installing optional FastAPI dependencies)
- `uv run --locked --all-extras ruff check .` and `uv run --locked --all-extras ruff format --check .`
- Review the dedicated **Industrial frontend** and original **CI** GitHub Actions workflows on the latest head commit.
- After a CI-generated evaluation inventory commit, verify that **both workflows actually execute on the new PR head**. A workflow marked `action_required` without any jobs is not a passing check.

These tests do not substitute for a real browser end-to-end run, live model-provider investigation, field Siemens acceptance, disk-failure testing or production security review. Do not merge solely because the React bundle compiles.
