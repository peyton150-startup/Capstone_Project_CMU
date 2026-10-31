# Future work: three 2026 manufacturing-agent papers (2026-10-31)

**Status:** PLANNED / FUTURE WORK ONLY. Nothing here changes code, tests, the simulator, settings or the runs in progress.
**Gate:** Same as [TOT_CRITIC_EVALUATION_FUTURE_WORK.md](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#scheduling-gate-protect-the-runs-in-progress): finish and score the current baseline runs first.
**Related:** [Multi-agent survey future work](MULTI_AGENT_SURVEY_FUTURE_WORK.md), [Review signal 2026-10-30](REVIEW_SIGNAL_2026-10-30.md) (item 3, deterministic safety rules), [pilot readiness and abstention](MVP_SCOPE.md#high-priority-future-work--pilot-readiness-fast-triage-and-the-rest-of-abstention-updated-2026-10-30).

Each paper was read (paper 2 through its publisher page and a summary, since the full text could not be fetched here) and its ideas checked against `main` (at `17ec5c8`). As in the review signal page, only the verified, new signal is kept. The rest is listed at the end so it is not re-proposed.

## Sources

| # | Paper | What it is | Closest match to this project |
|---|---|---|---|
| A | [Physics-Grounded Multi-Agent Architecture for Traceable, Risk-Aware Human-AI Decision Support in Manufacturing](https://arxiv.org/abs/2605.04003) (Hoang et al., 2026), "MAKA" | CNC machining compensation for titanium blades: central router, analysis agent (every number from a deterministic tool), knowledge-graph agent, critic returning accept / revise / escalate with a revision budget | Critic with bounded recheck; evidence ids; provenance |
| B | [Safe integration of Large Language Models into industrial process control: a multi-agent architecture with P&ID-grounded validation](https://doi.org/10.1007/s43684-026-00136-1) (Schall, 2026) | Process plant: LLM monitors propose, an orchestrator merges, a **deterministic** verifier checks each proposal against the plant diagram, then human approval | Human approval desk; `why_not_acted()` |
| C | [LLM-Driven Multi-Agent Control for Skill-Based Smart Manufacturing](https://arxiv.org/abs/2610.01364) (Köhle et al., 2026) | Modular factory sim: orchestrator vs peer-to-peer vs single agent; "silent faults" where a module reports success but nothing physically happens | Single vs multi-agent cohorts; mandatory post-action verification |

Numbers worth remembering, as reported by the authors (author-built benchmarks, small samples):

- **A:** with 30% of tool hints dropped, the critic raised tool-selection F1 from 0.29 to 0.67. Every number in an answer must map to a tool output id.
- **B:** all 35 injected unsafe proposals in the covered categories were caught, but about 6 of 8 **valid** proposals were also flagged. The LLM found the root cause in every run and still proposed forbidden actions in 10 to 70% of runs, depending on the scenario.
- **C:** single agent and peer-to-peer solved 93%, the orchestrator 87%, but only the orchestrator solved the transport silent fault reliably. Removing state injection lowered the single agent's solve rate. The orchestrator also got stuck in a retry loop on another silent fault (up to about 2M tokens).

## Code vs. model (same rule as the review signal)

| Item | Code | Model |
|---|---|---|
| 1. Silent-execution hazard | Hazard that reports a started repair that never happens; existing verification must catch it | Unchanged: must notice the symptom persists |
| 2. Action-target checks | Block or escalate an action whose machine or kind does not fit the cited evidence; count false blocks | Unchanged: still proposes the action |
| 3. Numeric claim provenance | Find numbers in the diagnosis text and match them to gathered observations | None |
| 4. Downstream impact at approval | Compute which line jobs and machines a stop would block; show it to the human | None |
| 5. Propagated-symptom case | A seeded case where the symptom shows on a different machine than the cause | Must attribute the cause to the right machine |

## 1. Silent-execution hazard (HIGH, offline first)

**Source:** C (silent faults), A (test under degraded conditions).

**Current behavior (verified):** `execute()` in `agent/investigation.py` counts an action as carried out only when the factory confirms it started, then waits for the finish tick, and verification after the action is mandatory. `providers/hazards.py` already injects tool faults (`Timeout`, `Gap`, `StaleRecord`, `Blackout`) but none on the action path. So the rule "a reported success is not proof of a fix" is designed in but never tested against a factory that lies about the repair.

**Change:** an opt-in hazard (for example `SilentExecute`) on the `execute_action` call: it returns a normal started/finish reply but does not pass the call through, so the machine is unchanged. It sits at the tool boundary like the others, fires on a fixed schedule, and is recorded in the hazard log.

**Pass criteria:** an offline scripted test where the verification step reports the symptom still present and the investigation ends unresolved, not "fixed"; the memory gate refuses the lesson (`intervention_not_successful`); no repeated re-execution loop (C's orchestrator failure). A live run is Codex's job after merge.

## 2. Action-target consistency checks in `why_not_acted()` (MEDIUM-HIGH)

**Source:** B (deterministic verifier: tag existence, actuatability, control-loop relevance), A (critic checks safety bounds in code).

**Current behavior (verified):** `why_not_acted()` checks only that an action is named, evidence is cited, and confidence reaches `min_action_confidence`. The provider already refuses unknown machines and actions. Nothing checks that the action's machine is the one the cited evidence is about, or that the action kind fits the diagnosed fault (for example a bearing replacement when the cited evidence is a speed setting).

**Change:** add deterministic conditions, each returning a reason as today:

- the target machine appears in at least one cited **observable** evidence record;
- the action kind is allowed for the hypothesis category, from a small fixed table (bearing wear → replace bearing, wrong setting → reset setting, and so on);
- an unknown category is escalated, never guessed.

This fits next to review signal item 3 (safety rules in code), and should share its place in the code.

**Pass criteria:** tests for each refusal reason, and a measured **false-block rate** on correct actions from saved records (B's main weakness was blocking 6 of 8 valid proposals). Keep a rule only if it blocks wrong actions without blocking many right ones. A blocked action is lowered to `escalate`, not dropped.

## 3. Numeric claim provenance (MEDIUM, evaluator side first)

**Source:** A (every non-trivial number maps to a tool output id).

**Current behavior (verified):** evidence ids are checked in code, but the diagnosis is free text, and numbers in it (a vibration level, a temperature, an rpm) are not checked. The review signal already notes that "free-text wording in the diagnosis is not checked by code".

**Change:** start as a scoring field, not a gate: extract numbers with units from the conclusion and check each against the values in the gathered evidence (within rounding). Report `unsupported_numbers` per case in `evals.py`. Make it a gate only if the counts show it is a real problem.

**Pass criteria:** unit tests on extraction and matching; a count over the saved master records. No model calls.

## 4. Downstream impact shown at approval (LOW-MEDIUM)

**Source:** B (downstream impact check).

**Current behavior (verified):** the simulator already models jobs moving machine to machine and blocking (`simulator.py`, "blocked by"). A proposal shows the machine and action, not what stopping that machine does to the rest of the line.

**Change:** a read-only, deterministic summary attached to the proposal: which downstream machines would be starved or blocked, and for roughly how many ticks, from the repair's known downtime. It informs the human; it never approves or blocks.

**Pass criteria:** seeded tests on a known line layout. No hidden truth in the summary.

## 5. Propagated-symptom evaluation case (LOW-MEDIUM)

**Source:** C (fault attribution degraded when evidence had to cross agents and modules).

**Current behavior (verified):** `build_challenge()` already puts different faults on three machines, and worn machines already work more slowly. What is not checked is the case where the **symptom** is on one machine (a downstream machine idle or blocked) and the **cause** on another.

**Change:** a seeded scenario in `evals/scenarios.json` where an upstream fault shows mainly as downstream starvation, scored on whether the agent names the upstream machine. Check first that existing cases do not already cover it.

## Already done or not adopted (do not re-propose)

- **Critic with accept / revise / escalate and a revision budget (A).** Built: critic verdict, one bounded read-only recheck with its own window (`CRITIC_FOLLOWUP_SECONDS`), and weak interventions lowered to `escalate` with the reason recorded.
- **Evidence ids required for claims (A).** Built: conclusions and hypotheses citing ungathered evidence are refused.
- **Degraded-tool testing (A).** Built: `providers/hazards.py`. Item 1 only adds the action path.
- **State injection every turn (C).** Built: each model question is given a view built by code from the investigation state, not from chat history.
- **Tool gating (C).** Built: provider allowlist; approval is never offered to the agent.
- **Comparing single vs multi-agent (C).** Built: cohorts A to D in the [comparison matrix](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#controlled-comparison-matrix).
- **Several faults on different machines (C).** Built: `build_challenge()`.
- **Knowledge graph (A).** Not adopted: manual RAG and Chroma recall stay unless a graph shows a measured gain.
- **MQTT, signed messages, one MCP server per module (B, C).** Not adopted: one process, in-process `FactoryProvider`; MCP stays Future Work 2's decision.
- **Weighted voting across several monitor agents (B).** Not adopted: adds sequential model calls (see [Not planned: a third agent](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#not-planned-a-third-agent-for-speed)).

When any item here is built, credit its paper in README "Research basis" in the same PR (AGENTS.md §11, step 9).
