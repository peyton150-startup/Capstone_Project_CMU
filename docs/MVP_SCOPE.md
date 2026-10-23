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

The planned macro investigation loop uses Pydantic Graph. CrewAI remains the
later specialist-agent orchestration layer in Future Work 3; CrewAI Flow must
not replace this macro loop. Neither framework is implemented or installed.

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
- specialized researcher / critic / planner agents
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

#### Agent-directed RAG and repeat retrieval (2026-10-18)

For capstone memory retrieval, the existing investigation agent owns both
reasoning and retrieval decisions using the selected Nemotron 3.5 Lightning
30B model. Do not introduce another reasoning LLM or a dedicated RAG agent.
This direction supersedes earlier suggestions in this document to assign memory
retrieval reasoning to a separate Evidence agent. Other proposed specialist
roles remain separate roadmap discussions.

The intended flow is:

```text
Investigation agent (Nemotron)
  -> identifies a knowledge gap and chooses a search
  -> memory retrieval tool (potentially exposed through the planned MCP server)
  -> PostgreSQL memory store
  -> evidence returned to the same agent
  -> agent assesses usefulness and coverage
     -> sufficient: continue the investigation using cited evidence
     -> insufficient: revise the search and retrieve again within budget
     -> exhausted: report the gap and continue with available observations
```

Python/SQL performs database retrieval. PostgreSQL with pgvector and a small
embedding model is the proposed semantic-search extension; a separate reasoning
model is unnecessary. Reranking is optional. Neither embeddings nor pgvector
is implemented by this requirement.

**Repeat-search behavior:** after each retrieval, the agent checks whether the
results address the question, provide relevant supporting evidence, and leave
important contradictions or gaps. The agent must also be able to reopen a
search if a draft answer reveals unsupported claims. A high similarity score
or the agent's confidence alone does not establish that an answer is supported.
Empty, irrelevant, incomplete, or contradictory results may trigger another
search using revised wording, different symptoms, broader/narrower filters, or
an alternative hypothesis. Search should seek evidence that could refute the
current hypothesis as well as evidence that supports it. Record the reason for
searching again and what changed; repeating an identical query against an
unchanged store is not progress.

Implementation default: at most three retrieval calls per knowledge gap,
including the initial search, also subject to the investigation's overall tool
and iteration limits. This is a bounded default, not a developer-validated
optimal setting. If the budget is exhausted or searches stop adding relevant
evidence, state what remains unknown, qualify the answer, and use other allowed
observation tools when useful. Do not keep searching until a preferred answer
appears. Historical lessons inform hypotheses; current observations and mandatory
post-intervention verification still determine whether an intervention worked.
Human approval and the hidden-ground-truth boundary remain in force.

Acceptance checks for runtime integration: an empty or irrelevant first result
can lead to a revised second search whose evidence reaches the answer; a useful
first result can end retrieval immediately; contradictory evidence can cause
hypothesis revision; insufficient evidence at the call limit produces an explicit
uncertain result without another retrieval; no second reasoning model or hidden
truth is used. Use a scripted model and local store for deterministic offline
tests. Record query attempts, returned source/memory IDs, the agent's usefulness
assessment, and the stopping reason for evaluation.

Status: future work, outside the current MVP; not implemented. This checkout currently implements filtered lookup through
`MemoryService.retrieve()` and `SQLMemoryRepository.retrieve()` using
`MemoryQuery` (investigation ID, category, limit). It has no connected agent
retrieval loop, free-text/semantic search, embedding adapter, or MCP memory tool.
Runtime integration must reconcile the completion contracts described in
`EPISODIC_MEMORY.md` and respect the reinstated memory teaching checkpoints
recorded in `PROGRESS.md`.

#### Maximal Marginal Relevance (MMR) for episodic recall — candidate (2026-10-23)

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

#### Near-duplicate memory check (planned 2026-10-22)

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

### Future Work 2 — MCP architecture, observability, and response verification

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
distinction below. CrewAI is not required for this first client. No MCP
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

### Future Work 3 — multi-agent research

