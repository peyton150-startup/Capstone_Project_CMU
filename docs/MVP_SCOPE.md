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

**Future Work 1 — richer research.** Technical manuals, maintenance
documentation, historical incidents, RAG, external knowledge sources. The
agent researches both the factory and a knowledge base.

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

#### Provider Abstraction and Fallback Requirement

The multi-agent system must not hard-code any agent directly to a specific API provider.

Each agent role must request a model through a centralized provider/model router so that the provider assigned to that role can be changed through configuration without changing the agent implementation.

For example, the Evidence Agent must depend on an abstract model/provider interface rather than directly importing or constructing a Cohere client.

The provider assignments should be configurable through environment variables similar to:

```text
ORCHESTRATOR_PROVIDER=nvidia

RESEARCHER_PROVIDER=groq
RESEARCHER_FALLBACK=nvidia

EVIDENCE_PROVIDER=cohere
EVIDENCE_FALLBACK=nvidia

ANALYST_PROVIDER=gemini
ANALYST_FALLBACK=nvidia

CRITIC_PROVIDER=mistral
CRITIC_FALLBACK=nvidia

VISION_PROVIDER=cloudflare
VISION_FALLBACK=gemini
```

Model names should also be configurable independently from providers, for example:

```text
RESEARCHER_MODEL=openai/gpt-oss-120b
EVIDENCE_MODEL=command-a
CRITIC_MODEL=mistral-small
```

Do not scatter provider selection logic throughout the codebase. There should be one centralized model/provider registry or router responsible for resolving:

```text
agent role
→ configured provider
→ configured model
→ provider adapter
→ model client
```

The intended outcome is that changing a provider should require approximately one configuration change.

For example:

```text
EVIDENCE_PROVIDER=cohere
```

should be replaceable with:

```text
EVIDENCE_PROVIDER=nvidia
```

without modifying the Evidence Agent, CrewAI workflow, Pydantic schemas, downstream agents, or handoff logic.

#### Common Agent Contracts

Provider-specific output formats must never leak into the multi-agent workflow.

Every provider adapter must convert model output into the same Pydantic contract required by the corresponding agent role.

For example:

```text
Cohere
   ↓
provider adapter
   ↓
VerifiedEvidence
   ↓
next agent
```

must be interchangeable with:

```text
NVIDIA
   ↓
provider adapter
   ↓
VerifiedEvidence
   ↓
next agent
```

Downstream agents should know only about the typed Pydantic object, not which provider generated it.

This same principle should apply to:

- ResearchTask
- ResearchFinding
- VerifiedEvidence
- AnalysisResult
- CritiqueResult
- SynthesisResult
- any other inter-agent contract created for the post-MVP extension

#### Automatic Provider Fallbacks

Specialized agents should also support a configured fallback provider.

If the primary provider fails because of:

- HTTP 429 / rate limiting
- quota exhaustion
- provider outage
- temporary server error
- timeout
- unavailable model
- other explicitly classified transient provider failures

the provider router may retry according to a bounded retry policy and then route the same typed task to the configured fallback provider.

Example:

```text
Evidence Agent
      ↓
Cohere
      ↓
429 / quota exceeded
      ↓
NVIDIA Nemotron
      ↓
VerifiedEvidence
      ↓
normal workflow continues
```

NVIDIA/Nemotron should act as the default general-purpose fallback for the Researcher, Evidence, Analyst, and Critic roles unless another fallback has been explicitly configured.

The Vision role may use Gemini as its initial fallback because multimodal capability must be preserved.

Do not silently fallback for malformed application data, schema bugs, programming errors, authentication/configuration mistakes, or other failures that should stop execution and be investigated.

Every fallback must be recorded in the investigation/audit state with at least:

```text
agent_role
primary_provider
primary_model
failure_type
fallback_provider
fallback_model
timestamp
```

#### Default Provider Responsibilities

Preserve the current intended specialization:

```text
NVIDIA / Nemotron
→ orchestration
→ planning
→ synthesis
→ general-purpose fallback

Groq / GPT-OSS 120B
→ primary research

Cohere / Command + Rerank
→ evidence retrieval, reranking, and grounding

Google Gemini
→ independent evidence analysis

Mistral
→ critic / challenger

Cloudflare
→ specialist vision/document processing
```

