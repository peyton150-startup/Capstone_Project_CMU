# Siemens agent tools and evidence: signal-ranked implementation decision (2026-11-11)

**Scope:** Documentation-only refinement of [MVP Future Work](MVP_SCOPE.md#fw-siemens-agent-evidence-ranking-20261111), prompted by reviewing the existing three guardrails in [PR #235](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/235) and pending [Siemens v2 record #236](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/236) / [collector #237](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/237). **No software is built or field-verified by this document.** At the time of review #235 was merged docs-only; #236 and #237 were open and not in main. Do not silently assume their status stays unchanged.

**Ranking rule:** Exactly **two HIGH** signal entries first; the other five are **MEDIUM**, ordered most useful to less immediately useful. This is an additive prioritization view, **not** a downgrade of pre-existing mandatory **P0 SDC/RMI shop-approval, security, data-quality, replay, or evidence-integrity gates**. One collector may be tested with site authorization before downstream diagnosis is ready. No supported machine-fault claim until all applicable consumer gates pass.

## Ranked decision table

| Rank | Priority in this comparison | Owner | Work | Mandatory gate or experiment | 
|---:|---|---|---|---|
| 1 | **HIGH** | Security and authorization | [Independent Siemens read-only authority](#rank-1-independent-readonly) | Before connecting to the physical controller |
| 2 | **HIGH** | Controller-specific data integration / agent evidence | [Qualified Siemens evidence with two historical cutoffs](#rank-2-qualified-evidence) | Before Siemens data enters detection or diagnosis |
| 3 | **MEDIUM** | Agent tools and evidence | [Physical-source lineage and diagnosis support](#rank-3-source-independence) | Before supported mechanical root-cause claims |
| 4 | **MEDIUM** | Agent tools and evidence / security | [Advertised tools match executable capabilities](#rank-4-capability-parity) | Before recorded Siemens agent triage |
| 5 | **MEDIUM** | Security and authorization | [Close specific existing tool-dispatch gaps](#rank-5-targeted-tool-guards) | When a concrete enforcement gap is found |
| 6 | **MEDIUM** | Evaluation, benchmarking and observability | [Passive latency and evidence-visibility audit](#rank-6-passive-latency) | Run on pinned archived cases before changing runtime behavior |
| 7 | **MEDIUM** | Evaluation, benchmarking and reasoning | [GR-2 overlap suppression: matched experiment only](#rank-7-gr2-benchmark) | After passive baseline, opt-in runtime PR only if beneficial |

## Detailed acceptance and code crosswalk

<a id="rank-1-independent-readonly"></a>

### 1. Independent Siemens read-only authority — HIGH

**Owner:** Security and authorization. **Why it ranks here:** Server-enforced least-privilege credentials, approved endpoints/nodes, revocation and offline forbidden-operation tests; no state-changing tests on a live CNC.

**Trigger / dependency:** Before connecting to the physical controller. **Existing acceptance:** SDC-01/02/12, existing SEC-1/2/4 and #235 item 2. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** Verify exact physical/controller/OPC UA application URI and trust chain, site consent, software/license, source-approved node and attribute scope, rates and retention. Require an account whose permissions are enforced read-only **by the OPC UA server**, independent of adapter code, with approved host/network egress and secret handling. Add independent expiry, revocation and allowlist-change stop rules. The collector may use a general-purpose asyncua library; an AST check for absent Write/Call methods alone is not a security boundary.

**Proof:** Isolated test-server and fake-client negative tests for forbidden Write, Call, unapproved Read/Subscribe, node expansion, expired/revoked scope, wrong server, certificate and login refusal. Test the **server denies** prohibited operations using a disposable test server/fixture, never the live controller. A controller-side read-only role and shop-approved safe connection test are separate field evidence. Fail closed when unknown; no automatic inference of authorized controller features.

<a id="rank-2-qualified-evidence"></a>

### 2. Qualified Siemens evidence with two historical cutoffs — HIGH

**Owner:** Controller-specific data integration / agent evidence. **Why it ranks here:** Source/axis identity, OPC UA types and quality, gaps, units, valid-time coverage, event-time and receipt-time cutoffs; refuse ineligible evidence for detector/agent diagnoses.

**Trigger / dependency:** Before Siemens data enters detection or diagnosis. **Existing acceptance:** SDC-03–09/15–18, RMI-01/02/04 and #235 items 3–5/36. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** Build one versioned, typed evidence-eligibility interface after the Siemens record and approved signal catalog; include server/machine/axis/spindle/node, map and permission revisions, units and physical meaning, native StatusCode and quality, event/update/hold semantics, collector session epochs and gaps. Store permissible Bad/Uncertain or incomplete samples for audit but exclude them from valid numerical inference unless explicitly authorized; unknown unit/meaning remains unknown.

**Two cutoffs:** A historical replay value may support an investigation only when (a) its event/source time qualifies for the requested **event-time cutoff** and (b) the collector had received it by the separate **knowledge/receipt cutoff**. Missing required timestamps, wrong order or ambiguous source clocks must never be silently resolved with later knowledge. The current legacy `providers/replay.py:_visible` walks records in file order and breaks at the first source timestamp after `now`; out-of-order/late records therefore need explicit tests for both premature exposure and wrongful exclusion. A post-trigger sample is a newly acquired fact, never retroactive pre-trigger evidence.

**Consumption:** Validate continuous coverage and freshness **for each requested window and each actual signal type**, not one arbitrary universal 50% threshold. A change-only state channel and a frequently sampled numeric channel have different semantics. Apply mandatory eligibility before features, statistical baselines, incident generation, and agent evidence; unknown/insufficient => a data-gap or abstention, never a healthy machine.

**Proof:** Good→Bad→Good, lost subscription, overflow, reconnect, corrected/late arrivals, out-of-order file, wrong server/axis, changed map/license, sparse change-only events, partial coverage, stale-now/valid-then, two independent as-of cutoffs, unqualified data never changing a diagnosis. Include regression tests for legacy replay without claiming Siemens hardware validation.

<a id="rank-3-source-independence"></a>

### 3. Physical-source lineage and diagnosis support — MEDIUM

**Owner:** Agent tools and evidence. **Why it ranks here:** Group raw readings, derived summaries and dependent alarms by origin; distinguish detected abnormality, plausible cause, evidence-supported cause and technician confirmation.

**Trigger / dependency:** Before supported mechanical root-cause claims. **Existing acceptance:** RMI-07 P0; #235 item 11. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** Add `physical_source_family` or equivalent traceable lineage to raw evidence, aggregates, OEM alarms and derived detection features. `agent/loop.py:diagnosis_supported` currently counts distinct observable evidence IDs, not distinct independent root sources. Raw load, its mean and a dependent load alarm should not be counted as three independent observations. However do **not** impose a blanket two-sensor rule; a single reliable signal may support an observed abnormality without confirming a mechanical root cause.

**Proof:** Same-source raw+mean+alarm, two axes sharing nominal sensor names, genuinely independent vibration and load sources, technician evidence vs model claims, and incomplete lineage tests. Explicitly distinguish abnormality observed, cause suspected, cause supported and technician-confirmed. Preserve existing `min_supporting_evidence` behavior for historical simulator fixtures until a versioned real-machine contract and matched tests are ready. **RMI-07 remains a P0 consumer gate** regardless of this MEDIUM relative ranking.

<a id="rank-4-capability-parity"></a>

### 4. Advertised tools match executable capabilities — MEDIUM

**Owner:** Agent tools and evidence / security. **Why it ranks here:** One source-qualified capability set at the same as-known cutoff drives tool descriptions and dispatch; invalid, stale or unauthorized sources cause explicit unavailability/abstention.

**Trigger / dependency:** Before recorded Siemens agent triage. **Existing acceptance:** RMI-01/04 P0; SEC-3; GR-3. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** `recorded_investigation.py:replay_tool_specs` and `replay_investigation.py:recorded_tool_specs` currently may expose a sensor after one historical finite value. Merge the planned real-machine capability policy at the *same knowledge cutoff* used by provider dispatch. Advertised tools, permitted argument/channel combinations and executable reads must agree; a model's tool list is not authorization. When a channel is stale *now*, do not suppress a valid historical window; differentiate current availability, historical eligibility, and completely unsupported source. No phantom factory/line, manuals or physical actions in read-only triage.

**Proof:** One old valid sample with current unavailable channel, stale-now/valid-past, approved and revoked channels, unknown sensor, identical signal names on multiple servers, no qualified channels, and provider call attempted despite missing advertised capability. Unknown/insufficient leads to explicit explanation or safe abstention. **RMI-01/04 remain P0 for any live diagnosis.**

<a id="rank-5-targeted-tool-guards"></a>

### 5. Close specific existing tool-dispatch gaps — MEDIUM

**Owner:** Security and authorization. **Why it ranks here:** Reuse typed argument/result validation and provider allowlists; add only proven missing dispatch authorization, output provenance and denial tests. No generic new guardrail framework.

**Trigger / dependency:** When a concrete enforcement gap is found. **Existing acceptance:** Existing `providers/factory.py`, `agent/loop.py`, SEC-1–5, #235 item 12. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** Preserve existing `providers/factory.py:run_tool` typed input/output validation, `SimulatorFactoryProvider.call` unknown-tool refusal, explicit registry and `agent/loop.py:call_tool` result identity checks. Review the concrete Siemens/replay execution path for any unvalidated operation, mismatched source, invalid unit, bad response, or model-to-tool authorization gap. Add only missing controls **at the authoritative dispatch boundary**; do not introduce a parallel Pydantic AI or new generic guardrail layer as a prerequisite.

**Proof:** Denied unknown/unapproved tool, malformed arguments/output, forged source/run context, bypassing a prompt-advertised list, revoked permission and alternative provider path. Preserve legacy working behavior and record metadata-only allow/deny reasons. If existing code already blocks a scenario, mark it verified rather than add duplicated code.

<a id="rank-6-passive-latency"></a>

### 6. Passive latency and evidence-visibility audit — MEDIUM

**Owner:** Evaluation, benchmarking and observability. **Why it ranks here:** Separate model-decision latency, tool latency, interpretation, truly repeated windows, missing-from-prompt evidence and decision-relevant overlaps. Metadata-only traces.

**Trigger / dependency:** Run on pinned archived cases before changing runtime behavior. **Existing acceptance:** Existing `agent/model_policy.py` evidence cap, #235 item 13, latency review. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** Instrument a passive audit on pinned archived investigations, measuring per-stage model decision and interpretation latency, provider/tool wall time, repeated exact/overlapping windows, and cause of repeats. `agent/model_policy.py` truncates the evidence section to `MAX_EVIDENCE_SECTION_CHARS=12_000`; some prior evidence is represented by IDs and tool-call descriptions. Classify separately: (1) query truly redundant, (2) earlier evidence omitted from current prompt, (3) overlap containing new decision-relevant information. Context omission as the cause of repeated reads is a **hypothesis**, not a finding.

**Proof:** Deterministic read-only trace analysis, no model retry or workflow changes, identical episode outputs with instrumentation on/off, safe metadata redaction, reproducible per-case breakdown by call and wall time. Baseline the already merged `DECIDE_CALLS`/reasoning effort/line context variants under matched settings before crediting new suppression.

<a id="rank-7-gr2-benchmark"></a>

### 7. GR-2 overlap suppression: matched experiment only — MEDIUM

**Owner:** Evaluation, benchmarking and reasoning. **Why it ranks here:** Keep default OFF; compare repeated, context-forgotten and genuinely new overlapping reads on paired cases, accuracy, severe misses and end-to-end time; enable only on measured net gain.

**Trigger / dependency:** After passive baseline, opt-in runtime PR only if beneficial. **Existing acceptance:** Existing GR-2 proposal in #235 item 34. **Status:** planned refinement only; not implemented or newly tested in this PR.

**Implementation boundary:** Keep existing GR-2 `NEAR_DUPLICATE_GUARD` proposal **off by default**. Only evaluate on paired frozen episodes after the passive audit. Measure tool executions saved *and* LLM selection/interpretation time, p50/p95 end-to-end runtime, diagnosis agreement, severe misses, abstentions, critic/verification reads and action safety. Suppress only provably answered immutable windows with complete coverage, identical machine/channel/epoch/snapshot and equivalent statistic; overlapping isn't automatically redundant.

**Go/no-go:** No runtime PR without a demonstrated end-to-end net benefit with no consequential diagnostic regression. If the main issue is prompt evidence truncation, test better compact evidence retrieval first. Never suppress a new time/quality revision, an independent critic check, or verification. The old exact-repeat guard remains untouched.


## Explicit exclusions and sequencing

**Noise not added as implementation commitments:** A new generic guardrail framework, automatic overlap suppression without matched results, a universal coverage fraction for every sensor, fabricated independent corroboration from repeated views, and uncontrolled physical write/Call negative tests. Existing GR-1 safe repair remains a separate optional experiment in [#235's plan](SIGNAL_PRIORITY_IMPLEMENTATION_ROADMAP_20261111.md), not a Siemens prerequisite.

**Pilot path:** (1) qualify machine/consent, record/collector, independently enforced read-only scope; (2) authorized capture-only validation; (3) qualified source/time/quality evidence, lineage and dispatch parity, then read-only diagnostic evaluation; (4) passive latency/visibility audit; (5) optional GR-2 ablation **only if justified**. The ordering is not the existing #235 optional GR-2→GR-1→GR-3 experimental sequence: mandatory data-safety work comes first.

**No acceptance claims:** Documentation only. No API/model requests, test suite, real OPC UA server or live CNC machine exercised by this work.
