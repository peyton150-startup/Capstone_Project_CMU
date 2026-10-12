# AGENTS.md — Capstone Project (Agentic AI Research Agent + Factory Simulator)

This file governs how Codex works in this repository. It persists across
sessions. Read it fully at the start of every session, then read
`docs/PROGRESS.md` to find out where we are.

---

## 0. What this project is

An agentic-AI capstone. Two halves:

1. **The simulator** — a simulated manufacturing environment: machines,
   sensors, production jobs, material batches, quality inspections,
   maintenance records, events, failures, and *hidden ground truth*.
   It is a first-class module and must run with **no LLM involved**.
2. **The research agent** (later) — an AI agent that investigates the
   environment through tools, forms hypotheses, takes bounded actions,
   and is evaluated on the consequences.

Conceptual flow:

```
Simulator
  → observable information
  → tool/API boundary
  → research agent
  → actions
  → tool/API boundary
  → simulator
```

The simulator knows the real state of the world. The agent must **never**
have direct access to that hidden truth; it only sees evidence and must
infer root causes.

---

## 1. THE MOST IMPORTANT RULE: never move faster than the developer's understanding

> **RULE CHANGE, 2026-10-06, by the developer.** The gated loop below
> governed every component up to and including row 13b in
> `docs/PROGRESS.md` (the wrong-setting scenario). The project then ran
> out of time, and the developer directed that everything remaining be
> built without gates. From row 13c on, the rule is **build first,
> explain afterwards**:
>
> - Do not stop for comprehension questions. Build each remaining
>   component in small, tested increments and commit and push each one.
> - Everything else in this file still holds: the architecture in §4,
>   determinism, hidden ground truth never crossing the tool boundary,
>   no fake complexity, tests for all behaviour.
> - In `docs/PROGRESS.md`, mark these rows "Understood: no — built
>   ungated, developer to review". Never mark understanding that was not
>   demonstrated.
> - For each component, record for the developer's later reading: which
>   modules changed, which functions and classes were added, and what
>   each one means, in plain English. Finish the whole build with one
>   such summary.
> - Stop and ask only where a choice is truly the developer's and no
>   default is written down in `docs/PROGRESS.md`.
>
> Sections 1.1–1.3 and §10 step 3 describe the earlier rule and apply
> only if the developer reinstates it.

Codex is operating in a **gated teaching + implementation loop**.

"I wrote the code" and "the developer understands the system" are **two
separate completion criteria**. A component is not done until both are
true, and they are tracked separately in `docs/PROGRESS.md`.

### 1.1 Core rule

Before implementing any meaningful new function, class, module, state
transition, algorithm, or architectural component, Codex must **first
teach** what it is going to do, then **verify understanding**, and only
then implement.

- Do **not** build the whole simulator and explain it afterward.
- Do **not** accept "yes" / "I understand" / "got it" as proof of
  understanding. Ask the developer to explain the concept back in their
  own words, or answer a short conceptual question.
- Do **not** proceed merely because the developer wants to move quickly.
  If asked to skip a gate, politely restate the rule and ask the question
  anyway.
- The developer's answer does not need to use Codex's exact
  terminology. Evaluate whether the **underlying concept** is understood.
- If there is a misunderstanding, explain the gap and ask another
  question. Re-teach until it lands.

### 1.2 The mandatory workflow for every major component

1. Explain the problem we are solving.
2. Explain what component/function we are about to build.
3. Explain why the component exists.
4. Explain its inputs.
5. Explain its outputs.
6. Explain what state it reads.
7. Explain what state it changes, if any.
8. Explain how it interacts with the rest of the simulator.
9. Show a small conceptual example of its behavior.
10. Ask a short comprehension question.
11. **Wait for the developer's response.** (End the turn. Do not continue.)
12. Evaluate the explanation.
13. Correct any misunderstanding.
14. Only once understanding is demonstrated, implement the component.
15. Walk through the important parts of the implementation.
16. Run or write appropriate tests.
17. Show what the tests demonstrate.
18. Ask one final question about what was just implemented before
    moving on.

Do not start the next major component until this loop is complete for the
current one.

### 1.3 After implementing a component, Codex must

1. State exactly which files changed.
2. Summarize the implementation in plain English.
3. Identify the 2–5 most important functions/classes.
4. Walk through the important control/data flow.
5. Explain any non-obvious code.
6. Run the relevant tests.
7. Explain what each important test proves.
8. Point out technical debt or deliberate simplifications.
9. Ask the developer to explain how the component works before moving to
   the next major component. If they cannot, teach it again.
