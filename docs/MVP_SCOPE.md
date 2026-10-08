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

MCP may expose these later; MCP itself is not an MVP objective. What
matters is that the agent must decide **"what information do I need
next?"** rather than having everything dumped into the prompt.

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

**Future Work 2 — MCP.** Expose factory systems as separate MCP servers:
Telemetry, Maintenance, Quality, Production, Documentation. The agent
operates across heterogeneous external systems.

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
`uv` is already implemented; the tools below are not yet adopted. Add them
in focused changes when their benefit justifies the work, rather than as one
large tooling migration.

| Improvement | Benefit for this capstone | Suggested timing / adoption condition |
|---|---|---|
| [Ruff](https://docs.astral.sh/ruff/) | Consistent formatting, linting, and import cleanup as the developer and coding agents share the codebase. | First tooling follow-up. Start with a small rule set; review automatic fixes and keep formatting changes separate from behavior changes. |
| [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Typed, validated configuration for Neon, API credentials, model choices, and later ingestion/storage settings. | Next, before configuration spreads across modules. Require credentials only for the component using them, protect secrets in logs, and preserve explicit simulator seeds and database-free execution. |
| [pre-commit](https://pre-commit.com/) | Run agreed formatting and lint checks before changes are committed. | After Ruff rules are established. Pin hook versions and document hook installation for each developer. |
| [GitHub Actions with uv caching](https://docs.astral.sh/uv/guides/integration/github/) | Repeatable automated tests and faster dependency setup from the committed lockfile. | When CI is introduced. Use locked installs, test the simulator without credentials, and keep live Neon checks separate from the default offline suite. |
| [uv audit](https://docs.astral.sh/uv/reference/cli/#uv-audit) | Check locked dependencies for known vulnerabilities and surface findings for review. | Add alongside CI. Use `uv audit --locked`, define how findings are handled, and review dependency changes rather than automatically upgrading packages. |
| [ty](https://docs.astral.sh/ty/) | Catch type mismatches as simulator observations, tool contracts, agent state, and persistence interfaces grow. | After basic linting is stable and interfaces expand. Introduce checking incrementally before making it a required CI gate. |
| [Dependabot for uv](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories) | Propose dependency updates for review, including changes to `uv.lock`. | After CI can validate update PRs. Review existing migration constraints when intentionally upgrading simulator dependencies; require passing tests before merging. |
| [pytest-xdist](https://pytest-xdist.readthedocs.io/en/stable/) | Shorter test runs by distributing independent tests across workers. | When measured test duration warrants it. First isolate random generators, temporary files, and any database fixtures per worker; confirm seeded results remain reproducible before using `pytest -n auto`. |

Priority: Ruff → Pydantic Settings → pre-commit → CI with uv caching and
dependency auditing. Add type checking and dependency-update automation as
interfaces and CI mature; parallelize tests only after isolation is proven.
None of these roadmap entries authorizes installing tools, changing package
versions, configuring hooks or CI, or refactoring working code now.
