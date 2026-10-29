# Future Work reevaluation register and prompt review

Reviewed 2026-10-11. This evaluates the supplied 43-part Datum/Ratchet prompt
against the current capstone. It records adoption conditions, not permission to
implement future components. `MVP_SCOPE.md` remains the scope authority.

The prompt is broadly sound: preserve principles, reuse existing boundaries,
and adopt infrastructure only when a real problem justifies it. The corrections
below take precedence over the corresponding conditions in the supplied prompt.
Datum/Ratchet inspiration labels come from that prompt; this review did not
audit those repositories or verify their implementation claims. A later execution
of its three-repository audit must record reference commits, inspected files,
and any unavailable material before claiming those repositories were reviewed.

## Current baseline

- **IMPLEMENTED:** project contracts, sourced tool envelopes, provider allowlist,
  safe tool error responses, deterministic IDs, separate human approval,
  observable evidence records, seeded simulator, and relevant boundary tests.
- **IMPLEMENTED:** uv, Ruff (including imports), pre-commit configuration,
  GitHub Actions, and informational pytest-cov. Hook installation is opt-in.
- **PARTLY IMPLEMENTED:** validation and provenance foundations, not external
  authentication, source completeness, response verification, or durable lineage.
  `Contract` freezes model fields; it does not provide recursively immutable
  containers, authenticated provenance, or an immutable storage history.
- **IMPLEMENTED (since this review):** the Pydantic Graph macro investigation
  loop (`agent/investigation.py`). Multi-agent roles (FW3) are added to this graph
  with the existing chat client; CrewAI was rejected on 2026-10-26 (it requires the
  `openai` SDK and `pydantic<2.13`). `VerificationRecord` is still a roadmap
  concept, not a current model.
- **NOT IMPLEMENTED:** a complete research agent, evaluator, recovery, action
  persistence, real factory connection, or the future frameworks in this register.
  Optional database connectivity and an Alembic scaffold are not durable action
  or evidence persistence.

The current approval desk starts maintenance on approval; it is not a separate
durable execution service. It rejects a second approval of an already decided
proposal, but does not provide network idempotency or deduplicate submissions.
`wait` changes simulation state; `propose_action` changes proposal state. Neither
belongs in the first read-only MCP slice.


## High-priority simulator fidelity candidates (2026-10-23)