10. Update `docs/PROGRESS.md` (implementation status and understanding
    status are separate columns).

---

## 2. What must be taught vs. what Codex may just do

### 2.1 Codex MUST slow down and teach anything involving

- architecture
- factory state
- simulation time
- sensor generation
- randomization
- deterministic seeds
- causal relationships
- state transitions
- failure/degradation models
- scenario injection
- event generation
- hidden ground truth
- observability boundaries
- agent-facing interfaces
- actions that modify the simulated environment
- evaluation
- scoring
- scenario difficulty
- interactions between multiple faults
- anything that could materially affect what the future agent observes
  or concludes

### 2.2 Codex MAY handle without a gate (mention it, don't lecture)

- serialization boilerplate
- repetitive validation
- standard Pydantic/dataclass definitions
- repetitive test setup
- type annotations
- basic CRUD/helper functions
- formatting
- repetitive implementations of additional sensors **once the pattern
  is understood**
- packaging/config files (`pyproject.toml`, `__init__.py`, etc.)

When in doubt, treat it as 2.1.

### 2.3 Target level of understanding

The developer needs to understand essentially **100% of the architecture
and the important behavior**. They do **not** need to memorize every
implementation detail or every line of boilerplate.

---

## 3. Teaching style

Assume the developer knows Python and software engineering but is
**learning simulation architecture and agent environments**.

- Do not explain elementary syntax.
- Focus on: why the design exists, what problem it solves, how state
  flows through the system, why an abstraction is needed, what
  alternatives exist, why we chose one design over another, what could
  go wrong, and how it affects the future agent.
- Use concrete examples. Canonical example of the key distinction:

  > If `MachineState` contains `bearing_health = 0.70`, the sensor model
  > reads that state and generates higher vibration. The sensor does not
  > decide the bearing is broken. It only produces evidence influenced by
  > the underlying state.

### 3.1 Example comprehension-gate questions

- What responsibility does this class have?
- Why does this state belong here instead of inside the sensor?
- What information can the agent eventually see?
- What information must remain hidden?
- Why are we using a seeded random generator?
- What makes this sensor value causal rather than simply random?
- What happens when simulation time advances?
- Which component owns this state transition?
- What would break if we coupled this directly to the agent?

---

## 4. Architecture principles

### 4.1 Three concepts that must never collapse into one

| Concept         | Meaning                                              | Owner      |
|-----------------|------------------------------------------------------|------------|
| **Reality**     | The simulator's true internal state (incl. hidden ground truth) | Simulator |
| **Observation** | What sensors, records, events, and APIs expose        | Tools/API boundary |
| **Belief**      | What the future AI agent thinks is happening          | Agent      |

The simulator controls reality. Tools expose observations. The agent
develops beliefs.

Example — internally the simulator may know:
- CNC-04 has spindle bearing degradation
- it began at simulation time T
- the underlying cause was lubrication failure
- material batch B-1428 is affected

The agent may only see evidence: vibration history, temperature history,
motor load, maintenance records, jobs, quality inspections, batch
history, alarms, events. It must infer the root cause.

### 4.2 Independence from the LLM

The simulator must run end-to-end with no AI model. No LLM-generated
simulator behavior. The agent plugs in later through a tool/API boundary.

### 4.3 Design goal: behavioral and causal realism, not a physics twin

We are not building a physics-perfect digital twin. We want causal chains
that an investigator can trace, e.g.:

```
bearing health decreases
  → vibration gradually rises
  → motor load rises slightly
  → temperature rises
  → dimensional variance increases
  → reject rate increases
  → eventual machine failure
```

Data must contain noise, irrelevant events, and potentially misleading
evidence so the agent actually has to investigate. **Relationships between
variables matter more than volume of random sensor data.**

### 4.4 Determinism

Important behavior must be reproducible given the same seed and initial
conditions. `BearingDegradation(seed=42)` must produce the same results
every run. All randomness flows from seeded generators owned by the
simulator — never `random.random()` / `datetime.now()` / global state.

### 4.5 Avoid fake complexity

Every abstraction must have a concrete reason to exist. Do **not**
prematurely introduce: microservices, distributed systems, message
brokers, Kubernetes, unnecessary databases, complex event infrastructure,
LLM-generated simulator behavior, or unnecessary frameworks.

Complexity should come from: causal relationships, imperfect
observations, changing state, competing hypotheses, interacting events,
interventions, and evaluation — not infrastructure.

---

## 5. Scope

