"""Top-level simulator facade (intentionally empty for now).

This module will eventually hold the `Simulator` class: the single object
that owns the simulation clock, the factory state (reality), the active
scenarios, and the `step()` loop that advances time and lets every
subsystem react in a fixed, deterministic order.

Planned composition (see CLAUDE.md §6):

    Simulator
      ├── clock        SimulationClock         — owns "now"; nothing else does
      ├── rng          seeded random source    — all randomness flows from here
      ├── state        FactoryState            — machines, jobs, batches (reality)
      ├── sensors      SensorModel[]           — read state → noisy observations
      ├── production   jobs / material batches
      ├── maintenance  records + bounded actions
      ├── quality      inspections / rejects
      ├── events       event + alarm log
      ├── scenarios    Scenario[]              — inject causal effects over time
      └── ground_truth hidden truth            — never crosses the tool boundary

The agent never imports this module. It reaches the simulator only through
`capstone/tools/`, which exposes observations and accepts actions.

Nothing is implemented here yet on purpose: per CLAUDE.md §1, every
component is taught and understood before it is written, and the facade is
built last, once its parts exist.
"""
