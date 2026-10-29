# AGENTS.md — Capstone Project (Agentic AI Research Agent + Factory Simulator)

This file governs how any coding agent (Claude Code, Codex, OpenCode)
works in this repository. It persists across
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
>   component in small, tested increments, each through its own pull
>   request (§11).
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
>
> **IN PRACTICE SINCE 2026-10-12:** the developer has worked through the
> gated loop again for each new agent checkpoint (checkpoints 1–8b in
> `docs/PROGRESS.md`, each with a pre-check and a closing question), so
> follow §1.1–1.3 for new components. Fixes applied without a gate since
> then are recorded as "built ungated, developer to review (understood:
> no)". If unsure which applies, ask the developer.

The coding agent is operating in a **gated teaching + implementation loop**.

"I wrote the code" and "the developer understands the system" are **two
separate completion criteria**. A component is not done until both are
true, and they are tracked separately in `docs/PROGRESS.md`.

### 1.1 Core rule

Before implementing any meaningful new function, class, module, state
transition, algorithm, or architectural component, the coding agent must **first
teach** what it is going to do, then **verify understanding**, and only
then implement.

- Do **not** build the whole simulator and explain it afterward.
- Do **not** accept "yes" / "I understand" / "got it" as proof of
  understanding. Ask the developer to explain the concept back in their
  own words, or answer a short conceptual question.
- Do **not** proceed merely because the developer wants to move quickly.
  If asked to skip a gate, politely restate the rule and ask the question
  anyway.
- The developer's answer does not need to use the agent's exact
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

### 1.3 After implementing a component, the coding agent must

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

## 2. What must be taught vs. what the coding agent may just do

### 2.1 The coding agent MUST slow down and teach anything involving

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

### 2.2 The coding agent MAY handle without a gate (mention it, don't lecture)

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

The code sits in `capstone-code/` (moved there 2026-10-20 at the developer's
request); its Python name is still `capstone`, so imports and
`python -m capstone.<module>` are unchanged. `tests/` and `docs/` stay at the
top level.

