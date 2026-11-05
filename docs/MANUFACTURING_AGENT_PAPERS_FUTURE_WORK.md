# Future work: three 2026 manufacturing-agent papers (2026-10-31)

**Status (rechecked 2026-11-05):** Items 1, 2, 4 and 5 are not implemented. Item 3 is **partly implemented**: structured numeric claims are validated in the investigation, but free-text numeric auditing and the proposed evaluator metric are not built. This document tracks remaining experiments; updating it does not change runtime behavior.
**Experiment gate:** The original [baseline scheduling gate](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#scheduling-gate-protect-the-runs-in-progress) applied to the October experiments, now archived. Preserve fixed configurations for any new matched comparison; no new experiment or implementation is authorized by this document.
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

## Implementation cross-check (2026-11-05)

This status check compares `main` source and tests; it is not a live evaluation or proof of improvement. For items 2–5, the distinction between *foundation built* and *proposed change built* matters.

| Item | Status | What remains / priority |
|---|---|---|
| 1. Silent-execution hazard | ❌ NOT BUILT | Existing action verification is not a test of an `execute_action` response that falsely reports a repair starting. Worth an offline failure-path test before real execution integration. |
| 2. Action-target consistency | ❌ NOT BUILT | `why_not_acted()` still checks only action presence, cited evidence and confidence. The provider checks known machine/action names and hydraulic capability, not evidence-to-target or diagnosed-fault-to-action consistency. Worth an **offline, false-block-measured** safety experiment. |
| 3. Numeric claim provenance | 🟡 PARTLY IMPLEMENTED | `NumericClaim`, `verify_numeric_claims()` and their tests already check *structured* evidence-linked arithmetic. Still missing: a check of numbers appearing only in free-text conclusions and a per-case `unsupported_numbers` evaluation field. Reuse the existing verifier; evaluate incremental value before any new gate. |
| 4. Downstream impact at approval | ❌ NOT BUILT | The production-line simulator already models blocked/starved work, but action proposals do not calculate or show downstream downtime effects. Optional operator-UX enhancement; defer until approval context is a demonstrated need. |
| 5. Propagated-symptom attribution case | ❌ NOT BUILT | Line-blocking tests exist, but no dedicated known-answer case measures diagnosis of an upstream cause from a downstream symptom. Worth combining with the [line-wide investigation evaluation](MVP_SCOPE.md#fw-line-scope), not implementing as a parallel experiment. |

Evidence: `capstone-code/capstone/agent/investigation.py` (`why_not_acted`, `check_conclusion`), `agent/evidence_brief.py`, `contracts/hypotheses.py`, `capstone-code/capstone/evals.py`, `tests/test_reasoning_evidence.py`, `capstone-code/capstone/tools/actions.py`, `tests/test_production_line.py`, `capstone-code/capstone/simulator/challenge.py` and `evals/scenarios.json`.

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

**Status (2026-11-05): ❌ NOT BUILT.** Still worth a bounded offline safety experiment, but do not enforce it without measuring false blocks of correct proposed repairs. The current `check_conclusion()` validates gathered IDs and declared numeric claims; neither it nor `why_not_acted()` associates an action's target with the cited machine observations or the fault category.

**Source:** B (deterministic verifier: tag existence, actuatability, control-loop relevance), A (critic checks safety bounds in code).

**Current behavior (verified):** `why_not_acted()` checks only that an action is named, evidence is cited, and confidence reaches `min_action_confidence`. The provider already refuses unknown machines and actions. Nothing checks that the action's machine is the one the cited evidence is about, or that the action kind fits the diagnosed fault (for example a bearing replacement when the cited evidence is a speed setting).

**Change:** add deterministic conditions, each returning a reason as today:

- the target machine appears in at least one cited **observable** evidence record;
- the action kind is allowed for the hypothesis category, from a small fixed table (bearing wear → replace bearing, wrong setting → reset setting, and so on);
- an unknown category is escalated, never guessed.

This fits next to review signal item 3 (safety rules in code), and should share its place in the code.

**Pass criteria:** tests for each refusal reason, and a measured **false-block rate** on correct actions from saved records (B's main weakness was blocking 6 of 8 valid proposals). Keep a rule only if it blocks wrong actions without blocking many right ones. A blocked action is lowered to `escalate`, not dropped.

**Refinement (2026-11-05):** split the change into two checks, because only the first is deterministic today.

- **2a. Target machine in targeted evidence.** The proposed machine must appear in cited observable evidence from a call that *targeted* that machine. Once a line snapshot or a cross-machine tool exists, every machine appears in some cited evidence, so "appears in cited evidence" alone would always pass. Uses `machines_targeted` from [A1 in the course notebooks page](COURSE_NOTEBOOKS_FUTURE_WORK.md#a1-split-machine-coverage-into-exposed-targeted-and-used-small-evaluation).
- **2b. Action fits the fault.** Not deterministic today: the conclusion names its cause only in free text (`Hypothesis.claim`, `AgentConclusion`), with no fault-kind field. Add a model-declared `fault_kind` to the conclusion from a fixed list (`bearing_degradation`, `wrong_setting`, `servo_drive_wear`, `hydraulic_leak`, `bad_material_batch`, `none`, `unknown`), then check the action against a fixed table (bearing to `replace_bearing`, setting to `reset_setting`, servo to `replace_servo_drive`, hydraulic to `repair_hydraulics`; batch, none and unknown allow no repair). A repair proposed for a batch fault is then blocked, since no repair addresses one. The same field gives the [failure funnel (A2)](COURSE_NOTEBOOKS_FUTURE_WORK.md#a2-failure-funnel-per-wrong-case-medium-evaluation) a structured conclusion cause to compare with the truth (hypotheses and candidates still need labels).
- **Expected effect is small at first.** The final report records that the agent rarely proposes a fix, and human approval plus post-action verification already guard actions. The false-block rate will rest on few saved records. Treat this as a safety rule, not an accuracy improvement.

## 3. Numeric claim provenance (MEDIUM, evaluator side first)

**Status (2026-11-05): 🟡 PARTLY IMPLEMENTED — do not rebuild the existing verifier.**

**Source:** A (every non-trivial number maps to a tool output id).

**Already built:** `contracts/hypotheses.py` defines `NumericClaim` (source evidence ID, machine, sensor, metric, value, unit and window). `agent/evidence_brief.py:verify_numeric_claims()` checks structured claims against observable readings, including values, units and time windows. `agent/loop.py` invokes it when interpreting hypotheses; `agent/investigation.py:check_conclusion()` checks declared conclusion claims. `tests/test_reasoning_evidence.py` covers wrong arithmetic, unit mismatch and unverified/out-of-window claims. These checks are not a proof of causality.

**Still missing:** numeric assertions that appear only in the diagnosis's *free text* are not automatically extracted or checked. `capstone-code/capstone/evals.py` does not report the originally proposed `unsupported_numbers` per-case field. An empty `numeric_claims` tuple does not establish that all numbers in prose are grounded.

**Remaining experiment:** evaluate a read-only/offline extractor for value-plus-unit assertions in saved conclusions, match them to gathered source readings with defined rounding and window semantics, and report `unsupported_numbers` per case. Do not mistake ticks, IDs, confidence values or estimated figures for sensor readings. Reuse the existing structured verifier wherever the asserted measurement can be represented as a `NumericClaim`. Make free-text checking a runtime gate only if a measured unsupported-claim problem and an acceptable false-flag rate justify it.

**Pass criteria:** extraction/matching tests with both supported and unsupported examples; count unsupported and ambiguous claims across saved master records; measure false flags. No new model calls.

**Placement (2026-11-05):** build the `unsupported_numbers` count in the same pull request as the [failure funnel (A2)](COURSE_NOTEBOOKS_FUTURE_WORK.md#a2-failure-funnel-per-wrong-case-medium-evaluation): both are evaluator-only reads of saved records. It is a measurement, not a gate.

## 4. Downstream impact shown at approval (LOW-MEDIUM)

**Status (2026-11-05): ❌ NOT BUILT.** Worth retaining as an optional operator-facing improvement, but it should not take priority over causal attribution, verification and pilot-readiness tests.

**Optional (developer, 2026-10-31):** kept on the list, but may not be implemented in the capstone.

**Source:** B (downstream impact check).

**Current behavior (verified):** the simulator already models jobs moving machine to machine and blocking (`simulator.py`, "blocked by"). A proposal shows the machine and action, not what stopping that machine does to the rest of the line.

**Change:** a read-only, deterministic summary attached to the proposal: which downstream machines would be starved or blocked, and for roughly how many ticks, from the repair's known downtime. It informs the human; it never approves or blocks.

**Pass criteria:** seeded tests on a known line layout. No hidden truth in the summary.

## 5. Propagated-symptom evaluation case (LOW-MEDIUM)

**Status (2026-11-05): ❌ NOT BUILT.** Worth a targeted seeded test as part of the existing line-wide context A/B evaluation; do not introduce a second evaluation framework or duplicate its cases.

**Optional (developer, 2026-10-31):** kept on the list, but may not be implemented in the capstone.

**Source:** C (fault attribution degraded when evidence had to cross agents and modules).

**Current behavior (rechecked):** `build_challenge()` puts **two physical faults on the same machine** (bearing wear and wrong setting), with a transient vibration disturbance and sensor drift/dropout on two other machines. It is not an upstream-cause/downstream-symptom attribution test. `tests/test_production_line.py` does demonstrate downstream starvation and upstream blocking when a machine is down; it does not test the agent's root-cause attribution. The 13 known-answer cases in `evals/scenarios.json` have no dedicated propagated-symptom scenario.

**Remaining change:** add a seeded known-answer case in `evals/scenarios.json` in which a demonstrated upstream fault primarily produces a downstream starvation/blocked-machine symptom. Score whether the agent attributes the cause to the upstream machine, not simply to the symptomatic machine; include an evidence trail showing how the simulator caused the propagation. Keep the new case in the [line-wide scope comparison](MVP_SCOPE.md#fw-scope-comparison) so it is measured alongside the alarm-centered baseline. First verify that the simulated symptoms actually occur for the chosen seed.

**Refinement (2026-11-05):**

- **Already planned there; do not add a second case set.** The [scope comparison](MVP_SCOPE.md#fw-scope-comparison) already lists a *wrong-machine alarm* and a *cascading failure* scenario. This item is those scenarios. Build them once, for that comparison.
- **The trigger must land downstream.** `detect_anomaly()` (`agent/monitor.py`) starts an investigation only on `alarm` or `status` events, or on a run of failed inspections. A starved or blocked downstream machine produces job events ("blocked by ..."), not alarm or status events, so it does not start an investigation by itself. The seeded case must make the first trigger a downstream symptom (an alarm or a reject run there) while the cause is upstream. Otherwise the investigation starts at the upstream machine and the case does not test propagation. Check the first trigger for the chosen seed before adding the case.

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