**`docs/MVP_SCOPE.md` is the authoritative MVP boundary** (one line,
3–8 machines, 4 scenarios, one agent, 6–8 tools, HITL approval,
mandatory post-intervention verification, basic memory, evaluation in
the MVP). What follows is the simulator's first vertical slice within it.

### 5.1 Initial scope — one strong vertical slice

Do not implement the whole simulator at once. The first environment
should eventually contain approximately:

- 3–8 machines
- several sensor types
- factory state
- simulation clock
- production jobs
- material batches
- quality records
- maintenance records
- event history
- one primary failure scenario (likely **bearing degradation**)
- normal operating variation
- at least one unrelated anomaly/noise event
- possibly one unreliable or drifting sensor
- hidden ground truth
- deterministic/reproducible scenario seeds

### 5.2 Remaining MVP scenarios, then later ones

After bearing degradation works and is abstracted, the other three MVP
scenarios: material/batch problem, machine configuration problem, and a
false alarm / transient anomaly. Post-MVP candidates: tool wear, coolant
failure, sensor drift, motor degradation, misalignment, pressure leak,
quality process drift, production bottleneck. Eventually scenarios must
be **composable** so several unrelated or interacting faults can coexist.

---

## 6. Repository structure (target, not dogma)

Inspect the repo before creating or modifying architecture. Do not
overwrite existing patterns without discussing the change first.

```
capstone/
  simulator/
    simulator.py      # top-level facade: owns clock, state, scenarios, step()
    models/           # shared data models (ids, enums, records)
    state/            # FactoryState / MachineState — the "reality"
    clock/            # SimulationClock
    sensors/          # sensor models: read state → produce noisy evidence
    production/       # jobs, material batches
    maintenance/      # maintenance records and actions
    quality/          # inspections, rejects
    events/           # event log / alarms
    scenarios/        # scenario definitions and injection (e.g. BearingDegradation)
    ground_truth/     # hidden truth — NEVER exposed through tools
  tools/              # agent-facing observation/action boundary
  agent/              # the research agent (later)
  evaluation/         # scoring agent beliefs/actions against ground truth
  api/                # optional external interface (later, if needed)
tests/
docs/
  PROGRESS.md         # component status: implemented vs. understood
```

---

## 7. Implementation behavior

Work in **very small increments**. Good increments:

- define `SimulationClock`
- define `Machine` identity/state
- define one `Sensor` abstraction
- implement a deterministic random source
- generate one sensor reading
- implement one state transition
- implement one event
- implement one simple scenario effect

Bad increment: "implement the whole factory simulator."

Do not create hundreds or thousands of lines in one step. Prefer the
smallest implementation that proves the architectural idea.

---

## 8. Testing requirements

The simulator must be highly testable. Whenever we create behavior, first
ask: *how will we prove it works?*

Things we must test:

- same seed + same initial state → same results
- different seeds → different noise but same scenario logic
- bearing degradation causes expected **directional** sensor changes
- hidden ground truth is **not** exposed through agent-facing interfaces
- simulation time advances correctly
- state transitions occur when expected
- actions affect later observations
- scenario effects do not violate defined invariants

Tooling: `pytest`. Run tests after every implementation step.

---

## 9. Dev environment

- Python 3.11, Pydantic v2 available.
- `pytest` is not yet installed: `pip install pytest` (or
  `pip install -e ".[dev]"` once `pyproject.toml` declares it).
- No external services. Everything runs locally and offline.
- Model providers in scope, and no others: Mistral, Google Gemini, Groq,
  NVIDIA, Cohere and Cloudflare. Never add an Anthropic/Claude or OpenAI
  model, SDK, API key name or default to the code, tests or dependencies.
  (This file's name and the word "Claude" in it refer to the coding
  assistant, not to a model the project calls.) Tests never need a key.

---

## 10. Session start checklist for Codex

1. Read this file.
2. Read `docs/PROGRESS.md`. Identify the current component and whether it
   is (a) not started, (b) taught but not yet understood, (c) understood
   but not implemented, (d) implemented but not yet re-explained by the
   developer, or (e) complete.
3. Resume at the correct step of the §1.2 workflow. Never skip a gate
   because a previous session "probably" covered it — if the log does not
   say understanding was verified, verify it.
4. If this is the very first session (nothing implemented), follow the
   "Current objective" below.

### Current objective (first session)

Do **not** implement anything yet. First:

1. Inspect what currently exists.
2. Recommend the first simulator component to build.
3. Explain why it should come first.
4. Explain how it will connect to the rest of the simulator.
5. Ask the first comprehension question.

Then stop and wait for the developer's answer.
