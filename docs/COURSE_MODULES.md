# Course modules in the capstone

How each module of the CMU agentic-AI course shows up in this project. Each
module starts with a gap note: what the capstone already does for that
module's topic, and what is missing. The missing pieces worth building are
then built, each through its own pull request.

Mode (developer's decision, 2026-10-20): these pieces are built in bulk
without teaching gates and learned later. In `docs/PROGRESS.md` they are
marked "built ungated, developer to review (understood: no)".

Scope (developer's decision, 2026-10-20): Modules 2, 3 and 4 only. Modules
0-1 are orientation, with nothing to build. Modules 5-7 (multi-agent
frameworks; evaluation, guardrails and observability; the capstone
write-up) are not a focus now.

---

## Module 2 — Agent architecture: memory, tools and reasoning loops

### What the capstone already does

**Working memory (one investigation).** `InvestigationState`
(`capstone/agent/state.py`) holds everything the live investigation knows:
the anomaly, the evidence with system-given IDs, where each piece came from
(`provenance`), the hypotheses with the evidence they cite, the open
questions, the budgets and counters, and one `DecisionRecord` per step. It
lives for one investigation and is then turned into a
`CompletedInvestigation` (`agent/completion.py`). It holds decisions, not
private reasoning. A model sees it through one fixed view, `render(state)`
in `agent/model_policy.py`, with a size limit on the evidence section.

**Episodic memory (across investigations).** `capstone/memory/`: a
reflection candidate is built from the finished record
(`memory/reflection.py`), a promotion gate decides whether it may be kept
(`memory/policy.py`: only verified fixes, no hidden truth, failures kept as
warnings), SQL is the authoritative store (`memory/repository.py`), and a
Chroma index with NVIDIA embeddings gives semantic recall
(`memory/semantic.py`, `memory/recall.py`, modes semantic / keyword /
none). The agent can read memory only through one tool,
`recall_memories` (`providers/recall.py`), whose answers are labelled
`memory`, never `observable`, so a memory can suggest where to look but
never prove a fix worked (`agent/investigation.py`, `verify`).

**Tools.** Every tool is a typed contract: `ToolRequest` / `ToolResult` /
`ToolError` / `ToolSpec` (`capstone/contracts/tools.py`). The factory
provider (`providers/factory.py`) validates arguments with one Pydantic
model per tool (`TOOL_ARGUMENTS`), describes each tool to the model
(`TOOL_DESCRIPTIONS`), refuses answers over 300 rows, and never returns
hidden truth. Read-only tools run freely; the three that change the
factory (`propose_action`, `get_proposals`, `execute_action`) are a fixed
procedure the loop runs itself, after human approval, and are never
offered to the policy.

**Reasoning loops.** Two levels:

- The inner ReAct-style loop (`agent/loop.py`, `run_inner_loop`): decide,
  call one tool, turn the answer into evidence, let the policy interpret
  it, record the step. The loop, not the policy, owns every limit: tool
  calls, iterations, time, repeated calls, unproductive steps, a stalled
  confidence, and the "diagnosis supported" stop.
- The outer stage graph (`agent/investigation.py`, on pydantic-graph):
  observe, plan, investigate, hypothesize, test, conclude, propose,
  execute, verify. The graph's edges are the only allowed order.

The policy (`agent/policy.py`) is the agent's judgement: seven typed
questions (plan, decide, interpret, hypothesize, conclude,
judge_verification, write_lesson). A scripted policy, the rule baseline
and the model-backed policy (`agent/model_policy.py`) all fit it.

### What is missing

Nothing in the module's core is missing: working memory, episodic memory,
typed tools and a bounded loop all exist, are tested and were taught
(rows A1-A9b in `docs/PROGRESS.md`). Two small gaps turned up, both where
memory meets the loop, so they are built under Module 3 (retrieval):

1. **A repeated memory search is not recognised as a repeat.** The loop
   spots a repeat as "same tool, same arguments, same tick". Memory does
   not change with the factory's clock, so the same search a few ticks
   later is still the same search, against an unchanged store, and costs a
   tool call for nothing. Future Work 1 says so: "repeating an identical
   query against an unchanged store is not progress".
2. **Recall has no budget of its own.** Future Work 1 sets a default of at
   most three retrieval calls; today the agent may spend its whole research
   budget on recall, and nothing records what each search asked and got
   back.

Built for Module 2: this note only.