[FW3 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
specialist role scopes extend server-side authorization already required at
the first MCP boundary. Reuse the same permitted capabilities and contracts.
An execution service may execute only an exact human-approved request;
an agent cannot grant itself approval or arbitrary execution authority.

This planned extension follows the single-agent MVP. The provider assignments
below are initial targets; exact models and API availability will be confirmed
when this extension is implemented.

#### Later CrewAI MCP client — planned, not implemented

When CrewAI specialist orchestration begins, use its documented `mcps` support
for discovery, structured server configuration, and tool filtering. Reuse the
same server/capability and `FactoryProvider` contracts as the earlier
Pydantic AI client; changing clients does not justify rebuilding the server.
See [CrewAI MCP](https://docs.crewai.com/en/mcp/overview).

```text
CrewAI specialist agent → mcps integration → existing MCP capability/server
  → same authoritative data boundary
```

Client filters reduce exposed tools; server-side authorization remains
authoritative. Assign each role the necessary scopes. Test filtered discovery,
denied direct calls, per-agent credentials/scopes, cross-client result parity,
trace correlation, hidden-truth isolation, and human approval before adoption.
Keep deterministic verification in Future Work 2, Pydantic Graph's macro loop,
and the existing CrewAI/LiteLLM plan below. Split servers only when real trust,
permission, or deployment needs justify it. No CrewAI/MCP code or dependencies
are added now.

#### Multi-Agent Handoff Protocol

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

#### Structured Inter-Agent Communication

CrewAI will coordinate when each handoff occurs, while Pydantic schemas will define the information transferred between agents.

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

#### Provider integration — CrewAI/LiteLLM behind one project boundary

**Revised 2026-10-11. Planned; no framework dependencies or live adapters added.**
Use CrewAI's `LLM` abstraction and LiteLLM as the default integration layer
for the six-provider extension. Do not preemptively build six HTTP clients,
authentication implementations, response parsers, or exception hierarchies.
A provider/model-specific adapter is justified only by a demonstrated missing
capability that configuration or the supported framework cannot address.

CrewAI documents native Google Gemini integration and LiteLLM support for
NVIDIA NIM, Groq, Mistral, Cohere, and Cloudflare Workers AI. Treat this as
integration availability, not proof that every model supports every role.
Install only the extras needed when implementing the extension. See
[CrewAI connections](https://docs.crewai.com/en/learn/llm-connections).

| Provider | Planned integration | Initial role |
|---|---|---|
| NVIDIA NIM / Nemotron | CrewAI LLM → LiteLLM → NVIDIA NIM | Planning, orchestration, synthesis; candidate general fallback |
| Groq / GPT-OSS | CrewAI LLM → LiteLLM → Groq | Primary research |
| Mistral | CrewAI LLM → LiteLLM → Mistral | Critic / challenger |
| Cohere Command | CrewAI LLM → LiteLLM → Cohere | Evidence reasoning and grounding |
| Google Gemini | CrewAI LLM → native Google integration | Independent analysis; candidate multimodal fallback |
| Cloudflare Workers AI | CrewAI LLM → LiteLLM → Cloudflare | Specialist vision/document tasks where the model supports them |

Preserve `capstone/providers/llm.py`'s existing `LLMProvider` protocol:
`investigate(Investigation) → Investigation`. The capstone domain should
consume explicit research artifacts without importing CrewAI or provider SDKs.
One planned `CrewAIProvider` implements this project boundary; a small
`ModelRegistry` resolves role configuration inside that integration.

```text
Capstone domain → LLMProvider → CrewAIProvider
  → agent role → ModelRegistry → CrewAI LLM configuration
  → CrewAI native integration / LiteLLM → provider
```

This replaces the earlier per-provider adapter/router design. The boundary
still translates framework task results into project contracts and enforces
project policy; the framework handles provider transport. It does not replace
`FactoryProvider`, simulator tools, or the human approval boundary.

#### Role configuration and execution limits

Use Pydantic Settings for role configuration, with one primary model and one
optional fallback model per role. Keep a small validated `RoleModelConfig`
with `model`, `fallback_model`, `timeout_seconds`, `max_output_tokens`, and
the retry/tool/iteration budgets described in Future Work 7. Optional
reasoning controls apply only where supported.

Use full framework model identifiers, with conceptual configuration such as:

```text
PLANNER_MODEL=nvidia_nim/nvidia/<selected-nemotron-model>
RESEARCHER_MODEL=groq/<selected-gpt-oss-model>
EVIDENCE_MODEL=cohere/<selected-command-model>
EVIDENCE_FALLBACK_MODEL=nvidia_nim/nvidia/<compatible-fallback-model>
ANALYST_MODEL=gemini/<selected-gemini-model>
CRITIC_MODEL=mistral/<selected-mistral-model>
VISION_MODEL=cloudflare/<selected-multimodal-model>
```

These placeholders are not runnable model IDs. Confirm model catalogs,
endpoint prefixes, credentials, access, context limits, and modalities when
implementing. Keep the intended model families above configurable rather
than pinning the roadmap to currently advertised endpoint names. Map the
project's credential settings to the integration's required names without
exposing secrets in configuration dumps or traces.

A model change should affect role configuration and compatibility records,
not agent implementations or handoff schemas. The registry creates configured
CrewAI LLM objects without scattering provider switch statements across agents.
Translate token/reasoning settings to supported parameter names. Enforce
investigation deadlines and total retry/tool/iteration budgets outside the
provider call as well; a per-request timeout is not a whole-run deadline.

#### Common contracts and structured handoffs

**Planned, not implemented; reevaluate when CrewAI specialist tasks begin.**
Use `Task(..., output_pydantic=RoleContract)` for typed handoffs, with ordinary
Pydantic/project `Contract` models created only as needed.
Extract the validated task artifact rather than passing raw model text to the
next agent. CrewAI also documents Pydantic `response_format` for LLM calls;
its suitability depends on the selected model and integration. See
[CrewAI tasks](https://docs.crewai.com/en/concepts/tasks) and
[CrewAI LLMs](https://docs.crewai.com/en/concepts/llms).

The planned contracts remain `ResearchTask`, `ResearchFinding`,
`VerifiedEvidence`, `AnalysisResult`, `CritiqueResult`, and `SynthesisResult`,
created only as the workflow needs them. Keep the existing full,
evidence-only, and challenge handoffs, with explicit artifacts rather than
private chain-of-thought. Framework conversion must not weaken project
validation or silently admit unvalidated raw output after conversion fails.

A valid Pydantic object proves structure, not factual correctness.
`VerifiedEvidence` must record the evidence checks actually performed; an
Evidence Agent's interpretation does not replace Future Work 2's deterministic
MCP-response verification, source provenance, or evaluator-only ground truth.
Bound any structured-output repair attempts within the shared execution budget.

#### Cohere Rerank is a separate retrieval operation

Cohere Command is an LLM integration; Cohere Rerank is a different operation.
Keep reranking in a generic retrieval tool. LiteLLM documents `rerank()` with
Cohere support, so a separate Cohere chat adapter is unnecessary for this
purpose. See [LiteLLM rerank](https://docs.litellm.ai/docs/rerank).

```text
ChromaDB retrieval → candidate documents → LiteLLM rerank()
  → Cohere Rerank → ranked documents with original source identifiers
```

Candidate and returned counts are configurable; 20 candidates and 5 results
are illustrative, not fixed requirements. Preserve document IDs and source
references through ranking. Relevance scores do not establish truth. Test
reranking separately from Command completion and role-model substitution:
changing the Evidence Agent's LLM must not implicitly change its reranker.

#### Generic cross-provider fallback, when needed

Add fallback in the multi-agent phase when real workflows need it. Do not
assume an ordinary CrewAI `LLM` object provides the required cross-provider
policy. Prefer one small generic layer that invokes a configured primary
CrewAI LLM and, on an explicitly eligible failure, its compatible fallback.
Consider a single LiteLLM Router integration only if the pool warrants it;
its documentation covers retries and fallback routing. See
[LiteLLM Router](https://docs.litellm.ai/docs/routing).

Start with bounded retries for classified transient rate limits, timeouts,
connection failures, temporary server errors, or provider outages. Quota
exhaustion may permit configured fallback without repeatedly retrying an
exhausted primary. Unavailable models require classification: temporary
service unavailability can qualify; a wrong model ID or missing account
access is a configuration error. Authentication failures, malformed task
inputs, programming errors, and schema failures must not silently trigger
cross-provider fallback. Use the explicit bounded validation/repair path for
model-generated invalid output, then surface failure.

Nemotron remains a candidate general fallback for Researcher, Evidence,
Analyst, and Critic; Gemini remains a candidate Vision fallback. Enable each
only after testing the role's required contracts, tools, context, and modalities.
Do not substitute a text-only model for a required vision capability.

Coordinate framework, SDK, and project retries so nested layers cannot
multiply attempts beyond the investigation budget. Fallback must preserve
the typed task and permitted evidence, record which model actually answered,
and must not replay state-changing tools or bypass approval. Log role,
primary/fallback provider and model, classified failure, attempt, timestamp,
and run/investigation correlation IDs in the audit trail. Align tracing with
Future Work 2 without logging secrets or hidden truth.

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

Keep default tests offline with scripted framework/model stand-ins. Prove:

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

Implement one framework boundary, one small model registry, and only the
reliability policy that the extension needs. No generic routing platform,
proxy deployment, six custom clients, or new dependencies in this documentation
change. The core single-agent MVP plan and simulator behavior remain unchanged.

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

**Future Work 5 — proactive autonomy.** The system no longer waits for a
human question:

```
Factory state → continuous monitoring → anomaly discovered
  → investigation created automatically → research → recommendation
  → approval → intervention → verification
```

[FW5 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
concurrency control requires an actual overlapping-work race, even within one
process. Durable scheduling requires a workload that must survive restart.
Use an outbox only for a demonstrated durable-state/dispatch dual-write gap:
persist intent atomically, dispatch afterward, and handle duplicate delivery.
An async dead-letter queue requires an actual retry pipeline. Compare a simple
DB worker or existing framework before selecting a broker/job framework.
Redriving consequential work must recheck approval, safety and idempotency.

### Development tooling — Python dependency and environment management

Adopted `uv` on 2026-10-08 at the developer's request; this is no longer
future work. It is development/infrastructure tooling, not part of the
research agent's reasoning architecture or an MVP requirement. The existing
`pyproject.toml` and setuptools build remain, with a committed `uv.lock`,
an isolated `.venv`, and `uv run` commands. Installed simulator dependency
versions were preserved and all 331 existing tests passed under the new
environment. See `README.md` for setup, the optional Neon connectivity
check, and the retained pip workflow. Agent, API, and ingestion validation
will follow when those components exist.

### Future Work 6 — Developer Efficiency / Project Tooling

[FW6 gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
existing uv/Ruff/hooks/CI/coverage are IMPLEMENTED. Extend architectural invariant
tests with each actual boundary; do not write tests for imaginary capabilities.
Assemble a scripted vertical acceptance test as the agent loop grows. Compare
ty with targeted mypy on real diagnostics when static checking prevents concrete
mistakes; choose one primary checker. Current code can justify a pilot without
waiting for a large agent. Hypothesis and xdist retain their existing conditional
gates below. Coverage remains diagnostic; critical branch checks require useful
behavioral blind spots rather than a whole-project percentage target.

These planned improvements support development and infrastructure. They are
not MVP requirements or part of the research agent's reasoning architecture.
`uv`, Ruff (including import sorting), Pydantic Settings, pre-commit, CI,
and informational pytest-cov are implemented; other items remain planned
as noted below. Add them
in focused changes when their benefit justifies the work, rather than as one
large tooling migration.

| Improvement | Benefit for this capstone | Suggested timing / adoption condition |
|---|---|---|
| [Ruff](https://docs.astral.sh/ruff/) | Consistent formatting, linting, and import cleanup as the developer and coding agents share the codebase. | Implemented 2026-10-08; import sorting added 2026-10-11. Rules remain `E4`, `E7`, `E9`, `F`, `I`; mechanical fixes are separate from tooling configuration. |
| [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Typed, validated configuration for Neon, API credentials, model choices, and later ingestion/storage settings. | Implemented 2026-10-08 for the existing Neon check: lazy settings, environment precedence, and masked optional database credentials. Future integrations will add fields when needed; simulator seeds remain explicit. |
| [pre-commit](https://docs.astral.sh/ruff/integrations/) | Run agreed formatting and lint checks before changes are committed. | Implemented 2026-10-11: Ruff check/fix then format, pinned to the resolved Ruff version. Local installation/use documented in README; no additional formatter or import sorter. |
| [GitHub Actions with uv caching](https://docs.astral.sh/uv/guides/integration/github/) | Repeatable automated tests and faster dependency setup from the committed lockfile. | Workflow implemented 2026-10-11: PRs and main pushes, pinned development Python, locked default install, Ruff, and one offline test run with informational coverage. No service credentials or live Neon/provider/MCP calls. Hosted execution is verified separately from local checks. |
| [pytest-cov](https://pytest-cov.readthedocs.io/en/stable/reporting.html) | Identify unexercised paths alongside semantic tests. | Implemented 2026-10-11 in both development dependency paths. Optional local terminal report and CI Markdown summary; no coverage threshold or 100% target. |
| [uv audit](https://docs.astral.sh/uv/reference/cli/#uv-audit) | Check locked dependencies for known vulnerabilities and surface findings for review. | Add alongside CI. Use `uv audit --locked`, define how findings are handled, and review dependency changes rather than automatically upgrading packages. |
| [ty](https://docs.astral.sh/ty/) | Check Pydantic contracts, Protocols, provider interfaces, and future graph/handoff/persistence types. | Candidate, not implemented. Reevaluate once interfaces and a reviewed diagnostic baseline are stable; see adoption conditions below. No required CI gate. |
| [Dependabot for uv](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories) | Propose dependency updates for review, including changes to `uv.lock`. | After CI can validate update PRs. Review existing migration constraints when intentionally upgrading simulator dependencies; require passing tests before merging. |
| [pytest-xdist](https://pytest-xdist.readthedocs.io/en/latest/distribution.html) | Shorter test runs by distributing independent tests across workers. | Candidate, not implemented. Reevaluate when measured suite duration is materially slow; require isolation and repeatable speedup before enabling `pytest -n auto`. |
| [Hypothesis](https://hypothesis.readthedocs.io/en/latest/stateful.html) | Find combinations at deterministic state/contract boundaries that examples miss. | Candidate, not implemented. Reevaluate when a specific invariant or sequence would otherwise need many hand-written cases. |

Ruff, Pydantic Settings, pre-commit, and CI with uv caching are now in place.
Dependency auditing remains planned. Add type checking and dependency-update automation as
interfaces and CI mature; parallelize tests only after isolation is proven.
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

**Added 2026-10-09.** Sensor summaries are implemented in the direct observation
tools and simulator provider; other additions remain planned. These additions
preserve the
existing reasoning loop, working state, durable-memory plans, provider
abstraction, typed multi-agent handoffs, termination rules, human approval,
post-intervention verification, and simulator architecture. Do not add a
failure-diagnostic benchmark mode.

#### Timing

| Addition | MVP integration | Later extension |
|---|---|---|
| Role-specific model benchmarking | No cross-provider harness needed to finish the single-agent slice. | Add a lightweight harness with Future Work 3, before treating specialist role assignments as final. |
| Reasoning and token budgets | Add limits for the single agent when building the reasoning loop (progress row 16). | Give every planner, researcher, analyst, critic, and synthesizer its own configuration when those roles exist. |
| Deterministic sensor computations | Implemented 2026-10-09: `get_sensor_summary()` and its typed provider result, for machine and factory sensors. Agent integration remains planned. | Add window comparisons or moving averages only when investigations require them; expose through MCP with Future Work 2. |
| Known-answer regression scenarios | Add the basic suite with scenario generation and evaluation (progress rows 14–15), then exercise the agent when row 16 exists. | Expand coverage after changes to prompts, models, tools, memory, providers, and handoffs. |

These are staged additions to the existing build order, not a separate framework
to implement before the remaining simulator actions and scenarios.

#### Role-specific model benchmarking

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

Each role should support `max_output_tokens`, `reasoning_effort`,
`timeout_seconds`, `max_retries`, `max_tool_calls`, and `max_iterations`.
The single-agent MVP uses the same concepts without introducing extra roles.
Retain deterministic global investigation/tool-call limits across all roles,
retries, and handoffs so local budgets cannot bypass termination rules.

The project/framework integration translates supported provider controls;
Future Work 3 uses CrewAI/LiteLLM rather than a custom adapter per provider.
Unsupported optional reasoning
settings may be omitted with their effective configuration recorded; enforce
execution limits in orchestration or reject configurations that cannot be
bounded safely. Reasoning effort is a resource setting, not proof of correctness.

#### Deterministic sensor computation tools

Compute exact arithmetic and statistics in Python from permitted observation
records. The LLM interprets those facts, forms hypotheses, and selects the next
evidence request. Raw readings remain available when useful.

Implemented a generic `get_sensor_summary()` capability for machine sensors
and factory sensors (`machine_id=None`). It reports machine/sensor identity,
units, inclusive window boundaries, sample count, actual first/last ticks,
first/last values, minimum, maximum, sample-weighted mean, delta, and endpoint
rate of change in sensor units per elapsed tick. It orders samples by tick,
does not fill missing readings, and returns null statistics for empty windows
and a null rate for zero elapsed time. Mixed units and nonfinite values are
rejected. Tests cover known inputs and the read-only, hidden-state boundary.

Add `compare_sensor_windows()` or moving averages only for a demonstrated
investigation need. All calculations stay read-only, use the existing typed
tool boundary, and reveal neither programmed root causes nor internal health
or degradation values. MCP is a later transport for the same observations.

#### Known-answer regression scenarios

Use implemented simulator behavior and fixed seeds: bearing degradation, bad
material batches, wrong settings, and false alarms once implemented, plus
normal-operation controls where supported. Workload changes, ambient changes,
sensor anomalies, and idle behavior can become additional cases only when the
existing simulator can reproduce the intended condition; do not invent new
fault models just to fill the test list.

Preserve scenario ID, seed/initial configuration, evaluator-only hidden ground
truth, observable sensor data, expected relevant evidence, agent conclusion,
confidence, tools used, iterations used, and final correctness. Keep evaluator
records containing truth separate from agent prompts, tool outputs, and
retrievable memory. Score diagnoses and interventions using the existing MVP
evaluation, including post-intervention verification.

Use scripted model stand-ins for deterministic offline workflow tests; live
model runs measure performance on repeatable cases without promising identical
answers. These regression cases support the normal investigation workflow;
they do not introduce the excluded failure-diagnostic benchmark mode.

#### Pydantic Evals — candidate, not implemented

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

### Implemented foundations for later research and persistence

Far-future portability candidates have separate
[register gates](FUTURE_WORK_REEVALUATION.md#future-technology--architecture-reevaluation-register):
schema-defined equipment requires a second genuinely different environment and
repetitive capability code; YAML requires an actual profile-authoring need.
Multi-tenant isolation/RLS requires mutually untrusted owners sharing persistent
infrastructure. None is a course MVP requirement. ADRs may document settled,
costly-to-reverse decisions without turning candidates into accepted designs.

The developer requested these foundations on 2026-10-08. They prepare existing
boundaries for extension without implementing the larger research frameworks.

| Foundation | Implemented scope | Remaining integration |
|---|---|---|
| Central contracts | `capstone/contracts/`: observable records, evidence, hypotheses, investigations, and tool requests/results with explicit validated fields. Hidden simulator state is excluded. | Connect these artifacts to the future agent, retrieval, evaluation, and persistence code as those components are built. |
| Alembic | Optional database dependency, settings-driven environment, registered memory metadata, and explicit revision `0001_episodic_memory`. SQLite upgrade/downgrade and offline PostgreSQL SQL tests; empty metadata still blocks autogeneration. This increment has not applied the revision to Neon. | Review the initial memory migration and apply it to the configured durable store as a separate step; review and test later schema revisions. |
| Run and investigation IDs | Deterministic UUID helpers using caller-supplied execution keys and per-run investigation sequences. No simulator RNG or wall clock is used. | Callers must assign a unique key per execution, including repeated runs with identical seeds, and pass IDs to stored records and evaluations. |
| Stable tool interface | `ToolRequest`, `ToolResult`, and strict argument/output validation around all existing agent-facing tools. Results include source, simulation time, context IDs, and structured errors. | Future MCP/database/document adapters can implement the same contract; human approval remains outside the agent tool list. |
| Provider/adaptor boundary | `FactoryProvider`, concrete `SimulatorFactoryProvider`, and a provider-neutral `LLMProvider` protocol for explicit investigation artifacts. | Real factory or LLM integrations will provide concrete adapters; no external model or factory connection is implemented by these interfaces. |

Smaller foundations are also implemented: a secret-free `.env.example`, typed
settings, and opt-in JSON metadata logging with run/investigation IDs. The
existing `capstone/` structure is retained and no empty framework scaffolding
is added. Ruff commands and these boundaries are documented in `README.md`.
pytest-cov, pre-commit, and CI were subsequently added on 2026-10-11 as
developer tooling (Future Work 6). Type checking and larger research frameworks
remain deferred; the original foundation work did not install them.

### Developer follow-up: Subquadratic whole-repository audit

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

### Future Work 8 — harder scenarios: the compound challenge and difficulty modes

Status: future work; not implemented. Recorded 2026-10-20 at the developer's
request. Both items build on the multi-fault scoring added in E5 (`Score.causes`,
`causes_found`, `wrong_causes`, `causes_resolved`, `fully_right`), which already
judges a run with several true faults.

#### Running the compound challenge in experiments

**Built 2026-10-20 (E6, docs/PROGRESS.md):** `run --challenge SEEDS` and the
known-answer case KA-09; the rest of this section is the original note.

Scoring is ready, but experiments cannot build the challenge yet.
`simulator/challenge.py` `build_challenge(seed)` already composes a worn bearing
and a wrong speed setting on one machine, a harmless vibration spike on a second
and a drifting, briefly silent temperature sensor on a third. `run_episode` and
`capstone/experiment.py` build only the four ordinary scenarios
(`simulator/generator.py` `FAULTS`), so a challenge run cannot be started,
recorded or reported. What is needed: a way for an experiment case to name the
challenge (for example a scenario kind beside the fault), `run_episode`
building it through `build_challenge`, the report showing several-fault runs
apart (as E5's summary already does), and a known-answer case for it. Its
monitoring, prompts and scoring must stay as they are for single-fault runs.
This changes what the agent observes and how it is scored, so it goes through
the teaching gate (AGENTS.md §2.1).

#### Easy / intermediate / hard modes, with a frontend button

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

#### Fault packs: one registry entry per sensor and its fault (planned 2026-10-22)

Status: planned, not implemented. Recorded at the developer's request after
a review of what adding a new sensor with a matching fault would take.

**The problem.** Adding a fault today touches about 6 places in code (12 or
so with a new sensor and a new repair), and most of them are lists of names
that must agree: `FAULTS` (`simulator/generator.py`), `FAULT_KINDS`
(`tools/diagnosis.py`), `CORRECT_ACTION`, `RELEVANT_EVIDENCE` and
`CAUSE_KINDS` (`evaluation/scoring.py`), the baseline's `FIX`
(`baseline.py`), `ACTIONS` (`tools/actions.py`), `MachineSensor` and the
tool descriptions naming the sensors (`providers/factory.py`), the sensor
list in `simulator/disturbances.py`, and the per-machine sensor list in
`simulator/line.py`. Miss one and the fault is half wired.

**The plan.** Describe each sensor and its paired fault once, as a "fault
pack", in one fixed registry, and build those lists from it. A pack holds:

- what the agent may see: the sensor's name and unit, the repair's name and
  the sentence the `propose_action` description gives it, and any alarm;
- what only the evaluator may see: the correct fix, the relevant evidence,
  whether it is a cause or a distractor, its known-answer cases;
- its code: the scenario that changes hidden state, the sensor's reading,
  the repair's effect, and the baseline's rule.

The two halves are kept apart in the registry, so evaluator-only data can
never be read into a prompt or a tool description.

**What it does not remove.** Each fault's real behaviour (the physics, the
sensor reading, knock-on effects such as heat, the repair, the baseline
rule) is still its own code. A new fault goes from about 12 files to 3 or 4
(its pack, its physics hooks, its tests), not to one.

**Fixed in code, chosen per experiment; not added or removed at runtime.**
If the set of faults could change while the program runs, the same seed
could build a different factory, and old results and the known-answer
cases would stop matching. So packs are fixed in code, and an experiment
chooses which packs it uses. Each seed's fault draw must be keyed so that
leaving a pack out, or adding one, does not shift what the other faults
draw (today `build_scenario` draws from `FAULTS` even when the fault is
forced, so a longer list can change a seed's machine and start tick).
Choosing packs per experiment is also most of what the easy / intermediate
/ hard modes above would need.

**When and in what order.** With four faults a registry is borderline
complexity without a concrete reason (AGENTS.md section 4.5); it earns its
place with the fifth. So, just before the next fault is added:

1. move the existing four faults into the registry, changing no behaviour;
2. prove nothing changed: the same seeds give the same factories and
   scores, the known-answer cases still pass, and the rule baseline still
   gets about 96% of causes right;
3. add the new sensor and its fault (for example coolant pressure with a
   coolant leak: pressure falls, the machine runs hotter, rejects rise, and
   the fix is a coolant repair) as the first new pack.

Step 1-2 is about a day. Before step 3, decide whether the new sensor
raises its own alarm: monitoring reacts only to an alarm, a stopped
machine or a run of rejects. New sensors, failure models and scenario
injection are on the teaching list (AGENTS.md section 2.1), so whether this
is taught or built ungated is the developer's call. The agent, its prompts,
memory and the experiment harness need no change: the prompts carry no
list of possible causes.

### Next build candidates (ranked, 2026-10-20)

A short list for the developer to choose from, most impact first. None is
started. Each would go through its own pull request (AGENTS.md §11); whether
each is taught first or built ungated is the developer's call.

| # | Candidate | Why it matters | Depends on | Size |
|---|---|---|---|---|
| 1 | **Make live runs finish.** Find why live episodes end "model unavailable" (reply length limit, provider errors, no fallback model set), fix it, rerun the eight known-answer cases. | In the developer's local live results of 2026-10-20, 15 of 17 runs ended "model unavailable" and concluded "undetermined". Until runs complete, no live result means anything. | Keys in `.env`; live API calls | Small to medium |
| 2 | **Benchmark the in-scope models** (`python -m capstone.benchmark`), then set the per-question limit, the investigation budget and the job table (which model does which job) from the numbers. | The time limits are still estimates; some jobs may suit a different model. | Item 1; the developer names the models | Small code, long runs |
| 3 | **The compound challenge in experiments** (Future Work 8, first part). | Scoring several true faults is ready (E5) but experiments cannot build the challenge. | Nothing | Medium |
| 4 | **An evaluator model for diagnosis labels**, checked against the developer's hand labels before it is trusted; a different model from the investigator; its verdict never reaches the agent or memory. | Experiments could then score root cause without labelling every run by hand (decided 2026-10-12). | Some hand labels to check it against | Medium |
| 5 | **A memory comparison command:** the same cases with no memory, keyword recall and semantic recall, reported side by side on diagnosis accuracy and tool calls. | Shows whether memory improves investigations, not just whether search works. | Item 1 (live runs) for meaningful numbers | Small to medium |
| 6 | **A live progress view:** a hook in the loop that announces each step as it happens, and a terminal viewer with approval at the prompt; only what the agent sees, the score only after the run. | A run can take minutes; a viewer also makes the demo. First screen of the later frontend (Future Work 8, modes). | Nothing | Medium |
| 7 | **Small cleanups:** `.env.example` lists the newer settings; stale worktrees removed. | Setting up a fresh checkout works first time. | Nothing | Small |

Can run in parallel: 1 (needs the keys, so in the developer's session), 3 + 4
(evaluation), 5 + 6 (different files). Item 2 waits for item 1. Difficulty
modes (Future Work 8, second part) wait for item 1's live results compared
with the rule baseline.

### Future Work 9 — sensor-triggered, on-demand machine vision (near-last priority)

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
