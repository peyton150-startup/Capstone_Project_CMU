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

Setup: `pip install -e ".[dev]"` then `pytest`.