# Manufacturing Research Assistant — Industrial Console

React 19 + TypeScript + Vite, paired with a **local read-only FastAPI adapter** over existing capstone artifacts.

The product uses restrained industrial HMI design: Ignition-like layouts, Siemens-style status colors, and large Grafana-like charts. It is an original UI, not a copy of any HMI vendor.

## Pages and capabilities

| Pages | Actual source or behavior | Not yet integrated |
| --- | --- | --- |
| Home and Overview | Navigable landing, source-gated summary | Real-time multi-machine incidents |
| Investigations, triage, deep, review | Whitelisted completed-audit evidence, hypotheses, conclusion, verification | Full typed TriageReport, live graph progress, human approval bridge |
| Machines and Signals | One configured Siemens capture, opaque signal IDs, Good numeric history | Simulator live inventory, verified Siemens units/mapping |
| Recordings, quality, sessions | Siemens v2 JSONL records, gaps, recent-window quality and epochs | Recorder process, confirmed subscription, durable sink/storage health |
| Lab, runs, evaluations, compare | Evaluator-only, truth-redacted experiment summaries | Managed run launch, labelled accuracy scores |
| Knowledge, manuals, memory | Navigation and explicit unavailable states | Authorized search/list APIs |
| System, observability, audit, settings | Service status, safe collector metadata, readonly environment allowlist | Live agent traces and validated settings updates |

**Synthetic preview:** opt-in, clearly labeled and isolated in src/preview.ts. It is never mixed with real data. Production mode does not invent values, machine states, diagnoses or rates.

**Read-only pilot:** The UI cannot start/stop Siemens recording, write to the CNC, call OPC UA methods or approve physical interventions. Collection remains a separate authorized PowerShell operation. API is loopback-only; private artifacts never belong in Git.

## Local Windows PowerShell setup (from repository root)

Prerequisites: uv, the repository-pinned Python, Node.js 22.

1. Install original locked Python environment: `uv sync --locked --all-extras`
2. Install optional API dependencies without changing uv.lock:
   `uv pip install --python .venv/Scripts/python.exe -r frontend/requirements-api.txt`
3. Install frontend: `cd frontend`, `npm install`, `cd ..`
4. In PowerShell A, optional approved absolute paths:
   `$env:CAPSTONE_UI_CAPTURE = "C:\PrestigePilot\capture-001.jsonl"`;
   `$env:CAPSTONE_UI_CAPTURE_AUDIT = "C:\PrestigePilot\audit-001.jsonl"`;
   `$env:CAPSTONE_UI_INVESTIGATIONS = "C:\ApprovedPrivate\audit.jsonl"`;
   `$env:CAPSTONE_UI_EXPERIMENTS = "C:\ApprovedPrivate\experiment.jsonl"`.
5. Required with configured private files:
   `$env:CAPSTONE_UI_TOKEN = "REPLACE_WITH_RANDOM_SECRET_AT_LEAST_24_CHARACTERS"`.
   Optional only with permission: `CAPSTONE_UI_SHOW_VALUES=1` allows recording value display;
   `CAPSTONE_UI_EVALUATOR=1` allows redacted evaluation summaries.
6. Start API: `uv run --no-sync python -m capstone.api` (127.0.0.1:8000).
7. In PowerShell B: `cd frontend`, `npm run dev`; visit http://127.0.0.1:5173.
   Enter local token through Access toolbar; it remains in browser memory only.

Never bind API or dev server to an external factory-network interface. Approval to read source telemetry is independent of local UI access.

## Checks

- React: `cd frontend; npm run build; npm test`
- API: `uv run --no-sync pytest tests/test_web_api.py` (after optional deps installed)
- Root: `uv run --locked --all-extras ruff check .`; `ruff format --check .`; CI test groups.

Optional API dependencies are deliberately not in the project's frozen uv.lock.
Existing core CI skips the optional API tests if FastAPI is absent; the
Industrial frontend workflow installs FastAPI and runs them.

## Remaining work

The navigable UI, source-safe read adapters, and tests are implemented here.
**Not** implemented: simulator run worker, human approval API, SSE streaming,
full triage/critic/ToT persistence, full accuracy scorecards, memory/manual
search APIs, field-proven Siemens subscriptions, disk/sink monitoring, or
physically validated Prestige telemetry. These screens explain their status
rather than claiming unsupported capabilities.
