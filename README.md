# Capstone_Project_CMU

Agentic AI capstone: a simulated manufacturing environment (machines,
sensors, jobs, batches, quality, maintenance, events, hidden faults) and,
later, an AI research agent that investigates it through tools.

- `CLAUDE.md` — development rules, architecture principles, and the
  gated teaching workflow used to build this project.
- `docs/MVP_SCOPE.md` — what the MVP includes, what it excludes, and the
  post-MVP roadmap.
- `docs/PROGRESS.md` — which components are implemented and which are
  understood (tracked separately).
- `capstone/simulator/` — the simulator (runs with no LLM).
- `tests/` — pytest suite.

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

Use `uv run --locked ruff format .` to apply formatting. The initial rules
check basic Python correctness and unused imports, with Python 3.11 as the
minimum target. Formatting uses 88-character lines. Automatic Git hooks and
CI checks are still future work.

## Optional Neon connection check

Install the database extra and put the Neon connection string in a local
`.env` file (ignored by Git):

```sh
uv sync --locked --extra database
```

```dotenv
DATABASE_URL="your Neon connection string"
```

Keep the SSL options supplied by Neon in the connection string. An existing
`DATABASE_URL` environment variable takes precedence over `.env`.

```sh
uv run --locked --extra database python test_db_connection.py
uv run --locked --extra database pytest
```

The first command prints `True` on success and exits unsuccessfully on
failure without printing connection details. It executes only `SELECT 1`,
creates no tables, and closes its connections. The simulator does not load
database configuration or require a database. Database tests run offline;
without the database extra, they are skipped.
