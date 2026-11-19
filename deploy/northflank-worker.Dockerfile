# Northflank background worker image: runs `python -m capstone.worker`.
#
# Why a Dockerfile instead of the Heroku buildpack: the buildpack runs a plain
# `uv sync`, which installs only the base dependencies. The worker also needs
# the `database` extra (SQLAlchemy, psycopg, Alembic) and the `agent` extra
# (pydantic-graph for triage). The Render web service installs extras through
# its own build command; Northflank needs this file.
#
# Northflank settings: build type Dockerfile, build context `/`, Dockerfile
# path `/deploy/northflank-worker.Dockerfile`. Runtime variables
# (CAPSTONE_WORKER_ENABLED, CAPSTONE_UI_RUN_DATABASE_URL, TRIAGE_*) come from
# Northflank, and NF_DEPLOYMENT_SHA supplies the commit for revision matching.
FROM python:3.14.7-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code-only changes reuse this layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --extra database --extra agent

COPY capstone-code ./capstone-code
RUN uv sync --locked --no-dev --extra database --extra agent

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --uid 10001 --no-create-home worker
USER worker

CMD ["python", "-m", "capstone.worker"]
