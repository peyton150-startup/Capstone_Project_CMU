# Developer Tooling Implementation Plan

> **For agentic workers:** Execute sequentially in this session; the developer has authorized implementation. Use verification-before-completion for the final checks.

**Goal:** Add four developer tools and document future integrations without changing simulator behavior.

**Architecture:** Keep tooling in development dependencies and Git configuration. Future integrations reuse existing contracts and providers. Preserve Pydantic Graph for the planned macro loop and CrewAI for later specialist orchestration.

**Tech Stack:** uv, Ruff, pre-commit, pytest-cov, GitHub Actions.

**Spec:** Developer's pasted task of 2026-10-11; scope and constraints below.

## Global Constraints

- Python supports >=3.11; development uses `.python-version` (3.14.7).
- Preserve both pip-compatible dev extras and the uv dev group.
- No runtime framework additions, live services, secrets, or behavior changes.
- Coverage is informational; no percentage threshold.
- Add only Ruff's `I` rules to `E4`, `E7`, `E9`, `F`.

## Review Focus

- CI must select the pinned interpreter and use locked installs.
- Hook Ruff version must match the lockfile, with lint fixes before formatting.
- Import changes must preserve imported names, scope, and non-import syntax.
- Default and database-extra tests must remain offline.
- Future client filtering must not replace server authorization or leak hidden truth.

### Task 1: Developer dependencies and checks

- [x] Add pre-commit and pytest-cov to both dev declarations; regenerate `uv.lock`.
- [x] Add `.pre-commit-config.yaml` with Ruff v0.16.10 and `.github/workflows/ci.yml` using documented setup-uv caching, locked checks, and one coverage test run.
- [x] Ignore generated coverage/test artifacts and document actual commands in README.

### Task 2: Mechanical import sorting

- [x] Enable `I`; run `uv run --locked ruff check --select I --fix .` followed by `uv run --locked ruff format .`.
- [x] Compare Python syntax against Git HEAD with import ordering normalized; inspect every changed import block.
- [x] Run lint, format, and all pre-commit hooks; commit tooling and mechanical changes separately.

### Task 3: Roadmap and verification

- [x] Refine Future Work 1/2/3/6/7 using official documentation and explicit adoption/test conditions.
- [x] Run `uv run --locked pytest` and `uv run --locked pytest --cov=capstone --cov-report=term-missing` with writable temporary directories.
- [x] Run database-extra offline tests and a simulator smoke check without optional packages.
- [x] Optionally assess ty with an isolated uv tool invocation; do not add it to dependencies or fix unrelated typing debt.
- [x] Record exact results in PROGRESS; inspect diff, commit, and push the authorized changes.
