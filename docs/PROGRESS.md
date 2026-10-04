# Progress Log

Two separate completion criteria per component (see CLAUDE.md §1):

- **Implemented** — code written, tests passing.
- **Understood** — the developer explained the component back correctly
  (both the pre-implementation gate and the post-implementation re-explain).

A component is complete only when both columns are checked.

| # | Component                     | Taught | Understood (pre) | Implemented | Understood (post) | Notes |
|---|-------------------------------|--------|------------------|-------------|-------------------|-------|
| 1 | SimulationClock               | yes    | yes              | yes         | yes               | `capstone/simulator/clock.py` — COMPLETE |
| 2 | Deterministic random source   | yes    | yes              | yes         |                   | `capstone/simulator/rng.py`; awaiting post-implementation re-explain |
| 3 | Machine identity / MachineState |      |                  |             |                   | |
| 4 | Sensor abstraction + 1 reading |       |                  |             |                   | |
| 5 | FactoryState + step()         |        |                  |             |                   | |
| 6 | Event log                     |        |                  |             |                   | |
| 7 | Scenario abstraction          |        |                  |             |                   | |
| 8 | BearingDegradation scenario   |        |                  |             |                   | |
| 9 | Ground truth + observation boundary (tools) | |          |             |                   | |

## Session notes

- **Session 1** — Repo was empty. Created CLAUDE.md, package skeleton,
  this log. Recommended SimulationClock as the first component; asked
  the first comprehension question. No simulator logic implemented.
- **Session 1 (cont.)** — Clock gate passed (developer explained single
  ownership of time, intermittent same-seed failures with multiple
  counters, and corrupted-ordering consequences for the agent).
  Implemented `SimulationClock` + 8 tests, all passing. Deliberate
  simplification: `clock.py` is a module, not the `clock/` package in
  CLAUDE.md §6; promote it if it grows.
- **Session 1 (cont.)** — Random source gate passed after two corrections
  (clock does not advance streams; sequence depends on `(seed, name)`,
  not seed alone — developer then correctly derived that renaming a
  stream changes its history). Implemented `RandomSource` + 9 tests, 17
  total passing. Stream names are frozen contracts once histories are
  recorded.
