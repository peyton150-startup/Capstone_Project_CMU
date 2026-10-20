# Capstone_Project_CMU

Agentic AI capstone: a simulated manufacturing environment (machines,
sensors, jobs, batches, quality, maintenance, events, hidden faults) and,
later, an AI research agent that investigates it through tools.

- `AGENTS.md` — development rules, architecture principles, and the
  gated teaching workflow used to build this project, for any coding
  agent (`CLAUDE.md` imports it for Claude Code).
- `docs/MVP_SCOPE.md` — what the MVP includes, what it excludes, and the
  post-MVP roadmap.
  [Future Work 2](docs/MVP_SCOPE.md#future-work-2--mcp-architecture-observability-and-response-verification)
  covers the minimal MCP slice, deferred server-count decision,
  OpenTelemetry/LangSmith, and response verification, with a readiness checklist.
- `docs/PROGRESS.md` — which components are implemented and which are
  understood (tracked separately).
- [Future Work reevaluation register](docs/FUTURE_WORK_REEVALUATION.md) —
  reviewed implementation conditions, adoption checks and reasons to defer or
  reject candidates, including the Datum/Ratchet prompt evaluation.
- `capstone/simulator/` — the simulator (runs with no LLM).
- `tests/` — pytest suite.

## Opt-in investigation challenge

```python
from capstone.simulator.challenge import build_challenge
from capstone.tools.observation import ObservationTools

sim = build_challenge(seed=42, machines=3)
for _ in range(300):
    sim.step()
observations = ObservationTools(sim)
readings = observations.get_readings("CNC-01", "temperature", 0, 300)
```

`build_challenge()` combines bearing wear and excessive speed on one machine,
a harmless vibration spike on another, and temperature drift with a temporary
signal loss on a third. Target machines and onset are seed-selected. The same
seed and actions replay the same observations. Existing `build_line()` behavior
and investigation tool formats are unchanged. No LLM or delayed maintenance
records are involved. See the [difficulty guide](docs/SIMULATOR_DIFFICULTY_COMPATIBILITY.md)
for timing, limitations, and the component walkthrough.

## Developer setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```sh
uv sync --locked
uv run --locked pytest
```

`pyproject.toml` declares dependencies, `uv.lock` records their resolved
versions, and `.python-version` selects Python 3.14.7, the interpreter used
for this migration. The package still supports Python 3.11 and later.
`uv` manages the local `.venv`; commit the lockfile when dependencies change.
The existing simulator dependency versions are preserved by migration
constraints in `pyproject.toml`; review those constraints before deliberately
upgrading them. Use `uv add PACKAGE` for runtime dependencies or
`uv add --group dev PACKAGE` for development tools.

The existing pip setup remains available: `pip install -e ".[dev]"`, then
`pytest`. To reproduce the locked versions with pip, export them with
`uv export --locked --no-emit-project --output-file requirements-export.txt`,
install that file with pip, then install the local package using
`pip install --no-deps -e .`.

## Formatting and linting

Ruff is included in the development dependencies. Run:

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The rules check basic Python correctness, unused imports, and import sorting
(`E4`, `E7`, `E9`, `F`, `I`), with Python 3.11 as the minimum target.
Formatting uses 88-character lines. To sort imports and then format:

```sh
uv run --locked ruff check --select I --fix .
uv run --locked ruff format .
```

Install the optional local Git hooks after syncing development dependencies:

```sh
uv run --locked pre-commit install
uv run --locked pre-commit run --all-files
```

The hooks run Ruff fixes before formatting. Their pinned Ruff version matches
`uv.lock`; update both together when upgrading Ruff. Hook environments need
network access on first setup. Hook installation is a per-checkout developer
choice; committing the configuration does not install hooks automatically.

## CI and informational coverage

`.github/workflows/ci.yml` runs on pull requests and pushes to `main` with
read-only repository permissions. It installs uv with caching, selects Python
from `.python-version`, syncs locked default dependencies, checks Ruff lint and
formatting, and runs the offline test suite once with terminal coverage and a
GitHub Actions Markdown summary. It uses no service credentials or live Neon,
LLM, or MCP calls. Dependency setup downloads packages; the tests run offline.
Optional database-extra tests remain available through the commands below.

For local coverage, run this single-line command in PowerShell or a POSIX shell:

```sh
uv run --locked pytest --cov=capstone --cov-report=term-missing
```

Coverage is informational, with no failure threshold or 100% target. Use it
to find unexercised paths; the semantic and invariant tests establish behavior.

## Optional Neon connection check

Install the database extra, copy `.env.example` to `.env` if you do not
already have one, and put the Neon connection string in that local file
(ignored by Git):

```sh
uv sync --locked --extra database
```

```dotenv
DATABASE_URL="your Neon connection string"
```

Keep the SSL options supplied by Neon in the connection string. An existing
`DATABASE_URL` environment variable takes precedence over `.env`.

`capstone/settings.py` is the typed configuration entry point. `get_settings()`
reads current environment variables and the repository's `.env` on demand,
without mutating environment variables or loading configuration on import.
The database URL uses Pydantic's `SecretStr`, which masks it in representations
and JSON serialization. Blank values mean unconfigured; only the database
check requires a URL. The simulator keeps its explicit seed inputs and does
not load these settings. Add configuration fields when their integrations
are implemented, rather than requiring credentials for future components.

```sh
uv run --locked --extra database python test_db_connection.py
uv run --locked --extra database pytest
```

The first command prints `True` on success and exits unsuccessfully on
failure without printing connection details. It executes only `SELECT 1`,
creates no tables, and closes its connections. The simulator does not load
database configuration or require a database. Database tests run offline;
without the database extra, they are skipped.

## Shared contracts and provider boundaries

`capstone/contracts/` defines observable records, sourced evidence, hypotheses,
investigation records, and the common `ToolRequest` / `ToolResult` envelope.
Unknown fields are rejected. These models keep observations and agent beliefs
separate from the simulator's internal ground truth.

`capstone/providers/factory.py` defines the `FactoryProvider` interface and
`SimulatorFactoryProvider`, a working adapter over the existing tools. Its
explicit tool list includes observations, bounded waits, and action proposals;
it never exposes approval or ground-truth calls. Existing direct tool methods
remain available. Results include source, simulation tick/time, optional
correlation IDs, and a structured error instead of raw exception details.
A refused request says what to correct: which arguments were wrong and why,
or the tool's own explanation (a `ToolInputError`, such as an unknown machine
or action). Any other failure, and an answer that breaks its contract
(`invalid_result`), is reported without detail. Sensor names are checked:
`vibration`, `temperature` and `load` on a machine, `air_temperature` for
the factory.

```python
from capstone.contracts.investigations import investigation_id_for, run_id_for
from capstone.contracts.tools import ToolRequest
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools

sim = build_line(seed=42)
desk = ApprovalDesk(sim)  # keep this on the human side
factory = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, desk))
run = run_id_for("experiment-42-repeat-1")
investigation = investigation_id_for(run, 1)
result = factory.call(
    ToolRequest(name="list_machines"),
    run_id=run,
    investigation_id=investigation,
)
```

Run keys must uniquely identify an execution, including repeated experiments
with the same seed. Reusing a key intentionally reproduces its UUID; investigation
IDs are derived from that run and a positive sequence number. ID generation
consumes no simulator random stream and uses no wall clock. There is no durable
storage or automatic agent loop yet.

### Deterministic sensor summaries

`ObservationTools.get_sensor_summary(machine_id, sensor, from_tick, to_tick)`
and the provider tool of the same name calculate statistics from observable
readings in an inclusive tick window. Pass `machine_id=None` for factory
sensors. No time advances, random draws, or hidden state are involved.

```python
for _ in range(10):
    sim.step()
