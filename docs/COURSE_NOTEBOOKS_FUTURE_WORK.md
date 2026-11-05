# Future work: improvements from the course lab notebooks (2026-11-05)

**Status:** PLANNED / FUTURE WORK ONLY. Reviewed against `main` at `948f40a`. Nothing here is built.
**Gate:** each item needs its own pull request and the teach-first gate (AGENTS.md §1), and should be measured on matched cases before it becomes a default.
**Source:** nine course lab notebooks (introduction to LLMs, tool calling, building a ReAct agent, tree of thoughts, agentic harnesses, MCP, multi-agent coordination, domain RAG, RAG with MMR).
**Related:** [Final report](../evaluation/FINAL_REPORT.md), [Investigation reasoning](INVESTIGATION_REASONING.md), [Run-2 findings](RUN2_FINDINGS_FUTURE_WORK.md), [Episodic memory](EPISODIC_MEMORY.md).

The notebooks were read against the project to find small and medium changes, not a refactor. Most of what they teach is already built (see the list at the end). Six items are planned (P7 from a focused review of the multi-agent notebook); P6 was considered and decided against. The goal is better results from the reasoning the agent already has.

## Recommended order

1. P1, audit by default (makes every later change measurable).
2. P2, aggregation tools and wider numeric verification.
3. A matched run on KA-03 to KA-06 and KA-09 before and after P2.
4. P3 and P4, measured in the critic on/off experiment from the final report.
5. P5, only after memory has run live and the measurement below says it is needed.
6. P7 before measuring P3 and P4, so their extra model calls are visible.

## P1. Audit log on by default (SMALL, evaluation)

**Notebook signal (agentic harnesses):** a production harness emits its loop as an event stream (every model step, tool call, input, output and stop reason). That stream is what makes a run inspectable.

**Current behavior:** `experiment.py` writes an audit log only when `--audit PATH` is given. The final report (R1, question 12) records that no master run kept its evidence, so "evidence-grounded" cannot be judged.

**Change:** write the audit log by default to a path derived from the run name, with an explicit opt-out. No reasoning changes.

**Check:** every new run produces a packet that `evaltools.run_packet` can read.

## P2. Aggregation tools: code computes, the model interprets (MEDIUM, tools)

**Notebook signal (agentic harnesses, from the SWE-agent paper; tool calling, part 1):** with the model held fixed, how tools present their output changes success. LLMs are unreliable at arithmetic and tallying.

**Current behavior, matching the persistent failures:**

- Batch faults (KA-03, KA-04) are never diagnosed. `get_inspections` returns one row per job, and `evidence_brief.py` lists those rows. Nothing computes a reject rate per batch, so the model must tally rows itself. No sensor moves for a bad batch, so the tally is the only signal.
- Setting faults (KA-05, KA-06) are never diagnosed. `get_settings` hides standard speeds and every summary tool covers one machine. On a serial line, routes cannot single out a machine (run-2 item 4). Only comparing machines with each other works, and no tool does that.
- In KA-09 the agent never examined CNC-07, where the real faults were. A view of the whole line would have shown CNC-07 as the outlier.

**Change:** two read-only research tools, built through the existing `run_tool` contract:

1. `get_inspection_summary(from_tick, to_tick, group_by)` with `group_by` of `batch` or `window`: passed, failed, total and reject rate per group.
2. `compare_machines(sensor, from_tick, to_tick)`: one row per machine with count, mean, minimum and maximum, plus mean job time and current rpm.

Optionally the same per-batch tallies go into the evidence brief.

**Rules that keep the reasoning test honest:**

- The tools return numbers only. No "abnormal", "bad batch" or "outlier" labels, no hidden thresholds, no simulator truth (the evidence brief rules already say this). The model still decides whether a number is normal, using the manual and the other batches or machines as its baseline.
- Extend `NumericClaim` so reject rates and comparison values are verifiable metrics. A misstated count is then refused before it is applied, the same way a misstated sensor mean is now.
- Known limit: numbers written only in prose are not extracted or checked today (`INVESTIGATION_REASONING.md`). To close that, a supported conclusion could require a structured claim for every number it depends on, or treat an uncited number as unverified.

**Follow-on:** the reject-rate stop rule from run-2 item 1 becomes cheap to build on `get_inspection_summary`.

