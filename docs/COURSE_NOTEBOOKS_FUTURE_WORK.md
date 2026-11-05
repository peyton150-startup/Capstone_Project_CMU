# Future work: improvements from the course lab notebooks (2026-11-05)

**Status:** PLANNED / FUTURE WORK ONLY. Reviewed against `main` at `948f40a`. Nothing here is built.
**Gate:** each item needs its own pull request and the teach-first gate (AGENTS.md §1), and should be measured on matched cases before it becomes a default.
**Source:** nine course lab notebooks (introduction to LLMs, tool calling, building a ReAct agent, tree of thoughts, agentic harnesses, MCP, multi-agent coordination, domain RAG, RAG with MMR).
**Related:** [Final report](../evaluation/FINAL_REPORT.md), [Investigation reasoning](INVESTIGATION_REASONING.md), [Run-2 findings](RUN2_FINDINGS_FUTURE_WORK.md), [Episodic memory](EPISODIC_MEMORY.md).

The notebooks were read against the project to find small and medium changes, not a refactor. Most of what they teach is already built (see the list at the end). Six items are planned from the notebooks (P7 from a focused review of the multi-agent notebook; P6 was decided against), and seven more (A1 to A7) refine how evidence enters the reasoning, how hypotheses are kept, and how the two are evaluated together. The goal is better results from the reasoning the agent already has.

## Recommended order

1. P1, audit by default, together with A1 (machine coverage split) and the deterministic parts of A2 (failure funnel). Makes failures measurable without new model calls.
2. A3, question resolution. A correctness fix, built whatever the funnel shows.
3. P2 aggregation tools and A4 line snapshot (sharing one set of functions; A4 is the planned `MVP_SCOPE.md` line-wide packet, refined), with A5 (support counted by distinct signal). Measured in the planned alarm-centered vs line-wide comparison, which should include KA-03 to KA-06, KA-09, KA-07 and KA-08 and the propagated-symptom cases (manufacturing papers item 5).
4. The rest of A2 (hypothesis history and label-based cause matching), then A7.
5. P7 before measuring P3 and P4, so their extra model calls are visible; then P3 and P4 in the critic on/off experiment from the final report.
6. A6 (unanimous pruning) only if the funnel shows the true cause being pruned or deferred.
7. P5, only after memory has run live and its measurement says it is needed.

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

**Refinements (A4):** a batch with zero inspections reports an unknown rate, never 0%; each row keeps passed, failed and total counts. The same functions feed the A4 line snapshot.

**Follow-on:** the reject-rate stop rule from run-2 item 1 becomes cheap to build on `get_inspection_summary`.

**Check:** KA-03 to KA-06 and KA-09 with frozen configuration and `--audit`, before and after. KA-07 and KA-08 must still conclude "no action". Compare tool calls and wall time as well as accuracy.

## P3. Rate each ToT candidate three times (SMALL, reasoning)

**Notebook signal (tree of thoughts):** the paper samples the value prompt three times per state and aggregates, with weights sure 20, likely 1, impossible 0.001.

**Current behavior:** `agent/tree_of_thought.py` asks one valuing question and the default temperature is 0, so each candidate is rated once.

**Change:** rate each candidate three times at a temperature above zero and aggregate in code. Keep the existing rule that "impossible" drops a candidate only with cited factory evidence against it. When the three ratings split (for example one "likely" and one "impossible"), record `rating_split` on that candidate in the ToT trace (`thoughts`). It describes a candidate, not the conclusion, so it does not go on the final label.

**Cost:** two extra calls per investigation compared with today. Record them.

**Refinements:** temperature is set per model, and both ToT questions use the `hypothesize` job, so raising the rating temperature needs its own `value` job in `providers/chat.py` (`JOBS`, `_JOB_SETTING`), as ToT P5 already proposes; generation must stay unchanged. `prune()` keeps the first rating per candidate, so three ratings need an explicit aggregation step, not three `Rating` objects passed in.

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

## Evidence, hypotheses and evaluation: refined plan (2026-11-05)

