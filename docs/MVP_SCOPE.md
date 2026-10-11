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

## 4. A small set of tools (6–8)

```
get_machine_state()
get_sensor_history()
get_production_batch()
get_quality_results()
get_maintenance_history()
search_incident_history()
propose_action()
observe_after_action()
```

MCP may expose these later; MCP itself is not a core simulator/agent MVP
objective. Future Work 2 defines a minimal first MCP slice and its planned
observability, after the core investigation loop works. What
matters is that the agent must decide **"what information do I need
next?"** rather than having everything dumped into the prompt.

The read-only `get_sensor_summary()` capability is implemented: Python computes
exact statistics for the agent to interpret. It uses the existing tool/provider
boundary; agent integration and MCP transport remain deferred. See Future
Work 7 for calculation details.

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

### Future Work 1 — richer research and document ingestion

Technical manuals, maintenance
documentation, historical incidents, RAG, external knowledge sources. The
agent researches both the factory and a knowledge base.

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

**Future Work 5 — proactive autonomy.** The system no longer waits for a
human question:

```
Factory state → continuous monitoring → anomaly discovered
  → investigation created automatically → research → recommendation
  → approval → intervention → verification
```

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

The developer requested these foundations on 2026-10-08. They prepare existing
boundaries for extension without implementing the larger research frameworks.

| Foundation | Implemented scope | Remaining integration |
|---|---|---|
| Central contracts | `capstone/contracts/`: observable records, evidence, hypotheses, investigations, and tool requests/results with explicit validated fields. Hidden simulator state is excluded. | Connect these artifacts to the future agent, retrieval, evaluation, and persistence code as those components are built. |
| Alembic | Optional database dependency, settings-driven migration environment, revision template, and offline tests. Empty metadata blocks autogeneration; no tables or revisions have been created or applied. | Design the actual persistence schema, register table metadata, review revisions, and test them before applying migrations. |
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