**Check:** KA-03 to KA-06 and KA-09 with frozen configuration and `--audit`, before and after. KA-07 and KA-08 must still conclude "no action". Compare tool calls and wall time as well as accuracy.

## P3. Rate each ToT candidate three times (SMALL, reasoning)

**Notebook signal (tree of thoughts):** the paper samples the value prompt three times per state and aggregates, with weights sure 20, likely 1, impossible 0.001.

**Current behavior:** `agent/tree_of_thought.py` asks one valuing question and the default temperature is 0, so each candidate is rated once.

**Change:** rate each candidate three times at a temperature above zero and aggregate in code. Keep the existing rule that "impossible" drops a candidate only with cited factory evidence against it. When the three ratings split (for example one "likely" and one "impossible"), record `rating_split` on that candidate in the ToT trace (`thoughts`). It describes a candidate, not the conclusion, so it does not go on the final label.

**Cost:** two extra `hypothesize` calls per investigation. Record them.

## P4. Separate uncertainty labels, including self-consistency (MEDIUM, reasoning and evaluation)

**Notebook signal (multi-agent coordination, "More Agents Is All You Need", Li et al. 2024):** sampling the same task several times and comparing the answers improves accuracy, and disagreement between samples is a cheap uncertainty signal.

**Current behavior:** `assessment` is `supported` or `unresolved`. Unresolved can come from the model or from the controller's completion checks. Agent and critic disagreement is partly tracked (`verdict_mismatch`, `recheck_trigger`) but not on the final label. Run-to-run variance is unmeasured (X2).

**Change:** keep `assessment` as it is and add a field `uncertainty_reasons`, which can hold several values at once:

| Reason | Meaning | Source |
|---|---|---|
| `unresolved` | the model says it is not sure, or the controller blocks the conclusion (open questions, unverified numbers) | existing completion checks |
| `inconsistent` | repeated conclusions name different causes | the final conclusion asked three times |
| `contested` | the critic made a serious objection and the final answer did not address it | critic verdict and the follow-up result |

`inconsistent` is the agent disagreeing with itself; it does not involve the critic. `contested` is the agent and critic disagreeing. A case can carry both, which is why this is a list rather than one status. Either new reason escalates to a human like `unresolved` does.

**Reporting:** the batch table reports each reason separately (for example "4 inconsistent, 2 contested, 3 unresolved") beside confident-wrong and false-intervention counts.

**Check:** confident-wrong conclusions should fall without many right answers turning uncertain. Record the extra calls and wall time.

## P5. MMR for memory recall (SMALL, memory; gated on a measurement)

**Notebook signal (RAG with MMR):** relevance-only top-k fills the context with near-duplicates when the store holds many similar documents. Fetch more candidates, then select with MMR to balance relevance and diversity.

**Current behavior:** `memory/semantic.py` takes Chroma's top `k` (default 5). `memory/repository.py` refuses exact duplicates only (same investigation or same fingerprint). The near-duplicate check in `memory/duplicate_threshold.py` is a measurement, not called by the service, and its threshold deliberately lets some duplicates through because "letting a duplicate through only crowds recall". Storage deduplication decides what is kept; MMR would decide which kept memories reach the prompt.

**Measurement first:** after filling the store on tuning seeds, run representative recall queries and record the pairwise similarity of the top five. If it is usually above about 0.9, build MMR. If results are already varied, defer.

**Change, if needed:** fetch about 20 candidates with their embeddings and select 5 with MMR (lambda about 0.6). The keyword fallback is unchanged.

**Check:** `memory_comparison run --known`, MMR on versus off.

## Multi-agent coordination notebook: focused review

The multi-agent coordination notebook (Part 1: agent count, roles, one-way / two-way / brainstorm protocols; Part 2: conditional routing, capped revise-and-review loops, failover, benchmarking by quality and cost) was reviewed on its own against `main`. Most of it is already built or already decided against (see the list below). One item is planned (P7), one was decided against (P6), and two notes connect it to existing plans.

### P6. Capped second critic round: DECIDED AGAINST (2026-11-05)

**Notebook signal (Part 2):** a reviewer and reviser loop that repeats until the review passes or a retry cap is reached.

