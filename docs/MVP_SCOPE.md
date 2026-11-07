# MVP Scope

The MVP is deliberately narrower than the full vision. Its job is to prove
the agent loop works end-to-end; later modules add sophistication on top
of a proven architecture.

## The MVP boundary

> The MVP will model a single simulated production line containing a small
> number of machines and intentionally injected failure scenarios. The agent
> will autonomously investigate detected anomalies by gathering evidence,
> maintaining competing hypotheses, selecting additional observations,
> recommending a bounded intervention, and evaluating the resulting state
> change. Actions that alter the production environment will require human
> approval. The simulator will retain hidden causal ground truth, allowing
> the accuracy and efficiency of the agent's investigations to be
> quantitatively evaluated.

## The one question the MVP answers

Can an autonomous research agent investigate a manufacturing anomaly,
gather evidence from a stateful environment, form and test hypotheses,
recommend an action, and verify whether that action solved the problem?

That is enough to demonstrate a real agent. The entire smart factory is
not required.

## Guiding principle

**Do not build a weak version of every feature. Build one complete
vertical slice:**

```
simulated problem → anomaly → agent research → diagnosis → action
  → environmental change → verification → memory
```

Once that works, each subsequent course module adds a layer of
sophistication instead of the whole course being spent getting the basic
system running.

---

## 1. Simulator: one small production environment

- 1 production line
- 3–8 machines, chosen per run (default 3), named CNC-01 upward in line order
- 1 product type
- 5–8 important sensor values: temperature, vibration, pressure,
  throughput, defect rate, machine state
- production jobs / batches
- a small maintenance history
- a small quality-inspection history

The simulator **evolves over time**; it is not a static dataset.

It contains **hidden ground truth**. Example:

```
bearing degradation → increasing vibration → temperature increase → defect rate rises
```

The agent sees the symptoms but does not initially know the cause.

## 2. Only 3–4 failure scenarios

1. **Machine degradation** — vibration rises, temperature rises, eventual
   quality problems.
2. **Material / batch problem** — sensors look mostly normal; one material
   batch produces increased defects.
3. **Machine configuration problem** — incorrect pressure/speed setting
   causes reduced quality.
4. **False alarm / transient anomaly** — temporary sensor spike that does
   not require intervention.

Scenario 4 matters: the agent should not always conclude that something
is broken.

**Simulator difficulty extension authorized 2026-10-18:** instrument drift,
missing samples, and temporary sensor anomalies are implemented as composable
hidden instrument conditions. The opt-in `build_challenge()` combines these
with bearing and speed faults without changing investigation tool formats or
the ordinary line builder. This supplies harder environments, not a completed
multi-fault evaluator or solver integration. Delayed information/maintenance
records are explicitly excluded by the developer. See the
[difficulty guide](SIMULATOR_DIFFICULTY_COMPATIBILITY.md) for implemented behavior,
tests, limits, and the assessment of Kanika's feedback.

## 3. One investigation agent

No multi-agent system in the MVP. One orchestrating research agent that
does:

```
Observe → Investigate → Hypothesize → Test → Decide → Act/Recommend → Verify → Remember
```