These items address three themes: what evidence enters the reasoning, how hypotheses are chosen and told apart, and how retrieval and reasoning are evaluated together. Each claim below was checked against `main` at `948f40a`. An outside review of the first draft cited OpenAI and Pydantic AI documentation; those do not apply directly (models are Mistral, Gemini and Groq through OpenAI-compatible endpoints with the project's own `urllib` client, and the code uses `pydantic_graph`, not a Pydantic AI `Agent`), but its code-level points were checked and the valid ones are folded in below.

### A1. Split machine coverage into exposed, targeted and used (SMALL, evaluation)

**Current behavior:** `run_packet.facts_of()` builds `machines_examined` only from explicit `machine_id` tool arguments. A line-wide snapshot or a cross-machine tool would not count, and a machine shown in a snapshot would wrongly look "examined".

**Change:** three facts in place of one:

| Fact | Meaning |
|---|---|
| `machines_exposed` | machines whose readings entered the evidence (snapshot, cross-machine tools, targeted calls) |
| `machines_targeted` | machines named in a tool call the agent chose |
| `machines_used_in_reasoning` | machines whose evidence a hypothesis, question or the conclusion cites |

Lands with P1 and **before** A4, or the snapshot experiment cannot be read.

### A2. Failure funnel per wrong case (MEDIUM, evaluation)

**Purpose:** say where each wrong case first failed, so the next fix is chosen from data. Evaluation only; truth never reaches the agent.

| Stage | Question | How it is decided |
|---|---|---|
| 1 | Was the faulty machine or batch exposed, targeted, used? | code, from A1 |
| 2 | Was the true cause ever proposed? | labels on each hypothesis and candidate claim |
| 3 | Was it proposed, then pruned or deferred? | labels plus the ToT disposition |
| 4 | Was it kept but not selected at the conclusion? | labels plus the conclusion's `hypothesis_id` |
| 5 | Right cause, wrong or missing action? | code, from existing action and resolution scoring |

**Matching free text to causes:** claims are free text, so stages 2 to 4 reuse `evaluation/auto_label.py` (per-fault-kind yes/no, machine ids chosen from ids code found in the text, uncertain answers flagged for review, agreement measured against hand labels) on every hypothesis and candidate claim, not only the conclusion. Anything uncertain is reported as `unknown_requires_review`, never forced into a stage. Code does the funnel logic; cause matching depends on labels.

**Compound and no-fault cases:** classify each true cause separately, then aggregate (KA-09). False-alarm cases use a separate no-fault branch (did the agent invent a cause or propose a fix).

**A structured conclusion cause:** [manufacturing papers item 2b](MANUFACTURING_AGENT_PAPERS_FUTURE_WORK.md#2-action-target-consistency-checks-in-why_not_acted-medium-high) proposes a model-declared `fault_kind` on the conclusion. If built, stage 4 and the episode result compare that field with the truth directly; labels are still needed for hypotheses and candidates. The `unsupported_numbers` count (manufacturing papers item 3) goes in the same pull request as the funnel.

**Prerequisite, hypothesis history:** `AuditRecord` keeps only the final hypotheses and `DecisionRecord` only a `hypothesis_id` per step. Add a structured hypothesis event to the audit each time hypotheses are set or revised: id, claim, stage, cited evidence ids and disposition (active, revised, dropped, contradicted, deferred). These are recorded decisions, not chain-of-thought.

**Prerequisite, full traces:** the 2026-11-04 Snap archive has 5 full traces of 57 episodes. Funnel conclusions need P1 first.

### A3. Keep a question open until it is resolved (SMALL to MEDIUM, reasoning; correctness fix)

**Current behavior (a defect):** in `agent/loop.py`, `gather()` removes a question from `unanswered_questions` as soon as a tool returns valid data, before interpretation. Because its id is then in `state.answers`, `apply_interpretation` cannot reopen it. An insufficient answer closes the question permanently, and `diagnosis_supported` and `check_conclusion` stop counting it. Two tests lock this in: `test_an_answer_closes_the_question_it_was_asked_for` and `test_a_good_answer_is_kept_when_the_policy_fails_to_interpret_it` (`tests/test_agent_loop.py`); they change on purpose.

**Change:**

- Two stores in `InvestigationState`: evidence gathered while attempting a question, and evidence that resolved it.
- The interpretation returns a status for the question it was answering: `resolved` or `insufficient`. A missing status means the question stays open (the same safe default as a missing `assessment`). Only a reply that passes its typed contract can resolve a question.
- Code marks a question `insufficient` on its own only where the tool semantics are clear: a sensor-reading tool with a requested window that returned no samples or too few. An empty `get_events` answer is valid ("no alarms in that window") and is not marked insufficient. A sparse series is not insufficient merely because its first sample is after `from_tick`.
- A controller-recorded `superseded` status for a question whose hypothesis was dropped: it no longer blocks completion and is not counted as resolved.
- Wired into both modes, `interpret()` and `interpret_and_decide()`, and into the critic follow-up check.
- Optional: say explicitly which open questions block completion. Today only questions tied to a current hypothesis do; planning questions with no `hypothesis_id` do not.

The existing budget stop prevents an open question from looping forever.

**Tests:** insufficient answers stay open with their evidence attached; resolved closes; superseded neither blocks nor counts as resolved; empty events resolve; both modes; follow-up.

### A4. Line snapshot at the start of the investigation (MEDIUM, evidence)

**Relation to existing plans (2026-11-05):** this refines the planned [incident-first, line-wide investigation scope](MVP_SCOPE.md#fw-incident-context) (HIGH in `MVP_SCOPE.md`), which already proposes a trigger record, whole-line status, unfiltered cross-machine events and neighbor trends, measured in the [alarm-centered vs line-wide comparison](MVP_SCOPE.md#fw-scope-comparison). Build one feature, not two. A4 adds: sensor summaries for **every** machine (not only the trigger's neighbors), reject counts per batch, the P2 shared functions, A1's coverage split, and A5's distinct-signal counting. **Open question to settle before building:** that plan's "line record" sorts machines into abnormal, apparently unaffected or lacking reliable observations, without saying who decides or by what threshold. If code decides, that conflicts with the rule below (no labels or thresholds). Either the model makes that call from the raw numbers, or the line record keeps only "observed" versus "lacking reliable observations", which code can decide from coverage.

**Current behavior:** `detect_anomaly()` (`agent/monitor.py`) returns at the first alarm or status event, and the investigation starts from that machine. In KA-09 the decoy on CNC-03 set the focus and CNC-07 was never examined. The trigger stays as it is; the change is what the agent sees first.

**Change:** after `observe()` (`agent/investigation.py`), a controller-owned, read-only snapshot recorded as one timestamped evidence item: every machine's status, per-machine summaries of key sensors, reject counts per batch, and current settings. Built from the same functions as the P2 tools.

**Rules:**

- Reads go through the factory provider (and so through `UnreliableProvider` hazards in `episode.py`), never directly through `ObservationTools`. It uses none of the agent's research calls, but its reads and time are recorded.
- Raw numbers only: requested window and actual coverage (`sample_count`, `first_tick`, `last_tick`), units, mean, min, max; passed, failed and total per batch; unknown where data is missing. No labels or thresholds.
- Its own section in the evidence brief within the 8,000-character limit. Every machine's id and status always appears; measurement detail is shortened first.
- Measured with A1, so "shown in the snapshot" is not mistaken for "examined".

**Check:** KA-03 to KA-06 and KA-09 should improve; KA-07 and KA-08 must still conclude "no action" (more data must not invent causes). Compare tool calls and wall time.

### A5. Count supporting evidence by distinct signal (SMALL, reasoning)

**Current behavior:** `diagnosis_supported` (`agent/loop.py`) counts distinct supporting evidence ids against `min_supporting_evidence`. A `get_readings` and a `get_sensor_summary` over the same machine, sensor and window already count as two. A snapshot would add a third view of the same signal. The evidence brief warns about repeated measurements, but the gate does not use that.

**Change:** count support by distinct (machine, sensor, window) signal, not by evidence id, for every tool. Fixes the existing double counting as well as the snapshot case.

### A6. Unanimous three-rating pruning (SMALL; only if A2 shows a pruning problem)

**Idea:** with P3's three ratings, drop a candidate as `contradicted` only when all three usable ratings say impossible and cite factory evidence. Fewer than three usable ratings, or a split, means deferred.

**Why this waits:** three ratings from one model on the same evidence are not independent proofs. More importantly, an unproven "impossible" already ranks below every sure or likely candidate, so with breadth 3 of 5 it usually drops out as `deferred` anyway: the rule would mostly change the label, not the outcome. It only matters if deferred candidates can come back, for example through a bounded reconsideration of one deferred alternative or ToT P5's re-valuation.

**Measure first (A2 stage 3):** how often the true cause is contradicted and how often it is deferred. Build A6 only if either is common.

**Tests (if built):** split votes, missing ratings, a shared wrong contradiction, a correct candidate that is only ranked out (`tests/test_tree_of_thought.py`).

### A7. `retrieved_not_cited` for the manual and memory (SMALL, evaluation)

**Already in place:** `run_packet.py` computes `cited_by_origin` from the conclusion's evidence ids and their provenance.

**Change:** report each manual and memory item at four levels: retrieved, shown to the investigator, cited in a hypothesis, cited in the conclusion. Name the gap `retrieved_not_cited`, not "unused": the manual can legitimately shape which check is asked for without being cited as evidence, because it is guidance, not proof.

### Considered and set aside

- **Phrasing-robustness tests:** the agent's inputs are mostly structured tool JSON; alarm text, manual passages and claims are natural language, but the expected value is low for now. Keep the existing structured-input and uncertainty tests.
- **Confidence calibration:** 13 known cases are too few. Keep the deterministic completion gates and the confident-wrong count; do not treat thresholds such as 0.9 as calibrated probabilities.

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