**Decision:** not planned. A second round would only run on cases where a serious critic objection survives the follow-up, which is a small subset of the master runs, so it would add model calls and wall time for little expected gain. The current design stays: one critic pass and at most one follow-up check, no repeated critic cycle (`INVESTIGATION_REASONING.md`). Cases where the objection survives end `contested` (P4) and escalate to a human instead.

### P7. Cost per correct diagnosis in the batch table (SMALL, evaluation; extends an existing table)

**Notebook signal (Part 2, benchmarking):** compare configurations by quality per unit of effort, not quality alone.

**Already in place (do not rebuild):** each run records its model calls (`ExperimentRecord.model_calls`, a `CallSummary`; progress row E1, reported by `format_model_calls`). The rubric's batch table (`evaluation/EVALUATION_RUBRIC.md`) already has means over reasoned runs for tool calls, factory calls, wall seconds, model questions, invalid replies and outage attempts. Token cost is not measured (audit X3). `MVP_SCOPE.md` already lists tool/model calls, tokens and p50/p95 wall time for its wider-scope experiment.

**What is missing:** those are means per run. Nothing divides cost by correct outcomes, so a configuration that adds calls and gets more cases right cannot be compared fairly with one that is cheaper and gets fewer right. P3 and P4 each add model calls, so this matters before they are measured.

**Change:** add one row to the rubric's batch table: total model questions, tool calls and wall seconds divided by the number of `fully_right` cases (shown as "n/a" when there are none). Computed from records already kept; no new recording. Tokens stay out until X3 is addressed.

**Check:** a record test on a scripted batch; no live run needed.

### Notes that connect to existing plans

- **Routing the critic like the branching.** The notebook's conditional routing (and its cited protocol-router result) matches ToT [P3 adaptive branching](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#p3--adaptive-branching-and-explicit-controller-limits---not-built). When P3's ambiguity controller is built, let the same observable signals also choose how much critic work a case gets (no follow-up on a clear case, the follow-up on an ambiguous one). No separate controller.
- **Distractors and the Line Sentinel.** The notebook cites a benchmark where a single agent degrades sharply as distractors are added. KA-09 has a deliberate distractor (the harmless CNC-03 spike) and the agent never reached CNC-07. That supports the [Line Sentinel](THIRD_AGENT_LINE_SENTINEL_FUTURE_WORK.md) design. P2's `compare_machines` is the cheap deterministic first step: build it first, and the Sentinel can use it later instead of new code.

### Already covered from this notebook (do not re-propose)

- **Minimal agent count and distinct ownership:** two roles today, a third designed only where it owns distinct information (Line Sentinel).
- **Brainstorm protocol:** ToT generate, value and prune.
- **Two-way protocol:** the critic's structured `check_request`, executed by the controller.
- **Explicit graph with conditional edges:** Pydantic Graph stages and gates. Switching to LangGraph would change nothing the project needs.
- **MCP-style tool registry with validation:** `run_tool` checks requests and answers against contracts.
- **Failover:** `FallbackClient` per job with per-question time limits; tool errors are returned, not raised into the loop.
- **Majority voting across agents:** covered by P4's self-consistency check.
- **Repeated review and revise loops:** decided against (P6).

## Worth learning, not building now

- **MCP server for the tools** (MCP notebook): wrapping `ObservationTools` in FastMCP with the manual as a resource is a good learning exercise but does not change reasoning. Stays deferred as in [Future Work 2](MVP_SCOPE.md#future-work-2--mcp-architecture-observability-and-response-verification).
- **Coordination protocols** (multi-agent notebook): the critic already runs a bounded two-way exchange (one structured check). The blind critic ([survey item 1](MULTI_AGENT_SURVEY_FUTURE_WORK.md)) is the next step there.
- **RAG fundamentals** (DPR, RAG-Sequence and RAG-Token) and the introduction notebook: background only.

## Already done (do not re-propose)

- ReAct-style loop with structured tool calls and a fixed procedure (`agent/loop.py`).
- ToT at depth one with code-side pruning and evidence-cited "impossible" (`agent/tree_of_thought.py`).
- Deterministic verification of numeric claims (`NumericClaim`), the code-side counterpart of the notebook's Python verifier.
- Harness-owned state and a bounded evidence brief (`agent/evidence_brief.py`).
- Permission gate: human approval before any action, and post-action verification.
- A project memory file for coding agents (`AGENTS.md`, imported by `CLAUDE.md`).
