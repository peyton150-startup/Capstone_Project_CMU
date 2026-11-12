# Triage-only future work — 31 active proposals (28 HIGH/P0-dependent, 3 MEDIUM)

**Status:** Documentation only; proposed backlog, 2026-11-12. No runtime behavior, settings, Python functions or tests were changed by this PR.

**New measured evidence (2026-11-12):** [A0 live-model baseline: 26 cases, latency/coverage, unsafe KA-09 no-action](benchmarks/2026-11-12-triage-a0.md). This is experimental evidence and does not implement any proposed TRI item.

**Algorithm-first LLM replacement research (2026-11-12):** [Code-audited, source-cited ranked synthesis of all five research passes](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md). Its 36 ranked methods/alternatives are **not 36 new backlog items**. The 31 active IDs, exactly three MEDIUM, three-stage Siemens boundaries, frozen A0 and existing A1–A4 ablations remain authoritative. [PR #246](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/246) is reviewed as a separate **open/unmerged code PR** at this source-audit point; do not mark its clearance fixes implemented on main.

**Merge preparation:** Reconciled with current `main` documentation on 2026-11-12, retaining subsequent progress entries; runtime code remains untouched.

## Hard scope boundary

**Every active item in this register is exclusively for rapid triage:** simulator `InvestigationState.mode="triage"` and the recorded/real-machine **read-only triage** entry point. This register does **not** authorize changing the deep/full investigation graph, critique, intervention, execution, verification, memory, deep-mode prompts or deep-mode budgets. Future implementations must be gated on triage mode and OFF by default until tested. Reuse shared helpers only with explicit deep-mode regression proof.

**Cross-cutting safety dependency distinction:** Siemens SDC-01–20 and RMI-01–07, controller authorization, the collector, and shared telemetry quality remain independently mandatory under their existing owner categories. Items TRI-05/06/07/26/27 describe only how validated output is *consumed by triage*; they must not relocate, reduce or duplicate shared controller obligations.

**Code review basis:** `main` `3b7d64c5` (2026-11-11), 2026-11-12 [Notion triage upgrade review](https://app.notion.com/p/4164c6e4d2e5817fafeee9eedb114eca) and follow-up corrections. The prediction that current 90-second triage makes roughly two reads but interprets one comes from older deep-run medians, **not a live triage measurement**. Run TRI-01 first.

**Labels:** HIGH = correctness/traceability or near-term independent experiment; P0-dependent = triage-only consumer of separately mandatory Siemens acceptance; exactly three MEDIUM = conditional refinements. **No active LOW.** Retired IDs are never reused. Simulator evidence gathering is proved before Siemens-specific use.

**Evidence-audit mapping, all 12 former HIGH findings covered:** H1→TRI-17; H2→TRI-31; H3→TRI-06/21; H4→TRI-32; H5→TRI-22; H6→TRI-34; H7→TRI-33; H8→TRI-04; H9→TRI-22; H10→TRI-18; H11→TRI-27; H12→TRI-19. Cross-cutting requirements remain in TRI-01–23; the new high entries are only gaps, not duplicate tickets. Statistical-trigger handoff TRI-27 is promoted to HIGH; TRI-25, TRI-26 and new TRI-35 are the **only three MEDIUM** candidates. TRI-24, TRI-28, TRI-29 and TRI-30 are removed from the active register with their still-useful acceptance criteria consolidated elsewhere.

## Priority map — active items only, signal-first within triage

**28 HIGH/P0-dependent and exactly 3 MEDIUM, no active LOW.** These are options to validate, not a mandate to implement all before the factory visit. IDs remain stable.

| ID | Priority | Triage-only work item |
|---|---|---|
| [TRI-01](#tri-01) | High / measure first | Measure actual 90-second A0 triage baseline |
| [TRI-02](#tri-02) | High / correctness | Block unsupported no-action and false clearance |
| [TRI-03](#tri-03) | High / correctness | Fix rival-separating unanswered question logic |
| [TRI-04](#tri-04) | High / correctness | Count independent physical supporting sources |
| [TRI-05](#tri-05) | P0-dependent / triage consumer | Bridge approved Siemens OPC UA records into triage |
| [TRI-06](#tri-06) | P0-dependent / triage consumer | Apply qualified data and dual-cutoff gates |
| [TRI-07](#tri-07) | High / correctness | Match advertised capabilities to permitted triage tools |
| [TRI-08](#tri-08) | High / reliability | Enforce full triage runtime deadline |
| [TRI-09](#tri-09) | High / correctness | Use recorded single-machine triage prompts |
| [TRI-10](#tri-10) | High / product | Build standalone triage report |
| [TRI-11](#tri-11) | High / measurement | Expose honest diagnostic-read budget accounting |
| [TRI-12](#tri-12) | High / efficiency | Gate manual retrieval during short triage |
| [TRI-13](#tri-13) | High / experiment | Generate tentative hypotheses in first question |
| [TRI-14](#tri-14) | High / dependent experiment | Route hypotheses-first triage through graph |
| [TRI-15](#tri-15) | High / experiment | Ablate bounded batch sizes |
| [TRI-16](#tri-16) | High / experiment | Reduce collected but uninterpreted reads |
| [TRI-17](#tri-17) | High / evidence | Reproducible source-linked triage evidence packet |
| [TRI-18](#tri-18) | High / discrimination | Offline fault signatures and pairwise isolability |
| [TRI-19](#tri-19) | High / selection experiment | Deterministic diagnostic-value prioritization of optional reads |
| [TRI-20](#tri-20) | High / dependent experiment | Structured provisional expectations |
| [TRI-21](#tri-21) | High / evidence validity | Window-, quality-, source- and cutoff-aware read coverage |
| [TRI-22](#tri-22) | High / false-negative control | No-fault, unknown, wrong-machine and multi-fault coverage |
| [TRI-23](#tri-23) | High / prompt validity | Audit actual model visibility of selected evidence |
| [TRI-27](#tri-27) | High / detection | Calibrate persistent statistical onset and incident handoff |
| [TRI-31](#tri-31) | High / collection efficiency | Fix evidence-call budget and fixed-order starvation |
| [TRI-32](#tri-32) | High / evaluation integrity | Score actual returned relevant evidence rather than requested tool name |
| [TRI-33](#tri-33) | High / screening fidelity | Preserve screening window/count/reference/coverage metadata |
| [TRI-34](#tri-34) | High / falsification | Select counterevidence that distinguishes competing faults |
| [TRI-25](#tri-25) | Medium / conditional | Aligned multi-window cross-sensor and temporal features |
| [TRI-26](#tri-26) | Medium / conditional | Comparable own-machine operating reference windows |
| [TRI-35](#tri-35) | Medium / conditional | Selective batch, job-route and quality context |

## Algorithm-first triage: highest-signal replacement tracks (no new TRI IDs)

The [research appendix](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md) code-audits `ModelPolicy.plan/decide/interpret/interpret_and_decide/hypothesize/conclude`, `ReasoningPolicy`, `run_inner_loop`, `gather`, screening, recorded-data capabilities, the A0 trace and **open PR #246**. It links primary MIT, Berkeley, Stanford, CMU, Cornell, UCR, TRACTIAN and manufacturing-inspection sources, with assumption and data-fidelity cautions.

| Sequence | Algorithmic ownership goal | Existing active work item | Decision and gate |
|---|---|---|---|
| **0 — correctness** | Executable question satisfaction; relevant physical source roots and unresolved rival checks; independent expected-machine roster for supported `no_action` | TRI-02/03/04/21/22/33 | **Before** performance claims; augment PR #246 acceptance rather than duplicate its implementation |
| **1 — quality** | Typed qualified incident packet + valid, constrained tool arguments + true returned/visible-evidence scoring | TRI-05/06/07/08/11/17/23/31/32/33 | Existing budget, hidden-truth firewall, simulator and recorded-machine separate gates |
| **2 — model call removal** | Python-generated standard `plan`, typed temporal `interpret`, contingent Python `decide` and bounded fallback to original LLM | TRI-13/14/16/19/20/21/34 | Separate **B** experiment arms; **not** a silent replacement for existing A1 hypotheses-first or A2 batching |
| **3 — optional causal engines** | Validated fault signatures, support/conflict matrix and bounded MIT-style consistency-based candidate generation for single and simultaneous faults | TRI-04/18/20/22/34 | **Offline first**, unknown fault retained; not full model-based physics diagnosis without validated system constraints |
| **4 — data-dependent ML** | Tree, logistic/forest, numeric kNN or detector alternatives only after representative labeled or well-sampled telemetry | TRI-18/19/25/26/27/35 (conditional) | Beat transparent Python baseline on held-out seeds, unseen machines, decoys, missing/compound faults; no blanket neural-network upgrade |

**Scope/priority preservation:** This table refines existing items; it does **not** activate retired TRI-24/28/29/30 or create additional MEDIUM items. Monitor/anomaly score integration (TRI-27) remains a separately measured **shadow-mode** experiment. Do not copy TRACTIAN's proprietary/large distributed inference infrastructure or claim its self-reported JANUS five-case benchmark validates this capstone.

## Detailed implementation and adoption requirements

<a id="tri-01"></a>

### TRI-01 — Measure actual 90-second A0 triage baseline

**Priority:** High / measure first. **Triage-only proposal:** Run `TRIAGE_THEN_DEEP=off` on fixed known-answer and recorded-path scenarios; log planning, decision, interpretation and conclusion latency, interpreted versus uninterpreted reads, p50/p95, timeouts, false no-action, missed severe faults.

**Acceptance / rejection test:** Reject timing claims inferred only from deep-run medians; freeze controls and record spread across seeds.

**Measured A0 (2026-11-12):** [Both 13-case repetitions documented here](benchmarks/2026-11-12-triage-a0.md): p50 87 s in each, p95 89/90 s, 25/26 timeouts, 6/26 entering `hypothesize`, 2/26 entering `test`, zero new test-stage readings, one unsafe `supported/no_action` on KA-09. The baseline is measured; other triage improvements remain proposals. Root-cause correctness was not judged; stage visits are not hypothesis counts.

<a id="tri-02"></a>

### TRI-02 — Block unsupported `no_action` and false clearance

**Priority:** High / correctness. **Triage-only proposal:** In triage completion, require qualified relevant normal-operation evidence before supported `no_action`. An incidental `get_time` or citation alone is not proof of health.

**Acceptance / rejection test:** Block timestamp-only supported no-action; allow genuinely supported healthy observations, even with no generated fault hypotheses.


**Algorithm-first cross-reference (2026-11-12):** [PR #246](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/246) is an OPEN/UNMERGED triage-only fix for no-hypothesis and simulator screening coverage. Review its exact safety behavior rather than build a competing guard. An omitted **non-alarmed** machine is not necessarily identified from the returned screening map: require comparison with a validated independent expected-machine roster, plus quality/cutoff and unanswered rival checks. Reconcile legitimate benign `no_action` cases with the PR's more conservative no-hypothesis rule before adoption. See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-03"></a>

### TRI-03 — Fix rival-separating unanswered question logic

**Priority:** High / correctness. **Triage-only proposal:** Triage checks in `diagnosis_supported` and `conclusion_gaps` must consider `hypothesis_id` AND `distinguishes_hypothesis_ids`; gate changes to triage or separately test shared fix against deep mode.

**Acceptance / rejection test:** A question about H1 versus H2 with no primary hypothesis remains open and prevents false supported closure.

**Code audit reinforcement:** `agent/loop.py:diagnosis_supported` currently checks whether any unanswered question's primary `hypothesis_id` is active; it does not check the question's `distinguishes_hypothesis_ids`. Triage-specific negative tests must keep H1-versus-H2 discrimination open even when the primary ID is null. Do not silently alter deep semantics.

<a id="tri-04"></a>

### TRI-04 — Count independent physical supporting sources

**Priority:** High / correctness. **Triage-only proposal:** Group triage evidence by actual controller/machine/spindle/axis/native-channel source roots; a raw reading, computed summary and derived OEM alarm do not count as independent sources.

**Acceptance / rejection test:** A repeated physical source never satisfies the two-supporter bar by itself; preserve SDC/RMI source lineage.

**Code audit reinforcement:** `agent/loop.py:diagnosis_supported` counts distinct observable evidence IDs, not distinct underlying physical sensors; derived load score + load summary + load alarm is one root family. This scope is triage only; the pre-existing RMI-07 field safety requirement remains mandatory independently.

<a id="tri-05"></a>

### TRI-05 — Bridge approved Siemens OPC UA records into triage

**Priority:** P0-dependent / triage consumer. **Triage-only proposal:** Map quality-qualified `OpcUaDataChange` from the merged Siemens collector into triage-only read tools; existing `providers/replay.py` uses legacy `TelemetryRecord` and is not automatically compatible.

**Acceptance / rejection test:** Offline fixtures confirm read-only tool parity, native types, status codes, source identity and cutoffs; shared collector security remains under SDC/RMI.

<a id="tri-06"></a>

### TRI-06 — Apply quality and dual-cutoff gates to triage evidence

**Priority:** P0-dependent / triage consumer. **Triage-only proposal:** Require valid StatusCode, units, coverage, freshness, source epochs and observation-versus-receipt cutoffs before triage uses values as supporting evidence.

**Acceptance / rejection test:** Unknown, stale, Bad, missing, delayed or future-known readings cannot establish health; do not bypass SDC-01–20/RMI-01–07.

**Code audit reinforcement:** `agent/incident_context.py` currently treats trigger-time event history and current status/settings snapshots as different times, and `model_policy.py:render` warns of that mismatch. Preserve both actual observation time and evidence receipt time when selecting and rendering a simulator or qualified recorded triage packet.

<a id="tri-07"></a>

### TRI-07 — Match advertised triage capabilities to dispatch

**Priority:** High / correctness. **Triage-only proposal:** Offer only currently approved, present and quality-qualified signals and bounded history windows; revalidate capability permissions when executing a triage tool.

**Acceptance / rejection test:** One old valid sample does not imply a currently usable channel; unknown tools or revoked channels fail closed.

<a id="tri-08"></a>

### TRI-08 — Enforce the full triage runtime deadline

**Priority:** High / reliability. **Triage-only proposal:** Bound provider calls and batches as well as model questions; preserve safe unresolved reporting if any component is blocked or exceeds its allowance.

**Acceptance / rejection test:** Clock-controlled tests include slow tools/models; deep-mode budgets and execution are unchanged.

<a id="tri-09"></a>

### TRI-09 — Use recorded single-machine triage prompts

**Priority:** High / correctness. **Triage-only proposal:** Replace simulated-line terminology and mandatory neighbor/inspection instructions with mode-specific, capability-aware real-CNC guidance, including same-machine historical comparisons.

**Acceptance / rejection test:** Single-machine recorded triage never invents unavailable machines, inspections, simulator ticks or machine actions.

<a id="tri-10"></a>

### TRI-10 — Build a standalone triage report

**Priority:** High / product. **Triage-only proposal:** Emit typed triage-only `supported`, `unresolved`, or `insufficient_evidence` with tentative cause ranking, support, contradictory evidence, unknowns, unavailable channels and ordered technician checks.

**Acceptance / rejection test:** No model and timeout paths produce conservative useful reports; do not assume a deeper investigation will run.

<a id="tri-11"></a>

### TRI-11 — Expose honest diagnostic-read budget accounting

**Priority:** High / measurement. **Triage-only proposal:** Separately record mandatory `get_time`, screening, optional manual reads, other research tools and model questions. Six research calls can mean five after time and four after simulator manual retrieval.

**Acceptance / rejection test:** Do not hide `get_time` in line-screening counters; any changed allowance must be explicit, measured and triage-only.

<a id="tri-12"></a>

### TRI-12 — Gate manual retrieval during short triage

**Priority:** High / efficiency. **Triage-only proposal:** Use manual search only for specific worthwhile triage questions and remaining budget; real-machine references must match the actual licensed machine/version.

**Acceptance / rejection test:** Compare manual-on/off triage without sacrificing critical readings; no simulator manual passed off as OEM evidence.

<a id="tri-13"></a>

### TRI-13 — Generate tentative hypotheses in triage's first question

**Priority:** High / experiment. **Triage-only proposal:** Opt-in `TRIAGE_HYPOTHESES_FIRST` creates two to four potential explanations and discriminating questions early, retaining normal workload, unknown cause and concurrent faults.

**Acceptance / rejection test:** A1 versus unchanged A0 improves hypothesis coverage and safe diagnostic utility without raising p95 or false no-action.


**Algorithm-first cross-reference (2026-11-12):** Add a separate **Python question-template `plan()` replacement experiment** for known triage symptoms (with unknown/novel fallback). This is **not** the existing model hypotheses-first A1; do not compare them as one variable or change the deep graph. Generate questions containing required observable channel/state/window and explicit `unknown`. See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-14"></a>

### TRI-14 — Route hypotheses-first triage through the graph

**Priority:** High / dependent experiment. **Triage-only proposal:** Modify both `plan()` and the typed Pydantic Graph `plan_step` route when the flag is enabled; preserve existing investigate/deep transitions and termination records when disabled.

**Acceptance / rejection test:** Graph tests show valid triage branches, no-evidence fallbacks, and bit-for-bit deep-mode control-flow compatibility.

<a id="tri-15"></a>

### TRI-15 — Ablate bounded batch sizes instead of forcing five reads

**Priority:** High / experiment. **Triage-only proposal:** Compare `DECIDE_CALLS` 1, 2, 3 and 5 only in triage; batch independent reads when the result of the first would not change the need for the rest.

**Acceptance / rejection test:** A2 changes isolate the effect of batching and avoid extra redundant reads, unneeded prompt context or unsupported conclusions.

<a id="tri-16"></a>

### TRI-16 — Reduce successfully read but uninterpreted triage evidence

**Priority:** High / experiment. **Triage-only proposal:** Instrument `run_batch`, `mark_read(uninterpreted)` and interpretation timeouts; try smaller batches or a triage-only final interpretation/conclusion combined step.

**Acceptance / rejection test:** Increase fraction of relevant read results understood within deadline, not merely number of calls completed.


**Algorithm-first cross-reference (2026-11-12):** Add a **typed, numerical/temporal `interpret()` reduction experiment**: compute window features and question true/false/insufficient/unavailable in Python, retain model for unresolved causality, log which model `interpret_and_decide` calls were avoided and every retained evidence ID. Do not count fewer calls as success if evidence understanding or correct diagnoses degrade. See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-17"></a>

### TRI-17 — Build an opt-in compact triage evidence packet

**Priority:** High / experiment. **Triage-only proposal:** Assemble qualified trigger/cutoff, target history, operating context, cross-checks, counterevidence and missing coverage without relying on opt-in line context or simulator-only tools.

**Acceptance / rejection test:** Compare compact/fixed/adaptive packets at equal budgets; no ground-truth leaks or unmeasured-machine-as-normal.

**Code audit reinforcement:** Reuse `agent/investigation.py:observe`, which already collects `get_time` and simulator `get_line_screening` automatically; use `gather(..., interpret=False)` to preserve evidence/provenance without extra model interpretations. `LINE_CONTEXT` is optional and, with its current fixed order, is not a complete mandatory diagnostic packet. The selector must never import `faults.py` evaluator labels at runtime.

<a id="tri-18"></a>

### TRI-18 — Build offline fault signatures and pairwise isolability

**Priority:** High / experiment. **Triage-only proposal:** On separate training seeds, measure which authorized observations distinguish normal changes, bearing, servo, hydraulic, wrong-setting and compound scenarios; truth labels remain evaluator-side.

**Acceptance / rejection test:** Held-out seeds evaluate distinguishing evidence recall, decoys and multi-fault cases; reject overfitted signatures.

**Code audit reinforcement:** `capstone/faults.py` defines evaluator-only relevant evidence for bearing (vibration/temperature/events), wrong setting (settings/inspections/vibration), bad batch (inspections/events/job route), servo (following error/events/inspections) and hydraulic (pressure/events/inspections); those definitions are testing oracle data, not allowed live selector lookups. Build signatures from disjoint training outcomes, not these hard-coded answers; include never-seen fault pair as unknown.


**Algorithm-first cross-reference (2026-11-12):** Evaluate **MIT consistency/conflict-directed diagnosis** *offline* over validated physical constraints and bounded 0/1/2-fault candidates, alongside signature/pairwise isolability. Existing ToT ranks model-proposed candidates; it is not a physical consistency solver. Require unknown-fault state and held-out multi-fault/decoy tests; do not discard candidates when the model is incomplete. Reference: [MIT model-based diagnosis](https://web.mit.edu/16.410/www/lectures_fall04/L21_model-based_diagnosis.pdf). See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-19"></a>

### TRI-19 — Rank eligible reads by deterministic diagnostic value

**Priority:** High / experiment. **Triage-only proposal:** Create triage-only Python selector using distinguishable hypothesis pairs, qualified sensor availability, trust, latency and prior coverage. Advisory first; executive execution as separate experiment.

**Acceptance / rejection test:** A3/A4 must beat A2, not just A0; no fabricated information gain probabilities; stable deterministic ties incl. `None` machine IDs.

**Code audit reinforcement:** `agent/model_policy.py:render` already sorts open questions by number of current hypotheses distinguished, signal reliability and estimated calls, but those questions are model generated **after** early collection. For opt-in Python triage selection, use earlier observable scores and qualified fixed heuristics before any LLM question. Initially compare with fixed order; expected information gain requires measured probabilities and remains out of this active plan.


**Algorithm-first cross-reference (2026-11-12):** Prototype **Stanford-style constraint-aware request templates** and **MIT-style contingent conditional checks** before any general solver or learned policy. An executable selector should rank *eligible* read calls against competing candidates and validate schema, capability, row limits, source quality and budget. Use a separate Python-first B-arm after A3 advisory/A4 executive; no fake information-gain probabilities. References: [Stanford CS221 CSP](https://stanford.edu/~shervine/teaching/cs-221/cheatsheet-variables-models/), [MIT planning](https://ocw.mit.edu/courses/16-410-principles-of-autonomy-and-decision-making-fall-2010/pages/lecture-notes/), [sequential manufacturing inspection](https://doi.org/10.3390/s21227524). See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-20"></a>

### TRI-20 — Store structured but provisional expected observations

**Priority:** High / dependent experiment. **Triage-only proposal:** Add optional per-signal expectations (qualified physical identity, direction, operating condition, unknown state) alongside current free-text hypothesis observations.

**Acceptance / rejection test:** New fields backward compatible and opt-in; LLM-predicted direction never treated as verified sensor physics.

<a id="tri-21"></a>

### TRI-21 — Make prior read coverage window- and quality-aware

**Priority:** High / dependent experiment. **Triage-only proposal:** Track machine/channel, source epoch, time interval, receipt cutoff, sensor state and quality; do not skip a new relevant read because a channel was previously queried.

**Acceptance / rejection test:** Fresh/repaired/expanded or changed-state windows remain eligible; stale or failed tool calls confer no coverage.

**Code audit reinforcement:** The existing `IncidentContext` stores one ID per tool and summary IDs keyed only by machine; a selector reading several sensors/windows on one machine needs `(machine, sensor, physical_root, window, cutoff)` keys or it will collapse distinct observations. The first `get_time` and `get_line_screening` readings and later snapshots are not automatically the same as trigger-time data.


**Algorithm-first cross-reference (2026-11-12):** Add an executable **temporal question-satisfaction evaluator** (Berkeley STL-inspired): a successful `gather(question_id)` response currently removes the question even if its measurements cannot answer it. Track `answered_true/answered_false/insufficient/unavailable/stale`, with valid sensor state, minimum sample coverage, time/data-cutoff, expected machine/source and persistence. Do **not** treat missing samples as false or normal. References: [Berkeley partial-trace monitoring](https://escholarship.org/uc/item/5dw5k0xp), [EECS149 STL lecture](https://ptolemy.berkeley.edu/projects/chess/eecs149/lectures/RuntimeMonitoring_STL.pdf). See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-22"></a>

### TRI-22 — Preserve competing and simultaneous faults in triage

**Priority:** High / evaluation. **Triage-only proposal:** Maintain bounded line- or machine-context coverage for decoy alarms and independent coexisting causes; retain alternative explanations rather than assuming top-1 fault.

**Acceptance / rejection test:** No new wrong-machine or missed second-fault regression in matched simulator compound cases.

**Code audit reinforcement:** `agent/monitor.py` selects the first alarm/status event or inspection threshold, which does not identify the true fault machine. `get_line_screening()` already covers the whole simulated line, but `incident_context.py` restricts detailed summaries to the trigger and immediate neighbors; include independently abnormal machines outside those neighbors when budgets permit. Test known-answer KA-09, not only the alarmed target.

<a id="tri-23"></a>

### TRI-23 — Audit prompt visibility of selected evidence

**Priority:** High / measurement. **Triage-only proposal:** Check `evidence_brief` and model-policy truncation after batching; verify important contradicting and distinguishing observations are actually visible and source-linked.

**Acceptance / rejection test:** Long evidence packets do not conceal decisive information behind unsupported summary statements.

**Code audit reinforcement:** `model_policy.py` limits each evidence item to 2,000 characters and all evidence to 12,000, favoring newest and previously cited items. Thus a retrieved relevant read is not necessarily *visible* to the LLM; evaluate both packet availability and prompt-visible distinguishing/counterevidence.

<a id="tri-25"></a>

### TRI-25 — Add aligned cross-sensor and temporal features

**Priority:** Medium / conditional. **Triage-only proposal:** Summarize overlapping quality-qualified load/RPM/temperature/ambient history and temporal order; handle raw readings, `get_sensor_trend` and summary results separately.

**Acceptance / rejection test:** State, frequency, clock and unit limitations are explicit; derived prose does not create new supporting evidence IDs or causal claims.

<a id="tri-26"></a>

### TRI-26 — Use comparable own-machine normal operating windows

**Priority:** Medium / prerequisite. **Triage-only proposal:** When approved signals permit, condition triage comparisons on cutting/idle/warmup/tool change, program, load and RPM; otherwise mark the baseline unavailable.

**Acceptance / rejection test:** Intentional operating changes and absent qualified baselines do not become faults or claims of normality; shared baseline development stays under RMI.

<a id="tri-27"></a>

### TRI-27 — Hand persistent deterministic anomalies to triage

**Priority:** High / detection/onset. **Triage-only proposal:** In the simulator, calibrate statistical score/persistence thresholds on separate healthy and fault runs and begin with shadow-mode scoring alongside native alarm/status/inspection triggers. `agent/monitor.py:detect_anomaly` currently scans every 10 ticks and does not use `screen_line` scores; distinguish alert onset delay from the 90-second investigation clock. Then  Connect qualified threshold or statistical alert candidates to one idempotent read-only triage incident with stable ID, as-known cutoff, severity and evidence source; do not build a new monitoring platform here.

**Acceptance / rejection test:** Track sensitivity, false alerts per eligible operating window, detection-to-triage delay, duplicate incidents and missed weak/compound faults; preserve independent alarm paths.  A persistent anomaly launches one triage; transient spikes, duplicate OEM alarms and replayed messages do not multiply LLM calls.

<a id="tri-31"></a>

### TRI-31 — Fix triage evidence-call budget and fixed-order starvation

**Priority:** High / collection efficiency. **Triage-only proposal:** `agent/incident_context.py:assemble_incident_context` currently tries `list_machines`, `get_settings`, events, inspections and then named sensor summaries under half the research-call allowance. Under default six total research calls and a counted `get_time`, this commonly means just two pre-plan context calls: events and fault-specific histories may not be fetched. Reorder eligible, read-only optional calls by observed trigger and machine/sensor relevance while retaining a small mandatory screening/coverage core and the overall triage budget. Measure before changing global call budgets; no use of hidden fault labels.

**Acceptance / rejection test:** On KA-01–13 and held-out faults, collect required vibration/temperature, following error, hydraulic pressure, settings or inspections within the same read allowance earlier than fixed order, with explicit skipped/retrieval-failed reasons. `LINE_CONTEXT` default and deep behavior unchanged.

<a id="tri-32"></a>

### TRI-32 — Score actual diagnostic evidence rather than tool-call names

**Priority:** High / evaluation integrity. **Triage-only proposal:** `evaluation/scoring.py` currently uses evaluator-only `Relevant.met_by(tool,args,machine)` and thus counts a matching read request as relevant evidence even when its result was empty, outside the onset window, unqualified, unavailable, duplicate or invisible to the model. Add evaluator-only packet scoring based on returned observation IDs, actual sensor/coverage/time validity, independent source families and contrasting observations; separate evidence misses, ambiguity and reasoning misses. Keep hidden truth out of runtime providers.

**Acceptance / rejection test:** Empty/out-of-time windows and duplicate representations never earn independent evidence credit; source-linked, prompt-visible distinguishing samples do. Pair initial 13 known-answer cases with separate held-out normal, decoy, wrong-machine, missing/blackout and compound variants; retain old scoreboard compatibility.

<a id="tri-33"></a>

### TRI-33 — Preserve bounded screening metadata in Python triage packet

**Priority:** High / screening fidelity. **Triage-only proposal:** `tools/screening.py:screen_machine` already computes `window_readings`, window start/end, `reference_median`, warm-up stage and both scores, but `compact()` drops most of that metadata for the LLM. Provide a bounded internal detailed-screening view to the selector without changing the current compact tool output by default; preserve physical root, baseline identity and `not_running_yet`, `too_few_running_readings`, `no_reference` or `feed_unavailable` rather than declaring a machine normal.

**Acceptance / rejection test:** Selector sees what period and eligible operating condition the deviation covers; LLM gets only concise source-cited results without prompt explosion. Existing compact-screening regression tests remain unchanged; no hidden truth.


**Algorithm-first cross-reference (2026-11-12):** A richer internal screening packet must also compare the **returned** machine set against an **independently validated expected roster** before any claim of complete line coverage. Avoid relying solely on keys returned by `get_line_screening`; this remains an incremental acceptance finding relative to open PR #246, not a claimed test failure. See [source-audited research](TRIAGE_ALGORITHM_FIRST_RESEARCH_20261112.md).

<a id="tri-34"></a>

### TRI-34 — Collect falsifying and rival-distinguishing measurements

**Priority:** High / fault falsification. **Triage-only proposal:** After mandatory line coverage, choose at least one affordable permitted check that might *disprove* each plausible observed pattern: sustained vibration versus isolated alarm, abnormal load versus speed-setting changes, rejects versus material/job routes or machine-specific following-error/pressure, and decoy alarm versus other-machine deviations. Use observable signatures and capabilities, never evaluator fault identifiers. Record diagnostic purpose and missing counterevidence explicitly.

**Acceptance / rejection test:** Evaluate counterevidence coverage and reduced false attribution on wrong-setting, false alarm, servo/hydraulic, batch and KA-09 decoy/compound cases at equal budgets; absence of a check must remain unknown and never become a negative result.

<a id="tri-35"></a>

### TRI-35 — Target batch, job-route and quality context on ambiguous rejects

**Priority:** Medium / conditional. **Triage-only proposal:** When observed trigger is rejected workpieces or related quality events, prioritize bounded `get_inspections`, `get_events` and selected `get_job_history` over low-value sensor repetitions, preserving observed batch IDs, machine visits, time and source. Never infer a batch cause from inspection failure alone.

**Acceptance / rejection test:** Test held-out bad-material, wrong-setting, servo-drive and hydraulic reject cases; route context should distinguish causes at acceptable budget/latency while leaving sensor-based mechanical checks available.

## Sequencing and mandatory acceptance

1. **A0 baseline and evidence validity (TRI-01/11/23/32):** measure actual 90-second triage, model/time/call accounting, prompt-visible qualified sensor windows, discriminating evidence recall, false clearances and p50/p95 before changes.
2. **Mandatory correctness (TRI-02–10/21/22):** keep no-action, rival questions, physical-source independence, real authorized data, source/time cutoffs, capability and time-limit gates. Shared Siemens SDC/RMI requirements remain separate and are not a prerequisite to simulator-first packet experiments.
3. **Simulator-only deterministic packet FIRST (TRI-17/31/33/34; conditional TRI-35):** fix context budget order, retain screening metadata, gather falsifying evidence and job/batch route on relevant symptoms. Leave original iterative reasoning and deep mode unchanged for initial comparison.
4. **A1/A2 model questions and batching (TRI-12–16):** separate, opt-in experiments after packet validation. Avoid conflating evidence-collection gain with reasoning changes.
5. **A3/A4 selector (TRI-18–20):** train fault signatures on disjoint offline data; evaluate advisory deterministic ranking before executive retrieval. No uncalibrated Bayesian information gain or hidden simulator truth.
6. **Only THREE MEDIUM (TRI-25, TRI-26, TRI-35):** aligned temporal/cross-sensor features, comparable operating baselines and selective job-route context, adopted only after measured incremental value.
7. **Detector handoff (TRI-27):** shadow-mode onset/persistence calibration and deduplicated triage incident trigger after simulator qualification; report detection delay separately from triage's 90 seconds.

**Removed from active triage backlog, identifiers never reused:** TRI-24 (untested vs inseparable faults) is covered by TRI-18; TRI-28 (absent hardware vs blackout) by TRI-06/07/17; TRI-29 (over-abstention evaluation) by TRI-01/02/32; TRI-30 (Bayesian information gain) deferred outside active backlog pending trustworthy likelihoods. There are no LOW items.

**General test gates:** read-only tool dispatch; no hidden truth leakage; correct timestamps and as-known cutoffs; missing/not exposed != healthy; honest uncalibrated uncertainty; normal, decoy, dual-fault and serious-fault cases; no higher false supported no-action or missed severe faults; latency, tokens, calls and evidence utility reported at equal budgets. Do not merge any future implementation on claimed quantum-mechanical speedup or without matched triage experiments.

**Related existing backlog:** [MVP scope](MVP_SCOPE.md), [deterministic triage evidence research](DETERMINISTIC_TRIAGE_EVIDENCE_RESEARCH_20261111.md), [real-machine acceptance](REAL_MACHINE_INTELLIGENCE_ACCEPTANCE.md), [Siemens data acceptance](SIEMENS_DATA_ACCEPTANCE.md), [signal-priority roadmap](SIGNAL_PRIORITY_IMPLEMENTATION_ROADMAP_20261111.md). Existing external owner responsibilities remain in their categories; this register is the canonical triage-specific view.