These are defaults, not hard dependencies.

The architecture should make it possible to substitute providers later without redesigning the agents.

#### Scope Constraint

Do not turn this into a large generic model-routing platform.

For the post-MVP extension, implement only what is necessary to:

1. Configure one primary provider/model per agent role.
2. Configure one optional fallback per role.
3. Resolve the configured provider through a centralized registry/router.
4. Normalize provider output into the existing Pydantic contracts.
5. Handle bounded retries and explicit fallback conditions.
6. Record which provider/model actually performed each agent step.
7. Test that swapping a provider does not require changes to the agent workflow.

Add focused tests proving at minimum:

- Evidence Agent works with Cohere as primary.
- The same Evidence Agent can be configured to use NVIDIA without changing its implementation.
- A simulated Cohere rate-limit failure routes to NVIDIA.
- Both providers return the same `VerifiedEvidence` contract.
- Downstream agents operate identically regardless of which provider produced that contract.
- Provider/fallback usage is visible in the audit trail.

Keep this modular and simple enough that changing a provider is primarily a configuration change rather than a code change.

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
`uv`, Ruff, and Pydantic Settings are implemented; other items remain planned
as noted below. Add them
in focused changes when their benefit justifies the work, rather than as one
large tooling migration.

| Improvement | Benefit for this capstone | Suggested timing / adoption condition |
|---|---|---|
| [Ruff](https://docs.astral.sh/ruff/) | Consistent formatting, linting, and import cleanup as the developer and coding agents share the codebase. | Implemented 2026-10-08: basic correctness rules and formatter, documented in `README.md`. Initial formatting is kept in a separate commit from configuration behavior changes. |
| [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Typed, validated configuration for Neon, API credentials, model choices, and later ingestion/storage settings. | Implemented 2026-10-08 for the existing Neon check: lazy settings, environment precedence, and masked optional database credentials. Future integrations will add fields when needed; simulator seeds remain explicit. |
| [pre-commit](https://pre-commit.com/) | Run agreed formatting and lint checks before changes are committed. | After Ruff rules are established. Pin hook versions and document hook installation for each developer. |
| [GitHub Actions with uv caching](https://docs.astral.sh/uv/guides/integration/github/) | Repeatable automated tests and faster dependency setup from the committed lockfile. | When CI is introduced. Use locked installs, test the simulator without credentials, and keep live Neon checks separate from the default offline suite. |
| [uv audit](https://docs.astral.sh/uv/reference/cli/#uv-audit) | Check locked dependencies for known vulnerabilities and surface findings for review. | Add alongside CI. Use `uv audit --locked`, define how findings are handled, and review dependency changes rather than automatically upgrading packages. |
| [ty](https://docs.astral.sh/ty/) | Catch type mismatches as simulator observations, tool contracts, agent state, and persistence interfaces grow. | After basic linting is stable and interfaces expand. Introduce checking incrementally before making it a required CI gate. |
| [Dependabot for uv](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories) | Propose dependency updates for review, including changes to `uv.lock`. | After CI can validate update PRs. Review existing migration constraints when intentionally upgrading simulator dependencies; require passing tests before merging. |
| [pytest-xdist](https://pytest-xdist.readthedocs.io/en/stable/) | Shorter test runs by distributing independent tests across workers. | When measured test duration warrants it. First isolate random generators, temporary files, and any database fixtures per worker; confirm seeded results remain reproducible before using `pytest -n auto`. |

Priority: Ruff → Pydantic Settings → pre-commit → CI with uv caching and
dependency auditing. Add type checking and dependency-update automation as
interfaces and CI mature; parallelize tests only after isolation is proven.
Items still marked planned remain roadmap entries; adopting them requires a
separate implementation task.

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

Adapters translate supported provider controls. Unsupported optional reasoning
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
pytest-cov, pre-commit, type checking, CI, and larger research/infrastructure
frameworks remain deferred; this foundation work does not install them.