```
capstone-code/capstone/
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
- Set up with `uv sync --all-extras` (as CI does), then `uv run pytest`
  and `uv run ruff check` / `uv run ruff format --check`.
- No external services. Everything runs locally and offline.
- Model providers in scope, and no others: Mistral, Google Gemini, Groq,
  NVIDIA, Cohere and Cloudflare, and (added by the developer on 2026-10-21,
  for comparing larger models) the routers Requesty, xKiro, LLM7 (for a
  support agent only: 100,000 free tokens a day) and Kilo Code's gateway,
  and (added by the developer on 2026-10-23) TypeSafe's System One model Jev,
  for the evaluator's typed judgments only (`TYPESAFE_API_KEY`). The routers
  also list Anthropic and OpenAI models; never use those through them either.
  Never add an Anthropic/Claude or OpenAI
  model, SDK, API key name or default to the code, tests or dependencies.
  (`CLAUDE.md` only imports this file for Claude Code; the coding
  assistant is not a model the project calls.) Tests never need a key.

---

## 10. Session start checklist for the coding agent

1. Read this file.
2. Read `docs/PROGRESS.md` (older notes are in `docs/PROGRESS_ARCHIVE.md`;
   read them only when needed). Identify the current component and whether it
   is (a) not started, (b) taught but not yet understood, (c) understood
   but not implemented, (d) implemented but not yet re-explained by the
   developer, or (e) complete.
3. Resume at the correct step of the §1.2 workflow. Never skip a gate
   because a previous session "probably" covered it — if the log does not
   say understanding was verified, verify it.
4. If this is the very first session (nothing implemented), follow the
   "Current objective" below.
5. Every change goes through a branch and a pull request (§11), never
   straight to `main`.

### Current objective (first session)

Do **not** implement anything yet. First:

1. Inspect what currently exists.
2. Recommend the first simulator component to build.
3. Explain why it should come first.
4. Explain how it will connect to the rest of the simulator.
5. Ask the first comprehension question.

Then stop and wait for the developer's answer.

---

## 11. Every change goes through a pull request

**Rule set by the developer, 2026-10-19:** every change, whatever its size
(a feature, a one-line fix, a docs or CI edit), goes on its own branch and
reaches `main` only through a pull request with a detailed description.
Never commit or push straight to `main`. The point is that every change is
documented on GitHub where the developer can read it.

1. Before starting, `git fetch` and branch from the latest `origin/main`
   (other sessions and people merge to it).
2. Name the branch for the change (`feature/...`, `fix/...`, `docs/...`,
   `ci/...`). One change per branch.
3. Before pushing, run what the change needs and fix any failure (rule set
   by the developer, 2026-10-26; CI runs every test group and a full
   coverage run on every PR, so the full local suite mostly repeats it):
   - **Docs-only, CI-only or config-only changes:** skip local tests. Run
     only `uv run python .github/test_groups.py check` if test files moved.
   - **Code changes:** `uv sync --all-extras`, then `uv run pytest` on the
     test files for the modules touched, plus `uv run ruff check`,
     `uv run ruff format --check` and `uv run python .github/test_groups.py
     check` (every new test file must be added to a CI group in
     `.github/test_groups.py`). Then push and let CI run everything.
   - **Still run the full `uv run pytest` locally when:**
     - the change touches something many modules share (the loop, scoring,
       contracts, the simulator core), or
     - CI is down or slow, or
     - a live model run is next, so a broken build is caught before
       spending API calls.

   Whatever ran locally, never merge on a failing or unfinished CI check
   (step 5).
4. Open the PR with a description that a reader who was not in the session
   can follow. It must have:
   - **What and why:** the problem, and what the change does about it.
   - **Changes, file by file:** each function, class or setting added or
     changed, and what it means in plain English.
   - **Tests:** which were added or changed and what each one proves.
   - **Verification:** the commands run and their results (test count,
     lint, CI groups), and whether anything ran against a real model.
     Never present a scripted or mocked run as a live one.
   - **Gate status:** taught and understood, built ungated, or a closing
     question still outstanding, matching `docs/PROGRESS.md`.
   - **Not done / known limits.**
   - Any commit that reached `main` without a PR, listed so it is recorded.
5. Wait for the PR's CI to finish (`gh pr checks <number> --watch`). Never
   merge on a failing or unfinished check.
6. **Pre-merge technical walkthrough (rule set by the developer,
   2026-10-22).** When the PR implements a feature, then after CI is green
   and before merging, give the developer a technical walkthrough based on
   the PR's actual changed files (`git diff origin/main...HEAD`):
   1. Explain what changed and why, starting with the architecture and
      then the implementation.
   2. Trace one real execution path through the modified code, with file
      paths and function names.
   3. Explain new frameworks, patterns and concepts the developer may not
      know, without spending time on basic syntax.
   4. Identify the important trade-offs, failure modes and assumptions.
   5. Ask three technical questions, one at a time, to verify
      understanding. End the turn after each question and do not reveal
      the answer until the developer has attempted it.
   6. Correct any misunderstanding and point to the relevant source code
      (file and function).

   Do not modify code during the walkthrough unless the developer asks.
   Keep every explanation grounded in the current repository, not
   assumptions. Merge only after the third question has been answered and
   any misunderstanding corrected, and record the result in
   `docs/PROGRESS.md` with one more commit on the PR branch. Docs-only,
   CI-only and config-only PRs skip this step.
7. When CI is green (and, for a feature, the walkthrough in step 6 is
   done), merge with a merge commit (keeps each commit) and
   delete the branch, locally and on GitHub. The developer gave standing
   permission for this on 2026-10-19; it does not cover force-pushes or
   rewriting history, which still need asking.
8. Record the change in `docs/PROGRESS.md` within the same PR.
9. **Rule set by the developer, 2026-10-20:** when a change is based on a
   research paper, credit it in the same PR: add a line to the "Research
   basis" section of `README.md` naming the change and linking the paper.
   List only papers that actually shaped a change that was made.

---

## 12. Who does what: Codex runs, Claude Code builds

**Rule set by the developer, 2026-10-29.** Two coding agents work in this
repository, with separate jobs:

- **Codex runs the master experiments.** The live benchmark runs against real
  models (the EV1 master baseline and later master runs, such as review-only
  critic vs critic follow-up, or `--hazards blackout`), their labelling, and
  the result notes in `docs/benchmarks/` and `docs/PROGRESS.md`.
- **Claude Code builds the code.** Features, fixes, tests, refactors and their
  pull requests. Claude Code does not start live master runs. It may run the
  test suite and scripted (offline) runs to check its own work, and it hands
  a change to Codex to run live once it is merged.

Everything else in this file applies to both: one live run at a time, every
change through a pull request (§11), and the developer's gates (§1).