The macro investigation loop runs on Pydantic Graph (`agent/investigation.py`).
The later multi-agent extension (Future Work 3) adds its roles to this same
graph and calls models through the existing chat client; no multi-agent
framework (CrewAI or another) is used (developer's decision, 2026-10-26).

Internally its reasoning is staged:

```
Anomaly detected
      ↓
Collect initial evidence
      ↓
Generate candidate hypotheses
      ↓
Determine missing information
      ↓
Query environment
      ↓
Compare evidence against hypotheses
      ↓
Select most-supported explanation
      ↓
Recommend intervention
      ↓
Human approves
      ↓
Simulator applies intervention
      ↓
Observe new state
      ↓
Determine whether intervention worked
```

The planned single-agent implementation must enforce configurable output-token,
timeout, retry, tool-call, and investigation-iteration limits. Provider-specific
reasoning controls are optional; global execution limits remain enforced by
the agent loop. See Future Work 7 for the later per-role extension.

## 4. The agent's tools (as implemented)

Revised 2026-10-19 to match the code. The original plan listed eight tools
(`get_machine_state`, `get_sensor_history`, `get_production_batch`,
`get_quality_results`, `get_maintenance_history`, `search_incident_history`,
`propose_action`, `observe_after_action`); the implementation covers the same
ground with smaller, more specific tools, all behind the one
`FactoryProvider` boundary (`capstone/providers/factory.py`) with typed
arguments and results.

Research tools a policy may choose (`research_tools()`):

```
get_time()                 current tick and clock time
list_machines()            machine state: status (running / idle / down), current job
get_settings()             each machine's spindle speed
get_readings()             raw machine sensor readings in a tick range (max 300 rows)
get_sensor_trend()         per-block mean/min/max/count of one machine sensor
get_sensor_summary()       count, mean, min, max, first/last, rate in a window
get_factory_readings()     the factory air thermometer
get_events()               event log: alarms, stops, jobs, material batches, maintenance
get_job_history()          everything the log says about one job
get_inspections()          pass/fail quality results, with material batch
get_maintenance_history()  service records from before the run, then this run's
wait()                     let time pass (the only way it does)
recall_memories()          past lessons, offered only when memory is given
```

The fixed procedure after a conclusion, never chosen by a policy
(`PROCEDURE_TOOLS`): `propose_action()` (asks a human), `get_proposals()`
(reads the decision), `execute_action()` (starts approved work). Looking
again after the work is the `verify` stage of the investigation, using the
research tools above, not a separate tool.

Mapping from the original list: machine state → `list_machines`,
`get_settings`; sensor history → `get_readings`, `get_sensor_trend`,
`get_sensor_summary`, `get_factory_readings`; production batch →
`get_events` and `get_inspections` (both carry batch numbers) and
`get_job_history`; quality results → `get_inspections`; maintenance history →
`get_maintenance_history`; incident history → `recall_memories`;
observe after action → the `verify` stage.

MCP may expose these later; MCP itself is not a core simulator/agent MVP
objective. Future Work 2 defines a minimal first MCP slice and its planned
observability, after the core investigation loop works. What
matters is that the agent must decide **"what information do I need
next?"** rather than having everything dumped into the prompt.

`get_sensor_summary()` and `get_sensor_trend()` compute exact statistics in
Python for the agent to interpret. See Future Work 7 for calculation details.

## 5. Hypothesis-driven research (keep in MVP)

This is what distinguishes the project from a chatbot. The agent maintains
a table like:

| Hypothesis          | Supporting evidence       | Contradicting evidence   | Confidence |
|---------------------|---------------------------|--------------------------|-----------:|
| Bearing degradation | vibration ↑, temperature ↑ | none yet                 | 0.72 |
| Bad material batch  | defect rate ↑             | other batches affected   | 0.18 |
| Sensor failure      | abnormal reading          | multiple sensors correlate | 0.10 |

Probabilities need not be mathematically rigorous. The process is the
point:

```
hypothesis → evidence request → evidence → revision
```

## 6. Human approval for consequential actions

The agent may not freely alter the factory.

```
Agent: "I recommend pausing Machine 3 and scheduling inspection."
        ↓
Human approval
        ↓
Simulator executes action
```

- Read-only research happens automatically.
- Actions that change the environment require approval.

## 7. Verification after intervention (mandatory)

The loop does not stop at "here is my recommendation." After the
intervention, simulator time advances, and the agent must ask: *did what I
predicted actually happen?*

```
Prediction:
  If Machine 3 is the cause, vibration and defect rates
  should fall after maintenance.
Observed:
  Vibration:   8.4 → 3.1 mm/s
  Defect rate: 11.2% → 2.3%
Conclusion:
  Intervention successfully addressed the anomaly.
```

## 8. Basic memory

Store per investigation: anomaly, evidence collected, hypotheses
considered, conclusion, action, outcome. A later incident can retrieve
similar prior investigations:

> "A similar vibration/temperature pattern occurred in Investigation #14
> and was caused by bearing degradation."

Enough to demonstrate persistent learning without building a full
organizational knowledge system.

## 9. Evaluation (in the MVP, not deferred)

Because the simulator knows the hidden cause, the agent can be evaluated
objectively. Record per scenario:

| Field | |
|---|---|
| True cause | from ground truth |
| Agent diagnosis | correct / incorrect |
| Relevant evidence available | |
| Evidence actually collected | |
| Recommended action | |
| Correct intervention | yes / no |
| Resolution achieved | yes / no |
| Tool calls used | |
| Investigation length | |

This supports reporting such as: *18/20 root causes correctly identified;
17/20 appropriate interventions selected; average investigation required
6.2 tool calls.* That turns the project from a demo into an experiment.

---

Build a small known-answer regression suite alongside MVP evaluation, using
fixed seeds and implemented simulator scenarios. Ground truth stays available
only to the evaluator. Repeatable simulator inputs do not imply identical live
LLM outputs. See Future Work 7 for the records and later expansion.

## Explicitly excluded from the MVP (→ Future Work)

Deferred, not abandoned — these are extensions of a proven architecture:

- multiple factories
- dozens of production lines
- hundreds of machines
- realistic industrial physics
- high-frequency IoT streaming
- computer vision
- real PLC integration
- real manufacturer data
- autonomous shutdowns
- full predictive maintenance
- multi-agent collaboration
- specialized researcher / planner / analyst agents (the critic is built)
- sophisticated long-term organizational memory
- knowledge graph
- internet research
- vendor research
- multimodal manuals
- digital-twin fidelity
- reinforcement learning
- dynamic tool creation
- autonomous policy learning

## Roadmap after the MVP

**MVP** — single research agent + small factory simulator + anomaly
investigation + hypothesis testing + HITL intervention + verification.

Future Work is not a commitment to implement every candidate. The
[reevaluation register and prompt review](FUTURE_WORK_REEVALUATION.md)
records current status, prerequisites, adoption checks, rejection conditions,
dependency impact and course/production scope. A trigger opens a review;
it does not authorize implementation. Candidates may be rejected, replaced
or deleted when the actual architecture or ecosystem changes.

**How to read this area (2026-10-30).** It lists only work that is not yet
built. What is built is recorded, with its pull request, in
[`PROGRESS.md`](PROGRESS.md); finished items were removed from here on
2026-10-30. The "Future Work N" numbers and the item letters and numbers inside
them are fixed IDs that code comments, tests and other documents cite, so they
stay even though the sections are now grouped by topic, with items sorted from higher to lower priority within each category.

## Future work index: categories and priorities

This reorganizes the existing roadmap, not its implementation status or authority to build. Explicit priorities are preserved; items previously unranked are assigned **LOW** for navigation unless their described dependencies indicate greater urgency. FAR FUTURE retains the project's near-last and absolute-last ordering. Each item links to the original detailed requirements below.

| Category | Highest priority | Scope |
|---|---|---|
| [Pilot readiness and safety](#future-work-pilot-readiness) | HIGH | First shop visit checklist and technician event log (SM-4), rapid triage, reliable abstention |
| [Simulator upgrades and machine fidelity](#future-work-simulator-upgrades) | HIGH | Haas fidelity, power/bearing validation, fault models |
| [Evaluation, benchmarking and reasoning](#future-work-evaluation) | HIGH | Line-wide investigation scope, live runs, critic, ranked technician check list (SM-11), ToT/GoT, runtime reliability |
| [Retrieval and memory](#future-work-retrieval-and-memory) | MEDIUM | Manual and episodic search, reranking, ingestion |
| [Multi-agent roles and coordination](#future-work-multi-agent-roles) | MEDIUM | Specialists, contracts, handoffs and model budgets |
| [Tooling and infrastructure](#future-work-tooling) | HIGH | **Single-machine reading for the first real CNC (SM-1 to SM-10, current focus)**; staged CPU anomaly detection (Python → NumPy/SciPy → optional ML), line-context assessment, manufacturer outreach; telemetry/replay, MCP and audits follow |
| [Planning and automation](#future-work-planning-and-automation) | LOW | Controlled interventions, controller servo diagnostic moves (SM-12) and proactive monitoring |
| [Frontend and operator experience](#future-work-frontend) | LOW | Difficulty recipes and safe configuration UI |
| [Long-term portability and optional interfaces](#future-work-long-term) | LOW / FAR FUTURE | Cross-machine support, added vibration/acoustic sensing (SM-13), vision and voice |

<a id="fw-sm-track"></a>

### Single-machine reading track: current focus, highest to lowest priority (2026-11-07)

**Why this comes first.** The next real test is one CNC machine at a shop visit. The developer's decision (2026-11-07): make the agent good at **reading one machine** before adding agents, reasoning complexity or fine-tuned models, and treat pinpointing the failed part as later work. One machine has no peers, so the useful comparison is the same machine doing comparable work today versus when it ran normally. SM numbers are the ranking (SM-1 highest); each item sits in its own category below and also appears in the full table. The machine, controller and exposed fields are not confirmed yet, so build only what the machine's saved `/probe` shows it supports.

| Rank | Priority | Category | Item | When | Depends on |
|---|---|---|---|---|---|
| SM-1 | **HIGH** | Tooling | [Versioned channel map from `/probe`](#fw-sm-channel-map) (**built, PR #206**; awaits a real probe) | Before connecting | Saved `/probe` |
| SM-2 | **HIGH** | Tooling | [Collection gaps and data quality in the telemetry file](#fw-sm-gap-events) (**gap markers built, PR #204**; staleness and UNAVAILABLE spans not yet) | Before connecting | Existing collector |
| SM-3 | **HIGH** | Tooling | [Read-only real-data provider over recorded JSONL](#fw-sm-real-provider) | Before connecting | SM-1, SM-2 |
| SM-4 | **HIGH** | Pilot readiness | [Shop visit checklist and technician event log](#fw-sm-visit-log) (**built, PR #207**; awaits the visit) | Before and during the visit | None |
| SM-5 | **HIGH** | Tooling | [Time-aware statistics for unevenly sampled data](#fw-sm-time-stats) | Once readings exist (demo agent data is enough to start) | SM-3 |
| SM-6 | **HIGH** | Tooling | [Operating-state segmentation](#fw-sm-state-segmentation) | Once readings exist | SM-1, SM-5 |
| SM-7 | **HIGH** | Tooling | [Same-machine baseline from its own normal history](#fw-sm-own-baseline) | Once normal cycles are captured | SM-4, SM-6 |
| SM-8 | **MEDIUM** | Tooling | [Richer trend features](#fw-sm-trend-features) | After SM-7 | SM-5, SM-7 |
| SM-9 | **MEDIUM** | Tooling | [Cross-signal relationship checks](#fw-sm-cross-signal) | After SM-8 | SM-8 |
| SM-10 | **MEDIUM (conditional)** | Tooling | [Cycle reference signatures](#fw-sm-cycle-signatures) | Only if program/operation IDs are exposed | SM-6, SM-7 |
| SM-11 | **MEDIUM** | Evaluation and reasoning | [Ranked component check list for the technician](#fw-sm-check-ranking) | After SM-1 to SM-9 work on real data | SM-4, SM-9 |
| SM-12 | **LOW** | Planning and automation | [Controller servo diagnostic moves](#fw-sm-servo-diagnostics) | Needs approval beyond read-only | SM-11 |
| SM-13 | **FAR FUTURE** | Optional interfaces | [Added high-resolution vibration or acoustic sensing](#fw-sm-hires-sensing) | Only with shop approval for new sensors | SM-11 |

```mermaid
flowchart LR
    subgraph A["Before connecting (HIGH)"]
        SM1["SM-1 Channel map from /probe"]
        SM2["SM-2 Gaps and data quality in file"]
        SM3["SM-3 Real-data provider"]
        SM4["SM-4 Visit checklist and event log"]
    end
    subgraph B["Once readings exist (HIGH)"]
        SM5["SM-5 Time-aware statistics"]
        SM6["SM-6 Operating-state segmentation"]
        SM7["SM-7 Same-machine baseline"]
    end
    subgraph C["Then (MEDIUM)"]
        SM8["SM-8 Richer trend features"]
        SM9["SM-9 Cross-signal checks"]
        SM10["SM-10 Cycle signatures (conditional)"]
        SM11["SM-11 Ranked technician check list"]
    end
    subgraph D["Later (LOW / FAR FUTURE)"]
        SM12["SM-12 Servo diagnostic moves"]
        SM13["SM-13 Added vibration/acoustic sensing"]
    end
    SM1 --> SM3
    SM2 --> SM3
    SM3 --> SM5 --> SM6 --> SM7 --> SM8 --> SM9 --> SM11
    SM4 --> SM7
    SM4 --> SM11
    SM6 --> SM10
    SM7 --> SM10
    SM11 --> SM12
    SM11 --> SM13
```

### All future-work entries — highest to lowest priority

| Priority | Category | Item | Short summary |
|---|---|---|---|
| **HIGH** | Tooling | [SM-1 Versioned channel map from `/probe`](#fw-sm-channel-map) | Map every data item to its unit, meaning, tool sensor and availability; current focus. Built (PR #206); awaits the machine's real probe. |
| **HIGH** | Tooling | [SM-2 Collection gaps in the telemetry file](#fw-sm-gap-events) | Write lost-data, stale and UNAVAILABLE spans into the JSONL instead of stderr. Lost-data gap markers built (PR #204); stale and UNAVAILABLE spans not yet. |
| **HIGH** | Tooling | [SM-3 Real-data provider](#fw-sm-real-provider) | Answer the existing observation tools from a recorded capture, read-only. |
| **HIGH** | Pilot readiness | [SM-4 Shop visit checklist and technician event log](#fw-sm-visit-log) | Can we read it, interpret it, verify it; log program/tool changes and maintenance. Built (PR #207); awaits the visit. |
| **HIGH** | Tooling | [SM-5 Time-aware statistics](#fw-sm-time-stats) | Time-weighted means and slopes for uneven samples; never span a gap. |
| **HIGH** | Tooling | [SM-6 Operating-state segmentation](#fw-sm-state-segmentation) | Idle, running, cutting and transitions from exposed fields only. |
| **HIGH** | Tooling | [SM-7 Same-machine baseline](#fw-sm-own-baseline) | Compare the machine with its own confirmed-normal history per state. |
| **HIGH** | Pilot readiness | [Fast read-only triage](#fw-rapid-triage) | Built 2026-11-05, opt-in; live latency target still to measure. |
| **HIGH** | Pilot readiness | [Degraded-data handling](#fw-degraded-data) | Set aside 2026-11-05: hazards will not be used. |
| **HIGH** | Simulator | [Haas VF/NGC reference machine](#fw-haas-retrofit) | Ground the simulator in model-specific manuals and known supported telemetry. |
| **HIGH — outreach plan only** | Tooling | [Haas live-telemetry pilot plan](#fw-haas-live-pilot) | Qualify one consenting shop and define safe read-only access, collection, storage, and shadow-mode deployment; build remains post-MVP. |
| **HIGH** | Tooling | [CPU-based statistical anomaly detection](#fw-cpu-anomaly-detector) | Staged CPU roadmap: built-in Python → NumPy/SciPy statistics (the target; an offline probe on 2026-11-06 found it catches every wear and leak case) → scikit-learn (optional, may be added later, not necessary) → River (skip for the capstone); send evidence-backed assessments into line context. |
| **HIGH** | Simulator | [Three-day bearing curve](#fw-bearing-progression) | Enable experiment selection and review wear curve with the manufacturing SME. |
| **HIGH** | Simulator | [Power signal fidelity](#fw-power-validation) | Validate kW assumptions, relevant scoring and energy calculations. |
| **HIGH** | Evaluation | [Line-wide investigation context](#fw-line-context) | Treat the alarmed machine as a starting point; check the relevant line before forming hypotheses. Buildable now. |
| **HIGH** | Evaluation | [Critic coverage check](#fw-critic-coverage) | Opt-in critic challenges both missing cross-machine checks and unsupported neighbor attribution. |
| **HIGH** | Evaluation | [Alarm-centered vs line-wide comparison](#fw-scope-comparison) | Match seeds and settings; wrong-machine, silent, cascading, independent and normal cases. |
| **HIGH** | Evaluation | [Current live run comparisons](#fw-live-runs) | Compare prompts, settings, manual, memory, and scorer outcomes on matched cases. |
| **HIGH** | Evaluation | [Critic follow-up effectiveness](#fw-critic-comparison) | Compare review-only with bounded critic-driven recheck. |
| **HIGH** | Evaluation | [Degraded matrix on live models](#fw-degraded-comparison) | Run clean vs degraded scenarios and examine false-confidence cases. |
| **HIGH** | Evaluation | [Pydantic AI reliability audit](#fw-runtime-audit) | Benchmark deadlines and typed runtime safety; do not migrate without evidence. |
| **MEDIUM** | Tooling | [SM-8 Richer trend features](#fw-sm-trend-features) | Rolling variability, persistence, spikes and trend acceleration. |
| **MEDIUM** | Tooling | [SM-9 Cross-signal relationship checks](#fw-sm-cross-signal) | Flag load and temperature rising at constant RPM as a discrepancy to explain. |
| **MEDIUM (conditional)** | Tooling | [SM-10 Cycle reference signatures](#fw-sm-cycle-signatures) | Compare repeated programs stage by stage, only if the controller exposes them. |
| **MEDIUM** | Evaluation | [SM-11 Ranked technician check list](#fw-sm-check-ranking) | Rank parts to check by likelihood divided by cost to check; update after each finding. |
| **MEDIUM** | Simulator | [Electrical current in amps](#fw-current-draw) | Measure whether current adds distinct value beyond existing power readings. |
| **MEDIUM** | Simulator | [More servo and hydraulic modes](#fw-additional-failures) | Evaluate encoder, pump, valve, lubricant and overlapping-failure scenarios. |
| **MEDIUM** | Simulator | [Fault draw and pack selection](#fw-fault-packs) | Keep seeded draws invariant and choose fault packs by experiment. |
| **MEDIUM** | Evaluation | [ToT + critic ablations](#fw-tot-ablation) | Evaluate pruning, deferral, earlier critic checks and adaptive search. |
| **MEDIUM** | Evaluation | [Concurrent-fault evidence scoring](#fw-multicause) | Support multiple evidence-backed causes rather than arbitrary top-k pruning. |
| **MEDIUM** | Evaluation | [Position-bias / logprob check](#fw-position-bias) | Compare score stability under order changes and optional token likelihood. |
| **MEDIUM** | Evaluation | [Bounded Graph of Thoughts](#fw-got-prototype) | Test graph hypothesis merges only if matched tests justify the overhead. |
| **MEDIUM** | Evaluation | [Model-response evaluation cache](#fw-eval-cache) | Use opt-in SQLite for repeat judgments without caching production investigations. |
| **MEDIUM** | Evaluation | [Role-specific model benchmarks](#fw-role-benchmarks) | Measure specialist task quality, latency, cost and schema failures. |
| **MEDIUM** | Retrieval | [MMR episodic search](#fw-mmr) | Test diversity of historical investigations against similarity retrieval. |
| **MEDIUM** | Retrieval | [Voyage manual reranking](#fw-voyage) | Benchmark only the manual/SOP retrieval path. |
| **MEDIUM** | Retrieval | [Jev for recall or routing](#fw-jev-recall) | Test model-driven recall rerank and routing if baseline errors warrant it. |
| **MEDIUM** | Multi-agent | [Line Sentinel (third agent)](#fw-line-sentinel) | Decide where and when to investigate, and whether that data can be trusted, after the line-wide packet; never names a cause. |
| **MEDIUM** | Multi-agent | [Planner / researcher / analyst roles](#fw-specialist-roles) | Add bounded specialist stages after demonstrated gains. |
| **MEDIUM** | Multi-agent | [Typed handoffs and contracts](#fw-handoffs) | Define evidence-only, full and challenge handoffs with shared provenance. |
| **MEDIUM** | Multi-agent | [Per-role execution budgets](#fw-agent-budgets) | Bound output, retries, tool calls and time across all agents. |
| **MEDIUM** | Tooling | [Simulated telemetry stream and replay](#fw-telemetry-replay) | Store context-rich readings once; query recent/history windows and compare replay with monitoring. |
| **MEDIUM** | Tooling | [Read-only MCP boundary](#fw-mcp) | Introduce authenticated MCP capabilities only when core agent is ready. |
| **MEDIUM** | Tooling | [Traces and response validation](#fw-response-check) | Observe agent/tool calls and verify schema, permissions and freshness. |
| **MEDIUM** | Tooling | [SubQ full-repo audit](#fw-subq) | Examine cross-file integrity on a pinned snapshot before sweeping refactors. |
| **LOW** | Planning | [SM-12 Controller servo diagnostic moves](#fw-sm-servo-diagnostics) | Approved test motions and servo frequency analysis to separate bearing, ball screw and guide. |
| **LOW** | Evaluation | [Prompt and setting comparisons](#fw-prompt-settings) | Finish existing targeted live A/B tests. |
| **LOW** | Evaluation | [Episodic memory live comparison](#fw-memory-comparison) | Compare no memory, keyword and semantic recall modes. |
| **LOW** | Evaluation | [Memory experiment reporting](#fw-memory-reporting) | Add focused reruns, repeats and memory-store manifest. |
| **LOW** | Evaluation | [Keyword / semantic parity](#fw-recall-parity) | Align indexed fields and introduce semantic relevance cutoff. |
| **LOW** | Evaluation | [Jev auto-label agreement](#fw-jev-labels) | Measure against hand labels before using predictions for scoring. |
| **LOW** | Evaluation | [Regression-case expansion](#fw-regression-cases) | Extend known-answer suite when causal simulator support exists. |
| **LOW** | Evaluation | [Deterministic sensor calculations](#fw-sensor-calculations) | Add window comparisons when justified by observed diagnostic need. |
| **LOW** | Evaluation | [Pydantic Evals framework](#fw-pydantic-evals) | Consider framework substitution only after measured reporting pain. |
| **LOW** | Retrieval | [Agent-directed RAG refinements](#fw-rag) | Improve remaining retrieval orchestration without redundant queries. |
| **LOW** | Retrieval | [Near-duplicate memory filter](#fw-near-duplicate) | Test write-time semantic duplication threshold. |
| **LOW** | Retrieval | [Docling / HybridChunker](#fw-docling) | Evaluate parsing of real PDFs and maintenance documents. |
| **LOW** | Multi-agent | [Role compatibility probes](#fw-role-compatibility) | Check structured outputs, fallback and budget behavior per provider. |
| **LOW** | Multi-agent | [Cohere Rerank](#fw-cohere-rerank) | Use retrieval-only reranking when justified; not a chat agent. |
| **LOW** | Multi-agent | [Requesty strict JSON](#fw-requesty-json) | Test gateway JSON schema translation by actual provider/model. |
| **LOW** | Tooling | [uv, ty, Dependabot, Hypothesis, xdist](#fw-tooling) | Conditionally improve testing and dependency hygiene. |
| **LOW** | Planning | [Controlled process experiments](#fw-experiments) | Plan and verify small approved machine-setting trials. |
| **LOW** | Planning | [Automatic monitoring triggers](#fw-proactive) | Start investigations proactively only after lifecycle safety is mature. |
| **LOW** | Simulator | [Additional optional fault pack](#fw-next-pack) | Add a new causal fault only if benchmark coverage needs it. |
| **LOW** | Frontend | [Difficulty modes and operator UI](#fw-frontend) | Offer 1/4/8-fault modes and safe configuration controls. |
| **LOW** | Portability | [Equipment profiles and tenancy](#fw-portability) | Consider YAML, schemas and isolation only when actual needs appear. |
| **FAR FUTURE** | Optional interfaces | [SM-13 Added vibration or acoustic sensing](#fw-sm-hires-sensing) | High-resolution sensors for part-level localization, with shop approval. |
| **FAR FUTURE** | Optional interfaces | [Sensor-triggered visual inspections](#fw-vision) | Use bounded camera/model observations only with shop approval. |
| **FAR FUTURE** | Optional interfaces | [Technician voice reports](#fw-voice) | Offer reviewed speech input only after demonstrated user value. |

**Organization:** Detailed sections are grouped by category and arranged HIGH → MEDIUM → LOW → FAR FUTURE within each group, while technical explanations and dependency notes remain with the relevant work. Future Work IDs are unchanged; FW7's specialist benchmarking and budgets appear under Multi-agent Roles. No implementation check or new feature development was performed.


<a id="future-work-high-priority-pilot-readiness-and-simulator-realism"></a>

## Future work: Pilot readiness and safety

<a id="future-work-pilot-readiness"></a>

### Shop visit checklist and technician event log (HIGH; SM-4; proposed 2026-11-07)

<a id="fw-sm-visit-log"></a>

**Category: Pilot readiness and safety. Rank: SM-4 in the [single-machine track](#fw-sm-track). Status: FUTURE WORK ONLY.** The first session with a real machine should answer three questions. It stays local, read-only and independent of model inference, as the [pilot plan](#fw-haas-live-pilot) already requires. The machine may not be a Haas; do not assume its control, interface or fields.

- **Can we read it?** Save `/probe` (to a folder outside the repository), identify fields and units for the [channel map](#fw-sm-channel-map), confirm shop-approved read-only access, and confirm recording while the machine runs has no measurable effect.
- **Can we interpret it?** Capture several normal operating cycles, watch state transitions (idle, warm-up, cutting, tool and program changes), inspect timestamps and gaps, and decide whether spindle load, RPM, alarms and any other exposed signals are enough for useful analysis.
- **Can we verify it?** Ask an operator or technician to log program changes, tool changes, warm-up, unusual events and maintenance during the capture: a timestamped file with event type, short note and who logged it, kept with the private pilot data, not in this repository. Also ask for past alarm and maintenance history and what technicians check first for common symptoms; these feed the [same-machine baseline](#fw-sm-own-baseline) and the later [ranked check list](#fw-sm-check-ranking). Without this context, abnormal readings cannot be interpreted reliably.

**Accept:** a saved probe, a capture with at least several normal cycles, and an event log whose entries can be matched to the capture's timestamps.

**Status (2026-11-07): tooling built, PR #207 (built ungated at the developer's direction; questions and walkthrough owed; understood: no).**
- *Built:* `capstone/ingestion/visit_log.py` reads the technician's CSV log (`at,event_type,note,logged_by,until`), refusing a bad line by number and a time with no UTC offset.
- *Built:* each entry is placed against the capture as covered (inside a gap-free stretch, 60 s tolerance), in a gap, or outside, with the offset to the nearest observation.
- *Built:* `python -m capstone.ingestion.visit_log check --probe --capture --events` prints the checklist under the three questions, plus the items only a person can confirm; `template --out` writes an empty log outside the repository.
- *Not built:* a check that the log's clock agrees with the controller's (needs the real probe's fields; SM-6 uses it). Counting normal cycles needs SM-6, so it stays a confirm-by-hand item.
- *Acceptance:* tested on synthetic files only. The visit itself, and so the acceptance check, has not happened yet.

### First increment — line-wide investigation before continuous monitoring (HIGH; proposed 2026-11-02)

<a id="fw-incident-context"></a>

**Status: FUTURE WORK, not implemented.** The immediate pilot-readiness
improvement is the [incident-first, line-wide investigation scope](#fw-line-scope)
under Evaluation. A bounded incident packet gives the existing investigator
the trigger, line snapshot, cross-machine events and neighbor trends before
planning. Its [critic coverage check](#fw-critic-coverage) is opt-in;
[matched-seed comparisons](#fw-scope-comparison) must show improved causal
attribution without unjustified upstream blame or excessive investigation.
Implement and evaluate this workflow change **before** the [simulated telemetry
store and continuous monitor](#fw-telemetry-replay). This remains within the
single-line, Pydantic Graph, read-only evidence, human approval and
post-intervention verification boundaries.

### High-priority future work — pilot-readiness: fast triage and the rest of abstention (updated 2026-10-30)

**Status: rapid triage is not built; the degraded-data work is mostly built. Priority:
HIGH, before a customer pilot and before expanding reasoning complexity.** These
are small, measurable changes to the existing simulator/agent workflow, not a new
agent framework or permission to connect to real machinery. Implement each item
in a separate PR with tests and matched before/after runs. Preserve Pydantic
Graph, shared budgets, human approval and hidden-truth isolation.

Built from the original list of three (2026-10-29): closing the critic feedback
loop (the opt-in `recheck` follow-up, C2r, PR #119, and the critic before every
conclusion with every hypothesis, C1b, PR #122), and the sensor-feed blackout
with the degraded-case matrix and the abstention scorecard (D1, D2). Measuring
the critic loop is under [live runs owed](#live-runs-and-follow-ups-still-owed).

<a id="fw-rapid-triage"></a>

#### 2. Split rapid triage from deep investigation (HIGH)

**Status (2026-11-05): built, opt-in, off by default** (`TRIAGE=on` or
`experiment run --triage`). `InvestigationState.mode="triage"` with
`triage_budgets` (90 s, 6 tool calls, no follow-up or critic: placeholders
until live latency is measured); `propose()` ends a triage, so it is
read-only by construction; `needs_deep_run` decides in code whether a deep
run (investigation 2, `follows_triage`) follows; experiment records and the
report give triage p50/p95 seconds, supported vs not, timeouts and deep runs.
Still owed: the live latency measurement and the triage/deep comparison runs
(Codex), and labelling triage conclusions apart from the deep run's.

**Gap:** `agent/state.py:Budgets` currently defaults to a
`timeout_seconds=1200` investigation with `followup_seconds=400`.
A potentially 20-minute response is difficult to present as immediate
shop-floor triage, although it may be acceptable for extended root-cause
research.

**Minimal implementation:** expose two explicit modes over the **same**
`FactoryProvider`, typed evidence and agent orchestration:

- **Rapid triage:** a tight configurable wall-clock/model/tool budget;
  report anomaly, leading **preliminary** cause(s), evidence, uncertainty,
  missing checks and whether a deep investigation is recommended. Return
  `insufficient_evidence` rather than force a diagnosis if the budget ends.
  This is **read-only**, with no maintenance proposal or execution.
- **Deep investigation:** the existing longer, bounded
  investigate/hypothesize/test/conclude/propose/verify/remember workflow,
  invoked separately when appropriate. Give it a new run/investigation
  identity and a traceable reference to the triage result. Never imply
  that starting deep research is equivalent to human approval for a fix.

**Engineering gate:** define a measurable triage response-time target
(SLO) from actual provider latency, then set limits that can meet it;
a candidate target such as p95 <= 90 seconds is a hypothesis, **not**
a capability claim. Record service latency separately from simulation
ticks, and count timeout/partial-result outcomes rather than hiding them.
Triage may be extended only through an explicit deep-run decision; it
must not secretly continue for 20 minutes.

**Acceptance tests:** identical seeded fault and normal-operation cases
run through triage and deep modes; a clear preliminary result vs.
`insufficient_evidence`; hard budget enforcement even when providers
are slow; deep mode retains existing human approval and post-action
verification; neither mode sees hidden truth. Report p50/p95 latency,
time-to-first-useful-answer, accuracy among answered cases, abstention
rate, and additional model/tool calls.

<a id="fw-degraded-data"></a>

#### 3. Degraded data and abstention: what is left (HIGH)

**Status (2026-11-05): set aside.** The developer said hazards will not be
used, so the items below (live matrix, conflicting-observations case, demo
traces) are not planned; the hazard code stays as it is unless it breaks.

Built (D1, D2): the timed sensor-feed blackout (`--hazards blackout`), the
standard hazards (timeouts, dropped rows, a stale record), the 11-case degraded
matrix (`evals/degraded.json`: clean and blackout pairs for bearing, wrong
setting, false alarm, bad batch and the compound challenge, plus one
standard-hazards case) and the abstention scorecard (accuracy when committed,
abstention rate, confident and wrong, false interventions, missing data read as
normal, recovery). Plain accuracy is unchanged: abstaining still counts as wrong
there.

Left:

- **Run the matrix live** against the clean-data baseline (Codex). The scorecard
  has not run on a real model.
- **A conflicting-observations case** (two permitted sources that disagree),
  which the matrix does not have.
- **The failure the matrix exists to catch:** an agent that reads missing data as
  a normal reading and answers confidently (for example "a false alarm" at 0.85
  on a wearing machine). Whether the agent-visible results mark
  `unavailable`/`stale`/`partial` apart from a normal value, and whether it can
  answer with an explicit insufficient-evidence outcome plus a next check or a
  human escalation, is open until the live run shows what it does. A failed
  retry must not be read as evidence that no fault exists.
- **Demo traces** showing both an appropriately uncertain answer and a
  successful recovery.

**Sequencing:** record the alarm-centered baseline and evaluate the
[incident-first context packet](#fw-incident-context) first; then rapid triage
mode and the live degraded-data run before any pilot demonstration. These tasks complement, rather than replace, the separate
Haas VF/NGC reference-machine retrofit below; no physical Haas connection is
needed.


## Future work: Simulator upgrades and machine fidelity

<a id="future-work-simulator-upgrades"></a>

### High-priority future work — retrofit the simulator around real Haas VF-series machines (2026-10-29)

<a id="fw-haas-retrofit"></a>

**Priority: HIGH.**

**Status: ROADMAP ONLY; not implemented. Priority: HIGH, after the current single-machine investigation/critic baseline is measured.** The developer wants the reference/default CNC to be a **specific Haas VF-series machine with Next Generation Control (NGC)** rather than the fictional generic CNCs. Keep the existing seeded simulator, machine-independent agent and `FactoryProvider` interfaces. This is a **machine-specific simulator retrofit, not a promise that we already have a connected Haas, a complete manual, or every physical sensor**. Start with a single Haas reference machine and make multiple-machine lines an optional configuration. Do not replace the existing simulator or its tests wholesale until parity and regression checks pass.

**Reference documentation and versioning.** Obtain and archive the authorized, model- and control-specific Haas VF/VM operator manual, service/troubleshooting procedures, alarm tables, available data-collection documentation, and relevant electrical/sensor documentation. Use the revision, model, year, control generation and software build as identifiers; verify rights to redistribute before checking any copyrighted manual into the public repo. The currently indexed `SIM-CNC-001` is a **synthetic manual**, not a Haas manual. Introduce manufacturer documents into the existing manual/SOP RAG index as a distinct, cited, versioned source; do not blend their statements with synthetic assumed facts. Manual instructions are diagnostic evidence, **not a list of telemetry fields guaranteed to be remotely readable**.

**Two supported control-generation profiles.**
- **Primary/default profile: Haas VF-series NGC** (exact VF model and software revision TBD). Discover exposed MTConnect data items through `probe`, then `current`/`sample` where enabled; consider NGC Ethernet Machine Data Collection (MDC) as a separate option. Haas documents the NGC MTConnect HTTP interface and Ethernet Q/E commands, but available items must be checked on the target controller.
- **Legacy compatibility profile: early-2000s to mid-2010s Haas Classic Control (CHC)**, including older VF machines. Haas's 2002 VF operator manual documents **Setting 143** and read-only RS-232 `Q` queries for controller identity, mode, tool changes, elapsed run/motion time, cycle time and part counters. Probe the actual installed hardware/firmware, port availability and permitted queries; do not assume NGC features exist on CHC or that all legacy models export spindle load, vibration or temperature.
- **Fallback for missing controller readings:** separately instrument external sensors with the factory's approval (for example vibration, motor-current clamp/energy monitor, thermocouple or acoustic monitoring) and timestamp/source them independently. Do not infer that Python can retrieve a value the machine does not expose. A derived metric or proxy must be labelled as **estimated** and validated, never presented as a measured sensor.

**Inventory and mapping before implementation.** Build an evidence-backed capability matrix: machine model/year/serial *recorded privately*, CHC or NGC, firmware, comms physical path, permissions, exposed field, unit, sampling interval, timestamp quality, whether the reading is direct/controller-derived/external/estimated, and whether it is safe to query during cutting. Map only supported measurements to typed provider fields; preserve explicit **unavailable/unknown** values rather than silently fabricating missing signals. Normalize operating mode, RPM, spindle load (when available), cycle counters, alarms and energy/power when exposed; align these with manual-based diagnosis and existing fault packs. Different fault candidates require different evidence sufficiency: for example load and RPM can help test hypotheses but cannot alone verify spindle-bearing damage.

**Proposed staged implementation:**
1. Record a reproducible one-machine baseline with the existing critic-enabled investigation, simulator ground truth, manual RAG and verification metrics.
2. Specify one concrete **Haas VF NGC digital reference profile** with realistic capabilities and units from official documentation; refit `simulator/state.py`, `simulator/sensors.py`, `simulator/scenarios.py`, fault packs and line builder through a machine profile/configuration layer, not a proprietary hard-coded agent. Preserve fault truth outside tool responses.
3. Add a versioned Haas manual corpus to the **manual index only**; update symptom-to-check and alarm-to-evidence mappings with citations. Keep MMR restricted to episodic memory as already decided; evaluate manual relevance/reranking separately.
4. Create an **NGC read-only adapter** (MTConnect or authorized MDC) and a **CHC read-only RS-232 adapter** only after a real machine's capability/permission check. A deterministic mock/recorded adapter should expose the same typed observations for offline tests. No controller writes, setting changes, E commands, macro writes or unapproved remote interventions. Existing human approval remains mandatory for proposed changes.
5. Add optional externally fitted sensors where needed and keep the observer's confidence, measurement provenance, timestamp offsets and gaps explicit; detect missing, stale and contradictory readings.
6. Validate on known-answer seeded scenarios, realistic legacy sparse-telemetry cases and — only with a cooperating shop — authorized historical/live read-only data. Report diagnosis accuracy, evidence relevance, false positive rate, root-cause uncertainty, supported/unobservable causes, time budget, and human verification outcomes.

**Release/acceptance gates:** The default simulator scenario must be a **single Haas VF NGC profile** once validated, while generic/multi-machine and CHC legacy profiles remain selectable. Existing tests, baseline/critic comparisons, human-approval gate and hidden-truth isolation must still pass. Include an explicit manufacturer-document revision trace, calibration notes, packet/serial failure tests and offline repeatability. Demonstrate that the agent says *insufficient data* where appropriate instead of assuming it has a sensor. Never connect to an actual shop floor or claim compatibility with every Haas/control/serial range without the specific owner's approval and verified interface.

**Primary references (to verify per target machine):** [Haas manuals archive](https://haascnc.com/owners/Service/operators-manual.html), [2002 VF-Series operator manual](https://www.haascnc.com/content/dam/haascnc/en/service/manual/operator/english---vf-series-operator%27s-manual---2002.pdf) (Setting 143, RS-232 Q commands), [NGC Machine Data Collection](https://haascnc.com/service/troubleshooting-and-how-to/how-to/machine-data-collection---ngc.html), [NGC MDC Ethernet commands](https://legacy-aem.haascnc.com/service/online-manuals/next-gen-control-electrical---service-manual/ngc---machine-data-collection.html).

### High-priority future work — simulator fidelity: what is left (updated 2026-10-30)

<a id="fw-fidelity"></a>

**Priority: HIGH for bearing and power review; MEDIUM for additional sensors and faults.**

These come from the developer's discussion with manufacturing engineer Brandon
Reff (2026-10-23). The bearing profile and kW power were first, and servo and
hydraulic failures were added as fault packs; all are built and recorded in
`PROGRESS.md` (F1 three-day bearing profile, F2 power in kW, F3-F5 the fault-pack
registry and the servo-drive and hydraulic-leak packs). The numbers behind them
are working assumptions for Brandon to review. What is left:

<a id="fw-bearing-progression"></a>

**A. Bearing progression.**

- Make the three-day profile usable in experiments: let experiments and the
  memory comparison choose `bearing_profile`, and lengthen the monitor's
  4,000-tick wait, which ends before a three-day fault's typical first alarm
  (about 5,000 ticks after it starts).
- Brandon's review of the curve: a quiet stretch at half the wear rate, then
  from an onset at health 0.8 a full-rate ramp to failure, a median of 4,294
  running ticks (target 4,320, about three operating days; the original curve
  reaches failure in 9-28 hours of running). Support compressed-damage
  experiments without changing global clock semantics, daily ambient cycles,
  agent time budgets or the existing known-answer cases. Measurements and how to
  repeat them: `docs/benchmarks/2026-10-26-bearing-three-day.md`.

<a id="fw-power-validation"></a>

**B. Machine power.**

- Brandon's review of the assumed numbers (idle 2 kW; running 2 kW plus spindle
  power 15 kW x load x speed ratio; bearing friction 1.5 kW x wear squared;
  noise 0.2 kW).
- kWh as energy summed over simulated time, only if a question needs it (no tool
  reports it). Distinguish kW (instantaneous power) from kWh, and never relabel
  the percentage motor-load readings as kW.
- Whether power belongs in `RELEVANT_EVIDENCE` for the wrong-setting fault: it
  is not credited as evidence in scoring today.
- Hydraulic pump power in the reading, when the hydraulic pack calls for it.

<a id="fw-current-draw"></a>

**C. Examine electrical current draw (amps) as a related observation.**

- Brandon also suggested watching machine **current draw**, distinct from
  reporting whole-machine electrical power in kW. Evaluate whether a useful
  measured channel would be spindle-motor current, servo-axis current, or
  hydraulic-pump motor current; label its machine/component and units clearly.
- Compare amperage at equivalent operating loads, speeds, and modes. A rising
  current can indicate increased mechanical resistance, but neither a high
  current nor high kW uniquely identifies a bad bearing. If amperage and
  power are both *computed from the same hidden load*, they are correlated,
  not independent corroborating evidence. Physical electrical assumptions
  (voltage, phases, power factor, efficiency) must be explicit before
  converting one into the other.
- This is a **related follow-up to HIGH-priority kW monitoring**, not a
  claim that a current sensor exists today. Evaluate the additional
  diagnostic value and cost before adding a separate telemetry channel.

<a id="fw-additional-failures"></a>

**D. More failure-capable components, after servo and hydraulics.**

- Servo/axis: an encoder or position-feedback fault, drive overheating, current
  in amps, and a breakdown when the drive is worn out.
- Hydraulics: pump wear, oil temperature, fluid level, a sticking valve.
- A rule in the rule-based baseline and a known-answer case for each of the
  servo and hydraulic packs.
- Ball screws and lubrication were discussed as additional possibilities, but
  were not specifically attributed to Brandon; do not present them as part of
  his feedback.
- Test normal operating variation, misleading overlap between causes,
  concurrent faults, deterministic seeds and hidden-truth isolation for each.

**Dependencies and sequencing.** Establish a baseline from current simulator
traces, get engineering confirmation on time/threshold and power bands, then
implement these as separate, small PRs with tests and regression comparisons.
Neither improvement changes the MVP commitment merely by being documented.

See the [simulator fidelity reevaluation gates](FUTURE_WORK_REEVALUATION.md#high-priority-simulator-fidelity-candidates-2026-10-23).

### Future Work 8 — harder scenarios: difficulty modes, a frontend, and simulator growth

Status: future work, partly built. Recorded 2026-10-20 at the developer's
request. The compound challenge runs in experiments (E6: `run --challenge
SEEDS` and the known-answer case KA-09), and scoring judges runs with several
true faults (E5: `Score.causes`, `causes_found`, `wrong_causes`,
`causes_resolved`, `fully_right`). What is left is below.

#### Fault packs: what is left (planned 2026-10-22)

<a id="fw-fault-packs"></a>

**Priority: MEDIUM for deterministic pack selection; LOW for a new fault.**

The registry (`capstone/faults.py`) and the servo-drive and hydraulic-leak packs
are built (F3-F5); a new fault now costs 3 or 4 files, not about 12, and the
agent-side and evaluator-side halves of each pack are kept apart. Left:

- <a id="fw-fault-seeds"></a> **Key each seed's fault draw** so that adding or leaving out a pack does not
  shift what the other faults draw. Today `build_scenario` draws from `FAULTS`
  even when the fault is forced, so a longer list could change a seed's machine
  and start tick; new packs avoid this only by being forced
  (`DEFAULT_DRAW` keeps every existing seed unchanged).
- <a id="fw-pack-selection"></a> **Choose packs per experiment.** Packs are fixed in code, not added at run time
  (the same seed must build the same factory). Choosing which packs an
  experiment uses is most of what the easy / intermediate / hard modes need;
  each pack carries a `difficulty` tag that nothing reads yet.
- <a id="fw-next-pack"></a> **The next pack** (for example coolant pressure with a coolant leak: pressure
  falls, the machine runs hotter, rejects rise, and the fix is a coolant
  repair). Decide first whether the new sensor raises its own alarm: monitoring
  reacts only to an alarm, a stopped machine or a run of rejects. New sensors,
  failure models and scenario injection are on the teaching list (`AGENTS.md`
  section 2.1), so whether this is taught or built ungated is the developer's
  call.


<a id="future-work-measurement-and-evaluation"></a>

## Future work: Evaluation, benchmarking and reasoning

<a id="future-work-evaluation"></a>

### Live runs and follow-ups still owed

<a id="fw-live-runs"></a>

**Priority: HIGH for baseline, critic and degraded-data comparisons; LOW for optional reporting improvements.**

The code for these is built; what is missing is a live, scored run or a small
follow-up. Live runs are Codex's, one at a time (`AGENTS.md` section 12). Judge
each against the master runs on the same known-answer cases.

- <a id="fw-prompt-settings"></a> **Prompt and setting changes** (live comparison outstanding for each):
  `STEP_QUESTIONS=1` against 2 (A12); hiding the action bar from the prompt with
  `STATE_ACTION_BAR=false` (A13); the check-before-stopping guidance (A14); the
  manual guidance with the manual on by default and the manual step (A15, M1b).
- <a id="fw-critic-comparison"></a> **The critic:** review-only against the follow-up (`CRITIC_FOLLOWUP`, C2r) and
  against the critic before every conclusion with every hypothesis (C1b), on the
  nine known cases. Check whether its objections separate right runs from wrong
  ones: in both live runs that reached it (2026-10-29) it objected, including
  when the agent was right. Tuning the critic comes after these runs.
- <a id="fw-degraded-comparison"></a> **The degraded-case matrix** (`evals/degraded.json`, D2) against the clean-data
  baseline; see pilot-readiness item 3.
- <a id="fw-memory-comparison"></a> **A live memory comparison run:** fill the store on tuning seeds
  (`experiment run --memory --audit ...`), backfill the index
  (`python -m capstone.memory.backfill`), then
  `python -m capstone.memory_comparison run --known`, label and report. The
  command is built and was made fair (C3a, C3c) but has never run against a real
  model; it is the only way to learn whether memory improves investigations.
- <a id="fw-memory-reporting"></a> **Memory comparison follow-ups** (C3c notes): a `--cases` option on `run` to
  rerun chosen cases in every mode (the developer's idea, for cases lost to
  outages); repeats with a per-case win/loss count between modes; and a header
  recording the store's size, embedding model and policy version. With one run
  per case and outages removing cases, the totals are noisy and not always like
  for like.
- <a id="fw-recall-parity"></a> **Make keyword and semantic recall comparable** (C3c notes 6-7): both searches
  should read the same fields of a memory (keyword reads category, symptoms,
  action, machine and lesson; semantic embeds category, symptoms, diagnosis and
  lesson), and semantic search needs a relevance cutoff instead of always
  returning k memories, or a keyword/semantic difference is not purely words
  versus meaning and semantic mode puts unrelated memories in front of the agent.
  This changes what the agent sees: teach first.
- <a id="fw-jev-labels"></a> **Finish the check on Jev's labels** (T1): measure its agreement with hand
  labels (`python -m capstone.evaluation.auto_label ... --hand`) before any
  experiment trusts it; add it to scoring only after that.
- <a id="fw-regression-cases"></a> **Grow the known-answer suite after changes** to prompts, models, tools,
  memory, providers and handoffs. New cases (workload changes, ambient changes,
  sensor anomalies, idle behavior) are added only when the existing simulator
  can reproduce the intended condition; do not invent fault models just to fill
  the list. Ground truth stays with the evaluator, and repeatable simulator
  inputs do not imply identical live model outputs.

### Line-wide investigation scope (HIGH; near-term; proposed 2026-11-02)

<a id="fw-line-scope"></a>

**Status: FUTURE WORK, buildable now; no runtime changes in this PR.**
This work changes the existing investigation workflow and its evaluation,
not the underlying simulator, model or reasoning framework. It does **not**
depend on a new telemetry store, continuous monitor or replay system and
should not wait for them. An alarm tells us where a symptom appeared,
**not** where the problem originated. Preserve Pydantic Graph, the existing
`FactoryProvider`, shared budgets, manual and episodic retrieval, human
approval, mandatory verification and evaluator-only hidden causal truth.

1. <a id="fw-line-context"></a> **Line-wide investigation context (first
   increment).** Today the triggering `DetectedAnomaly` effectively narrows
   the investigation to its machine. Add a mandatory, bounded
   **incident-context assembly step** in the `observe` stage of
   `agent/investigation.py`, before the manual and planning stages. Pass
   the existing investigator an *incident*, not a machine-only assignment:
   - **Trigger:** source event/alarm/anomaly kind, description, original
     machine ID (nullable), event identifier if available, and trigger
     simulation tick/time. A routine check with `machine_id=None` uses
     this same step; it does not mean an always-on monitor exists.
   - **Whole-line snapshot:** `list_machines()` for **every** machine's
     observed status and current job, with an as-of tick, and a simple
     upstream/downstream topology based on the CNC-01-upward line order.
     Capture current machine state *at trigger time*: querying it later
     does not reconstruct a historical snapshot.
   - **Cross-machine events:** recent `get_events()` with **no machine
     filter**, over a bounded configurable preceding simulation-tick
     window. Preserve event times/source, coverage and missing/incomplete
     history; do not leak events after the trigger into a before-trigger
     incident packet.
   - **Neighbor trends:** bounded `get_sensor_summary()` or
     `get_sensor_trend()` for the triggering machine and its immediate
     upstream/downstream neighbors. Preserve sample counts, time window,
     missing/stale/partial status and provenance. Do not dump all raw
     sensor readings across the factory into the model's prompt.
   - **CPU detector assessment (later HIGH-priority tooling increment):**
     once the [statistical anomaly detector](#fw-cpu-anomaly-detector) is
     built, always include a **bounded assessment for every machine in the line**,
     not only the machine that alarmed: timestamp-bounded trend/deviation
     status, data sufficiency, underlying measurement references and rule IDs.
     Use a compact whole-line screening pass and request detailed windows for
     flagged machines and relevant neighbors. This addresses the specific
     failure mode where the agent assumes the alarmed machine caused its own
     alarm. This is **derived sensor evidence, not a cause diagnosis**; do not give
     the investigator hidden truth or treat a score/label as a confirmed fault.
     The detector is a normal part of the agent with **no setting to turn it
     on or off** (developer's decision, 2026-11-06). Its effect is measured by
     comparing runs before and after it is merged, not by a switch.
   - **Line record:** categorize each machine as abnormal, apparently
     unaffected or lacking reliable observations *for this window*,
     without treating incomplete evidence as proof of health. Keep this
     context and each examined machine/reason in investigation state and
     trace; let the investigator select deeper targeted checks and
     hypothesis-discriminating observations as needed.

   **Refinements (2026-11-05):** see [A4 line snapshot](COURSE_NOTEBOOKS_FUTURE_WORK.md#a4-line-snapshot-at-the-start-of-the-investigation-medium-evidence)
   for additions (every machine's sensor summaries, reject counts per batch,
   reads through the hazard-wrapped provider, a coverage split of exposed,
   targeted and used machines) and an open question: who decides the line
   record's "abnormal" category, and by what threshold, given the rule that
   code returns numbers, not labels.

   Start correlation with only **topology plus an explicit simulation-time
   window** (for example, if CNC-02 alarms, inspect CNC-01's preceding
   abnormal events). Correlation supplies a lead, not causal proof.
   Preserve distinct incident groups for independent machine faults.
   Do not invent a triage LLM or new tool by default: existing
   `list_machines()`, unfiltered `get_events()` and trend/summary tools
   should support the initial packet. A small typed assembly step or
   backward-compatible `DetectedAnomaly` enrichment is sufficient.
   Evidence provenance matters; two summaries of the same readings are
   not independent confirmations. Keep packets compact so extending
   scope does not exhaust the research budget.

2. <a id="fw-critic-coverage"></a> **Critic coverage check (second,
   independently evaluated increment).** Give the existing critic one
   additional responsibility: before committing to a root cause, challenge
   whether a *sufficient relevant portion* of the line was examined.
   Object when the conclusion names a root machine without the context
   record, or when an abnormal upstream/downstream machine was neither
   investigated nor ruled out using cited observations. Also object when
   the investigator blames a neighbor without a supported temporal/physical
   link, or collapses unrelated faults into a single cause. More scanning
   is not automatically better: request the **smallest discriminating,
   read-only follow-up** and retain time, token, tool and recheck limits.

   Introduce an **opt-in setting** comparable to `CRITIC_BLIND`, so the
   coverage check can be measured separately from the line-wide packet.
   It must also work in blind-critic mode. Run the baseline
   [critic follow-up effectiveness comparison](#fw-critic-comparison)
   before attributing changes to this new critic responsibility; otherwise
   review-only versus recheck effects become confounded. The critic's
   opinion remains a challenge, never authoritative sensor evidence or
   permission to intervene.

3. <a id="fw-scope-comparison"></a> **Alarm-centered vs line-wide
   comparison (acceptance gate).** Freeze the simulator code, fault
   injections, seeds, context cutoff, available observation tools,
   model/prompt settings, retrieval options and budgets. Compare on
   *identical observable cases*:
   **A** current alarm-centered workflow,
   **B** incident-first line-wide packet without coverage critic, and
   **C** incident-first packet *with* opt-in coverage critic.
   Record any unavoidable prompt differences as the treatment; do not
   claim identical prompt text when context is intentionally expanded.
   Keep all injected root-cause truth evaluator-only.

   | Scenario | What it tests |
   |---|---|
   | Wrong-machine alarm | CNC-02 alarms while CNC-01 is the real source; find the causal machine rather than repeat the alert location. |
   | Silent degradation | A progressive fault has no alarm; use the existing explicit routine-check/scheduled-scan trigger to test investigation of trends, **not** pre-alarm detection. |
   | Cascading failure | One machine's fault delays downstream work or causes multiple symptoms; explain causal propagation without counting duplicate symptoms as independent proof. |
   | Independent failures | Two unrelated machine faults coexist; find the second cause and avoid false upstream blame or a fabricated common origin. |
   | Normal / false-alarm control | No persistent fault; detect whether wider scope invents causes, adds irrelevant checks or recommends unnecessary intervention. |

   Score each arm for true root-machine identification, causal links,
   affected-machine coverage, false healthy-neighbor attribution, missed
   concurrent causes, abstention/insufficient evidence, wrong or unnecessary
   intervention, critic follow-up utility, tool/model calls, tokens and
   p50/p95 wall time. Record incident-packet provenance, actual observed
   windows, missing/stale data and the machines investigated. Preserve
   existing diagnosis, action and post-intervention verification metrics.
   Compare on repeated matched runs where model variability permits and
   distinguish provider failures from reasoning misses. The broader packet
   succeeds only if causal attribution improves without unacceptable
   false positives, added cost or over-investigation.

   **Simulation realism gate:** Existing line blocking can illustrate some
   downstream effects, but do not claim a strong cross-machine propagation
   scenario until the simulator genuinely reproduces it; add a distinct
   known-answer scenario first if necessary
   ([regression-case expansion](#fw-regression-cases)).
   Automatic detection of alarm-free degradation is a different claim,
   measured only after the later [deterministic continuous monitor](#fw-telemetry-replay)
   exists. Neither a scheduled trigger nor reading trend data alone
   demonstrates autonomous early detection.

**Implementation order:** pin alarm-centered baseline → incident packet in
`observe` → matched A/B seeded evaluation → opt-in critic coverage check →
matched B/C evaluation. If B still misses faults on machines that never
alarmed, evaluate the [Line Sentinel](#fw-line-sentinel) as arms D and E.
Only then consider the
[telemetry ingestion and replay](#fw-telemetry-replay) or
[proactive dispatch lifecycle](#fw-proactive). Each implementation
increment gets its own PR and tests. This documentation creates no new
understanding/implementation completion claim.

### Ranked component check list for the technician (MEDIUM; SM-11; proposed 2026-11-07)

<a id="fw-sm-check-ranking"></a>

**Category: Evaluation, benchmarking and reasoning. Rank: SM-11 in the [single-machine track](#fw-sm-track). Status: FUTURE WORK ONLY; deliberately after the reading work (developer's decision, 2026-11-07).** The project's end goal is to tell a technician which part to check first, then second. Controller telemetry usually narrows a problem to a subsystem (spindle, one axis, coolant, hydraulics) but often cannot separate parts inside it, such as a bearing from a ball screw on the same axis. So the output is a ranked check list, not a certain diagnosis.

1. **Symptom map, built with technicians.** For each likely failed part, the signal pattern it would cause. Example: a worn ball screw raises that axis's servo load at the same commanded feed, and is a common cause of excess servo load that gets misread as an electrical fault.
2. **Score each part** by how well the observed pattern from [SM-9](#fw-sm-cross-signal) fits, weighted by how often that part actually fails on this machine (from the [maintenance history](#fw-sm-visit-log)).
3. **Order by probability divided by cost to check.** Decision-theoretic troubleshooting shows that, under its assumptions, checking components in decreasing probability-to-cost ratio gives the lowest expected cost ([Breese and Heckerman, 1996](https://arxiv.org/pdf/1302.3563); [Heckerman, Breese and Rommelse, CACM 1995](https://www.microsoft.com/en-us/research/publication/decision-theoretic-troubleshooting/)). A likely part that takes five minutes to inspect goes ahead of a slightly more likely part that needs a teardown.
4. **Update after each finding.** When the technician reports a part is fine, rescore the rest and recommend the next check.

Python computes the scores; the Investigator explains the evidence and walks the technician through the checks. Human approval and verification are unchanged. *Accept:* on technician-confirmed cases only, report the rank of the true part and the number of checks to find it; never report accuracy on unlabeled real data.

### Future Work 7 — model evaluation, execution budgets, and computed evidence

[FW7 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
record a minimal versioned execution manifest with the first repeatable scripted
or live evaluation. Add only fields for components that exist. Persist explicit
decision artifacts and evidence lineage, with evaluator-only setup/truth kept
out of model prompts and agent memory. Durable investigation status should derive
from the authoritative Pydantic Graph flow rather than duplicate orchestration.
Reevaluate recorded replay only after the complete loop/evaluator demonstrates
a gap beyond seeded reruns. Tape misses must be explicit, and static replay
cannot score counterfactual intervention effects.

**Added 2026-10-09.** These additions are planned (sensor summaries, the known-answer scenarios and the single-model provider benchmark are built). They preserve the existing reasoning loop, working state, durable-memory plans, provider abstraction, typed multi-agent handoffs, termination rules, human approval, post-intervention verification, and simulator architecture. Do not add a failure-diagnostic benchmark mode.

#### Timing

| Addition | Later extension |
|---|---|
| Role-specific model benchmarking | Add a lightweight harness with Future Work 3, before treating specialist role assignments as final. |
| Reasoning and token budgets | Give every planner, researcher, analyst, critic, and synthesizer its own configuration when those roles exist. |
| Deterministic sensor computations | Add window comparisons or moving averages only when investigations require them; expose through MCP with Future Work 2. |

These are staged additions to the existing build order, not a separate framework
to implement before the remaining simulator actions and scenarios.

#### Pydantic AI runtime reliability review — candidate (2026-10-28)

<a id="fw-runtime-audit"></a>

**Priority: HIGH / audit only.**

**Status:** HIGH-priority audit / small benchmark; roadmap only, not a
framework migration. **Newest update reviewed: Pydantic AI v2.63.0
(2026-10-27; published 2026-10-28 UTC).** Its release adds `DetectLoops`
for repeated-action loops and `Dataset.evaluate(task_timeout=...)` to
bound each evaluation task attempt. Also review the recent v2.58.0
(2026-10-19) whole-run `timeout=` / `RunContext.deadline`, per-request
`request_timeout`, and SDK-level `max_retries`, and the v2.60.0
(2026-10-22) model-selection context deadline/usage-limit changes.
Official release references:
[v2.63.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.63.0),
[v2.60.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.60.0),
[v2.58.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.58.0).
Version/date are a review snapshot, not an automatic update policy. The project already uses **Pydantic Graph** for the
macro investigation and has custom provider reliability controls in
`capstone/providers/chat.py`, including `FallbackClient` and
`run_with_deadline`. Review currently documented Pydantic AI runtime
features for per-call and run deadlines, retries, fallback observability,
loop detection, and evaluation timeouts; verify installed/package
compatibility and actual API availability before relying on any of them.

**Integration gate:** compare those facilities against existing code with
the current `ChatClient`, Pydantic answer contracts, graph states, and
`Budgets`. Do not introduce a second orchestration loop, replace Pydantic
Graph, or create nested retries that overrun one 60-second investigation
budget. A timeout must terminate or explicitly account for work; tool calls
must not resume or replay consequential actions. Preserve hidden-truth
isolation, human-only maintenance approval, and mandatory post-action
verification.

**Benchmark before adoption:** run the same seeded cases through current
code and the smallest feasible native-feature prototype. Inject 429/5xx,
latency, malformed JSON, repeated identical tool calls, failed fallback,
and deadline exhaustion with offline stubs. Compare root-cause accuracy,
completed investigations, p50/p95 wall time, tool/model call count, logged
failure reasons, code removed, and reproducibility. Keep current controls
where Pydantic AI does not materially improve reliability or would require
disproportionate migration. No new SDK, version bump, provider, or runtime
change is approved by this review.

#### Graph of Thoughts (GoT) hypothesis reasoning — medium-priority evaluation (2026-10-29)

<a id="fw-got"></a>

**Priority: MEDIUM; only after matched current baselines.**

**Status:** ROADMAP ONLY; not implemented. Evaluate after a measured baseline of
the current investigator, optional depth-one Tree of Thoughts (ToT), and critic.
This is a targeted reasoning experiment, not a replacement for Pydantic Graph
or a commitment to add a second orchestration framework.

<a id="fw-tot-ablation"></a>

**Module 4.1 follow-up, gated behind the current evaluations:** The
[ToT/critic evaluation future-work plan](TOT_CRITIC_EVALUATION_FUTURE_WORK.md)
records the four next experiments: evidence-grounded pruning and deferred
alternatives; pre-pruning critic checks; adaptive branching and limits; and
evaluating model confidence/position bias against evidence strength. It also
specifies A/B/C/D matched-run ablations and measurable go/no-go criteria.
The developer reported **run 1 of 2 currently in progress** (2026-10-29);
that status is not independently verified. Finish and preserve the existing
two-run series unchanged before starting these new experiments.

**Existing code:** `agent/investigation.py` uses Pydantic Graph for stage
routing; `agent/loop.py` enforces tool, evidence and time budgets;
`agent/tree_of_thought.py` optionally generates up to five hypotheses,
rates them and prunes to at most three via `--tree-of-thought`.
`agent/critic.py` can review up to five surviving hypotheses.
`investigation.py` records the critique and supports an optional, bounded
`recheck` of one critic-proposed read-only observation. The critic cannot
directly change the conclusion or approve an action. This is *not* Graph
of Thoughts.

**Prerequisite: measure the existing opt-in critic feedback loop.** This
remains a **HIGH-priority pilot-readiness evaluation**, independent of whether
GoT is adopted; see
[pilot-readiness work](#high-priority-future-work--pilot-readiness-fast-triage-and-the-rest-of-abstention-updated-2026-10-30).
The optional `recheck` now allows at most one critic-directed, read-only
discriminating observation followed by agent interpretation. Compare it with
review-only critique using matched runs, and verify that an objection leads
to better evidence and diagnosis rather than just extra calls. The critic must
not approve actions, manufacture observations, override independent evidence
requirements, or repeat indefinitely. Measure this effect separately before
attributing improvements to GoT.

<a id="fw-multicause"></a>

**Prerequisite: evidence-scored, multi-cause diagnosis (2026-10-29).**
**Part built 2026-10-30 (PR #136, offline only):** only factory evidence
(`origin == "observable"`) can rule a candidate out, so a manual section or a
memory cannot; each pruned branch carries a status, `contradicted` or
`deferred` (untested, not false), kept in the run's trace, the audit log and the
critic's view; and a kept, unproven "impossible" rating is scored low
(`unproven_confidence`) instead of ranking high. Still to do is the rest of this
paragraph and the score below.
Before testing GoT, investigate whether an evidence-scored *multi-label*
hypothesis policy better fits real machines with concurrent faults. The
current ToT `prune()` still ranks by model confidence, keeps at most three
candidates, and can discard additional plausible causes solely because of
their rank (they are now recorded as `deferred`, but not retained).
Instead, retain independently supported, materially distinct causes even
when several may all be true (for example bearing wear and excessive
cutting load). Use a bounded active set and prioritize which hypotheses
receive tool calls, rather than treating the top-k selection as a truth
test. Reject a candidate for grounded contradictory evidence, invalid
citations, or duplication; when a budget forces deferral, record it as
*untested/deferred*, not false.

Compute an **explainable evidence-strength score per hypothesis**, with
separate contributing factors: observed support, observed contradictions,
coverage of relevant symptoms, sensor/data reliability, and remaining
unanswered discriminating checks. Use independent observations and evidence
provenance, not just self-reported model confidence. Do not count correlated
alarm/raw/summary views of the same observation as separate corroboration.
Keep the score distinct from a probability of truth until it is calibrated
against held-out labelled cases; simultaneous faults need not have scores
that sum to 100. Permit rescoring as real evidence arrives and retain an
explicit status (`candidate`, `supported`, `contradicted`,
`deferred`, `unresolved`), plus an auditable score breakdown.

<a id="fw-position-bias"></a>

**Positional-bias and optional log-probability scoring evaluation (2026-10-29).**
**Status: medium-priority, evaluation only; do not enable until demonstrated
beneficial.** Current opt-in ToT sends the candidates in fixed generated order,
asks for a single batch of model-reported confidences, sorts descending, and
uses original candidate order as the tie-breaker
(`agent/tree_of_thought.py:prune`). The chat provider
(`providers/chat.py:ChatClient.ask`) sets temperature 0 but neither requests
nor parses token log probabilities. Neither model-reported confidence nor
raw token likelihood removes position/order effects or proves correctness.

Evaluate **position invariance** before changing the scoring mechanism:
(1) independently score each distinct hypothesis with the same sensor
observations and evidence rubric, without presenting rival hypotheses as
competing choices; (2) on a fixed set of matched cases, repeat the listwise
judge after systematically rotating/permuting candidate order, retaining
stable candidate IDs and normalizing output back to those IDs; and
(3) compare per-candidate variance, rank reversals and correlation with
presentation position against the single-order ToT baseline. Prefer a
small bounded set of permutations, measure additional model calls and
latency, and keep all runs within documented experiment budgets.
Randomization is a diagnostic and possible mitigation, not proof that
position bias is gone. Do not replace deterministic evidence validity
checks with model votes.

**Log-probability feasibility spike (optional):** check actual support from
the configured NVIDIA/Nemotron and fallback model endpoints for
`logprobs`/`top_logprobs` in the relevant response mode, including
schema-constrained JSON output. Only if supported, test the likelihood of
a tightly specified, length/label-controlled verdict per hypothesis and
compare it with evidence-based scores and order-aggregated model ratings.
Be alert to tokenization and label-order bias; avoid comparing raw
sequence likelihoods of differently worded hypotheses or assuming
logprobs are calibrated truth probabilities. The clients currently
return only validated typed answers, so collecting optional logprobs
would need an explicitly measured, backward-compatible provider
response/metadata path; fallback must remain functional where scores
are unavailable.

**Go/no-go:** use held-out seeded single- and multiple-fault cases with
missing/noisy/conflicting evidence. Compare order sensitivity,
multi-label precision/recall/F1, calibration (only when a probability
claim is made), independent-evidence citation quality, false
interventions, root-cause/action correctness, additional tokens/calls,
p50/p95 latency and availability across providers. Do not force softmax
competition across hypotheses that can be simultaneously correct.
Adopt the simplest scoring method that is materially more robust, and
record untested/deferred hypotheses rather than silently pruning them.
This evaluation precedes any production GoT scoring integration.

**Required code/design review:** `agent/tree_of_thought.py` (score and
evidence-based rejection versus hard top-three pruning);
`contracts/hypotheses.py` (score components and per-hypothesis status);
`agent/state.py` and `agent/loop.py` (`leading_hypothesis`,
`diagnosis_supported`, and stopping conditions must not terminate while
material concurrent faults remain untested); `agent/artifacts.py` and
`agent/investigation.py` (current `AgentConclusion.hypothesis_id`
is singular; consider a typed multi-cause conclusion with linked evidence
and per-cause action/verification outcomes); and `agent/critic.py`
(current review considers only two leading explanations). Preserve
existing Pydantic Graph orchestration, human approval, read-only research
tools, and observable verification of any approved intervention.

**Acceptance test:** compare current top-k ToT and independent scoring on
matched single-fault and compound-fault seeds, including noise, missing
data, false alarms, and correlated telemetry. Evaluate multi-label
precision/recall/F1, missed concurrent causes, false positive causes,
quality/uniqueness of cited evidence, unnecessary interventions,
post-action verification, p50/p95 runtime, and model/tool calls under
the same budgets. Do not promote scores to calibrated probabilities,
adopt the multi-cause output contract, or feed scores into the GoT prototype
without demonstrated improvements and regression coverage. This is
documentation-only future work, not authorization to change runtime code.

<a id="fw-got-prototype"></a>

**Minimal GoT prototype:** extend the *hypothesis reasoning policy*, not the
macro workflow. Represent each competing diagnosis and its dependencies with
typed nodes and explicit edges (`supports`, `contradicts`, `depends_on`,
`refines` or `combines`) referencing observed evidence IDs. Allow a bounded
merge of compatible branches (for example, concurrent bearing wear and
excess cutting load), revision after a real tool result, and pruning based
on grounded contradictions. A graph relation is an analyst hypothesis,
not new sensor evidence. Keep candidate/merge counts, depth, model calls,
tool calls, and elapsed time under the current shared budgets. Persist
the proposed nodes/edges and selection outcomes as auditable artifacts,
not hidden model chain-of-thought.

**Evaluation and adoption gate:** use `capstone.experiment` with matched
seeded single-fault and compound-fault cases to compare (1) standard policy,
(2) opt-in ToT, and (3) a bounded GoT prototype. Hold model, manual/episodic
retrieval, critic mode, tools, cases, and configured budgets constant in each
comparison; evaluate critic feedback separately to avoid confounding.
Measure root-cause accuracy, multiple-cause recall, evidence validity,
contradiction handling, action correctness, false interventions, verified
resolution, schema failures, model/tool calls, p50/p95 wall time, and
provider cost where measurable. Include noisy, missing, stale and conflicting
telemetry plus later Haas VF/NGC-compatible observations when available,
without exposing simulator ground truth to the policy. Adopt GoT only if
repeatable gains justify its added latency and maintenance complexity under
the target pilot SLA; otherwise keep standard/ToT and the improved critic.
No dependency changes or production enablement are authorized by this entry.

Reference: [Graph of Thoughts: Solving Elaborate Problems with Large Language
Models](https://arxiv.org/abs/2308.09687) (Besta et al., 2023).

#### Evaluation-only model-response cache — medium priority (2026-10-29)

<a id="fw-eval-cache"></a>

**Priority: MEDIUM.**

**Status: PLANNED; not implemented.** Introduce a lightweight, opt-in
**SQLite-backed evaluation cache** for repeated LLM judgment calls while
developing hypothesis scoring, positional-bias tests, Tree of Thoughts (ToT),
and a later Graph of Thoughts (GoT) prototype. The aim is to avoid paying for
identical diagnostic calls during debugging and rescoring, **not** to make live
agent runs appear faster, more consistent, or more accurate than they are.

**Reuse what exists first:** `capstone.evals --records` already reads saved
`ExperimentRecord` JSONL for offline rescoring without rerunning the agent;
`--resume` continues an interrupted scenario evaluation from completed
episodes. Keep these workflows. Add per-model-response caching only when they
cannot support the experiment (for example replaying an identical hypothesis
rating request while varying a downstream scoring formula). Do not conflate
episode-result reuse with replay of individual model calls.

**Key and stored record:** for a cacheable evaluation request, hash a canonical
representation of the complete system/user prompt, exact evidence/context,
candidate identities **and order**, model/provider ID and version when known,
generation parameters, response schema, prompt/template revision, and
relevant tool/manual/retrieval snapshot identifiers. Save the exact validated
typed response plus timestamp, source call metadata, cache key version and
cache-hit flag. Do not store API keys, secrets or evaluator-only ground truth
in model-accessible cache entries. Missing inputs or mismatched versions
must cause a miss, not a potentially incorrect reuse.

**Safety and experiment integrity:** evaluation-only and explicitly opt-in;
default to fresh calls in real investigations, live accuracy comparisons,
latency/provider-reliability benchmarks, and tests of response variability.
Position-permuted hypothesis lists get different cache keys and must first
be sampled with fresh model calls; reuse their distinct captured responses
only for subsequent *offline* scoring analysis. Never serve stale live sensor
readings, intervention approvals, tool execution results, or hidden simulator
causes from a model-response cache. Preserve existing provenance, human-only
action approval, verification, and reality/observation/belief separation.
Handle invalid replies, cache corruption, and schema drift as misses/errors
rather than silently accepting answers. Track cache hits separately from
fresh-call counts, costs and latency in reports.

**Implementation and measurement gate:** prototype at the model client /
evaluation harness boundary, with injectable clock/storage and scripted
offline tests; avoid adding Redis, new services, or a second orchestration
layer. Compare uncached versus warm-cache debugging workloads for API calls,
wall time, storage use, and reproducibility, while ensuring fresh-run
quality metrics are unchanged. Retain only if savings justify cache
invalidation and maintenance complexity. Do not implement or enable
runtime caching merely by adding this roadmap entry.

#### Deterministic sensor computation tools

<a id="fw-sensor-calculations"></a>

**Priority: LOW / conditional.**

`get_sensor_summary()` is built (machine and factory sensors). Add
`compare_sensor_windows()` or moving averages only for a demonstrated
investigation need. All calculations stay read-only, use the existing typed tool
boundary, and reveal neither programmed root causes nor internal health or
degradation values. MCP is a later transport for the same observations.

#### Pydantic Evals — candidate, not implemented

<a id="fw-pydantic-evals"></a>

**Priority: LOW / conditional.**

Reevaluate when scenario generation, evaluation, and the normal agent workflow
exist, and a small experiment harness would remove custom reporting plumbing.
Pydantic Evals provides `Dataset`, `Case`, and custom evaluators; the candidate
integration reuses seeded cases, project investigation contracts, and MVP
scoring rather than creating another diagnostic workflow. See
[Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/).

```text
Dataset → Case per scenario/seed → normal research-agent workflow
  → deterministic evaluators → experiment/report
```

Keep public observations/setup references in task inputs. Keep expected root
cause and acceptable interventions evaluator-side, with scenario ID, seed,
and family/difficulty metadata. Do not forward the full case or expected output
to the model, or store evaluator truth in memory/RAG. Custom code evaluators
can score root cause, intervention, resolution, deterministically scoreable
evidence retrieval, tool/iteration counts, schema success, and hidden-truth
leakage with zero tolerance. Qualitative LLM judges are only a later option
where authoritative truth cannot provide a deterministic score.

Before adopting, test case/input separation, leak detection, fixed-seed setup,
score parity with existing evaluation, schema failures, and report counts using
scripted models offline. Live outputs remain probabilistic even for repeatable
simulator inputs. Reuse this harness for Future Work 7's later role benchmarks
only if useful; it must not require six providers or replace pytest, simulator
unit/integration tests, post-intervention verification, or MVP scoring.
Do not add the rejected failure-diagnostic benchmark mode. No Evals dependency,
dataset, evaluator, or runtime integration is implemented now.


## Future work: Retrieval and memory

<a id="future-work-retrieval-and-memory"></a>

### Future Work 1 — richer research and document ingestion

Technical manuals, maintenance
documentation, historical incidents, RAG, external knowledge sources. The
agent researches both the factory and a knowledge base.

[FW1 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
classify each ingestion source as an atomic snapshot or independent records
before allowing partial acceptance. Preserve accepted/rejected scope and
immutable document/revision lineage. Reevaluate fact-specific source authority
when comparable claims conflict, including conflicting revisions of one source.
Do not silently resolve a missing or conflicting claim through model opinion.

#### Maximal Marginal Relevance (MMR) for episodic recall — candidate (2026-10-23)

<a id="fw-mmr"></a>

**Priority: MEDIUM.**

**Status:** medium-priority future work, not implemented. Reevaluate after the
baseline episodic-memory retrieval is measured and actual investigations show
that several near-duplicate incident results crowd out other relevant causes.
This is retrieval-time diversification, **not** the near-duplicate write-time
memory check below; it does not require another reasoning LLM.

MMR first retrieves a larger candidate pool, then selects a smaller set that
balances similarity to the query against redundancy with already selected
items. The goal is to let the agent consider multiple plausible manufacturing
causes (for example bearing degradation, misalignment, and tool imbalance)
without losing the strongest supporting incidents. It does not guarantee
coverage of every cause or make an unsupported diagnosis true.

**Strict scope: `recall_memories` (episodic memory) only.** Evaluate MMR
exclusively when the agent recalls stored investigation lessons/incidents.
**Do not apply MMR to the machine-manual RAG index, manual search tool, SOPs,
or procedural-document retrieval.** Those remain relevance-first and are not
part of this MMR proposal. Respect memory outcome, category, provenance,
source IDs, and applicable recall filters. Do not introduce LangChain or a
new database just for MMR; use the retrieval stack actually selected when
this work is implemented.

**Evaluation gate:** compare standard similarity retrieval with MMR on the
same stored incidents and seeded investigation scenarios. Sweep the candidate
pool size, returned result count, and relevance/diversity weight rather than
assuming a universal default. Measure relevant-incident recall, duplicate
results, coverage of genuinely distinct plausible causes, root-cause accuracy,
time/token cost, and whether required evidence is missing. Include cases where
several similar reports are all important and where alternate faults coexist.
Keep the original retriever as the default unless MMR improves investigation
quality without exceeding the existing investigation budget. Any implementation
gets its own PR and deterministic offline tests.

#### Voyage AI Rerank for manual retrieval — candidate (2026-10-28)

<a id="fw-voyage"></a>

**Priority: MEDIUM.**

**Status:** MEDIUM-priority experiment; roadmap only, not implemented. Test
Voyage's current reranking API (for example, `rerank-3-lite`, subject to
provider/version verification) only when manual-retrieval evaluations reveal
wrong or poorly ordered troubleshooting sections. This is a relevance
reranker, not an embedding-index replacement, new reasoning role, or proof
that a passage is correct.

**First scope: manual/SOP retrieval, not MMR.** Preserve the existing
`search_manual` tool, `KeywordManualSearch` / `ChromaManualIndex`,
document/chunk IDs, versions, provenance, and manual-to-evidence boundary.
Retrieve a bounded candidate pool and optionally rerank it before returning
the same source-linked sections to the agent. Never send evaluator-only truth,
simulator hidden state, or unapproved real maintenance records to the API.
Fall back to the original retrieval ordering on outage, timeout, or invalid
response, within the overall investigation deadline.

**Keep experiments separate:** the existing MMR candidate above is strictly
for `recall_memories` (episodic diversity), **never for the manual**. Only
after the manual reranker is measured, consider a separate episodic-memory
reranking experiment against standard similarity, MMR, Jev, and their relevant
combinations; do not conflate retrieval diversification with scoring
relevance. Compare Voyage with the existing optional Cohere Rerank candidate
in Future Work 3 before adopting more than one external service.

**Evaluation/adoption gate:** use identical seeded investigations, frozen
manual/query sets, and labeled relevant passages to compare baseline manual
retrieval versus reranking. Measure relevant evidence recall/precision at k,
retained contradictory evidence, grounded root-cause accuracy, incorrect
repairs, cost, failure/fallback rates, and p50/p95 end-to-end wall time under
the 60-second investigation budget. Stub the reranker for offline tests and
opt into external API tests. Record provider/model version and privacy terms;
adopt only if the measured benefit exceeds extra latency, expense, and
operational complexity. No new key, dependency, paid API call, or implementation
is authorized by recording this item.

#### Jev (TypeSafe AI) for episodic recall reranking and investigation routing — candidate (2026-10-23)

<a id="fw-jev-recall"></a>

**Priority: MEDIUM.**

**Status:** medium-priority future work, not implemented. Consider a small
proof of concept only after the baseline memory-recall and agent-tool-routing
paths work and measured errors or wasted calls justify another model request.
Jev is a probabilistic decision model for typed choice, score, and boolean
judgments, **not** a replacement for the Nemotron investigation/reasoning
agent, deterministic numerical tools, or human approval.

**First use case — episodic recall:** use Jev to score/rerank already retrieved
investigation lessons for relevance to current observed symptoms and the
agent's question, preserving memory IDs, outcome (resolved or unresolved),
source provenance and contradictory evidence. Limit this evaluation to
`recall_memories` and the episodic-memory Chroma/PostgreSQL retrieval path.
**Do not route machine-manual RAG, `search_manual`, SOPs, or procedural
documentation through Jev.** Keep a baseline retrieval fallback and avoid
irreversibly discarding potentially useful or contradictory memories on a
single model score.

**Second use case — investigation routing:** optionally evaluate bounded
choices such as the next read-only diagnostic tool or subsystem to inspect
from the agent's *observable* evidence. The main agent still owns hypotheses,
testing, intervention recommendations and verification; evaluator-only
ground truth must never be supplied to Jev. Any control over state-changing
tools remains behind existing approval and safety policies.

**Evaluation gate:** compare the same seeded incidents and investigation
budgets using (1) baseline similarity recall, (2) MMR, (3) Jev reranking,
and (4) MMR plus Jev; test routing separately against the existing agent.
Measure relevant-incident recall, contradictory evidence retained, incorrect
filtering, root-cause accuracy, tool calls, wall-clock latency, API/token
cost, timeouts and total completion within the 60-second investigation
budget. Use deterministic offline stubs for tests and opt-in live API
experiments. On API failure, uncertainty or exceeded time budget, fall
back to current retrieval/routing rather than blocking an investigation.
Review the current TypeSafe API, privacy and pricing before adoption; no
dependency or live service is authorized by this roadmap entry.

References:
[TypeSafe Jev introduction](https://typesafe.ai/blog/introducing-system-one-models-and-jev);
[Vercel's Jev typed-evaluation API](https://vercel.com/changelog/ai-gateway-now-supports-typesafe-clients-and-http-api-for-jev).

#### Agent-directed RAG and repeat retrieval (2026-10-18)

<a id="fw-rag"></a>

**Priority: LOW for remaining improvements.**

Built (`PROGRESS.md`: R3, A7b, A9a, C3b, M1): the investigation agent itself
chooses memory and manual searches (`recall_memories`, `search_manual`), by
meaning, with at most three retrieval calls per knowledge gap, the first
included; a repeated search is refused; each search is recorded. Per the
decision of 2026-10-18 there is no second reasoning model and no dedicated RAG
agent.

What is left:

- **Record the agent's usefulness assessment after each search** and the reason
  for searching again: whether the results addressed the question, supported or
  contradicted the hypothesis, and what gap remains. Today the query, the
  outcome and the returned ids are recorded, not the assessment.
- **Reopen a search from a draft answer.** If a draft conclusion shows
  unsupported claims, the agent can search again. A high similarity score or the
  agent's confidence alone does not establish that an answer is supported.
  Empty, irrelevant, incomplete or contradictory results may trigger another
  search with revised wording, different symptoms or an alternative hypothesis,
  and search should seek evidence that could refute the current hypothesis as
  well as support it. Repeating an identical query against an unchanged store is
  not progress.
- **Memory through the planned MCP server** (Future Work 2).

Acceptance checks for the remainder: an empty or irrelevant first result can
lead to a revised second search whose evidence reaches the answer; contradictory
evidence can cause hypothesis revision; insufficient evidence at the call limit
produces an explicit uncertain result without another retrieval; no second
reasoning model or hidden truth is used. Use a scripted model and local store
for deterministic offline tests.

#### Near-duplicate memory check (planned 2026-10-22)

<a id="fw-near-duplicate"></a>

**Priority: LOW / conditional.**

Status: planned, not implemented. The concept was taught and the developer
showed understanding on 2026-10-22 (see `PROGRESS.md`). Building it goes
through its own PR and the pre-merge walkthrough.

**The problem.** A lesson is refused as a duplicate today only if its
normalized wording matches a stored one exactly (`lesson_fingerprint`, and
the SQL store's unique `fingerprint`). Success lessons are written by the
model, so paraphrases of one lesson are all stored, and recall's few slots
fill with the same advice.

**The plan.** After `MemoryPromotionPolicy` accepts a memory and before the
SQL insert, `MemoryService.promote` asks the Chroma index for the most
similar stored memory. If it is at or above a fixed similarity threshold,
the new memory is refused and the original kept. The policy stays free of
I/O; the SQL store's exact check stays as the last guard.

- **Compared only within the same category, outcome and machine.** Without
  the outcome filter, "the fix was tried and failed" scores close to "the
  fix worked" and would be thrown out, leaving a one-sided record that
  makes the agent repeat a failed action instead of looking for more
  evidence. Without the machine filter, the fixed failure sentence for two
  machines differs by one word and the second would be thrown out, losing
  "this fix failed on two machines". A memory with no machine (no action
  proposed) is compared only with others that have none.
- **Embedded as a passage on both sides.** Stored memories are embedded as
  passages (`memory_document`: category, symptoms, diagnosis, lesson); the
  new one must be too, not as a query, or the scores are not comparable.
- **Refusal:** `accepted=False`, `stored=False`, a new reason
  `similar_lesson` (kept apart from the exact `duplicate_lesson`), and
  `existing_memory_id` set to the match. Nothing is written. The audit log
  already holds the investigation, since `learn_from` writes it first.
- **Fallback:** if Chroma cannot open, was built by another embedding
  model, or the lookup fails, skip this check and store as today. A broken
  index must never refuse lessons.
- **Repeatable:** the same lessons and model give the same decision. Each
  refusal records the embedding model and threshold that made it.
- **Index change:** category and machine are not in the Chroma metadata
  yet (it holds `memory_id`, `outcome`, `timestamp`), so they are added and
  the index rebuilt once (`python -m capstone.memory.backfill --rebuild`).

**Trade-off of the machine filter.** It keeps "worked (or failed) on
several machines" as separate memories, which tells the agent whether a
lesson generalizes. The cost is weaker de-duplication: one lesson can be
stored once per machine per outcome, so recall can still fill with the same
advice for different machines. If that happens, group results at recall
time (for example "worked on CNC-02, CNC-04") without changing the store.

**Not part of this plan: a machine filter on the agent's recall tool.**
`recall_memories(text, limit)` has no machine argument today (recalled
memories show their machine). Adding one changes an agent-facing tool and
needs its own gate. Its risk: the agent filters to the alarmed machine and
misses the same pattern fixed on a sibling machine, or a material-batch
fault that spans machines.

**Measuring the threshold.** Measure it on real data before building;
never guess it.

1. Collect real lessons from the memory store and experiment runs. Repeat
   runs of one scenario give natural paraphrases.
2. Make labelled pairs, about 50 to 100, each sharing category, outcome and
   machine as the real check would. The developer labels each pair "same
   lesson" or "different", not a model. Include hard cases: same symptom
   with a different action, same action with different symptoms.
3. Embed both lessons of each pair as passages with the configured model
   (Nemotron by default; a live embedding call needing `NVIDIA_API_KEY`) and
   compute cosine similarity.
4. Compare the score ranges of "same" and "different" pairs.
5. Choose by cost. Refusing a different lesson loses it silently, which is
   worse than letting a duplicate crowd recall. So set the threshold just
   above the highest-scoring "different" pair, then report what share of
   true duplicates it still catches.
6. Hold out about a fifth of the pairs and confirm the threshold on them.
7. Record the model and threshold. Measure again whenever the embedding
   model changes, since scores from different models are not comparable.

The labelled pairs live in a file in the repository so the measurement can
be rerun. Unit tests use fixed fake vectors and need no key.

**Provisional result (2026-10-22): 0.909**, on 60 drafted pairs with
Claude's draft labels, because the store held no real lessons. It caught 19 of
23 repeats and refused none of 28 different lessons, with almost no margin.
Comparing the whole memory text beat the lesson sentence alone (19 vs 10
repeats caught). Re-measure on real lessons before building the check. See
[`benchmarks/2026-10-22-near-duplicate-threshold.md`](benchmarks/2026-10-22-near-duplicate-threshold.md).
Tool: `python -m capstone.memory.duplicate_threshold`.

#### Docling + HybridChunker — candidate, not implemented

<a id="fw-docling"></a>

**Priority: LOW / conditional.**

Reevaluate when actual manuals, SOPs, maintenance reports, and PDFs enter the
RAG phase. Docling conversion followed by `HybridChunker` could replace custom
PDF parsing and naive fixed-character splitting. The chunker refines document
hierarchy using token limits. See [Docling chunking](https://docling-project.github.io/docling/concepts/chunking/).

```text
PDF/manual → Docling structured document → HybridChunker
  → embeddings → planned ChromaDB → retrieval/reranking → research agent
```

Reuse project `Evidence` and document source identifiers, preserving document
ID, source/path, available page/position provenance, headings, sections, and
table context. Select the embedding model before choosing a tokenizer. Use a
matching supported Hugging Face tokenizer, or the OpenAI/tiktoken integration
where appropriate; do not assume every embedding API has a local tokenizer.
Use one coherent token/chunk-size policy. See the
[hybrid chunking example](https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/).

Before adoption, test representative real documents for conversion quality,
tables, provenance round trips, token limits including contextual text, and
retrieval relevance. Adopt only if this removes custom parsing/chunking work.
Keep ingestion in a future optional `rag` or `ingestion` extra; it must not
replace ChromaDB, project contracts, or simulator behavior, and needs no
LangChain/LlamaIndex wrapper merely to be used. No ingestion runtime or
dependency is added now.


<a id="future-work-more-roles-multi-agent"></a>

## Future work: Multi-agent roles and coordination

<a id="future-work-multi-agent-roles"></a>

### Future Work 3 — multi-agent research

[FW3 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
specialist role scopes extend server-side authorization already required at
the first MCP boundary. Reuse the same permitted capabilities and contracts.
An execution service may execute only an exact human-approved request;
an agent cannot grant itself approval or arbitrary execution authority.

<a id="fw-line-sentinel"></a>

#### Third agent: the Line Sentinel (MEDIUM; proposed 2026-11-03)

**Status: FUTURE WORK ONLY — not implemented.** One third model-driven role that decides **where and when** an investigation starts and **whether the data there can be trusted**. It never names a cause. In the 57 archived master runs, the investigator was right 0 of 13 times when the faulty machine was not the one that alarmed (wrong setting KA-05/06, decoy KA-09), because `detect_anomaly` hands over the first alarm's machine.

Deterministic code scores every machine against its peers and its own recent past, in the same operating context, with thresholds calibrated on normal-operation seeds only. It labels each machine **abnormal**, **can't tell** (untrusted or missing data, no baseline) or **normal-looking**. The model may only request bounded read-only checks and set the order of machines, citing evidence; code computes every score and label. The Investigator starts from the top of the brief but may look at any machine; the Critic reads the same brief. The model never monitors: a deterministic alert or a scheduled routine check wakes it once per incident.

It comes after the [line-wide incident packet](#fw-line-context) and its evaluation, and is measured as two new arms in the [scope comparison](#fw-scope-comparison): **D** (code-only brief) and **E** (with the model). Build E only if D still misses non-alarming faults. The data-trust checks from an earlier draft's separate Evidence Integrity Agent are kept as code inside the Sentinel; a separate integrity role is reconsidered only if a live degraded-data run shows a gap the Sentinel does not cover.

See **[the Line Sentinel design: evidence, calibration, boundaries, proposed contracts and tests](THIRD_AGENT_LINE_SENTINEL_FUTURE_WORK.md)**. The larger multi-provider workflow below stays a long-term option.

The larger multi-provider workflow below follows the single-agent MVP. Its
provider assignments are initial targets; exact models and API availability
will be confirmed when this extension is implemented.

<a id="fw-specialist-roles"></a>

#### Planned Multi-Agent Workflow

The bounded post-MVP extension research workflow will be:

```text
                    RESEARCH QUESTION
                           │
                           ▼
                  NEMOTRON PLANNER
                     NVIDIA
                           │
                    FULL HANDOFF
                           ▼
                GPT-OSS RESEARCHER
                      GROQ
                           │
                    FULL HANDOFF
                           ▼
               COHERE EVIDENCE AGENT
                     COHERE
                           │
                  VERIFIED EVIDENCE
                           │
               ┌───────────┴───────────┐
               │                       │
      EVIDENCE-ONLY HANDOFF       RESEARCH STATE
               │                       │
               ▼                       │
           GEMINI ANALYST              │
          GOOGLE GEMINI                │
               │                       │
        independent analysis           │
               │                       │
               └───────────┬───────────┘
                           │
                   CHALLENGE HANDOFF
                           ▼
                   MISTRAL CRITIC
                       MISTRAL
                           │
               critique / contradictions
                           │
                    FULL HANDOFF
                           ▼
                NEMOTRON SYNTHESIZER
                       NVIDIA
                           │
                  enough evidence?
                    /          \
                  NO            YES
                  │              │
                  ▼              ▼
           more research    recommendation
                                  │
                                  ▼
                            action / HITL
                                  │
                                  ▼
                             VERIFICATION
```

Cloudflare will operate as a specialist provider and does not need to appear in every investigation.

When appropriate:

```text
Document / image / specialist task
                │
                ▼
        CLOUDFLARE WORKERS AI
                │
        specialist model
                │
                ▼
      structured observation
                │
                ▼
       normal research state
```

Cloudflare may also provide fallback inference if another provider is unavailable or reaches its rate limit.

---

#### Standing constraints for any further role

The critic is built on the project's own pieces, not on CrewAI or LiteLLM
(developer's decision, 2026-10-26; the reasons, checked on PyPI, are in
`PROGRESS.md`). Every further role follows the same pattern:

- **Orchestration:** new stages and edges in the stage graph
  (`agent/investigation.py`, `build_graph`); the edges stay the only allowed
  order.
- **Model:** a setting naming its model (like `CRITIC_MODEL`, a comma-separated
  chain), resolved by the same client factory, with `FallbackClient` for outages.
  Give a role its own fallback or request limits only when measurements show it
  needs them. Decide per role what happens when its model is unavailable: the
  critic's stage carries on without it and records that; the investigator stops.
- **Typed handoffs:** project `Contract` models; a reply that does not match is
  refused, with its reason recorded, as for the policy questions.
- **What a role may see:** a view built by code, like `render(state)`; an
  evidence-only handoff leaves the other agent's conclusion out.
- **Budgets:** each role's questions draw on the investigation's one time and
  call budget, enforced by the loop and the graph, not by the role. A role that
  needs extra time gets its own window and the deadline moves by what it used,
  as the critic's does.
- **Records:** each role's questions are tagged with the role in experiment
  records.
- **Watching the run live:** a role built as a graph stage is shown after it
  finishes. A role that asks several model questions inside one stage shows
  nothing until it ends, so give it `notify` checkpoints between questions.

Rules that do not change: a role's output is a belief, never observable
evidence, never proof that a fix worked, and never written to memory as fact;
no role sees ground truth; no role can approve or carry out an action
(approval stays human, execution stays the fixed procedure after approval);
verification after an intervention stays mandatory.

Build one role at a time, each through the teaching gate and its own PR, and
measure each against the single agent on held-out seeds with several runs per
case before adding the next. The six-provider workflow below is the long-term
target, not the first build. A second agent can lower accuracy (the paper
behind R4c found an LLM given a specialist's answer did worse than the
specialist alone), so a role stays only if the comparison shows it helps.

**Updated 2026-11-05:** the Guo et al. multi-agent survey review now tracks
one implemented and live-evaluated experiment (blind critic; **no proven
accuracy gain**), one unbuilt feedback proposal (operator rejection notes),
and one partly documented write-up (the README already credits the paper).
Survey-specific detail remains in
[MULTI_AGENT_SURVEY_FUTURE_WORK.md](MULTI_AGENT_SURVEY_FUTURE_WORK.md), not a
second implementation backlog. The [run-2 findings](RUN2_FINDINGS_FUTURE_WORK.md)
are retained as historical failures: the critic follow-up allowance is built,
while the post-alarm reject-rate guard and robust serious-objection mismatch
classification remain open.
Three 2026 manufacturing-agent papers add five more (silent-execution hazard,
action-target checks, numeric claim provenance, downstream impact at approval,
a propagated-symptom case): [MANUFACTURING_AGENT_PAPERS_FUTURE_WORK.md](MANUFACTURING_AGENT_PAPERS_FUTURE_WORK.md).

#### Tools for specialist roles

A role that needs factory evidence gets it through the same
`FactoryProvider` boundary and tool allowlist as the investigator, in the same
process. Whether tools later travel over MCP is Future Work 2's decision; a
multi-agent role does not by itself justify an MCP server, and any MCP client
adopted then must add no OpenAI SDK. Test, for each role: only its permitted
tools are offered, a call to any other tool is refused, hidden truth never
appears in its view, and human approval cannot be bypassed.

<a id="fw-handoffs"></a>

#### Multi-Agent Handoff Protocol

**Status (2026-10-30):** the critic is the one role built; it receives the evidence and the agent's hypotheses and returns a typed `CritiqueResult`, on Ministral 14B then Cohere through `CRITIC_MODEL`. The planner, researcher, evidence, analyst and synthesizer roles below are planned.

The post-MVP extension will support multiple specialized research agents using different LLM providers when appropriate. Agents will not communicate through unrestricted conversation. Instead, all inter-agent communication will use typed Pydantic contracts so that outputs from one model can be reliably consumed by another model.

##### API Provider Requirements

The post-MVP extension will use the following external AI providers. API credentials for each provider will be stored securely as environment variables and will never be committed to the repository.

The providers we will be using are:

- **NVIDIA**
- **Groq**
- **Mistral**
- **Cohere**
- **Google Gemini**
- **Cloudflare**

The corresponding environment variables should be structured approximately as:

```text
NVIDIA_API_KEY=
GROQ_API_KEY=
MISTRAL_API_KEY=
COHERE_API_KEY=
GOOGLE_API_KEY=
CLOUDFLARE_API_TOKEN=
```

Each provider will have a defined purpose within the multi-agent system rather than being treated as an interchangeable collection of models.

**NVIDIA**
- Primary model provider
- Nemotron 3.5 Lightning 30B A3B
- Lead planning
- Agent orchestration reasoning
- Final synthesis
- Determining whether additional research is required

**Groq**
- High-speed inference provider
- GPT-OSS 120B
- Primary research agent
- Broad investigation
- Tool-assisted research
- Evidence and source collection

**Mistral**
- Independent reasoning provider
- Mistral Small 4
- Critic/challenger agent
- Search for unsupported assumptions
- Identify contradictions
- Generate alternative explanations
- Challenge proposed conclusions

**Cohere**
- Evidence and retrieval specialist
- Command family
- Cohere Rerank
- Retrieval-augmented generation
- Evidence validation
- Reranking retrieved ChromaDB results
- Grounding research conclusions in retrieved information

**Google Gemini**
- Independent analysis provider
- Gemini model selected for the project
- Deep analysis of verified evidence
- Independent conclusions
- Long-context analysis
- Multimodal analysis when appropriate

**Cloudflare**
- Specialist/fallback inference provider
- Workers AI
- Access to additional open models
- Vision or multimodal specialists when appropriate
- Provider redundancy if another API becomes unavailable or rate-limited

The exact model assigned to a role may be updated as models and free API availability change, but these six providers form the post-MVP extension provider pool.

---

#### Handoff Types

The system will support three explicit handoff modes.

##### 1. Full Handoff

Transfers the evidence, sources, conclusions, confidence, assumptions, unresolved questions, and recommended next steps from one agent to another.

This is used when the next agent needs the previous agent's complete research state to continue the investigation.

A full handoff may include:

```text
task
claim
evidence
sources
conclusion
confidence
assumptions
contradictions
unresolved questions
recommended next steps
```

##### 2. Evidence-Only Handoff

Transfers the underlying evidence and sources without transferring the previous agent's conclusion.

This is used when another agent should independently analyze the same evidence without being anchored by the first model's interpretation.

For example:

```text
GPT-OSS Researcher
        ↓
collects evidence
        ↓
Cohere validates evidence
        ↓
EVIDENCE ONLY
        ↓
Gemini Analyst
        ↓
forms independent conclusion
```

Gemini should not automatically receive GPT-OSS's interpretation if the goal is independent reasoning.

##### 3. Challenge Handoff

Transfers both the verified evidence and a proposed conclusion to another agent with the explicit goal of challenging that conclusion.

The critic will look for:

```text
contradictions
unsupported claims
weak evidence
missing evidence
alternative explanations
incorrect assumptions
overconfidence
```

Mistral will primarily perform this role.

---

<a id="fw-interagent-contracts"></a>

#### Structured Inter-Agent Communication

The stage graph (`agent/investigation.py`) will decide when each handoff occurs, while Pydantic schemas will define the information transferred between agents.

Agents will not depend on another model's hidden reasoning or chain of thought.

Only explicit research artifacts will be transferred, including:

```text
claims
evidence
sources
observations
assumptions
confidence
contradictions
uncertainties
unresolved questions
recommended actions
```

A research result may follow a schema similar to:

```python
class ResearchFinding(BaseModel):
    task_id: str
    claim: str

    evidence: list[Evidence]
    sources: list[Source]

    reasoning_summary: str

    confidence: float

    assumptions: list[str]
    contradictions: list[str]
    unresolved_questions: list[str]

    recommended_next_steps: list[str]
```

This common schema allows output generated by NVIDIA, Groq, Mistral, Cohere, Google Gemini, or Cloudflare models to be consumed by another agent regardless of the model provider.

---

#### Common contracts and structured handoffs

**`CritiqueResult` is built; the other contracts are planned.** Each handoff is a project `Contract`, asked for
the same way as the seven policy questions (`ModelPolicy._ask` in
`agent/model_policy.py`): the reply must match the contract or it is refused
and its reason recorded (`INVALID_REPLY`, L4); NVIDIA is asked to keep to the
schema (`structured_output`, L5). Never pass raw model text to the next role.

The planned contracts remain `ResearchTask`, `ResearchFinding`,
`VerifiedEvidence`, `AnalysisResult`, and `SynthesisResult` (`CritiqueResult` is built),
created only as the workflow needs them. Keep the full, evidence-only, and
challenge handoffs, with explicit artifacts rather than private
chain-of-thought.

A valid Pydantic object proves structure, not factual correctness.
`VerifiedEvidence` must record the evidence checks actually performed; an
Evidence Agent's interpretation does not replace Future Work 2's deterministic
MCP-response verification, source provenance, or evaluator-only ground truth.

#### Provider Responsibilities

The initial responsibility map will therefore be:

```text
NVIDIA
Nemotron 3.5 Lightning 30B A3B
→ Planner
→ Lead reasoning
→ Final synthesis
→ Research-loop decisions


Groq
GPT-OSS 120B
→ Primary researcher
→ Broad investigation
→ Tool-assisted research
→ Source collection


Cohere
Command + Rerank
→ Evidence agent
→ Retrieval
→ ChromaDB reranking
→ Evidence grounding
→ Evidence validation


Google Gemini
Gemini
→ Independent analyst
→ Evidence-only analysis
→ Long-context reasoning
→ Multimodal analysis when appropriate


Mistral
Mistral Small 4
→ Critic
→ Challenger
→ Contradiction detection
→ Alternative explanations


Cloudflare
Workers AI
→ Specialist models
→ Vision/multimodal tasks when appropriate
→ Additional open-model access
→ Provider fallback
```

---

#### Multi-Agent Communication Boundary

The post-MVP extension will **not** support unrestricted agent-to-agent conversations.

It will avoid architectures where every agent may continuously communicate with every other agent:

```text
Agent A ↔ Agent B ↔ Agent C ↔ Agent D
     ↖────────↕────────↗
```

Instead, communication will remain controlled:

```text
Orchestrator
     ↓
defined agent role
     ↓
typed Pydantic output
     ↓
selected handoff type
     ↓
next defined role
```

The orchestrator determines whether a **Full Handoff**, **Evidence-Only Handoff**, or **Challenge Handoff** is appropriate for each research step.

This allows different models and providers to work together while preserving traceability, preventing unnecessary context transfer, reducing model anchoring, and making the multi-agent research process testable and explainable.

The core post-MVP extension provider set is therefore:

**NVIDIA, Groq, Mistral, Cohere, Google Gemini, and Cloudflare.**

#### Provider integration — the existing chat client

**Revised 2026-10-26 (developer's decision; replaces the CrewAI/LiteLLM plan of
2026-10-11). The critic is built; the other roles are planned.** Every role calls its model
through `providers/chat.py`, the one standard-library client that already
reaches every in-scope provider through its OpenAI-style chat endpoint. No
framework, SDK or per-provider client is added. A provider-specific change is
justified only by a demonstrated gap the client cannot cover, with a test for
that gap.

| Provider | Integration | Initial role |
|---|---|---|
| NVIDIA NIM / Nemotron | `ChatClient` (structured output on) | Lead investigator, synthesis; candidate general fallback |
| Groq / GPT-OSS | `ChatClient` | Primary research |
| Mistral | `ChatClient` | Critic / challenger |
| Cohere Command | `ChatClient` | Evidence reasoning and grounding |
| Google Gemini | `ChatClient` | Independent analysis |
| Cloudflare Workers AI | `ChatClient` | Specialist or fallback models |

The roles are initial targets; each is confirmed by measurement (Future Work 7)
before it is relied on. The routers in AGENTS.md section 9 (Requesty, xKiro,
LLM7, Kilo Code) can serve small roles too, measured per role
(`docs/benchmarks/2026-10-21-routers.md`).

```text
stage graph (agent/investigation.py) → role's question → job table
  → client_for("provider/model") → ChatClient / FallbackClient → provider
```

The boundary stays where it is: roles return project contracts, the graph
enforces the order and the budgets, and nothing here replaces
`FactoryProvider`, the simulator tools or human approval.

#### Role-specific model benchmarking

<a id="fw-role-benchmarks"></a>

**Priority: MEDIUM, conditional on new specialist roles.**

**Status:** the provider benchmark (`python -m capstone.benchmark`, A8c and L2) measures each model alone on the seven policy questions from real episodes. What is left is benchmarking for new roles.

Test candidate models against representative capstone tasks: infer likely
causes from sensor evidence, compare trends, identify missing evidence, plan
research, analyze verified evidence, challenge conclusions, and synthesize
competing conclusions. Assess explicit results and evidence-supported
explanations; do not request or score private chain-of-thought.

Record task correctness, explicit reasoning quality, unsupported-claim rate,
Pydantic/schema success, tool-use success where applicable, latency, input and
output tokens, total tokens, and failure rate. Record cost when provider usage
and pricing data are available; mark missing usage or cost as unavailable.
Use the results to justify quality/cost/latency tradeoffs and revise role
assignments through the provider abstraction.

Candidates may include NVIDIA/Nemotron, Groq/GPT-OSS, Google Gemini, Mistral,
Cohere, and Cloudflare-hosted specialist models. Verify actual model names,
availability, and supported controls at implementation time. Keep the task
set and scoring rubric small; the harness must not become a project of its
own or require every provider to be connected at once.

#### Per-agent reasoning and token budgets

<a id="fw-agent-budgets"></a>

**Priority: MEDIUM, conditional on new specialist roles.**

**Status:** the single agent has per-job models, request and question seconds, output tokens, retries and its `Budgets`; per-role values are not built.

Each role should support `max_output_tokens`, `reasoning_effort`,
`timeout_seconds`, `max_retries`, `max_tool_calls`, and `max_iterations`.
The single-agent MVP uses the same concepts without introducing extra roles.
Retain deterministic global investigation/tool-call limits across all roles,
retries, and handoffs so local budgets cannot bypass termination rules.

The project's chat client (`providers/chat.py`) translates supported provider
controls; Future Work 3 uses it rather than a framework or a client per provider.
Unsupported optional reasoning
settings may be omitted with their effective configuration recorded; enforce
execution limits in orchestration or reject configurations that cannot be
bounded safely. Reasoning effort is a resource setting, not proof of correctness.

<a id="fw-role-compatibility"></a>

#### Compatibility gate and focused tests

Before assigning any selected model to a role, run a small opt-in compatibility
probe. Record the exact model/endpoint, package versions, test date, required
features, and observed results. Test basic completion, project Pydantic
output, tool calling when required, timeout and output limits, usage/token
reporting, and the required context size. Test any required reasoning or
multimodal controls too. Model capabilities and parameter support vary;
verify rather than treating a documented provider integration as sufficient.

| Provider | Completion | Pydantic output | Role-required tools | Usage | Limits/context | Role-ready |
|---|---|---|---|---|---|---|
| NVIDIA | TBD | TBD | TBD | TBD | TBD | TBD |
| Groq | TBD | TBD | TBD | TBD | TBD | TBD |
| Cohere | TBD | TBD | TBD | TBD | TBD | TBD |
| Gemini | TBD | TBD | TBD | TBD | TBD | TBD |
| Mistral | TBD | TBD | TBD | TBD | TBD | TBD |
| Cloudflare | TBD | TBD | TBD | TBD | TBD | TBD |

Mark unneeded features not applicable and unavailable usage unavailable;
never invent token counts. Decide whether a missing feature disqualifies the
model for that role. Prefer a compatible model or supported configuration
before writing a narrow special-case adapter with tests for the concrete gap.
This compatibility probe complements Future Work 7's task-quality benchmarks;
it does not replace them or require all six providers for the core MVP.

Keep default tests offline with scripted model stand-ins. Prove:

- The Evidence Agent can switch between configured Cohere and NVIDIA models
  without agent, handoff, or downstream-contract changes.
- Both paths produce the same required validated `VerifiedEvidence` contract;
  invalid/raw outputs are rejected rather than forwarded.
- A simulated eligible Cohere rate limit uses the configured compatible
  fallback, while authentication/configuration errors stop execution.
- Retries and fallback stay inside shared budgets, preserve tool permissions,
  and never duplicate a consequential action.
- Provider/model/fallback usage is visible in the audit trail.
- Retrieval reranking preserves source IDs and remains independent of the
  Evidence Agent's configured completion model.

Reuse the existing chat client, job table and fallback; add only the
reliability policy a role is shown to need. No multi-agent framework, generic
routing platform, proxy deployment, six custom clients, or new dependencies. The core single-agent MVP plan and simulator behavior remain unchanged.

<a id="fw-cohere-rerank"></a>

#### Cohere Rerank is a separate retrieval operation

Cohere Command is a chat model; Cohere Rerank is a different operation and
not a chat call. If reranking is needed, add it as one small retrieval step
calling Cohere's rerank endpoint through the same standard-library transport
(no SDK), not as a role.

```text
ChromaDB retrieval → candidate documents → Cohere Rerank
  → ranked documents with original source identifiers
```

Candidate and returned counts are configurable. Preserve document IDs and
source references through ranking. Relevance scores do not establish truth.
Test reranking separately from chat models: changing the Evidence Agent's
model must not change its reranker. Not planned for the first roles.

<a id="fw-requesty-json"></a>

#### Requesty gateway structured JSON output — candidate (2026-10-27)

**Status: documentation-only future-work candidate; not enabled or live-tested
for Requesty in this project.** Requesty announced that its OpenAI-compatible
Chat Completions gateway can accept `response_format` with `type:
"json_schema"` and `strict: true`, then translate the request to the
provider-specific structured-output format for upstream Anthropic, Google,
and other supported models. Requesty reports testing 244 models, **not**
universal schema compliance; some models support only `json_object` or fail
even when the parameter is accepted.

**Existing seam:** `capstone/providers/chat.py` already sends
`answer_type.model_json_schema()` as a strict `response_format` when
`Provider.structured_output` is enabled. This is currently enabled for
NVIDIA (L5), **not Requesty**. The smallest experiment is to exercise that
same flag and existing `ChatClient.ask` path with Requesty, without a
new SDK, regex parser, parallel response contract, or new agent layer.
The exact schema must come from the project's existing Pydantic answer
contract; the returned payload must still pass `model_validate_json`.

**Evaluation before enabling:**
- Run opt-in live probes on the *specific Requesty model IDs* we use for
  investigation and fallback. Test required and extra fields, wrong types,
  nested/optional fields, invalid/empty output, refusals, token truncation,
  and unsupported-schema or `json_schema` HTTP 400 responses. Record the
  model and upstream provider, endpoint, date, schema, response validity,
  latency, and tokens. Verify that our Pydantic schemas are accepted by each
  provider's supported JSON Schema subset, rather than assuming `strict`
  guarantees correctness for every routed model.
- Compare schema adherence and invalid-reply counts against current
  prompt-only Requesty calls and the already structured NVIDIA baseline.
  Keep existing typed validation and invalid-reply accounting (L4).
- Preserve the project's fallback rules and shared question/episode time
  budgets. Requesty's *gateway-level* failover is a distinct mechanism from
  our `FallbackClient`; do not silently stack retries or assume the
  configured model was the upstream model that answered. Confirm the
  actual-model audit trail before relying on gateway failover.
- If a given model supports only `json_object`, record it as weaker
  **syntax-only JSON mode**, not schema enforcement. Keep schema validation
  and rejection on our side; do not change global provider behavior until
  opt-in compatibility tests justify it.

**Adoption gate:** enable per validated model/provider path only if measured
schema adherence improves without unacceptable 60-second episode latency,
cost, compatibility failures, or lost provenance. This note does not
implement Requesty structured output, modify fallback behavior, install
dependencies, or mark the feature implemented or understood.

Source: [Requesty — Structured Outputs Across LLM Providers: 244 Models
Tested](https://www.requesty.ai/blog/structured-outputs-across-llm-providers-the-compatibility-mess).


<a id="future-work-platform-and-tooling"></a>

## Future work: Tooling and infrastructure

<a id="future-work-tooling"></a>

### Single-machine reading for the first real CNC (HIGH; SM-1 to SM-10; proposed 2026-11-07)

<a id="fw-single-machine"></a>

**Category: Tooling and infrastructure. Rank: SM-1 to SM-3 and SM-5 to SM-10 in the [single-machine track](#fw-sm-track) (SM-4 is under Pilot readiness, SM-11 under Evaluation, SM-12 under Planning, SM-13 under Optional interfaces). Status: FUTURE WORK ONLY; nothing here is built.** These items move the project from reading individual sensor values to understanding how one machine behaves over time and under different operating conditions. They keep the Pydantic Graph architecture, `FactoryProvider`, human approval and evaluator-only truth unchanged, and add no new agent.

**Why the simulator path cannot be reused as is (checked against `main` at `8969c5f`, 2026-11-07):**

- `ObservationTools.get_sensor_summary()` (`tools/observation.py`) computes `rate_of_change` from the first and last readings only, and `mean` with `fmean` over readings. A signal that rises sharply, peaks and returns to its start reports zero change, and every reading counts equally however long it held.
- `TelemetryRecord` (`ingestion/record.py`) stores the value as text with no engineering unit.
- The collector (`ingestion/collector.py`) prints `gap: some observations were lost` to stderr; the JSONL file does not record where data was lost.
- No provider reads collected JSONL, so the Investigator cannot use real data yet (the "main missing piece" in the [pilot plan](#fw-haas-live-pilot)).

**Before connecting to the machine (HIGH):**

- <a id="fw-sm-channel-map"></a> **SM-1: Versioned channel map from `/probe` (HIGH).** From the saved probe, record for each data item its id, category, type and subtype, units as the probe states them, what it measures physically, which tool sensor it feeds (or none), and whether the machine actually reports it. Tie the map to a hash of the probe so a controller update cannot silently change a channel's meaning. Units and meaning come from the probe, never from assumption. This is the mapping table the pilot plan defers until the probe exists. *Accept:* every observation in a capture maps to one channel entry or is reported as unmapped; no unit is guessed.
  **Status (2026-11-07): built, PR #206 (built ungated at the developer's direction; questions and walkthrough owed; understood: no).**
  - *Built:* `capstone/ingestion/channel_map.py` reads every DataItem of a saved probe with its units exactly as stated. A person's assignment file adds what each item measures and which agent sensor it feeds; nothing is inferred from names.
  - *Built:* the map holds a hash of the probe's device description, so a changed controller layout is refused. `check_capture` maps each observation to one entry or lists it as unmapped, flags category/type disagreements, and records which channels reported a value.
  - *Built:* command line `python -m capstone.ingestion.channel_map build|check`, which refuses to write inside a git checkout.
  - *Acceptance:* tested on a synthetic probe shaped like demo.mtconnect.org. Not yet run on the real machine's probe, which does not exist yet.
  - *Not built:* use of the map by the real-data provider (SM-3) and by per-channel staleness (SM-2's remainder).
- <a id="fw-sm-gap-events"></a> **SM-2: Collection gaps and data quality written into the telemetry file (HIGH).** When a poll reports a gap, a poll fails, or the agent restarts (`instance_id` changes), append a typed marker next to the existing `started`/`heartbeat`/`stopped` markers, with the time span and sequence range affected. Mark channels as stale when no update arrives within an agreed age. The MTConnect standard defines an `UNAVAILABLE` result as indeterminate, so it is a gap, not a value. Replay and the Investigator then know exactly where data was lost. *Accept:* replaying a capture with an injected gap reports the gap at the same place, and no statistic spans it.
  **Status (2026-11-07): partly built, PR #204 (built ungated at the developer's direction; questions owed; understood: no).**
  - *Built:* the collector writes a `gap` marker (`CollectorMarker` event `gap`, schema version 2) before the readings that follow a loss. It says the cause (`buffer_overrun`, `out_of_range` or `agent_restart`), the lost sequence range as far as it is known, the last reading's receive time, and both agent run ids on a restart.
  - *Built:* `gap_free_runs` splits readings at every gap and collector start, so a statistic can stay within one run. The monitor reports a gap as a data-loss warning, not a crash.
  - *Acceptance:* tested with a scripted agent. An injected overrun appears between the readings it separates, with the exact range. Not yet run against a real capture.
  - *Deliberately not marked:* a failed poll on its own. The agent buffers, so a real loss shows as an overrun or OUT_OF_RANGE on the next successful poll.
  - *Not built:* per-channel staleness (needs SM-1's channel map, because change-reported channels stay silent when unchanged), and UNAVAILABLE spans written as gaps (with SM-5; readings already carry `available=False`). No replay or provider uses the markers yet (SM-3 will).
- <a id="fw-sm-real-provider"></a> **SM-3: Read-only real-data provider over recorded JSONL (HIGH).** A `FactoryProvider` implementation that answers the existing `ObservationTools` from a capture: map timestamps to the tools' time axis, map channels through SM-1, return unavailable for anything not collected, and never return readings after the replay cutoff. Collecting readings and making them usable for diagnosis are separate problems; this item is the bridge. Do not feed real observations into the simulator's tick-based arithmetic without SM-5. *Accept:* the existing tool contracts hold on a recorded fixture and simulator regressions stay green.

**Once representative readings exist (HIGH):**

- <a id="fw-sm-time-stats"></a> **SM-5: Time-aware statistics for unevenly sampled data (HIGH).** Controller data often arrives only when a value changes (confirm per data item from the capture), so readings are not evenly spaced. Example: spindle load at 10% for 90 s, then 90% for 10 s, averages to 50% over the two readings, but the time-weighted mean is 18%. For change-reported channels, keep how long each value held and compute time-weighted mean, time above a level, peak excursion and a time-aware slope. For regularly sampled channels, use the actual timestamps and allow uneven intervals. Never carry a value across a known gap or `UNAVAILABLE` interval as if it were measured. For the real-data path this replaces the endpoint-only `rate_of_change` and supersedes [deterministic sensor calculations](#fw-sensor-calculations). Can be built and tested against the public demo agent before the visit.
- <a id="fw-sm-state-segmentation"></a> **SM-6: Operating-state segmentation (HIGH).** Label windows as idle, spindle running, cutting, tool or program change and warm-up, using only fields the controller exposes (for example execution state, spindle speed, load, program, tool number). If two states cannot be told apart, merge them rather than guess. The 2026-11-06 offline probe of the [CPU anomaly detector](#fw-cpu-anomaly-detector) found that comparing all readings flagged healthy machines on idle-to-cutting transitions, and running-only comparison fixed it. Tool-condition monitoring research also isolates actual cutting (removing air cutting) before extracting features ([Bombiński et al., 2016](https://doi.org/10.1016/j.procir.2016.03.203)), and spindle speed plus load from MTConnect alone can separate running, cutting and efficient cutting ([Parto et al., 2018](https://saemobilus-test.cld.sae.org/papers/machine-utilization-spindle-data-using-mtconnect-f-0074-2018-12800)). Start with running versus idle. *Accept:* on a captured session, segment boundaries match the [technician event log](#fw-sm-visit-log) within an agreed tolerance.
- <a id="fw-sm-own-baseline"></a> **SM-7: Same-machine baseline from its own normal history (HIGH).** For each state from SM-6, save the machine's normal ranges (median, MAD, mean, standard deviation, count, with warm-up stages) from periods the technician confirms were normal. This is the real-machine version of the simulator's saved "before" file in the [CPU anomaly detector](#fw-cpu-anomaly-detector); here it cannot come from a fault-free simulator run. Compare heavy cutting with past heavy cutting at similar RPM and load, never with idle. Until enough normal data exists, report `baseline_unavailable`, never normal. The [Line Sentinel](#fw-line-sentinel) peer comparison does not apply to one machine. Same typed output contract as the detector.

**Then (MEDIUM):**

- <a id="fw-sm-trend-features"></a> **SM-8: Richer trend features (MEDIUM).** Add rolling variability, persistence (how long a deviation has lasted), spike counts and trend acceleration, so a summary captures spikes, sustained changes and speed-ups instead of averages and endpoints. These are the detector's stage-1 statistics computed on SM-5's time-aware windows within SM-6 states.
- <a id="fw-sm-cross-signal"></a> **SM-9: Cross-signal relationship checks (MEDIUM).** Measure relationships, not just single signals: for example, a sustained rise in spindle load and temperature across comparable cutting cycles while RPM stays about constant. Report it as a structured observation, not a diagnosis, because the workload, tool, coolant or material may have changed. It gives the Investigator a specific discrepancy to explain. Correlated features are not independent corroboration. Illustrative shape (values made up):

  ```json
  {
    "machine_id": "CNC-01",
    "assessment": "sustained_deviation",
    "operating_context": "comparable_cutting_cycles",
    "load_change_percentage_points": 17,
    "temperature_change_f": 13,
    "rpm_change": 0,
    "next_step": "investigate_cause"
  }
  ```

  The real assessment also carries the time window, baseline ID, data quality and links to the source observations. Use units from SM-1, not assumed ones.
- <a id="fw-sm-cycle-signatures"></a> **SM-10: Cycle reference signatures (MEDIUM, conditional).** If the machine repeats a program and the controller exposes program name, block or line, or part count, save a reference signature of normal cycles and compare later cycles at matching stages (time alignment such as dynamic time warping). Building envelopes from successful similar operations ([Cunha, UFSC](https://repositorio.ufsc.br/handle/123456789/263932)) and segmenting machine data with dynamic time warping ([MDPI, 2019](https://www.mdpi.com/2504-4494/3/4/97)) are established approaches. Build only if the first machine exposes these fields and runs repeated programs; a shop running mostly one-off jobs may give too few comparable cycles, in which case keep SM-7's per-state baselines keyed by program and tool.

**Limit to keep in view.** Ordinary controller telemetry may show a developing abnormality without identifying the damaged part. NIST found that simple vibration-based metrics are, in many cases, insufficient to diagnose spindle condition ([Vogl and Donmez, 2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC5217751)). Part-level localization is [SM-11](#fw-sm-check-ranking) and later.

### CPU-based statistical anomaly detector and line-context assessment (HIGH; proposed 2026-11-06)

<a id="fw-cpu-anomaly-detector"></a>

**Category: Tooling and infrastructure. Priority: HIGH. Status: stage 0/1 BUILT 2026-11-06** as the always-on `get_line_screening` tool (`capstone/tools/screening.py`, saved file `capstone/tools/healthy_reference.json`), called by the loop at the start of every investigation on its own allowance. Not yet run live. The roadmap below is kept as written. This is a **small CPU-only Python monitoring component**, not a separate LLM or a fine-tuned 0.8B model. It extends the existing read-only `ObservationTools.get_sensor_summary()`, `get_sensor_trend()`, raw readings and machine status, while preserving the existing simulator, `FactoryProvider`, Pydantic Graph, approval and verification boundaries.

**First increment (no new infrastructure required):**

1. Use bounded sliding windows of observable per-machine temperature, vibration, load and other available signals, compared against the saved "before" reference (below), with warm-up ranges. Start with transparent, deterministic, configurable checks: rate-of-change/rolling trend, deviation from an eligible baseline, corroboration across signals, and sustained exceedance. Report both direction and magnitude, not a guessed root cause. Compare only compatible operating contexts (running vs idle; speed/load/job when observable); do not treat a normal warm-up, program change or job transition as degradation.
2. Require minimum samples and adequate coverage; flag absent, stale, partial or unreliable windows as `insufficient_data` or `baseline_unavailable`, **not normal**. Use persistence windows, hysteresis, cooldowns and incident deduplication so transient sensor spikes do not repeatedly launch expensive investigations. Document the threshold choices and their units; calibrate with actual representative data later, not made-up certainty.
3. Produce a bounded, structured, **derived monitoring assessment** per machine, intended for the [line-wide incident context](#fw-line-context). Include machine and sensor IDs, source tick/time cutoff, exact observation window, sample count/quality, baseline reference when valid, measured trend/delta/deviation and applicable rule IDs, state such as `normal_with_coverage` / `sustained_deviation` / `insufficient_data`, and links/identifiers for the supporting underlying observations. This is computed evidence, **not** the LLM's diagnosis; avoid cause names or invented confidence probabilities. Preserve the distinction between raw sensor measurements, derived features and agent hypotheses; correlated features are not independent corroboration.
4. Always attach a **compact assessment for every machine on the line** as an evidence section of the [existing line context](#fw-line-context), before the investigator plans, even when only one machine alarms. Flagged machines and relevant upstream/downstream neighbors get more detailed bounded sensor windows; no unbounded data dump. The investigator can inspect original readings and may disagree with the summary. The detector must not silently equate the alarm location with the root cause, or collapse unrelated faults into one cause. The detector can also create a `DetectedAnomaly` when persistent abnormal behavior lacks a manufacturer threshold alarm, routed through the **existing** bounded triage/deep investigation entry point; never call an LLM on every sensor sample. Keep manufacturer/controller alarm and safety behavior independent and retain human approval for consequential actions.
5. Keep the first version in-process on the CPU, offline, and deterministic under a fixed simulator seed: no GPU, training, persistent database, new agent or real-machine access. The larger [telemetry ingestion and replay](#fw-telemetry-replay) work remains a separate MEDIUM-priority extension.

**Staged implementation roadmap — advance only when the previous stage's metrics justify added complexity:**

| Stage | Technology | Deliverable and role | Gate to advance |
|---|---|---|---|
| **0 — transparent rule baseline (first build)** | Python standard library and existing `ObservationTools` | Rolling windows, observed delta/rate, sustained-change flags, missing-data checks, deduplication, and a typed derived assessment attached to the optional line-context section. No training or new database. | Document false alarms, missed progressive faults, onset-to-trigger delay, CPU time and whether derived context helps or biases the investigator. |
| **1 — stronger statistical baseline (next candidate)** | NumPy; SciPy only where needed | Robust rolling statistics (for example median/MAD), baseline-normalized deviations, regression slopes and multi-window trend comparisons. Explicitly condition on running/idle and available load, speed and job context; handle missing samples without pretending they are zero. No neural network or fitted anomaly model required. | On the same held-out seeded cases, demonstrate better detection/false-positive trade-off than stage 0, with acceptable latency and explainable detector output. If not, keep stage 0. |
| **2 — batch machine-learning experiment (optional; may be added later, not necessary)** | scikit-learn, e.g. `IsolationForest` | Offline train/test pipeline using historical **feature windows** (not raw arbitrary sequences): rolling load, vibration, temperature, trend, variability and operating context. Train only on data available before each test window, keep machines/time periods separated when assessing generalization, and avoid using simulator hidden truth as features. Send flagged features and source readings to line context; never state an anomaly score is a diagnosed failure. | Require sufficient representative data and a measurable gain over stage 1 on held-out faults and normal operation, including stability across jobs and machines. Synthetic results are a proof-of-concept, **not** real-shop validation. |
| **3 — streaming/online ML experiment (optional, later)** | River or another measured CPU-friendly online method | Incremental anomaly scoring as observations arrive, potentially adapting context-specific baselines without retraining from scratch. Preserve model/checkpoint versioning and freeze or guard updates during suspected faults so the system does not learn a degradation pattern as normal. | Only if continuous authorized telemetry and drift measurements show that a static stage-1/2 detector degrades. Validate replay parity, concept-drift behavior and recovery before enabling triggers. |

**Offline probe results (2026-11-06, no model calls, not yet built):** a throwaway script replayed all 13 known-answer cases to the tick monitoring raised its alarm and scored every machine on the line. For each machine and sensor it compared the last 60 readings with the first half of that machine's history using two scores: a robust z-score (median and MAD) and a plain z-score (mean and standard deviation). A machine was flagged only when both scores reached 3 or more.

- **Comparing every reading is noise.** Machines further down the line sit idle until parts reach them, so their load later jumps tenfold or more. On all readings, healthy machines outscored the faulty one, and in both false-alarm cases the top flag was a healthy machine. **Running-only comparison is required:** use only ticks where the machine's own `load` reading shows it was cutting (the probe used load above 15).
- **With running-only comparison and the two-score rule:**
  - Bearing, servo and hydraulic cases (KA-01, 02, 10 to 13): 6 of 6 flagged the faulty machine, through the expected sensor (vibration, following error, hydraulic pressure), with no healthy machine flagged.
  - False alarms (KA-07, KA-08): the alarmed machine correctly looked normal. In KA-07, two healthy machines were flagged through `power`, the noisiest signal, which needs a stricter rule.
  - Bad batch (KA-03, KA-04): nothing flagged, which is correct.
  - Wrong setting (KA-05, KA-06): missed. This fault shows in inspections and settings, not in sensor trends, so the detector cannot replace those tools.
  - Challenge (KA-09): the alarm fires at tick 71, too early for any machine to have enough running data. Scored again at tick 900, it flagged CNC-07 (the real bearing fault) and nothing else. **The assessment must be refreshed during the investigation, not computed only once at the alarm.**
- **Decision on the stages.** Stage 0 together with the stage-1 statistics above is the target: deterministic, explainable, CPU-only, and it already finds every progressive machine fault in the known cases. **scikit-learn (stage 2) is optional: it may be added later if wanted, but it is not necessary.** On these cases it would not fix either weakness, since setting faults leave no sensor trend and KA-09's problem is timing, and a model trained on simulator data mostly learns the simulator's own noise. Revisit it only if real or richer data shows faults stage 1 misses. **River (stage 3) is skipped for the capstone:** it needs continuous live telemetry that drifts, which the project does not have, and it risks learning slow wear as normal.
- **Saved "before" reference (developer's decision, 2026-11-06).** Instead of waiting for each machine to build up its own history, the detector compares against a **"before" file**: each machine's normal running range per sensor, saved from a fault-free run of the line.
  - **How the file is made:** run the line with no fault injected and save, for each machine and sensor, the median, MAD, mean, standard deviation and sample count of its running readings (load above the running threshold). The file is generated deterministically by a script from a fixed seed, committed with the code, and loaded when the detector runs. It holds only observable readings a shop would have from a healthy period, never hidden truth.
  - **Warm-up is saved too.** A machine that has just started cutting runs colder than a warmed-up one: in the probe, healthy CNC-04 was flagged "temperature low" after 19 running readings. So the file also keeps ranges by **running time since the machine started cutting** (for example, the first 50, 50 to 150, then steady), and a machine is compared with the range for its own stage of warm-up.
  - **What still applies:** the detector needs a few readings from the machine itself (the probe used 20 for the recent window). A machine that has not started cutting reports "not running yet", never "normal". Its output always says which reference it used.
  - **Offline probe of this design (2026-11-06, no model calls):** with a 1,000-tick fault-free "before" (taken both from the case's own seed and from a different one, with the same answers either way), the two-score rule found all 6 wear and leak faults and **flagged no healthy machine in any of the 13 cases**. That removed KA-07's `power` false flags. KA-08 scored 6 of 8 machines at its alarm instead of 4. Wrong-setting faults are still missed. At KA-09's tick-71 alarm, five of seven machines, including CNC-07, had not started cutting, so nothing could score them yet.
- **As built (2026-11-06):**
  - The file records two days (2,880 ticks), so the daily swing in factory air temperature and several material batches are inside the range.
  - Only temperature has warm-up stages. Load and power depend on the material batch, so a warm-up stage holding one batch was far too narrow and flagged healthy machines.
  - Across the 13 known cases at their alarm ticks, a two-score rule (both at least 3) still finds all 6 wear and leak faults and flags no healthy machine.
  - **Compact answer (2026-11-07):** the agent receives, for each machine, each sensor's `[robust_score, plain_score]`, with temperature adding its warm-up stage, or the reason there is no score. The full per-sensor rows (window, medians) stay inside `screening.py`. The full rows were about 16,000 characters, against the 2,000 a prompt shows of one piece of evidence, so most machines never reached the model.
  - **Blackout:** while a machine's sensor feed is down (`--hazards blackout`), its entry reads `feed_unavailable`, matching the refused sensor tools.
- **One place for every setting (developer's rule, 2026-11-06):** the seed, length, running threshold, window sizes, warm-up boundaries and warm-up sensors live in the file's `settings`. The screening and the tool description read them from there. A test checks that regenerating gives the committed file, so a value cannot be copied elsewhere and drift.
- **Real data needs a new "before" file (developer's note, 2026-11-06):** the committed file describes the simulator only. Before the screening is used on a real machine, record a new file from a confirmed healthy period of that machine, such as right after maintenance. Never use the simulator's file against real readings.
, not labels ([A4](COURSE_NOTEBOOKS_FUTURE_WORK.md#a4-line-snapshot-at-the-start-of-the-investigation-medium-evidence)). The recommendation is to give the investigator the two scores, the window and the coverage, and not a "flagged" label, so the model still makes the call.

**Shared output contract across all stages:** the investigator receives **the same typed, read-only assessment shape** in the [line-wide incident context](#fw-line-context): source/cutoff, machine, sensor window and operating mode, measured features, quality/coverage, rule or model version, alert state and links to supporting observations. A model's anomaly score may be included as a derived numerical signal but must not replace raw evidence or be converted into a fabricated probability of a root cause. **No setting turns the detector on or off, and none selects a stage (developer's decision, 2026-11-06):** it is a normal implementation that always runs, and moving to a later stage replaces the earlier code rather than adding a switch. Each stage should operate on CPU at capstone scale; measured throughput and memory, not an assumption, decide production capacity.

**Sequencing:** The line-context packet already exists (merged in #186). The detector is added to it as a normal, always-on part, with no on/off setting. To attribute any improvement or bias to it, compare matched-seed runs from the commit before it is merged with runs after; the archived line-context runs serve as the "before". Start with one sensor trend and one simulator scenario rather than implementing every possible anomaly rule at once.

**Acceptance/evaluation:** On matched normal, progressive wear, speed/configuration change, isolated spike, missing-data, multi-machine and wrong-machine-trigger cases, compare threshold-only versus trend-based detection. Measure onset-to-detection lead time, false positives per simulated operating hour, missed incidents, duplicate launches, detector CPU time/memory, and incremental LLM requests. Compare line context **before versus after** the detector is merged (earlier commit against later, same seeds and settings) on the same observable histories, scoring correct machine/cause, unsupported inference, abstention, evidence provenance and tool use. Keep simulator ground truth exclusively evaluator-side, and do not claim real factory reliability from synthetic tests.

### Simulated telemetry ingestion, unified sensor history and replay (MEDIUM; proposed 2026-11-02)

<a id="fw-telemetry-replay"></a>

**Status: FUTURE WORK ONLY.** First prove the separate
[incident-first, line-wide context increment](#fw-incident-context) without
requiring a new database or continuous monitor. Prioritize the
simulated-stream proof after that comparison and the existing single-agent
investigation baseline are stable; do not claim a live
collector, persistent sensor database, real-machine access, or a completed
replay test today. This is a data-acquisition and evidence-availability layer,
not a new LLM "live mode" or a replacement for the existing reasoning graph.

**Stage A — capstone-scale simulated stream and historical queries:**

1. Make the existing seeded simulator a **timed telemetry producer** through a
   small, replaceable producer/ingestion interface. It must still support
   deterministic offline tests without a database, wall-clock sleep, an LLM or
   proprietary factory data. Persist observations to one logical time-series
   reading store (PostgreSQL; TimescaleDB is optional after measured volume
   warrants it), separate from Chroma manuals and episodic memories. Keep
   observable events/alarms and job/status transitions correlated by timestamps
   and identifiers, whether in a companion event table or typed record stream.
2. Specify a common reading contract before choosing transport: source and
   sample identifiers, run/line/machine identity (nullable for factory ambient
   readings), channel, value, unit, **observed timestamp or simulation tick**,
   ingestion timestamp, quality/freshness flags and provenance. Capture
   operating context **at the reading's time**: machine status/mode, spindle
   RPM, measured load if available, active job/operation and applicable
   settings. Distinguish absent data from a measured zero; do not fabricate
   sensors or context. Preserve source clock offsets, gaps, duplicates,
   out-of-order arrival and ingestion lag, and make replay writes idempotent.
3. Make the agent's read-only `FactoryProvider` observation surface return
   **windowed readings, trends, events and summaries** from this store.
   "Live" means a sufficiently fresh recent window (for example last N
   seconds); "historical" means an older bounded window of **the same stored
   measurements**. Both need explicit source time, as-of cutoffs, completeness
   and freshness; a recent query is not proof that the physical machine is
   currently healthy. Preserve existing tool contracts where practical, using
   a separate provider implementation rather than rewriting investigator,
   critic, manual RAG or memory logic.
4. Run a **deterministic, always-on monitoring service**, not an LLM polling
   sensor rows. Begin with documented fixed/manufacturer thresholds,
   sustained-change/rate-of-change rules and missing/stale-data detection;
   add context-matched baselines only when representative observations exist.
   Compare like operating conditions (RPM, load, mode and job), with
   hysteresis, deduplication and clear alert provenance. Cold-start status
   must be `baseline_unavailable` or equivalent, never "normal by default".
5. **Decouple alarm location from investigation scope.** A machine alarm is
   one symptom, not a root-cause label. The near-term agent-side
   [line-wide context, coverage critic and matched comparison](#fw-line-scope)
   are separately buildable now and do **not** depend on this store.
   Here the deterministic monitor adds triggers: silent degradation,
   cross-machine flow changes, routine health checks and data-quality
   incidents can initiate triage. Correlate upstream/downstream machines using
   a bounded line-wide status/event summary before targeted deep research.
   Group likely cascading alarms into an incident, but preserve distinct
   independent faults; never assume one shared cause. Existing safety and
   controller alarm handling remain independent of the LLM.

**Replay acceptance gate:** Capture one seeded stream with known fault truth
kept evaluator-only, then supply the **same timestamped observation windows**
from (a) the advancing simulated stream and (b) replay of stored records.
Verify equal available observations, context, event ordering, freshness/gap
semantics and deterministic monitor decisions. With pinned prompts/model
settings, compare root-cause/affected-machine conclusions, cited evidence,
abstention and tool usage; do not require byte-identical free-text output
from a nondeterministic model. Test an alarm on the wrong machine, an
alarm-free progressive fault, a cascading line effect, independent concurrent
faults, cold start, dropped/stale/late/duplicated readings and a normal run.
Report detection delay, false/missed triggers, data completeness, diagnostic
accuracy, budget use and replay parity. Do not confuse tape replay with
counterfactual post-intervention verification.

**Stage B — real equipment is deferred and conditional.** The concrete shop-facing [Haas live-telemetry pilot plan](#fw-haas-live-pilot) below is ready for outreach, but does not authorize implementation or machine access. Only with a willing
shop, authorized read-only access and a verified machine capability matrix
should an MTConnect/OPC UA or approved MQTT/external-sensor adapter replace the
simulator producer. The *same* ingestion contract and agent-facing read tools
should work; OT security, edge buffering, clock synchronization, shadow mode
and shop-floor validation are separate pilot gates, not Stage A deliverables.
No assumption that a physical machine is available for the capstone.

**Dependencies and boundaries:** Preserve seeded determinism, hidden-truth
isolation, human approval and verification. This follows the
[incident-first context and matched-seed evaluation](#fw-incident-context),
which can use simulator-held data before any database. Coordinate with
[rapid triage](#fw-rapid-triage), [degraded data](#fw-degraded-data),
[Haas reference-machine capabilities](#fw-haas-retrofit) and
[Future Work 5 monitoring/dispatch](#fw-proactive). The present
`ObservationTools` read simulator-held observations; this proposal does
**not** assert that a PostgreSQL time-series pipeline already exists. Build
and compare the simplest measured slice before introducing a broker, new
multi-agent monitor or high-frequency infrastructure.

### Haas live-telemetry collection and manufacturer pilot (HIGH for outreach planning; post-MVP implementation)

<a id="fw-haas-live-pilot"></a>

**Status: DOCUMENTED PLAN ONLY (2026-11-03).** The developer intends to
contact manufacturers about a small, read-only Haas pilot. This is a
**module within the existing capstone repository**, not a separate GitHub
product. The collector, deterministic monitor and research agent must be
**separately runnable processes** so a model timeout or deployment restart
cannot block acquisition. Nothing in this plan implies a connected Haas,
approved shop, finished collector, or verified diagnosis on physical data.
Keep the existing seeded simulator and master-run evaluator usable without
factory access. This extends [the unified ingestion/replay plan](#fw-telemetry-replay)
and [Haas capability review](#fw-haas-retrofit); it does not move real
equipment into the current MVP.

**What already exists (checked against `main`, 2026-11-04).** Built and
tested only against the public `demo.mtconnect.org` agent, never a Haas:
the read-only MTConnect collector (`capstone/ingestion/`: GET only, minimum
1 s and default 5 s poll interval, 10 s timeout, 20 MB response cap,
`started`/`heartbeat`/`stopped` markers, 60 s heartbeat, `--save-probe`;
`gap` markers for lost data added by SM-2, PR #204), the
deterministic monitor (`capstone/monitoring/`) and the collector watchdog
(`capstone/watchdog/`), PRs #165–#167. The output-path guard (collector,
monitor and watchdog refuse to write inside a git checkout) is in its own
pull request. **Not built:** the on-site spool and outbound upload, any
hosted ingestion API, a provider that lets the agent read collected data,
alert delivery to a person, and file rotation.

#### What to offer a manufacturer

- **One-machine, opt-in pilot.** Begin with an approved connectivity/field
  discovery session; propose **7 days of collection**, with a **30-day
  extension only if the manufacturer agrees**. No line-wide installation
  or production-system integration is required for the first pilot.
- **Read-only and non-disruptive by design, not assumed safe.** No controller
  writes, resets, cycle-start/stop, setting edits, macro/program transfers,
  autonomous maintenance or production intervention. Verify supported query
  frequency and operational impact with the shop before leaving a collector
  running. The factory's safety systems remain authoritative; technicians
  decide what to do with any findings.
- **Useful first output.** Give the participating shop a limited summary of
  machine operating state, available trends, alarms and data gaps, plus
  evidence-backed *candidate* anomalies. Do not promise predictive
  maintenance, a confirmed bearing diagnosis, or verified cost savings from
  a week of mostly normal observations.
- **Explicit consent and data control.** Approval must come from an
  authorized shop owner/manager and its IT/OT contact, not just an operator
  willing to talk. Agree in writing on approved machine(s), queried fields,
  access method, retention/deletion, hosting location, permitted use,
  anonymization, sharing and revocation. Keep raw shop data private; never
  commit customer telemetry, program content, serial numbers, credentials or
  identifiable job/customer details to this public repository. Only
  explicitly authorized anonymized examples may be published.

#### Connectivity: choose the safest supported path

1. **Identify the machine before designing the adapter:** exact Haas model,
   approximate year, Classic Haas Control (CHC) versus Next Generation
   Control (NGC), control/software revision, available Ethernet/serial
   connection and who administers it. Record any identifying details in a
   private pilot inventory.
2. **Prefer existing read-only telemetry.** For a compatible, approved NGC
   machine, inspect MTConnect's available data items (for example via its
   read-only probe/current/sample interface) and consider authorized Haas
   Machine Data Collection if appropriate. For CHC, separately check the
   model's supported read-only RS-232/Q queries. Do **not** presume every
   Haas supports MTConnect, or that spindle temperature, vibration, motor
   current, power or detailed fault signals are exported. Public guides
   (MachineMetrics) say NGC MTConnect is under Settings → Network →
   MTConnect, on port 8082, usually on by default, with software
   100.20.000.1200 or later recommended for the fullest data. No login is
   documented for it, so treat it as an open read interface: keep the
   collector on the same approved network segment. No Haas list of data
   items was found; sources suggest machine state, execution, spindle
   and feed, alarms, program and part count. The machine's own `/probe`
   (`python -m capstone.ingestion --save-probe`) is the authoritative list.
3. **Default network topology:** run a small **on-site Python collector/
   bridge** on an approved PC or mini-computer within the factory network
   and read only the authorized controller endpoint. **For the first pilot,
   keep the data on that PC** (the collector already writes local JSONL)
   and export it by an agreed manual step. Later, if approved, buffer
   samples locally during internet outages and send encrypted **outbound
   HTTPS** batches to a hosted ingestion API; neither the upload nor the API
   exists yet. No inbound internet exposure of
   the CNC or factory router. If the shop expressly authorizes a tightly
   controlled VPN to a compatible endpoint, consider direct hosted
   collection; **Render does not automatically reach private factory LANs**.
   A Render background worker can run a non-serverless cloud process, but
   that alone does not solve the OT network boundary.
4. If no safe/approved connection exists, stop; do not improvise firewall
   rules, scan the OT network or deploy external sensors without separate
   written approval. Offer an offline export or recorded-data pilot only
   if the shop permits it.

#### Implementation inside the capstone (after the MVP gates)

Proposed additions under `capstone-code/capstone/` (names are provisional):

- `ingestion/` (**collector built**): still to add an optional CHC
  adapter, the edge spool and idempotent batch upload.
- **A real-data provider (the main missing piece).** `FactoryProvider` in
  `providers/factory.py` is already the plug-in point (the hazards wrapper
  uses it). A new provider must read collected JSONL and answer the
  existing tools: map wall-clock timestamps to ticks, map each Haas data
  item to a tool sensor with its unit, and return unavailable for anything
  not collected. The tools' sensors today are `vibration`, `temperature`,
  `load`, `power`, `following_error` and `hydraulic_pressure`; most will
  probably be unavailable on a Haas, and spindle speed or feed may need
  new sensor names. Write the mapping table only after the machine's
  `/probe` is saved.
- `monitoring/` and `watchdog/` (**built**): still to add delivery of alerts
  to a person (they only write files today), cooldown where needed, and
  per-channel thresholds from the probe. Do not run an LLM on every poll.
  Use the existing investigation/critic path only when an actionable
  incident is formed.
- **Keep shop data out of this public repository:** the output-path guard
  refuses paths inside a git checkout, and `.gitignore` lists `telemetry/`
  and `pilot-data/`. A blanket `*.jsonl` rule is not possible:
  `docs/benchmarks/` tracks benchmark JSONL files.
- **Storage:** keep raw transport payloads when authorized and practical,
  but normalize to a versioned record with source/machine/channel,
  value/unit or typed event, source timestamp (UTC plus clock-offset
  quality), receive timestamp, sequence, provenance, validity and
  operating context. Persist to an access-controlled PostgreSQL store
  or appropriate compressed time-series files (e.g. Parquet). JSONL is
  suitable for small fixtures, interchange and deterministic replay;
  **Markdown is documentation, not telemetry storage**. Preserve actual
  missing data rather than filling values from simulator assumptions.
- **Deployment:** one capstone repo, separate collector/edge process,
  hosted ingestion API/storage and independent monitoring/agent workers.
  Pin per-pilot configurations and credentials outside source control;
  record service health, upload lag, gaps, clock drift and restarts. On the
  on-site PC: enough disk for the pilot plus a rotation rule, clock sync
  (NTP) checked before the start, and a named person who patches the PC
  and restarts the collector when the watchdog reports it silent.

The agent should see the same *types* of observations in simulation, replay
and live mode; it must not see simulator-only hidden fault truth. Missing
channels are unavailable, not zero or fabricated. A real-data investigation
is initially **shadow/read-only**: it may report a suspected cause and
request technician validation, but cannot execute a machine fix.
Counterfactual post-repair verification is **not possible** from a static
recording; only separately authorized technician actions and subsequent
measurements can support real-world outcome claims.

**What one machine can and cannot test.** The planned
[Line Sentinel](#fw-line-sentinel) compares machines with their peers; one
machine has none, so only its comparison with its own past applies. A
7-day capture is mostly a cold start (`baseline_unavailable`) and mostly
normal operation. The pilot can test collection, data quality, the monitor
and the watchdog. It cannot test diagnosis accuracy unless the shop
shares past alarm and maintenance history or a technician logs events
during the week.

#### Phased trial and acceptance checks

1. **Outreach/discovery (before coding):** confirm one willing shop, the
   decision-maker and IT/OT approver, target model/control, rough available
   data fields, connection options and pilot permission. Prepare a one-page
   data-flow/privacy sheet and read-only pilot agreement.
2. **Bench proof (no production machine required):** implement against
   recorded/synthetic protocol fixtures; test decoding, corrupt responses,
   disconnect/retry, spool/backfill, duplicates, sequence gaps, timestamps,
   missing fields and clean stop/revoke. Keep simulator regressions green.
3. **Approved on-machine smoke test:** during a shop-approved window,
   first save the machine's `/probe` (`--save-probe`, to a folder outside
   the repository), then check what the controller actually exposes and whether the permitted
   poll rate has negligible *measured* production impact. Confirm
   controller generation, units, timestamps, alarms, mode and load/RPM
   field mapping; save the capability matrix privately.
4. **7-day collection pilot:** obtain logs without gaps being silently
   hidden. Proposed targets, to agree with the shop before starting: a 5 s
   poll interval (never below the collector's 1 s minimum, slower if the
   shop asks); collection running at least 95% of the approved hours; no
   unexplained gap over 10 minutes; and stop at once if the shop reports
   any effect on the machine or network. Report collection uptime, missing/late/duplicated samples,
   freshness, observed modes and alarm/event coverage; review findings
   with the shop. Extend to 30 days only after explicit approval and
   demonstrated stable operation.
5. **Replay and shadow agent check:** replay selected captured windows
   through the common observation interface, compare with live windows
   and confirm no future-sample leakage. Test monitor alert noise and
   abstention for unsupported sensors; have a technician review any
   candidate incident. Measure investigatory accuracy **only** where a
   confirmed maintenance/root-cause label exists. Do not mix unlabeled
   real data into synthetic known-answer accuracy metrics.
6. **Exit/revocation:** verify the shop can stop collection at once,
   disable the bridge credentials and obtain/deletion-request its data
   under the written agreement. Do not proceed beyond a read-only pilot
   without a new security and safety review.

**Rough build sizing, not a promise:** The collector, monitor and watchdog
exist, so collecting from one compatible Haas with local storage is a few
days of setup and testing once access is approved. The real-data provider
and mapping table add roughly a week after the probe is saved; the spool,
upload and hosted API add another 1–2 weeks. Then the actual 7- or 30-day
capture period. The specific machine's protocol support,
shop access/security approval, optional edge hardware and integration tests
can dominate the calendar. Budget hosting, outbound connectivity and a
shop-approved edge device separately. Building the full anomaly-monitor/
agent integration is additional scope; prove collection first.

#### Discovery questions for calls (2026-11-04 onward)

- Which Haas model/year and control generation (NGC or CHC) is available,
  and is there existing MTConnect/MDC or an approved export path?
- Who may approve a **read-only** pilot and coordinate IT/OT network access?
- Is there an approved on-site PC/network segment for a collector that
  sends **outbound-only** encrypted updates, or must data remain on-site?
- Which data can leave the site (mode/status, alarms, spindle RPM, load,
  cycle/part count)? Are any channels, job IDs or timestamps restricted?
- Would a short, approved connectivity check followed by **7 days** of
  collection be acceptable, with an optional 30-day extension?
- Can a technician confirm relevant events/maintenance outcomes so
  later agent assessments can be grounded rather than guessed?
- Can the shop share past alarm history and maintenance records for the
  machine, so a mostly normal week can still be compared with real events?
- Is any work on this machine export-controlled (for example ITAR) or under
  a customer confidentiality agreement that limits what data can leave?

**Agreement checklist (before any data leaves the machine):** a written
pilot agreement or NDA; who owns the raw data and anything derived from
it; retention and deletion; whether any export-controlled or confidential
customer work runs on the machine; liability and insurance for the
on-site PC; confirmation that connecting does not affect the machine's
warranty or service terms (ask the shop or its Haas Factory Outlet); and
how the shop stops the pilot.

**Short, accurate operator-facing explanation:**
> I'm building a manufacturing research assistant that investigates unusual
> machine behavior. I'm looking for one shop willing to try a limited,
> read-only data pilot on a Haas CNC: first confirm what the controller
> already exposes, then—if your team approves—record operational readings
> for about a week. We wouldn't change machine settings or interfere with
> production. Your team would approve the connection and what data can
> leave the facility, and you could stop the pilot at any time.

**Go/no-go before the first real packet:** Named shop owner/IT approval;
verified machine and read-only supported interface; agreed field list,
poll rate, retention and hosting; secure network design; edge/API
credentials and revocation; documented rollback/stop; and a shop-approved
low-impact connection test. If any is missing, use synthetic or explicitly
permitted recorded data instead.

### Future Work 2 — MCP architecture, observability, and response verification

<a id="fw-mcp"></a>

**Priority: MEDIUM, only after single-agent MVP.**

**Updated 2026-10-11. Planned; no MCP or tracing integration implemented.**

[FW2 gates](FUTURE_WORK_REEVALUATION.md#corrections-to-the-supplied-conditions):
extend the existing contract/provider barricade at each external boundary;
validated structure is not factual truth. Source completeness is scoped to
the requested data/window. PARTIAL cannot establish absence in missing scope,
and COMPLETE establishes absence only with an exhaustive source guarantee.
Source status, response verification and investigation confidence remain
distinct. Authenticate and authorize the first MCP client. Bound remote calls
under one investigation budget; a circuit breaker requires measured need.
Add aggregate metrics only for defined health questions, with bounded labels
and network latency measured separately from simulation time.

Start with the smallest useful MCP boundary after the core single-agent MVP
works. The "MVP MCP" plan below means the first minimal MCP integration,
not a prerequisite for finishing the simulator/agent MVP. Multiple agents
remain the later extension in Future Work 3.

#### Server count is an explicit, deferred decision

Do not commit to one server for the whole system, one server per agent, or
any fixed number of servers. Prefer capability boundaries. Multiple agents
may share a server with different authorization scopes; access to that
server does not grant every operation it offers.

Revisit the number and boundaries after the first MCP implementation and
actual workflows provide evidence. Consider permissions, trust, read versus
write access, data ownership, operational risk, deployment needs, independent
failure or scaling, and whether separation improves security or maintenance.
Do not split servers solely for presentation value.

#### Minimal MCP slice and existing architecture

Begin with read-only access to public machine state, sensor readings, alarms,
simulation time, observable state transitions, historical observations, and
authoritative source/event identifiers where available. Prove this path:

```text
Agent → MCP → authoritative simulator/data source → verified response
  → agent conclusion
```

Build on `FactoryProvider`, `SimulatorFactoryProvider`, `ToolRequest`, and
`ToolResult`. The existing adapter validates arguments and observable result
schemas, and includes source, simulation tick/time, and optional run and
investigation IDs. MCP should transport these permitted observations rather
than introduce another model of factory reality. The simulator still runs
locally without an LLM, MCP, database, or telemetry service.

The current provider also offers `wait` and `propose_action`; the first MCP
slice must expose an explicit read-only subset. Waiting changes simulation
time and is not a read operation. Human approval stays outside agent access.
"Authoritative machine state" means public observations, never hidden health,
programmed fault causes, scenario configuration, or evaluator ground truth.

<a id="fw-mcp-client"></a>

#### First MCP client: Pydantic AI — planned, not implemented

After the core single-agent MVP works, use Pydantic AI's MCP client support
for the first read-only integration. This avoids a custom MCP client wrapper
and reuses the observable provider boundary:

```text
Single research agent / Pydantic AI → MCP client capability
  → factory MCP server → FactoryProvider / ToolRequest / ToolResult
  → authoritative simulator/data source
```

The current documentation recommends the `MCP` capability for normal usage.
Use `MCPToolset` directly when shared clients, explicit lifecycle management,
or advanced transport settings require it. Prefer Streamable HTTP for remote
servers; consider stdio or in-process transport for local tests. SSE is a
compatibility option for existing systems, not a new-deployment default.
See [Pydantic AI MCP client](https://pydantic.dev/docs/ai/mcp/client/).

Reuse `SimulatorFactoryProvider` and existing observable Pydantic contracts;
do not invent a parallel factory schema. Before adoption, test discovery,
lifecycle cleanup, strict schemas, read-only allowlisting, denied waits/writes,
authorization, provenance, freshness, state consistency, and hidden-truth
isolation. Do not expose approval, scenario causes, or internal health fields.
Preserve the macro Pydantic Graph loop and the verification/observability
distinction below. No multi-agent framework is used (Future Work 3). No MCP
package, client wrapper, transport, or server is implemented now; consider a
custom wrapper only for a demonstrated unsupported requirement.

#### Candidate future capability boundaries

These are possible boundaries, not an agreed server list or count:

| Candidate boundary | Possible responsibilities | Permission posture |
|---|---|---|
| Factory / Telemetry | Public machine state, readings, alarms, observable transitions, simulator observations | Primarily read-oriented |
| Knowledge | Manuals, SOPs, PDFs, RAG retrieval, maintenance history, historical incidents | Primarily read/search-oriented |
| Operations | Create work orders, propose maintenance, acknowledge alarms, request changes, execute approved actions | Stricter state-changing permissions; separate propose, approve, and execute |
| External Integration | Snowflake, email, manufacturer systems, external APIs/databases | Add only when useful; scope to each source and operation |
| Administrative / Control | Simulator configuration, agent permissions, privileged controls, system configuration | Potentially isolated; unnecessary for the initial slice |

Some capabilities may share a server. Administrative access must not become
a path for investigation agents to retrieve hidden truth. Adding an external
integration does not authorize sending messages or changing external systems.

#### Least-privilege authorization

Map authorization as `Agent → MCP capability → allowed operation → required
scope`. Example future scopes are `factory:read`, `telemetry:read`,
`documents:read`, `knowledge:search`, `maintenance:propose`,
`operations:request`, and `operations:execute`.

Enforce authorization before executing each operation. Agents are not
inherently trusted. Shared-server agents can have different scopes; successful
connection is not blanket authorization. Approval must come from the human
approval boundary and cannot be granted by an agent to itself.

<a id="fw-observability"></a>

#### OpenTelemetry and LangSmith

The planned first MCP slice includes OpenTelemetry as the common
instrumentation layer and LangSmith as the developer-facing observability
and debugging interface. Propagate trace IDs and nested spans so a request
can be followed through:

```text
user request → orchestrator → agent → MCP request → MCP server
  → simulator/database/source → MCP response → verification
  → agent result → final response
```

The single-agent slice needs no multi-agent orchestrator framework. Correlate
traces with existing run/investigation IDs without treating those UUIDs as
OpenTelemetry trace IDs. Confirm supported SDK/exporter integration when
implementing this plan.

LangSmith supports inspecting agent execution, model/tool/MCP calls, latency,
failures, metadata, run comparisons, and development-time evaluation. It is
not the source of factory truth. Do not build a duplicate observability
platform. Keep secrets and evaluator-only truth out of agent-visible traces
and operator views; instrumentation must not alter simulator randomness or
simulation time. Preserve offline tests and optional telemetry integration.

<a id="fw-response-check"></a>

#### Small deterministic MCP-response verification layer

LangSmith answers **"What did the agents and tools do?"** A complementary
custom verification trace answers **"Should the system trust this MCP
result?"** A successful MCP call alone does not establish trustworthy data.

| Check | Question |
|---|---|
| Authorization | Was this agent permitted to perform this operation? |
| Schema | Does the response match the expected structured contract? |
| Source / provenance | Can important values be linked to authoritative simulator, database, or document records? |
| Freshness | Is the time-sensitive evidence recent enough for this decision? |
| State consistency | Where practical, does the response agree with the permitted authoritative source state? |

Use deterministic checks where possible. Another LLM must not be the sole
verifier of authoritative state. Verification reads only permitted source
observations; it must not reveal hidden truth or infer correctness merely
from the response's own source label. Historical readings can be valid
historical evidence even when unsuitable for a current-state decision.
Use simulation ticks/source time for simulator freshness, and define the
allowed age for each decision; do not compare simulation time with wall time.

Report `VERIFIED`, `FAILED`, or `PARTIAL / INSUFFICIENT EVIDENCE`. Record
individual check results, including checks that could not be performed.
Missing provenance, unavailable independent state checks, or undefined
freshness requirements must not silently pass. `VERIFIED` describes the
defined checks on this response, not proof of the agent's diagnosis.

Keep the custom record small: `trace_id`, `agent_id`, MCP server/capability,
operation, timestamp, source identifier, authorization result, schema result,
freshness result, source/state verification result, and overall status.
Reuse run/investigation correlation IDs when useful. Do not add advanced
analytics, search, replay, or a custom observability backend without a
demonstrated need.

#### Optional operator-facing live trace

If inexpensive, show a small panel such as:

```text
Diagnostic Agent → requested public machine state
Factory MCP → returned public machine state
Verification → authorization: pass; schema: pass; freshness: pass;
               source: pass; state consistency: pass
Result: VERIFIED
```

Show failures and insufficient evidence just as clearly. Keep this view
understandable to an instructor, operator, or evaluator; LangSmith remains
the detailed engineering interface.

#### Implementation sequence

1. Expose the minimum useful read-only factory/simulator MCP boundary.
2. Add OpenTelemetry propagation across agent → MCP → source.
3. Connect instrumentation to LangSmith for developer observability.
4. Add deterministic response verification with explicit limits.
5. Record the minimal custom verification trace.
6. If inexpensive, show those events in the small live trace panel.
7. After the MCP slice is stable, revisit server boundaries using real
   workflows. Split only where concrete benefits outweigh complexity.

#### Readiness checklist usable now

Before starting implementation, review these existing foundations:

- Reuse `capstone/contracts/tools.py` for requests, result envelopes, source
  clocks, and run/investigation context. These contracts provide schema
  validation; they do not yet implement per-agent authorization, independent
  provenance verification, or freshness policies.
- Review `capstone/providers/factory.py` and select the read-only operations
  explicitly. Preserve the exclusion of approval and hidden-ground-truth
  calls, and test that writes and waits are denied before dispatch.
- Reuse existing public observation contracts and sensor summaries; add
  source/event identifiers only where their semantics can be backed by real
  records. The current source label alone is not record-level provenance.
- Keep `capstone/observability.py` metadata logging distinct from distributed
  tracing and response verification. It is a starting point for correlation,
  not an implemented OpenTelemetry/LangSmith integration.
- Plan offline tests for denied calls, malformed responses, stale evidence,
  missing provenance, source mismatches, partial checks, trace correlation,
  and hidden-truth isolation before claiming the MCP slice is verified.

#### Decision criteria for a later server split

Evaluate each proposed separation explicitly:

1. Does the capability require different permissions?
2. Does it have a different security risk or trust boundary?
3. Is it read-only or state-changing?
4. Does it rely on a different authoritative data source or owner?
5. Should it be deployed independently?
6. Should failures be isolated?
7. Would separate scaling be useful?
8. Would combining capabilities create overly broad agent access?
9. Would another server materially simplify auditing?
10. Does the split add more value than complexity?

The previous roadmap's prescribed Telemetry, Maintenance, Quality,
Production, and Documentation servers is superseded by this decision process.
Future Work 3's model-assisted evidence review remains useful for claims and
retrieval, but does not replace deterministic MCP-response checks or human
approval. Post-intervention verification and evaluator-only ground truth
remain separate responsibilities.

### Developer follow-up: Subquadratic whole-repository audit

<a id="fw-subq"></a>

**Priority: MEDIUM, after core reasoning and memory integration.**

After integrating the Agent 1 reasoning workstream and Agent 2 memory workstream,
have Subquadratic (SubQ) audit the entire project before making broad refactors.
This is a developer audit task, not a new runtime dependency or research-agent
role. Its purpose is to find issues whose evidence is scattered across code,
tests, schemas, persistence, agent state, and architecture documents.

Give the reviewer a reproducible repository snapshot: branch, commit, working
directory changes, project instructions, MVP scope, progress log, source, tests,
schemas, migrations, and relevant sanitized logs. Exclude credentials, local
environment files, dependency directories, Git internals, and generated caches.
Record any files omitted or unread; do not claim whole-repository coverage when
parts were not inspected. Distinguish implemented paths from planned or absent
API, orchestration, evaluation, and persistence components.

**Architecture consistency prompt:**

> Read the entire repository, including the API layer where implemented, agent
> orchestration, tests, schemas, migrations, persistence code, and architecture
> documents. Trace a task from user input through the agent loop, tool boundary,
> human approval, post-intervention verification, reflection, memory promotion,
> and database storage/retrieval. Identify inconsistencies, dead code, duplicated
> logic, incompatible contracts, and differences between implementation and
> architecture. State explicitly where a path does not exist yet. Give file and
> line evidence, impact, and suggested validation before changing anything.

**Authorization and hidden-truth prompt:**

> Read the repository and all tests. Find every place authorization is enforced.
> Trace all action entry points and determine whether an agent can mutate the
> environment or persistent state without the intended authorization boundary.
> Check human approval, proposal versus execution, verification, tool/provider
> allowlists, evaluator-only ground truth, and promotion/retrieval provenance.
> Distinguish intended permissions from bypasses. Give evidence by file and line,
> reachable call paths, and tests that prove or fail to cover each finding before
> changing anything. Do not expose credentials or private evaluator answers in
> agent-visible artifacts.

Require an audit report with inspected snapshot and coverage, severity-ranked
findings, concrete cross-file evidence, reproduction or regression-test proposals,
and unresolved questions. Review findings before authorizing fixes. Evaluate
whether SubQ finds additional supported issues compared with a Codex/Claude review
of the same snapshot, rather than assuming a larger context guarantees accuracy.

The intended division is Codex/Claude for routine implementation, debugging,
tests, and focused refactors; trial SubQ for whole-repository analysis, cross-system
debugging, architectural consistency, and proposals for larger refactors using
code, specs, and sanitized logs together. Subquadratic describes long-context
software engineering and reasoning across distributed evidence in its
[SSA article](https://subq.ai/how-ssa-makes-long-context-practical).
Its [introduction](https://subq.ai/introducing-subq) reports an 81.8% SWE-Bench
Verified result; that is a published benchmark claim, not a guarantee about this
repository or an audit performed here.

At audit time, check model availability and account access. The official
[model documentation](https://docs.subq.ai/using-the-api/models/) currently lists
`subq-preview` for long-context chat with files and function calling, in early
access. It separately lists `subq-snap-preview` for fast structured decisions;
Snap is not the model selected for this repository audit. Recheck capabilities
before running the audit. No SubQ dependency, credentials, integration, external
repository upload, or model invocation is added by this roadmap entry.

### Future Work 6 — Developer Efficiency / Project Tooling

<a id="fw-tooling"></a>

**Priority: LOW / conditional.**

[FW6 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
existing uv/Ruff/hooks/CI/coverage are IMPLEMENTED. Extend architectural invariant
tests with each actual boundary; do not write tests for imaginary capabilities.
Assemble a scripted vertical acceptance test as the agent loop grows. Compare
ty with targeted mypy on real diagnostics when static checking prevents concrete
mistakes; choose one primary checker. Current code can justify a pilot without
waiting for a large agent. Hypothesis and xdist retain their existing conditional
gates below. Coverage remains diagnostic; critical branch checks require useful
behavioral blind spots rather than a whole-project percentage target.

Built: `uv`, Ruff (including import sorting), Pydantic Settings, pre-commit,
GitHub Actions with uv caching, and informational pytest-cov. The rest are
planned or candidates. These improvements support development and
infrastructure; they are not MVP requirements or part of the research agent's
reasoning architecture. Add them in focused changes when their benefit justifies
the work, rather than as one large tooling migration.

| Improvement | Benefit for this capstone | Suggested timing / adoption condition |
|---|---|---|
| [uv audit](https://docs.astral.sh/uv/reference/cli/#uv-audit) | Check locked dependencies for known vulnerabilities and surface findings for review. | Add alongside CI. Use `uv audit --locked`, define how findings are handled, and review dependency changes rather than automatically upgrading packages. |
| [ty](https://docs.astral.sh/ty/) | Check Pydantic contracts, Protocols, provider interfaces, and future graph/handoff/persistence types. | Candidate, not implemented. Reevaluate once interfaces and a reviewed diagnostic baseline are stable; see adoption conditions below. No required CI gate. |
| [Dependabot for uv](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories) | Propose dependency updates for review, including changes to `uv.lock`. | After CI can validate update PRs. Review existing migration constraints when intentionally upgrading simulator dependencies; require passing tests before merging. |
| [pytest-xdist](https://pytest-xdist.readthedocs.io/en/latest/distribution.html) | Shorter test runs by distributing independent tests across workers. | Candidate, not implemented. Reevaluate when measured suite duration is materially slow; require isolation and repeatable speedup before enabling `pytest -n auto`. |
| [Hypothesis](https://hypothesis.readthedocs.io/en/latest/stateful.html) | Find combinations at deterministic state/contract boundaries that examples miss. | Candidate, not implemented. Reevaluate when a specific invariant or sequence would otherwise need many hand-written cases. |

Items still marked planned remain roadmap entries; adopting them requires a
separate implementation task.

#### Conditional test hardening — planned, not implemented

Hypothesis would reuse pytest and seeded simulator/provider fixtures. Start
with a concrete property: same seed and operations reproduce observations;
ticks never go backward; invalid requests/ranges do not mutate state; public
schemas and results exclude hidden truth; approval cannot be bypassed;
sensor summaries honor inclusive windows; reads consume no RNG draws and do
not alter later results. Generated valid reads should not crash the boundary.
Only introduce `RuleBasedStateMachine` after invariants for observe/wait/propose/
human-approve sequences are clear. Test replay of minimized failing examples
and keep human approval outside agent inputs. This supplements fixed-seed
regressions and ordinary examples; it must not generate new fault models,
leak evaluator truth, or create a separate state-machine project.

pytest-xdist would reuse the suite and coverage setup. Before adopting, measure
serial runtime, inspect global mutable state, isolate RNG instances, temporary
paths and database fixtures, and remove fixed-port assumptions. Run repeated
`pytest -n auto` trials, verify seeded results and coverage remain consistent,
and compare elapsed time with serial pytest. Keep it only for a meaningful
measured gain; do not make parallelism default merely because test count grows.
No Hypothesis or xdist dependency is added in this task.

#### ty adoption — candidate, not implemented

Reevaluate when contracts, `FactoryProvider`/`LLMProvider` Protocols, graph state,
handoffs, and persistence interfaces are stable enough for a reviewed baseline.
An isolated `uvx ty check` assessment can inform this decision without changing
project dependencies. See [ty installation](https://docs.astral.sh/ty/installation/)
and [type checking](https://docs.astral.sh/ty/type-checking/).

ty defaults to the lower bound of `requires-python`; confirm Python 3.11
analysis explicitly with `--python-version 3.11` during the assessment. See
[ty Python version](https://docs.astral.sh/ty/python-version/).
Before adoption, check optional-package environments,
Pydantic patterns, and Protocol conformance; distinguish real errors from
intentional invalid-input tests or unsupported analysis patterns. Add ty as a
development dependency only after agreeing a baseline and narrow exceptions,
then use `uv run ty check`; consider a CI gate only after it is stable. Do not
add blanket ignores, experimental annotations, broad unrelated typing fixes,
or competing type checkers. ty must not replace pytest or runtime validation.
The current task does not add ty to project dependencies or CI.

**Informational baseline, 2026-10-11:** `uvx ty check --python-version 3.11
--output-format concise` with ty 0.0.86 and database-extra dependencies found
67 diagnostics (exit 1): three core optional-value narrowing findings in job
event recording/inspection lookup, and 64 test findings including intentional
invalid arguments/read-only assignments, optional values, and generic result
typing. These warrant a scoped baseline review, not an immediate blocking
gate. No unsupported Pydantic pattern was established by this assessment;
no fixes or ignores were added. The baseline has seven diagnostic types:
19 invalid-argument-type, 27 unresolved-attribute, 15 not-subscriptable,
three invalid-assignment, and one each call-non-callable, invalid-return-type,
and unknown-argument.


## Future work: Planning and automation

<a id="future-work-planning-and-automation"></a>

<a id="fw-experiments"></a>

**Future Work 4 — planning and experimentation.** Controlled experiments:
*"Reduce Machine 2 feed rate by 5% for the next ten units and compare
defect rates."*

[FW4 gates](FUTURE_WORK_REEVALUATION.md#corrections-to-the-supplied-conditions):
reuse basic proposal checks and define the smallest legal action transitions
with the next action/graph integration. Recheck mutable safety conditions at
execution; preflight is not approval or a hidden-cause prediction. Before any
retryable/concurrent/restartable mutation boundary, including state-changing
simulator MCP tools, require scoped action identity and payload/approval binding.
Test duplicate delivery, conflicts, concurrency and uncertain outcomes.
Database deduplication alone does not guarantee a single remote physical effect.
Separate execution success from observable verification of effectiveness;
the graph cannot report resolved success without post-intervention verification.

<a id="fw-proactive"></a>

**Future Work 5 — proactive autonomy.** The system no longer waits for a
human question:

```
Factory state → continuous monitoring → anomaly discovered
  → investigation created automatically → research → recommendation
  → approval → intervention → verification
```

**Related investigation scope:** [Incident-first line-wide investigation](#fw-line-scope) is the first, database-free workflow test. [Simulated telemetry ingestion and replay](#fw-telemetry-replay) follows with a shared live/history evidence store and deterministic line-wide monitor. FW5 is the later durable incident scheduling/dispatch lifecycle; an alarm must not restrict investigation to the machine that raised it, and no LLM needs to poll every reading.

[FW5 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
concurrency control requires an actual overlapping-work race, even within one
process. Durable scheduling requires a workload that must survive restart.
Use an outbox only for a demonstrated durable-state/dispatch dual-write gap:
persist intent atomically, dispatch afterward, and handle duplicate delivery.
An async dead-letter queue requires an actual retry pipeline. Compare a simple
DB worker or existing framework before selecting a broker/job framework.
Redriving consequential work must recheck approval, safety and idempotency.


<a id="fw-sm-servo-diagnostics"></a>

**Controller servo diagnostic moves (LOW; SM-12 in the [single-machine track](#fw-sm-track); proposed 2026-11-07).** Machine builders diagnose feed-axis bearings, ball screws and linear guides without added sensors by running the axis through a set diagnostic motion and frequency-analysing the servo data ([US10760994](https://patents.google.com/patent/US10760994); [US10585416](https://patentimages.storage.googleapis.com/bd/9f/dd/c9ea54ab547f24/US10585416.pdf)). This could separate parts that [SM-11](#fw-sm-check-ranking) can only rank. It needs high-rate servo data the read-only interface may not expose, and it moves the machine, so it is a consequential action: shop and technician approval, the FW4 gates above and a new safety review are required. Out of scope for a read-only pilot.

<a id="future-work-scenarios-and-a-frontend"></a>

## Future work: Frontend and operator experience

<a id="future-work-frontend"></a>

<a id="fw-frontend-stack"></a>

**Frontend stack (developer's decision, 2026-11-02).** The frontend is a
React app, and the backend it talks to is a FastAPI service in front of the
existing `capstone` package. Do not build it with Gradio or Streamlit. FastAPI
exposes read-only endpoints that return the existing Pydantic contracts
(`CompletedInvestigation`, audit records, progress-watcher snapshots), plus the
approval and settings actions, validated by the same backend rules as today.
It never exposes the simulator's ground truth or any API key. Live progress
reaches the page through the watcher queue described under "Frontend note"
below (for example over a WebSocket or server-sent events), never by blocking
the run. Neither FastAPI nor React is a dependency yet; each is added in the
PR that first uses it.

### Easy / intermediate / hard modes, with a frontend button

<a id="fw-frontend"></a>

**Priority: LOW; deferred until a scored live baseline.**

The developer wants three difficulty modes with 1 / 4 / 8 problems to fix,
and a button on a frontend to pick one. **Deferred by the developer's
decision of 2026-10-20:** no scenario-difficulty work starts until the first
live model-backed agent run has been compared with the rule-based baseline
(R4c, about 96% of causes right). The live result decides whether harder cases
are needed at all, and how hard. Candidate ingredients recorded then: a glitch
during a real load change, lasting sensor drift, recurring glitches, and
composed faults (the compound challenge above). A mode is a seeded scenario
recipe, so runs stay reproducible; the frontend only chooses the recipe and
never shows the agent the hidden causes. There is no frontend yet; the live
progress view discussed on 2026-10-19 would be its first screen.

**Frontend settings note (developer, 2026-10-27).** If a frontend is built,
expose the user-adjustable settings currently configured through `.env` as
frontend controls, including `STEP_QUESTIONS` (one or two model questions
per step) and `STATE_ACTION_BAR` (show or hide the action threshold in the
prompt), and the critic and manual settings (`CRITIC`, `CRITIC_MODEL`, `CRITIC_SECONDS`,
`CRITIC_FOLLOWUP`, `MANUAL_STEP`; see `docs/superpowers/specs/2026-10-28-critic-review-only-design.md`). Keep the same backend validation and enforcement; hiding the
threshold does not disable it. API keys and other secrets stay in backend
configuration and must not be sent to the frontend. This is a future
requirement, conditional on building a frontend; no settings UI is built yet.

### Frontend buttons

<a id="fw-frontend-buttons"></a>

The controls a frontend should offer when one is built (list of 2026-10-31).
Each is a setting in `capstone-code/capstone/settings.py` (read from `.env`)
or an option of the experiment command. The frontend only picks values; the
backend keeps validating and enforcing them. Nothing here is built yet.

| Button | Setting | Default | What it does |
|---|---|---|---|
| Difficulty mode | (planned, see above) | — | Easy / intermediate / hard: 1, 4 or 8 problems |
| Critic | `CRITIC` | off | A second model reviews the agent's leading explanation |
| Blind critic | `CRITIC_BLIND` | off | The critic sees the hypotheses shuffled, under neutral labels, with no confidence or leader; code sets its verdict from its pick |
| Critic follow-up | `CRITIC_FOLLOWUP` | off | After an objection, or agreement below the action bar, the agent makes one more reading |
| Critic model | `CRITIC_MODEL`, `CRITIC_FALLBACK_MODEL` | — | The critic's model and its backup |
| Critic time | `CRITIC_SECONDS`, `CRITIC_FOLLOWUP_SECONDS` | 40 s, 90 s | Time allowed for the review and the follow-up |
| Manual step | `MANUAL_STEP` | on | Search the maintenance manual before planning |
| Questions per step | `STEP_QUESTIONS` | 1 | One or two model questions per tool result |
| Show the action bar | `STATE_ACTION_BAR` | on | Show or hide the action threshold in the prompt (it is enforced either way) |
| Action bar | `MIN_ACTION_CONFIDENCE` | 0.9 | Confidence needed before an action is allowed |
| Memory recall | `MEMORY_RETRIEVAL_MODE` | semantic | semantic, keyword or none |
| Agent models | `DEFAULT_MODEL`, `FALLBACK_MODEL`, per-stage `*_MODEL` | — | Which in-scope model each stage uses |
| Sampling | `PROVIDER_SAMPLING`, `MODEL_SAMPLING` | — | Temperature and similar settings per provider or model |
| Model limits | `MODEL_REQUEST_SECONDS`, `MODEL_QUESTION_SECONDS`, `MODEL_RETRIES`, `MODEL_MAX_OUTPUT_TOKENS` | 45 s, 90 s, 3, 16384 | Timeouts, retries and output length |
| Tree of thought | `--tree-of-thought` | off | Rate several candidate explanations before choosing |
| Manual search | `--manual`, `--no-manual` | semantic | Search the manual by meaning or by keyword, or give no manual |
| Tool hazards | `--hazards` | off | `standard` (timeouts, dropped rows, a stale record) or `blackout` (the alarmed machine's sensor feed is down) |
| Cases and seeds | `--known`, `--seeds` | — | Which known cases and seeds an experiment runs |

Model choices are limited to the providers in AGENTS.md §9. API keys
(`*_API_KEY`, `CLOUDFLARE_*`), `DATABASE_URL` and other secrets are never
frontend controls: they stay in backend configuration and are never sent to
the frontend.

**Frontend note: the watcher runs in the run's own thread (developer's
note, 2026-10-26).** The live progress view (LV, `python -m
capstone.progress`) reads the run through `InvestigationDeps.watch`, which
`notify` in `agent/loop.py` calls in the same thread as the investigation.
A watcher that raises is caught, but a watcher that hangs (say, a slow
network write in a future frontend) holds up the run. Fine for a terminal;
a frontend should hand the work off to another thread instead of doing it
in the watcher: the watcher only puts the state copy on a queue and returns
at once, and a separate thread or process sends it to the page.

**2026-10-26 (developer):** the mode switch still waits for the scored
single-agent run against the rule baseline. Meanwhile, new faults (servo/axis,
optional hydraulics; Future Work 8 D) are built as fault-pack registry entries
(below), each tagged with the difficulty it belongs to, so the modes become a
small filter over the registry when they are built.

### Operator investigation screen (human–AI interaction guidance)

<a id="fw-frontend-operator-screen"></a>

**Priority: LOW; recorded 2026-11-02, not built.** What the first operator
screen should show once a frontend exists, taken from two readings on
designing for people who act on AI output:
[Amershi et al., "Guidelines for Human-AI Interaction" (CHI 2019)](https://www.microsoft.com/en-us/research/wp-content/uploads/2019/01/Guidelines-for-Human-AI-Interaction-camera-ready.pdf)
(mainly G2 "make clear how well the system can do what it can do", G9
efficient correction, G10 scope services when in doubt, G11 make clear why)
and [Google PAIR, "Errors and Graceful Failure"](https://pair.withgoogle.com/chapter/errors-failing/)
(say specifically what the system could not do; hand control back with
context; collect feedback on errors). Neither paper has shaped a code change
yet, so neither is in README "Research basis".

The screen is a read-only view of `CompletedInvestigation`
(`capstone-code/capstone/contracts/completed_investigations.py`) and the run's
audit records. It never reads the simulator or ground truth, so it sees only
what the agent saw.

| Panel | What it shows | Source today | Gap |
|---|---|---|---|
| Incident header | Machine, alarm summary, symptoms, sim time | `Anomaly`, `VerificationResult.observed_tick` | — |
| Diagnosis | Leading explanation and up to four alternatives, each with its claim | `hypotheses`, `conclusion.diagnosis` | — |
| Evidence | Supporting, contradicting and unexplained evidence for each hypothesis, linked to the reading it came from | `supporting_/contradicting_/unexplained_evidence_ids`, `evidence` | — |
| What would settle it | The next check that tells the hypotheses apart | `Hypothesis.discriminating_check` | — |
| How sure | Model confidence, shown as the model's own rating, not as a probability; next to it, whether the evidence substantiates the diagnosis | `confidence` | No evidence-assessment field yet (backend item 1 below) |
| Why it stopped | Plain reason when the agent escalated or abstained: too little evidence, conflicting evidence, stale or missing readings, model or provider failure | `termination_reason` (free text) | Reasons are not a fixed set yet (backend item 2) |
| Critic | Whether the critic agreed, and whether its follow-up reading changed the leader | critic records | Not in the handoff contract yet |
| Proposed action | Action, machine, reason, evidence; the action bar it had to clear; clearly marked "not executed" until approved | `ActionProposal`, `MIN_ACTION_CONFIDENCE` | — |
| Approve / reject | Approve, or reject with a reason chosen from a short list plus free text | approval desk | Reasons are free text and never read back (backend item 4) |
| Verification | Expected versus observed after the action; "unverified" and "unknown" shown as such, not hidden | `VerificationResult` | Expected outcome not recorded yet (backend item 5) |
| Full trace | Every tool call and model step, behind a "details" link, not on the main screen | audit records | — |

Rules for the screen:

- Lead with the problem, the likely cause, its evidence and the next step.
  Keep agent traces and reasoning steps behind the details view.
- Never show model confidence as "90% likely". It is the model's own rating
  and is not calibrated.
- When the agent could not finish, say specifically what was missing (which
  machine, which sensor, which time window) and give the operator the next
  manual check, not a generic error.
- An escalation is a normal outcome, not a failure screen: it hands the case
  to a person with everything the agent found.
- Approval stays a backend decision under the same rules; the screen only
  collects the operator's choice. Rejection reasons are stored as operator
  feedback, never as evidence or ground truth.
- Updates arrive through the progress-watcher queue described above, never
  by blocking the run.

**Backend changes this screen depends on** (each a small additive change to
existing contracts, each its own PR and gate; none started):

1. An evidence assessment next to confidence (substantiated, incomplete,
   contradicted), set by rules in code from the evidence ids and numeric-claim
   checks, not by the model.
2. A fixed set of stop and escalation reasons (insufficient evidence,
   contradicting evidence, stale or missing telemetry, provider failure,
   budget exhausted), kept beside the existing free-text `termination_reason`.
3. Critic outcome in the handoff: agreed or objected, and whether the
   follow-up reading changed the leading hypothesis.
4. Structured rejection reasons at the approval desk, read back into memory
   as operator feedback.
5. The expected observation for a proposed action, so verification can show
   expected versus observed.

**Later, separate from correctness scoring:** a small usability check with
people who know manufacturing: same investigation shown as a plain report and
as this screen; measure whether they find the conclusion and its evidence,
tell a supported conclusion from a speculative one, and avoid approving an
unsupported action. This does not replace improving diagnostic accuracy.


<a id="future-work-far-future"></a>

## Future work: Long-term portability and optional interfaces

<a id="future-work-long-term"></a>

### Far-future portability candidates

<a id="fw-portability"></a>

**Priority: LONG TERM / conditional.**

Far-future portability candidates have separate
[register gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
schema-defined equipment requires a second genuinely different environment and
repetitive capability code; YAML requires an actual profile-authoring need.
Multi-tenant isolation/RLS requires mutually untrusted owners sharing persistent
infrastructure. None is a course MVP requirement. ADRs may document settled,
costly-to-reverse decisions without turning candidates into accepted designs.

### Added high-resolution vibration or acoustic sensing (FAR FUTURE; SM-13; proposed 2026-11-07)

<a id="fw-sm-hires-sensing"></a>

**Priority: FAR FUTURE. Rank: SM-13 in the [single-machine track](#fw-sm-track).** Precise spindle fault localization usually needs dedicated measurement, not aggregate controller signals: NIST's defect-driven method separates spindle dynamics from defect geometry with its own condition-estimation device ([Vogl and Donmez, 2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC5217751)). Adding accelerometers or microphones is a separate capability that needs written shop approval for new hardware, its own data contract and its own evaluation. Consider it only after [SM-11](#fw-sm-check-ranking) shows which parts controller data cannot separate.

### Future Work 9 — sensor-triggered, on-demand machine vision (near-last priority)

<a id="fw-vision"></a>

**Priority: FAR FUTURE (near-last).**

**Status: far-future only; not implemented. Recorded 2026-10-21 at the
developer's request. This is a near-last roadmap item, to be considered only
after the other planned Future Work and live factory integration prerequisites;
Future Work 10 is even lower priority.
Do not move it into MVP scope or the ranked next-build candidates.** The
feature is optional and requires an actual factory's approval and a measured
need; recording it is not approval to build or install anything.

**Concept:** Keep the vision model OFF during routine monitoring. A low-cost,
deterministic monitor checks approved live machine telemetry (for example,
vibration and temperature) against machine-specific thresholds, sustained
changes, or operating-mode-aware trends. A meaningful trigger starts the
existing Manufacturing Research Assistant investigation. The agent decides
whether visual evidence could help distinguish its hypotheses and, if so,
calls a bounded read-only `inspect_machine_vision` tool. It does not wake
vision for every sensor sample or run continuous VLM inference.

**Proposed eventual path:**

1. Receive sensor observations through a read-only real-factory provider
   (e.g., OPC UA / MQTT); preserve timestamps, units, machine identity,
   operating mode, provenance, gaps, and uncertainty.
2. Filter noise with documented thresholds, duration/hysteresis and
   deduplication; trigger a bounded investigation, not an equipment action.
3. If visual inspection is warranted, obtain authorized frames or a short
   before/after-event clip from an existing camera/NVR (e.g., RTSP/ONVIF).
   Existing recording may be continuous, but the *vision model* remains off
   until requested.
4. Run a general-purpose vision-language model on demand first; return
   structured *observations* with frame references, model version, time,
   visibility limits, and an explicit "nothing visible"/"uncertain" outcome.
   Do not treat speculation or model confidence as proof of a machine fault.
5. Correlate visual observations with current sensor evidence, equipment
   specifications, approved manuals, and maintenance history through the
   existing investigation loop. Maintain competing hypotheses; keep
   recommendations and actions subject to the established human approval
   and verification boundaries.
6. Evaluate on held-out, authorized labeled cases before considering
   machine-specific visual anomaly detection or a fine-tuned detector.
   Machine specifications inform operating limits and diagnoses; manuals
   alone do not train visual recognition.

**Prerequisites and non-goals:** This is a read-only diagnostic aid, not
safety monitoring, an emergency-stop mechanism, or autonomous industrial
control. Factory operations/IT must approve camera and telemetry access,
network isolation, security, retention, and handling of workers' images
and proprietary data. Prefer local processing with minimal data leaving
the site. Course artifacts must use public, synthetic, or appropriately
authorized/anonymized evidence; access permission alone is not permission
to publish or send material to an external model provider. No camera
integration, training dataset, vision dependency, new agent, or GPU
infrastructure is part of the current implementation.

**Adoption/acceptance gate:** Compare the sensor-only baseline with
sensor-plus-on-demand-vision on labeled cases. Measure diagnosis quality,
false alarms, missed relevant events, investigation latency, per-event
compute/cost, and whether visual evidence actually changes a supported
conclusion. Test camera offline/unavailable, obscured view, misleading
imagery, clock mismatch, duplicate triggers, and no-visible-defect cases.
Ensure sensor-only investigation still works without the camera and no
vision result can bypass approval or the evaluator-only ground-truth
boundary.

### Future Work 10 — optional technician voice input (absolute last priority)

<a id="fw-voice"></a>

**Priority: FAR FUTURE (absolute last).**

**Status: far-future only; not implemented. Recorded 2026-10-21 at the
developer's request. This is the absolute last roadmap item, after all
other Future Work, including the optional machine-vision feature.** Do not
start it during the MVP or add it to the ranked next-build candidates.
It is a speculative convenience feature, not a current requirement.

**Concept:** If a future real-factory investigation needs information that
sensors and records cannot provide, an authorized technician could optionally
speak a short report or answer focused follow-up questions. Examples include
unusual sounds, visible wear, recent maintenance, operating conditions, or
error codes. A voice interface would transcribe the technician's words and
let them review or correct the transcript before submitting it to the
existing investigation agent.

**Boundary:** Treat technician statements as human-reported evidence with a
source and time, not as verified machine facts. The investigation agent must
correlate them with telemetry, manuals, and maintenance records, retain
uncertainty, and preserve existing human approval and post-action
verification. There is no always-on microphone, autonomous machine control,
or reason to create a separate diagnostic authority for the voice agent.
Text entry remains a supported alternative.

**Prerequisites and adoption gate:** Consider this only if work with actual
technicians demonstrates a meaningful advantage over a simple typed form.
Obtain factory and participant consent and approval before capturing audio;
define retention, access, transcription review, redaction, and external-model
data handling. Evaluate transcription accuracy with shop-floor noise and
equipment terminology, time saved, completeness of useful observations,
and whether the voice input improves supported diagnoses. If it does not
show measurable value, leave it unbuilt. No audio integration, Voxtral
dependency, voice-agent service, microphone access, or new training data is
approved by this roadmap entry.