summary = factory.call(
    ToolRequest(
        name="get_sensor_summary",
        arguments={
            "machine_id": "CNC-01",
            "sensor": "temperature",
            "from_tick": 1,
            "to_tick": 10,
        },
    )
)
```

Results include requested window, actual first/last sample ticks, sample count,
sensor unit, start/end values, minimum, maximum, sample-weighted mean, delta,
and `rate_of_change`. Rate is `(end_value - start_value) / (last_tick -
first_tick)` in sensor units per simulation tick, not a regression slope.
Missing ticks are not interpolated. Empty windows return zero samples and
null units/statistics, as does an unknown sensor name in a direct call (the
provider refuses one); a single sample has zero delta and a null rate. Mixed
units and nonfinite readings are rejected.
Tick bounds must be ordered, nonnegative integers; unknown machines are
rejected. The result uses `SensorSummaryObservation`; MCP remains deferred.

## Structured logging

`create_event_logger(stream)` in `capstone/observability.py` creates an opt-in
JSON logger. Pass it as `logger=` to `SimulatorFactoryProvider` to record tool
name, success, simulation tick, and correlation IDs. It accepts identifier
metadata only, masks secret wrappers, and rejects arbitrary payloads, reasons,
and exception text. It adds no wall-clock time, changes no root logger, and
does not enable an external tracing service.

## Database migrations and episodic memory

Alembic is included in the optional database extra. `alembic.ini` points to
`migrations/`; `migrations/env.py` reads the typed settings without storing the
URL in configuration files. You can inspect the revision history with:

```sh
uv run --locked --extra database alembic heads
uv run --locked --extra database alembic history
```

Revision `0001_episodic_memory` creates the accepted-memory table, unique
investigation/lesson constraints, and category index. The promotion policy,
service, SQL repository, and schema are implemented. Migration tests exercise
temporary SQLite databases and render PostgreSQL SQL offline; this increment
has not applied a migration to Neon. See [episodic memory](docs/EPISODIC_MEMORY.md)
for the lifecycle, explicit migration command, generated SQL, and remaining
runtime/evaluation integration. Autogeneration is still refused if metadata is
empty; reviewed revisions remain the mechanism for schema changes.

The existing `capstone/` layout is retained: `settings.py` for configuration,
`contracts/` for shared data, `providers/` for adapters, `tools/` for observable
operations, `simulator/` for reality, `memory/` for durable lessons, and
`database/` for connectivity. Agent,
evaluation, and ingestion modules will be added when they have working behavior.

## Research basis

Parts of this work were based on these papers. Each line names the change
and the paper it came from.

- Scoring-integrity tests (`tests/test_scoring_integrity.py`): scoring
  never changes the simulator, gives the same score twice, and stays right
  as time moves on. Based on [When Agent Evaluation Becomes Unreliable](https://arxiv.org/abs/2610.16067)
  (Chen, 2026).
- Evidence-vs-reasoning miss label (`Score.miss_kind` in
  `capstone/evaluation/scoring.py`): each wrong diagnosis is marked as a
  run that never looked at all the relevant evidence, or one that looked
  and misread it. Based on [How Far Can Root Cause Analysis Go on Real-World Telemetry Data?](https://arxiv.org/abs/2607.13548)
  (Gopal & Krishnan, 2026).
- Rule-based diagnostic baseline (`capstone/baseline.py`, run with
  `uv run python -m capstone.baseline --known`): fixed rules over the
  agent's own tools, scored the same way as the agent, as the yardstick the
  LLM agent must beat. Based on [When LLMs Sit Above Diagnostic Tools: Unrealized Complementarity in Industrial Fault Diagnosis](https://arxiv.org/abs/2610.05031)
  (Kim, 2026) and [Exploring LLM-based Frameworks for Fault Diagnosis](https://arxiv.org/abs/2509.23113),
  both of which found simple or specialist methods matching or beating the LLM.
- Unreliable tools (`capstone/providers/hazards.py`, `--hazards` on
  `python -m capstone.experiment run`): on a fixed schedule the agent's
  tools time out, drop rows from part of a range, and show one stale
  maintenance record, each with a way to recover. Based on [Beyond Function Calling: Benchmarking Tool-Using Agents under Tool-Environment Unreliability](https://arxiv.org/abs/2606.25819)
  (Tian et al., 2026, ToolBench-X).
