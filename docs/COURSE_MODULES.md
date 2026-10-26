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

---

## Module 3 — RAG agents and vector databases

### What the capstone already does

**A vector database beside an authoritative store.** Accepted lessons are
written to SQL first (`memory/repository.py`); a Chroma collection
(`memory/semantic.py`) keeps one embedding per lesson, made by NVIDIA's
`nemotron-3-embed-1b` (`providers/embeddings.py`) with separate passage and
query roles. A search returns memory IDs only; the records are read back
from SQL, so a stale index can never invent a memory. The collection
records which model built it and refuses to open under another
(`IndexModelMismatch`); `python -m capstone.memory.backfill --rebuild`
rebuilds it from SQL.

**Three retrieval modes.** `MEMORY_RETRIEVAL_MODE` = semantic / keyword /
none (`memory/recall.py`, `MemoryRecall`). Semantic falls back to keyword
search when the index is missing or fails.

**Agent-directed retrieval.** The agent decides when to search: memory is
one tool, `recall_memories(text, limit)` (`providers/recall.py`), chosen by
the same `decide` question as any factory tool. Its answers are labelled
memory, so they can suggest where to look but never count as a look at the
factory, nor as proof that a fix worked.

**Records of memory use.** Experiments record what each run recalled and
whether the agent cited it (`evaluation/memory.py`, E2).

### What is missing

1. **No measure of whether memory helps.** Nothing runs the same cases with
   and without memory, or with keyword against semantic recall, so there is
   no evidence that retrieval improves diagnoses rather than only working
   as a search. (Next build candidate 5 in `docs/MVP_SCOPE.md`.)
2. **Retrieval has no bounds or record of its own** (the two gaps from
   Module 2): the same search repeated a few ticks later is not caught as a
   repeat, there is no limit on searches (Future Work 1 sets a default of
   three), and nothing records what each search asked and got back.

Out of scope, by the rules: no new vector database, no RAG framework, no
second reasoning model for retrieval (Future Work 1: "Do not introduce
another reasoning LLM or a dedicated RAG agent"), no document ingestion.

### Built for Module 3

- **Memory comparison command** (`capstone/memory_comparison.py`):
  `python -m capstone.memory_comparison run --name cmp-1 --known --out
  cmp.jsonl` runs the same cases once per mode (none: no recall tool at
  all; keyword; semantic), interleaved case by case, all reading the same
  store and none writing to it; `report` prints one line per mode (outage
  runs, then over the rest: causes right among labelled runs, resolved,
  average tool calls and factory calls, searches answered, refused and
  failed, memories recalled and cited) and one line per case with the modes
  side by side. Semantic mode never answers by keyword: with no index it is
  refused, and a search that fails mid-run is recorded as failed (C3c,
  2026-10-26). Tested with scripted policies only; not yet run live.
- **Bounded, recorded memory search** (`providers/recall.py`,
  `evaluation/memory.py`, `experiment.py`): a minimal slice of Future Work
  1's agent-directed retrieval, on the existing SQL + Chroma design. The
  agent still chooses when and what to search. Within one investigation
  the store does not change (lessons are promoted only after a run), so
  the same search again, at any tick, is refused with a message telling
  the agent to revise its wording, try other symptoms or another
  hypothesis, or use the factory's tools; and at most three searches are
  answered (`MAX_SEARCHES`, Future Work 1's default), after which the
  agent is told to carry on without memory and say what it left unknown.
  A refusal reaches the next prompt through the usual failed-call list.
  Each search is recorded for the experimenter (`RecallSearchRecord`:
  words, limit, answered / repeated / budget_spent / failed, memory IDs
  returned), in `ExperimentRecord.recall_searches`, and counted in the
  experiment and comparison reports. Not done from Future Work 1: the
  agent's own judgement of each result's usefulness is not asked for or
  recorded, and the limit is per investigation, not per knowledge gap.

---

## Module 4 — Tree-of-thought reasoning and multi-agent concepts (part 1)

### What the capstone already does

**Competing hypotheses, tested with evidence.** MVP section 5 is built: the
`hypothesize` question proposes two to four explanations with confidences
and the evidence each cites, including ones that need no change to the
factory, plus questions that would tell them apart; the `test` stage
gathers evidence against them; `interpret` revises them; the loop stops
only when the leading one is confident, backed, uncontradicted and no open
question still tests a current explanation (`diagnosis_supported`). That is
a single chain of thought kept honest by evidence, not a search over
thoughts.

**Separate roles inside one agent.** Each of the seven questions can go to
a different model (the job table in settings), and evaluation is a
separate component that the agent never sees. There is no second agent.

### What is missing

1. **No search over candidate explanations.** One model question writes
   the hypotheses in one go; nothing generates more candidates than are
   kept, values them separately, or prunes the weak ones. Tree of Thoughts
   (Yao et al., 2023) is exactly that: generate several thoughts, value
   each, keep the best, expand.
2. **No way to compare that against the current step.** Any such step must
   be opt-in and measured with the same harness as the default.

Multi-agent concepts (part 1) are noted only: the Module 5 framework work
is not a focus now (developer's decision, 2026-10-20).

### Built for Module 4

- **Tree-of-thought hypothesize step** (`capstone/agent/tree_of_thought.py`,
  `TreeOfThoughtPolicy`), off by default, turned on with
  `--tree-of-thought` on `python -m capstone.experiment run`. It changes
  only `hypothesize`, at depth one with breadth-first search: one question
  generates up to five distinct candidates (`Candidates`), a second rates
  each sure / likely / impossible with a confidence and a question that
  would tell it apart (`Ratings`), and code (`prune`) keeps at most three:
  dropped are candidates rated impossible, citing evidence never gathered,
  never rated, or ranked below the best three. The survivors become H1, H2,
  ... with their rated confidence and their questions become open
  questions (T1, ...) that test them, so the test stage expands the kept
  branches with real evidence rather than more model thinking. Both
  questions go to the `hypothesize` job's client (the job table is
  unchanged); `thoughts` keeps each tree for the experimenter. Compared
  with the ordinary step on the scripted seed-6 episode through
  `run_experiment`: the same conclusion and a resolved fix, at the cost of
  one more model question. Not yet run live, so whether it helps a real
  model is unknown.
