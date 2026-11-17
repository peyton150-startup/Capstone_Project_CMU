# Managed simulator model-call observability (local and Render)

## Scope and integration

This patch adds an **operator-neutral, read-only** model-request timeline for the
existing managed simulator runner. It does not change triage decisions, model
routing, model provider calls, budgets, or human approval behavior.

* The existing `ModelPolicy.calls` records the attempted `ModelCall` and
  `Attempt` fields. We project these into a small, versioned Pydantic model.
* Each completed question is appended to the existing **transactional**
  `run_events` journal as `model.call`. A `model.monitor` marker distinguishes
  old runs with no instrumentation from new runs with zero model requests.
* The same `SimulatorRuns` base class powers local SQLite and the currently
  deployed Render `PostgresSimulatorRuns` (with Supabase PostgreSQL). The
  Postgres journal stores these events in the database immediately; it does
  not depend on Render's ephemeral filesystem or the private audit artifact.
* The API revalidates each stored event before returning it. The authenticated
  `GET /api/v1/lab/runs/{id}/model-calls?workspace=simulator` endpoint
  returns the **latest 200 model questions**, chronological by journal sequence.
  This is bounded; `truncated` indicates older calls exist.
* The managed run detail page polls the selected Local or Render API every
  four seconds. History survives browser reloads and reconnects.

### Security contract

The public record contains only: model ID, agent, phase/mode, question kind,
high-level result, request attempt count, ordered attempts, bounded latency,
provider-reported input/output tokens, prompt **character count and version
hash** (not prompt content), retry/fallback selection, and a fixed error class.
Provider error strings (even validation messages), HTTP bodies, API keys, auth
headers, model responses, prompts, tool arguments and simulator ground truth
never cross the model-call projection.

Unknown/malformed provider strings map to `other_error`. Missing token data
stays null; zero is never invented. The pilot workspace rejects access.
The persisted event journal is never returned wholesale as model telemetry.

### Local smoke test

From the repository root, launch a **fresh** local API process with:

```powershell
uv run --env-file .env --no-sync python -m capstone.api
```

With `CAPSTONE_UI_SIM_RUNS=1`, the SQLite path `CAPSTONE_UI_RUN_DB`, and
distinct viewer/operator/reviewer tokens configured, start a simulator run
through the frontend with **Local** selected. The run detail now includes
**Model request timeline**. If an actual provider returned HTTP 401/429 or
timed out, the attempt's categorized outcome appears without provider text.

To inspect the safe endpoint manually:

```powershell
$headers = @{ Authorization = "Bearer $env:CAPSTONE_UI_TOKEN" }
Invoke-RestMethod -Headers $headers -Uri "http://127.0.0.1:8000/api/v1/lab/runs/<run-uuid>/model-calls?workspace=simulator"
```

A completed run is not proof of a successful model request. Check each
question's `answered`, `invalid_reply`, or `no_answer` outcome.

### Render smoke test

Set the model credentials **on Render's FastAPI service**, not on Vercel:
`NVIDIA_API_KEY` (or the selected provider's key), `TRIAGE_MODEL`,
`DEFAULT_MODEL`, and `FALLBACK_MODEL` as applicable. Vercel is only the
React client. On the deployed frontend select **Render**, exit preview, and
start an authorized simulator run. The same timeline and API contract apply.

The current hosted journal uses `CAPSTONE_UI_RUN_BACKEND=postgres` and
`CAPSTONE_UI_RUN_DATABASE_URL`. This change reuses its existing
`run_events` table and needs **no additional migration**.

### PR overlap and future integration

* PR #293 adds phase-specific audits; #294 expands safe stage progress. This
  patch deliberately builds on #294 and does **not** duplicate those fields.
* PR #295 changes deterministic triage. Deterministic stages legitimately
  produce zero model calls; an empty timeline is not proof of missing keys.
* PR #292 adds the **future** independent Render job queue/repository, but
  does not yet execute a separate worker. When its separate-worker runtime
  is wired in, its `RunRepository` event allowlist and claim-fenced append
  path will need to include these model-call events; this patch intentionally
  does not bypass #292's lease fencing or create a second queue.

### PydanticAI decision

The project uses **Pydantic Graph and a custom typed chat client** rather
than `pydantic_ai.Agent` for model requests. PydanticAI's built-in
OpenTelemetry instrumentation traces calls made by PydanticAI agents, not
automatically those from this project's custom urllib client. Replacing that
transport for instrumentation alone would change timeouts/fallbacks and
would enlarge this PR. This patch instead reuses `ModelCall`/`Attempt`
and Pydantic `BaseModel` boundaries, without new dependencies.

A later opt-in OpenTelemetry/Logfire integration could add spans without
publishing prompts, responses, or provider credentials.