These two candidates came from Brandon Reff's manufacturing-engineering
feedback. They are **HIGH priority; not implemented**. The authoritative
details and ranked build candidates live in
[MVP_SCOPE.md, Future Work 8](MVP_SCOPE.md#high-priority-simulator-fidelity-faster-bearing-vibration-ramp-and-machine-power-planned-2026-10-23).
This register records adoption gates, not authorization to change behavior.

| Candidate | Adoption gate | Validation and deferral rules |
|---|---|---|
| Bearing progression: modestly steeper, shorter visible vibration ramp, approximately three simulated days. **Built 2026-10-26 as an opt-in `three_day` profile; default unchanged** (`docs/benchmarks/2026-10-26-bearing-three-day.md`) | Define the start/end of the noticeable degradation period, verify whether the three-day estimate is calendar or machine-operating time, and map that duration to the one-minute default tick (about 4,320 ticks if calendar time). Review old and revised curves with engineering feedback. | Preserve early normal variability and smooth, non-instantaneous rise; compare seeded traces, alarms, repairs, detection timing, and existing short-episode compatibility. Defer any fixed universal threshold until calibrated. |
| Machine electrical power consumption in kW. **Built 2026-10-26: `PowerSensor`, standard on every machine; assumptions to be reviewed** | Define machine and operating-mode baselines and component contributors, with no invented hydraulic subsystem. Add power as a causal, noisy observation, distinct from existing percentage motor load; kWh only by integrating power over elapsed simulated time. | Validate units, idle/cutting/stopped behavior, seed replay, normal job variation, and provider boundary; avoid diagnosing bearing failure from high power alone. Defer unvalidated current-draw/electrical assumptions. |

Both candidates must keep hidden truth out of agent observations and preserve
seed determinism. No simulator code, added dependencies, or test behavior has
changed from documenting these gates.

**Additional feedback cross-check (2026-10-23):** Brandon also suggested
examining **electrical current draw in amps** and adding distinct failure
opportunities for **servo motors/axis drives** and **hydraulic systems**.
Current draw is an optional follow-up to the high-priority power sensor,
requiring explicit electrical assumptions and a check for redundant signals.
The servo and hydraulic additions are medium-high priority, after the
immediate bearing and kW updates. Hydraulics must be opt-in per machine
configuration. Candidates require independent causal fault behavior, sensors,
approved maintenance/verification paths, and seeded tests; neither is built.
See [Future Work 8 details](MVP_SCOPE.md#high-priority-simulator-fidelity-faster-bearing-vibration-ramp-and-machine-power-planned-2026-10-23).

## Haas VF-series retrofit adoption gates (2026-10-29)

**HIGH-priority planned simulator reference migration, not implemented.** See [Haas VF reference future work](MVP_SCOPE.md#high-priority-future-work--retrofit-the-simulator-around-real-haas-vf-series-machines-2026-10-29). First establish the current one-machine/critic baseline. The future default simulator reference is a versioned **Haas VF NGC** profile; optionally support **Classic Haas Control (CHC) via RS-232** for older shops. Do not confuse the synthetic `SIM-CNC-001` manual with real manufacturer documentation. Python can fetch supported telemetry, but cannot create unexposed measurements.

| Gate | Adoption evidence | Stop / defer condition |
|---|---|---|
| Specific machine identity and manual | Exact VF model, control generation/firmware, reviewed OEM document version, permitted distribution | Model/version unknown, manual contradicted or rights unclear |
| Telemetry discovery | Read-only NGC MTConnect `probe` / MDC or CHC Setting 143 RS-232 Q capability check; field/units/timestamp inventory | No safe access/permission, unknown or absent measurement |
| Sensor and fault fidelity | Calibration against known physical operating modes; clear direct vs calculated vs external vs unavailable provenance | Simulator invents sensors or infers an unverified root cause from a proxy |
| Safe adapters | No writes; isolated interfaces behind existing `FactoryProvider`; malformed/stale data and outages covered | Tool performs controller changes or bypasses human approval |
| Comparative evaluation | Seeded offline parity vs present generic simulator and critic baseline; authorized shop evidence only with consent | Lost regression correctness, hidden truth leaks, unreasonable false confidence/latency |

## Corrections to the supplied conditions

1. **Parts 1–3: separate structure, completeness, and truth.** The barricade
   admits validated project data, including fallible observations and beliefs;
   call this the validated domain, not factually trusted reality. Completeness
   is relative to a requested scope/window and pagination/snapshot semantics.
   Even a COMPLETE response supports absence only when the source promises an
   exhaustive read for that scope. PARTIAL can support positive evidence from
   accepted records; it cannot support absence in the missing scope. Keep source
   read status separate from response-check status and investigation confidence.
   A conclusion unaffected by missing scope need not automatically become partial,
   but the missing scope must remain visible. Do not override atomic imports.
2. **Parts 4–7: trigger safe retries earlier.** Review idempotency before any
   retryable, concurrent, or restartable mutation boundary, including simulator
   writes exposed over MCP and proposal creation. Do not wait for physical factory
   integration. A local single-process simulator does not need a new database for
   this documentation task. Scope a caller-supplied operation key; a payload hash
   checks intent but cannot distinguish two intentionally identical operations.
   Pin canonical parameters and approval version. Recheck authorization on retry.
   Concurrent duplicates must not each dispatch. Define in-progress results,
   terminal results, retention and late retries, crashes, and unknown outcomes.
   A DB uniqueness constraint alone cannot guarantee one remote physical effect:
   require downstream idempotency or reconciliation before redispatch. Expand
   duplicate tests to concurrency, timeout after effect, restart, key conflict,
   and expired approval. These are project adoption requirements informed by
   [AWS's idempotent API guidance](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).
3. **Parts 8–11: do not wait for persistence to define legal behavior.** Define
   the smallest action transitions with the next action/graph integration;
   persistence and recovery extend them later. Execution outcome and verification
   outcome are separate: an operation can execute successfully but be ineffective.
   Define post-action observation windows, settling/completion, deadlines, and
   INCONCLUSIVE outcomes. An investigation cannot claim verified resolution by
   skipping observable verification. Failure/cancellation may end with unresolved
   outcome and required follow-up; do not force endless verification. Preflight
   builds on existing target/action/reason checks. Recheck mutable safety conditions
   at execution; a dry run is not authorization and cannot predict hidden causes.
4. **Parts 12–18: record reproducibility before experiments.** A minimal manifest
   belongs with the first repeatable evaluation, including scripted runs, rather
   than after historical live comparisons already matter. Add corpus/policy/role
   fields only when those components exist. Keep evaluator-only scenario identity,
   seed and expected truth away from model prompts and agent memory when they can
   reveal answers. Frozen evidence needs versioned/snapshotted content or immutable
   references for durable replay. Static replay cannot evaluate counterfactual
   intervention effects or answer unrecorded requests; fail explicitly on misses.
5. **Parts 14–15: conflicts depend on semantics, not source count.** Reevaluate
   authority when evidence claims incompatible values for the same fact, target,
   units, scope and time. This may involve two revisions of one source, or manuals
   and telemetry; two real factory integrations are not required. Retain both
   claims and an explicit unresolved result now when encountered. A separate
   conflict entity remains optional and later. An authority policy is accountable
   and versioned, and does not make every claim from that source true.
6. **Parts 19–24: use demonstrated needs, not arbitrary project size.** Property
   tests need named invariants and useful generated cases. A type-checker pilot
   can be justified by current interfaces; it need not wait for a large agent.
   Compare diagnostics after distinguishing intentional invalid-input tests and
   missing annotations from genuine incompatibility. Existing ty baseline is
   informational, not evidence that mypy is better. A scripted acceptance test
   should be assembled incrementally and gate CI when the loop is complete;
   live paid model calls remain opt-in. Python object privacy is not a security
   sandbox: test tool exposure and graph wiring, not an absolute claim that code
   running in the same process cannot access a private attribute.
7. **Parts 30–33: gate on races and durability requirements.** Concurrency can
   occur with tasks/threads in one process, not only multiple processes. An outbox
   atomically commits an intent alongside domain data; remote notification occurs
   afterward and may duplicate. A durable DB job table may solve the need without
   a broker. Distinguish rejected-record quarantine in synchronous ingestion from
   an asynchronous dead-letter queue. Redriving a consequential action rechecks
   approval, expiry, current safety and idempotency. The outbox distinction follows
   [AWS's transactional outbox guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).
8. **Parts 34–36: permissions begin at the first remote boundary.** Authenticate
   and authorize the first MCP client; later role scopes extend that policy when
   another role arrives. An executor is a bounded service operating on an exact
   human-approved request, not a role with arbitrary write permission. Metrics
   require bounded-cardinality labels; keep run IDs in traces, not metric labels.
   Separate simulation time from wall-clock network latency. Multiple machines or
   factories owned by one user do not automatically justify multi-tenant RLS.
9. **Parts 40–43: make review bookkeeping honest.** A trigger opens a review;
   it does not approve adoption. Record ADOPT, DEFER, REJECT, or REPLACE with
   evidence, test criteria, cost and owner. No fixed framework API or version is
   guaranteed for a future phase. Never claim Datum/Ratchet were audited merely
   because the supplied prompt describes them. Do not advance implementation or
   developer-understanding status for documentation edits.

## Rules shared by every register entry

**PLANNED** means the behavior is expected at the specified phase; the exact
library remains subject to review. **CANDIDATE** permits adoption or rejection.
**CONDITIONAL** requires the stated condition to actually occur. **IMPLEMENTED**
requires current code evidence. **REJECTED FOR NOW** means no demonstrated need.

At each gate: inspect current code and scope; demonstrate the problem; check
current official documentation, maintenance and Python/framework compatibility;
compare installed facilities and a simpler alternative; estimate custom code
removed versus migration/operational cost; specify acceptance tests; record the
decision and review date. A candidate may be deleted or replaced. Security and
correctness obligations remain even when their proposed technology is rejected.

All entries preserve simulator independence, seeded determinism, separate
Reality/Observation/Belief, `FactoryProvider` and project contracts, human-only
approval, observable post-intervention verification, and evaluator-only truth.
They cannot replace these boundaries, Pydantic Graph's macro loop, or pytest.
Typed model output never proves factual correctness. Future optional runtimes
must remain optional to the simulator. No fixed server count is committed.

The table identifies the problem and integrating component through its candidate
and placement columns. **Dependency** denotes additions on eventual adoption:
`none` = project code/docs only; `dev` = development only; `optional` = optional
runtime packages; `TBD` = mechanism depends on design, with no dependency assumed.
**Scope**: `MVP` = core course behavior; `extension` = post-MVP enhancement;
`production` = durable/deployed operation need, not a course requirement.
All rows were last reviewed **2026-10-11**; this is a capstone gate review, not a
claim of implementation or a fresh compatibility test of every named framework.

## Future Technology / Architecture Reevaluation Register

| Part / candidate | Decision; placement | Earliest trigger | Verify before adoption | Reject or defer if | Dependency; scope |
|---|---|---|---|---|---|
| 1 — Trust barricade | Foundations IMPLEMENTED; extension PLANNED; FW2 | Every new external input | Conversion point, schemas, permission, provenance, safe errors and leak tests | Duplicates contracts/provider or calls beliefs truth | none; MVP boundary / extension |
| 2 — Partial evidence | PLANNED; FW2 | First fallible or scoped source | Pagination, requested/observed scope, exhaustive-read semantics, independent status axes | Existing result already expresses these guarantees; do not defer absence safety | none; extension |
| 3 — Per-record ingestion | CANDIDATE; FW1 | First actual ingestion workflow | Atomic snapshot versus independent records, accepted/rejected counts and sanitized errors | Partial acceptance breaks snapshot consistency | TBD; extension |
| 4 — Bounded calls | PLANNED; FW2 / FW3 | First live network/model call | Framework retries, one total deadline/budget, cancellation, retry safety and rate-limit policy | Custom wrapper duplicates working native bounds | TBD; MVP live provider / extension |
| 5 — Circuit breaker | CANDIDATE; FW2 | Measured repeated remote failures create material cost/latency | Backoff insufficient, threshold/probe/reset behavior, existing client support | Rare failures, local simulator, or no measured benefit | TBD; production |
| 6 — Action idempotency | PLANNED safety requirement; FW4 | Before retryable/concurrent/restartable mutations | Scoped key, approval binding, atomic claim, downstream guarantees, unknown-outcome recovery | Reject proposed mechanism if effect cannot be made safe; block automatic redispatch | TBD; extension / production |
| 7 — Duplicate-storm tests | PLANNED; FW6 / FW4 | With idempotency implementation | Sequential/concurrent duplicates, crash/restart, timeout after effect, conflicts | Boundary is mocked away; no implementation yet | none; extension |
| 8 — Action lifecycle | Existing pending/approved/rejected IMPLEMENTED; extension PLANNED; FW4 | Next action/graph integration; extend for recovery | Minimal legal transitions, execution versus verification, actor and terminal semantics | Second orchestration engine or speculative state list | none initially; MVP / production recovery |
| 9 — Investigation status | CANDIDATE; FW7 | UI/audit/resume needs persisted graph status | Derive from authoritative graph events/checkpoints, recovery consistency | Duplicates graph transitions or no consumer needs it | TBD; extension |
| 10 — Required verification | PLANNED core rule; MVP §7 / FW4 | First agent intervention loop | Complete/settle before observing; no resolved path bypasses verification; failure deadlines | Hidden truth used as operational evidence; requirement cannot be dropped | none beyond graph; MVP |
| 11 — Action preflight | Basic checks IMPLEMENTED; extension CANDIDATE; FW4 | Next consequential action or external execution | Reuse checks, conflict/safety rules, revalidate at execution, no hidden oracle | Redundant helper or stale dry run treated as permission | none; MVP basic / extension |
| 12 — Decision audit | PLANNED; FW7 / memory | First persisted investigation or comparative experiment | Explicit rationale, evidence/tool IDs, versions, retention and redaction | Raw chain-of-thought or oversized duplicate event store | TBD; MVP basic record / extension |
| 13 — Evidence lineage | Source fields IMPLEMENTED; durable extension PLANNED; FW1 / FW7 | First durable evidence/RAG/external source | Content/revision identity, immutable references, retention and time semantics | Mutable references cannot reproduce cited evidence or whole-source copying is unnecessary | TBD; extension |
| 14 — Source authority | CANDIDATE; FW1 / FW2 | Conflicting comparable fact claims affect a decision | Fact-specific policy, time/units/scope normalization, unresolved handling | Universal ranking or LLM silently overwrites conflicts | none; extension |
| 15 — Conflict artifact | CANDIDATE; FW2 | Conflicts need tracking beyond evidence/verification records | Existing representations, resolution ownership and policy history | Supporting/contradicting evidence is sufficient | none / storage TBD; extension |
| 16 — Execution manifest | PLANNED; FW7 | First repeatable scripted/live evaluation | Minimal config/version capture, evaluator segregation, optional fields only as needed | Claims identical LLM outputs or leaks answer-bearing setup | none; MVP minimal / extension |
| 17 — ReplayFactoryProvider | CANDIDATE; FW7 | Complete loop/evaluator plus a repeatability gap | Tape misses, request matching, time/order, recorded scope, no counterfactual effects | Seeded reruns suffice or replay fabricates unseen data | none / storage TBD; extension |
| 18 — Pydantic Evals | CANDIDATE; FW7 | MVP scoring/loop ready; custom reporting about to grow | API/versions, scripted parity, arbitrary workflow, truth separation, code removed | Adds plumbing or replaces authoritative scoring/pytest | optional; extension |
| 19 — Hypothesis | CANDIDATE; FW6 | Named invariants need many input/sequence combinations | Generated validity, shrinking/replay, RNG isolation, Python/pytest support | Handwritten cases suffice or generated assertions mirror implementation | dev; extension |
| 20 — Critical branch coverage | CANDIDATE extension; FW6 | Current informational coverage reveals meaningful blind spots | Target approval/provider/evaluator branches with behavior tests | Arbitrary whole-project threshold or coverage mistaken for correctness | none; MVP maintenance |
| 21 — ty versus mypy | CANDIDATE; FW6 | Concrete interface mistakes justify a pilot; current baseline available | Comparable scope, Pydantic/Protocol support, diagnostic review, minimum Python, cost | High-noise gate or two checkers without a concrete reason | dev; extension |
| 22 — Architecture invariants | Some IMPLEMENTED; extensions PLANNED; FW6 | Each new trust/mutation boundary | Existing tests first; actual exposed capabilities and workflow paths | Fake tests for nonexistent components or impossible same-process security claim | none; MVP / extension |
| 23 — Vertical acceptance | PLANNED; FW6 | Assemble with loop; full gate when evaluator exists | Scripted model, seeded observations, human approval, intervention, verification and score | CI requires live credentials/paid models or hides integration behind mocks | none; MVP |
| 24 — ADRs | CANDIDATE; relevant FW section | Settled architecture choice is costly to reverse | Current decision, alternatives, consequences, status and review trigger | Repeats minor library setup or records proposals as accepted | none; MVP documentation |
| 25a — Pydantic AI MCP | PLANNED; FW2 | Core agent MVP works and tool transport is needed | Current API, optional dependency, read-only allowlist, auth, schemas, cleanup, parity | Direct provider remains sufficient or changes macro loop | optional; extension |
| 25b — CrewAI MCP | REJECTED 2026-10-26 (developer); FW3 roles use the in-process `FactoryProvider` | — | CrewAI requires the `openai` SDK (AGENTS.md section 9) and `pydantic<2.13` (project pins 2.13.4) | Reopen only if both blockers are gone and a role shows a need | none; extension |
| 26 — CrewAI output_pydantic | REPLACED 2026-10-26 by project `Contract` handoffs asked through `ModelPolicy._ask`; FW3 | First actual specialist handoff | Invalid replies refused with a recorded reason (L4); NVIDIA structured output (L5) | Redundant contracts or an extra parsing framework without a gap | none; extension |
| 27 — Docling + HybridChunker | CANDIDATE; FW1 | Actual representative manuals enter RAG | Conversion/table quality, provenance, embedding tokenizer, dependency cost and retrieval | Simpler ingestion wins on actual corpus | optional; extension |
| 28 — Equipment profiles | CANDIDATE; portability | Second genuinely different environment exposes repetitive capability code | Describe observations/actions, validate profiles, preserve causal simulator code | Configuration cannot reduce real onboarding work | none initially; production portability |
| 29 — YAML configuration | CANDIDATE; portability | Users must author multiple factory profiles | Need for YAML versus typed Python/JSON, safe loading, contract validation, versioning | Format aesthetics only; existing config suffices | optional if YAML chosen; production portability |
| 30 — Concurrency control | CONDITIONAL; FW5 | Overlapping tasks/threads/processes can mutate same durable work | Actual race, unique claims/transactions first, lock ownership/expiry | Single execution owner or DB constraint already solves race | TBD; production |
| 31 — Transactional outbox | CONDITIONAL; FW5 | Durable state plus downstream dispatch creates a dual-write gap | Intent in same transaction, dispatcher recovery, duplicates/order and idempotent consumer | Synchronous execution or durable DB queue already suffices | TBD; production |
| 32 — Dead-letter/quarantine | CONDITIONAL; FW5 / FW1 | Durable async retries reach terminal failure; ingestion rejection separately | Failure record, redrive ownership, approval/safety rechecks and retention | No async retry pipeline; synchronous rejected-record log suffices | TBD; production / ingestion extension |
| 33 — Background framework | CANDIDATE; FW5 | Work needs durable scheduling/restart survival | Compare DB worker/native facilities/maintained queues, cancellation, delivery and deployment cost | Inline/batch execution satisfies actual need | optional plus services if selected; production |
| 34 — OpenTelemetry metrics | PLANNED with observability; FW2 | Operational health questions need aggregate instrumentation | Bounded labels, latency clock, exporters, privacy, volume and cost | Existing reporting suffices or labels expose secrets/high cardinality | optional; extension |
| 35 — Role capability scopes | Baseline policy PLANNED at first MCP; role extension FW3 | First remote boundary; refine when second role gets tools | Server-side identity/authorization, least privilege, exact approval binding | Client filters treated as auth or executor can approve itself | none / auth integration TBD; extension |
| 36 — Tenant isolation / RLS | CANDIDATE far future; portability | Mutually untrusted owners share persistent service | Threat model, tenancy keys, DB roles, pooling context and cross-tenant tests | Single owner or isolated deployments; RLS selected without a need | TBD; production |
| 37 — pytest-xdist | CONDITIONAL; FW6 | Measured suite duration materially harms iteration | Worker/RNG/temp/DB/port isolation, repeated determinism and elapsed speedup | Little speedup or flaky parallel behavior | dev; extension |
| 38 — Ruff/hooks/CI/coverage | IMPLEMENTED; FW6 | Review only concrete maintenance gaps | Current configs/pins and actual local/hosted execution | Duplicate Black/isort/Flake8 or reinstall current tooling | existing dev only; course tooling |
| 39 — Copied infrastructure stacks | REJECTED FOR NOW; all sections | New capstone requirement independently justifies a component | Specific benefit, smaller option, operating cost, architecture fit | Datum/Ratchet usage is the only justification | no additions; production if justified |

Parts 40–41 are documentation rules satisfied by this linked register and
section references. Parts 42–43 govern execution: documentation only, no future
dependencies, an honest progress entry, and unchanged understanding status.
Framework-specific details stay in their existing Future Work entries rather
than being copied into another implementation specification here.

## Addendum to use with the original prompt

Apply this review's corrected gates before executing that prompt. Audit the
three repositories at recorded commits; if a reference is unavailable, report
that limitation and evaluate the pattern without inventing reference findings.
Map every proposal to current code and its existing roadmap entry. Use this
register as the gate authority, updating review dates only for rows actually
reviewed. Do not mark a planned framework or partial foundation IMPLEMENTED.
Separate required safety behavior from optional technology. Reuse existing
validation, action checks, tests and provider contracts. A future review may
reject, replace or delete a candidate without weakening approval, truth
isolation, determinism or mandatory verification. No future runtime is approved
for installation by this roadmap review.
