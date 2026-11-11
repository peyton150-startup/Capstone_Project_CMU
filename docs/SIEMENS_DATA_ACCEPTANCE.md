# Siemens SINUMERIK Data Integrity and Acceptance Contract — SDC-01 to SDC-20

**Applies to:** [Capstone_Project_CMU](https://github.com/peyton150-startup/Capstone_Project_CMU), draft [PR #233](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/233), read-only Siemens SINUMERIK data used by the Manufacturing Research Assistant.

**Status:** **Requirements documented; NOT implemented, NOT offline tested, NOT machine verified.** This document neither authorizes a controller connection nor changes machine/software configuration. The review is of the current `main` source and the draft scope, not physical Prestige hardware. Any required Siemens source, license, permission, hardware generation or sensor may be unavailable. Preserve existing MTConnect behavior and fixtures.

**Product focus:** identify **developing abnormalities** under comparable production conditions and investigate defensible causes. Siemens/DMG MORI tool-breakage, machine-protection, collision, alarm and pallet controls remain independent; use their permitted read-only observations for context and comparison, **never** recreate, reset, bypass, command or acknowledge them.

## Non-negotiable three-decision rule

1. **Collected / acquisition-qualified?** Machine + Siemens source identity, exact installed generation/version/option, server trust, live permission, exact approved NodeId/attribute/event, read-only request type and scope verified. If not, **do not request or persist** the data.
2. **Valid evidence?** Original source/node/channel/axis identity, physical meaning, units/type/scaling, native quality, effective event time, freshness, source epoch, gap/clock confidence and provenance verified. A collected record may be stored with a *bad-quality* status for auditing but **cannot** become a numeric health observation.
3. **Eligible for this analysis?** Anomaly or investigation consumer explicitly supports this signal and has sufficient coverage, operational context, compatible reference, permissions and temporal availability. A record can pass (1) and (2) but fail (3). A trend may be supported without a credible component-level diagnosis.

**Do not translate** unavailable, Bad, stale, unapproved, unsupported, unlicensed, unsynchronized or unverified into zero, healthy, idle, no alarm or a mechanical root cause. Distinguish **machine health** from **data/feed health**.

## Hardware/version/option applicability gate

| Siemens generation to qualify | Documentation and compatibility decision | Option and source separation |
|---|---|---|
| **840D sl** (including legacy DMG MORI CELOS/SLIMline builds) | Actual NCU, NCK/Operate/HMI and OPC UA server version; use matching 840D sl/828D Siemens configuration guide. Latest *supported for installed hardware* is an assumption until OEM evidence. | Licensed **Access MyMachine / OPC UA** end-customer server, separate OEM/PLC interfaces and any existing approved DMG MORI gateway. |
| **828D older PPU/PU** | Record precise PPU/PU revision; do **not** apply PU.5 or SINUMERIK ONE compatibility assumptions. | Licensed and permissioned actual supported OPC UA version or shop export/gateway; no assumed Advanced, event, history or PLC access. |
| **828D PU.5** | Verify PU.5 hardware and its matching newer Siemens documentation. Different implementation and address-space conditions may apply. | Inspect licensed end-customer server, PLC access, options and manufacturer permissions separately. |
| **SINUMERIK ONE** | Verify actual NCU/Operate/PLC/OPC UA server version; consult Siemens ONE/PU.5 matching configuration manual. | **End-customer**, **separately licensed OEM**, and potentially separate **integrated S7-1500 PLC OPC UA** servers are not interchangeable. OPC UA Advanced may expose methods not allowed in this collector. |

**Source selection:** first check a **shop-approved pre-existing MTConnect agent / DMG MORI CELOS X MDC or IoTconnector**; if it cannot supply the required approved data, qualify Siemens **Access MyMachine / OPC UA**. A filtered shop export may be the only permitted path. Never infer that newest software implies a purchased/enabled license or that an OEM option exposes a physical sensor. A "2026 machine" purchase/announcement does not establish manufacture year or SINUMERIK ONE.

**Required qualification artifact:** facility and internal machine ID; OEM model/serial (private); verified build/commission/retrofit dates or `unknown`; NCU/PU/PPU; NCK/CNC, HMI/Operate, PLC, drive/OPC UA versions; endpoint/application URI, certificate identity; server ownership; installed licenses, actual rights; OEM namespace/customizations; approved protocol/rate/retention; dated operator and IT/OT consent; configuration fingerprint. Changing any safety-relevant input can suspend affected capabilities pending requalification.

## Canonical data contract: mandatory fields, with truthful nullable values

The future controller-neutral **observation envelope** must preserve:

| Group | Mandatory identity versus nullable payload | Acceptance rule |
|---|---|---|
| Identity | `schema_version`; protocol and version; stable `site_id`, `machine_id`, `source_server_id`; endpoint/application URI or approved non-OPC-UA equivalent; subsystem + physical axis/spindle/channel identity where applicable; OPC UA namespace **URI plus identifier kind/value** and raw namespace index when supplied; canonical signal ID; mapping/config fingerprint; consent profile ID | Required source and approval fields are non-null; axis/spindle may be legitimately inapplicable but not silently guessed. A NodeId namespace index alone is unstable across server restarts. |
| Values | Native OPC UA Variant data type, rank and dimensions; original value **only when authorized**; canonical typed value nullable; native/canonical engineering units nullable when unknown; scaling rule ID; physical interpretation/reference frame; sampled/change/event mode | No lossy float coercion of Boolean, enum, bitfield, array or event; preserve warranted precision; unknown units/semantics **block** quantitative claims. |
| Quality | Complete native 32-bit `StatusCode` including severity, subcode and information bits where present; interpreted Good/Uncertain/Bad; eligibility and explicit reason/status | Good ≠ physical health; Uncertain excluded from normal baseline/diagnosis by default; Bad value is not usable; overflow/overload and status changes can invalidate continuous coverage. OPC UA event fields without DataValue quality must not receive invented Good codes. |
| Time | Source timestamp **nullable**, server timestamp **nullable**, collector receipt time, original offset/resolution if available, applicable OPC UA picoSeconds, time-source/clock uncertainty, connection/session epoch and native subscription notification sequence **where applicable** | Preserve distinct clocks, never fabricate a source timestamp or MTConnect sequence. OPC UA notification sequence is **per subscription**, not equivalent to a CNC sampling sequence or MTConnect data sequence. |
| Provenance | Source node/event/subscription; query or collection policy, authorization ID, hardware/software/license revision, approved rate/filter, raw segment ID/hash, normalization revision, loss/recovery boundary | Every accepted record can be reconstructed and attributed to exactly one authorized source and mapping; provenance persists into feature windows and evidence IDs. |

**Stored quality-degraded observation** is distinct from **accepted numeric evidence**. If Bad, Uncertain, invalid, stale or out-of-coverage, persist only the authorized audit/status metadata with no downstream use of the numeric value unless an explicitly signed policy defines an exceptional use. If the raw value itself is not authorized, do not acquire it, temporarily store it, log it or forward it.

## Requirements: positive and negative tests are mandatory

Every `SDC-xx` below is a **requirement**, not an implementation claim. A `documented` status means specified only. The exact target modules and pass/fail tests below must be transferred into the implementation verification matrix when engineering begins.

### SDC-01 — Source identity and controller compatibility (P0)

**Must capture:** qualified site/machine/OEM model; manufacturer year **only when verified**; controller family and NCU/PU/PPU hardware revision; NCK/CNC/Operate/HMI/PLC/OPC UA version; endpoint certificate/application URI; end-customer/OEM/PLC server ownership, options/license, role and OEM retrofit history; signed source-profile version.

**PASS:** a signal uniquely identifies the physical machine and the approved exact server/build; incompatible/changed build or ownership invalidates mapping before reuse. **FAIL:** identity inferred from IP, HMI branding, model family, coincidental machine name or an unsupported license. **Tests:** correctly qualified machine; wrong NCU, endpoint, software fingerprint, duplicate name, expired option, unknown retrofit. **Evidence:** approved machine version/option inventory + bound server identity. **Code:** new source profile; `ingestion/record.py`, `channel_map.py` and preflight.

### SDC-02 — Authorization, allowed acquisition operations and revocation (P0)

**Must capture:** exact authorized server+node+attribute+event identity; purpose/sensitivity; allowed Read/Subscribe (and explicit limited Browse discovery only); per-field rate, host, approver, expiry, retention and stop/revocation. No Write/Call, CNC/PLC command, file service, tool edit, program select or alarm acknowledge; this **includes** alarm-refresh methods under the present no-method rule.

**PASS:** no disallowed read or persistence, even if Siemens credentials are broader; expired/withdrawn permission blocks future requests. **FAIL:** unapproved variables fetched from a broad browse/subscription or filtered only after storage. **Tests:** allowed scalar; unknown node, overbroad account, changed allowlist, foreign server, revoke during recording, forbidden method, sensitive browse. **Evidence:** approved node register, offline negative I/O trace and site consent. **Code:** new allowlist/enforcement layer, `collector.py`, `pilot_preflight.py`. **Note:** if MTConnect/XML gateway returns all channels in one request, prove the **source itself is restricted/filtered** or block that feed; post-receipt stripping cannot retroactively prevent acquisition.

### SDC-03 — Loss-aware versioned observation schema (P0)

**Must preserve:** identity, typed measurements, optional native/canonical units, exact StatusCode, clock fields, source/receipt time, session epoch, subscription/protocol-specific continuity, authorization/map revision, source and archive linkage as defined above.

**PASS:** round-trip preserves native identity/value/quality/precision and all meaningful nullable fields; original MTConnect v1 records remain readable. **FAIL:** forced `sequence` or `instance_id` for Siemens, invented timestamp/unit, collapsed type, absent source approval. **Tests:** scalar/enum/array/event round-trip; missing timestamps; namespace URI/index change; schema migration; legacy JSONL fixture; null required ID rejected. **Evidence:** versioned schema plus round-trip fixtures. **Code:** `ingestion/record.py` and new protocol-neutral canonical envelope.

### SDC-04 — Verified signal meaning, topology and engineering units (P0)

**Must verify:** physical subsystem, NC channel and axis/spindle/tool index, data type, range/scale/resolution, actual vs setpoint, sign, coordinate frame and OEM/Siemens variable documentation + technician interpretation. SINUMERIK indexed NC variables, PLC symbolic/absolute addressing, arrays, enums, flags and case-sensitive namespaces require generation-specific mapping. A browsed but unsupported node is not validated.

**PASS:** one unique canonical signal links to a verified physical quantity+unit+frame on the correct machine; changes in type/meaning invalidate map/baseline. **FAIL:** guessed `spindle_load` from a label, first-index-only multi-axis map, cross-server ID collision, incompatible units/frames combined. **Tests:** five-axis topology, duplicate names/NodeIds on separate sources, wrong index, bitmask, wrong scaling, unsupported browse-visible variable, namespace drift. **Evidence:** signed mapping ledger with OEM/manual reference and observed sample. **Code:** `ingestion/channel_map.py`, `providers/factory.py`, sensor contracts.

### SDC-05 — OPC UA quality and StatusCode semantics (P0)

**Must interpret:** all severity/subcode/info bits on **every** DataValue before reading its Value, including Good/Uncertain/Bad, status-only notifications, queue **Overflow** where indicated, communication failures and server overload. Do not assume a successful OPC UA session implies a healthy sensor or current values.

**PASS:** Good still passes other checks; Uncertain excluded from ordinary baseline/diagnostic numeric calculations absent separate policy; Bad ignores value; loss indicators break affected coverage; Good→Bad→Good starts eligible intervals only when valid. **FAIL:** Bad/Uncertain becomes zero or healthy, queue overflow ignored, status-only update treated as numeric. **Tests:** Good/Uncertain/Bad variants, Good with info bits, Good_Overload, Good→Bad→Good, stale last usable, no value, status-only update. **Evidence:** native StatusCode test vectors and expected eligibility table. **Code:** new quality interpretation; `ingestion/quality.py`, `time_stats.py`, `monitoring/monitor.py`, `providers/replay.py`.

### SDC-06 — Numeric and typed-value integrity (P0)

**Must validate:** Variant type/rank, finite numeric values, native precision, scaling, signed/unsigned ranges, explicit physical-domain rules, unit conversion, arrays and enum/bitfield semantics without arbitrary float casts.

**PASS:** zero remains zero, missing remains missing, unusual but potentially real readings flagged for review, nonfinite/overflow/type-invalid values never enter numeric statistics. **FAIL:** `nan`/`Infinity`/strings/arrays coerced into accepted floats, inconsistent units or loss of diagnostic precision. **Tests:** IEEE invalids, malformed string, signed overflow, negative load with documented invalid domain, precision, wrong conversion, enum and array rank. **Evidence:** typed fixture results, canonical map reference. **Code:** `ingestion/record.py:number`, `contracts/observations.py`, `time_stats.py`, `replay.py`.

### SDC-07 — Timestamp fidelity and as-of event chronology (P0)

**Must preserve:** nullable source and server times, receipt time, original resolution incl. picoSeconds if used, UTC normalization/original offset, source clock identity, drift and latency uncertainty; separate *event time* from *time the data became known*.

**PASS:** no late-arriving or unreceived evidence can leak into historical as-of decisions; sorting uses qualified event time; fallback time retains `time_quality=fallback` and cannot masquerade as source time. **FAIL:** naive/damaged/future time silently accepted, CNC/PLC skew uncorrected, summary endpoints in file-order. **Tests:** null source time, source/server disagree, delayed event, two clocks, same timestamp, reversed records, server restart, post-cutoff data arriving early/late. **Evidence:** deterministic dual-clock fixtures and cutoff proof. **Code:** `record.py`, `time_stats.py`, `providers/replay.py:_visible`, recorded entrypoints.

### SDC-08 — Sample/update semantics and freshness (P0)

**Must record:** read versus poll versus data-change subscription versus event; requested **and revised** sampling/publishing intervals, queue, filter/deadband, expected update behavior, keepalive/session state, per-signal validated maximum hold/freshness, source update and rate.

**PASS:** no fabricated uniform samples from change-only notifications; latest Good becomes stale at approved limit; healthy subscriptions and silent failed sources distinguished where observable; source load remains under shop/OEM budget. **FAIL:** last value held indefinitely until some other channel updates, quiet subscriptions incorrectly labelled disconnected, one reading fills a long baseline. **Tests:** keepalive with unchanged value; deadband; revised publish interval, silent source, expired hold, queue overflow, low-rate pressure and high-rate axis channels. **Evidence:** per-signal acquisition policy + measured revised values. **Code:** `quality.py`, `time_stats.py:holds_in_run`, new OPC UA subscription accounting.

### SDC-09 — Connection epochs, detectable loss and recovery (P0)

**Must mark:** connect/start/stop, crash, reconnect, server reboot, session/subscription replacement, overflow, restart, clock change, timeout, and mapping requalification.

**PASS:** gaps are first-class and no values/events are invented across them; post-reconnect current state and previous historical state remain distinguishable; unknown machine status is not down/healthy. **FAIL:** missing alarm clear treated as cleared; data from distinct epochs spliced into continuous baseline. **Tests:** network interruption, resubscription, queue loss, server restart, previous-to-new epoch, duplicate notifications and crash resume. **Evidence:** loss/epoch timeline. **Code:** `record.py` markers, `quality.py`, `time_stats.py`, `monitoring/monitor.py`.

### SDC-10 — Siemens alarm/condition lifecycle (P0)

**Must keep separate:** event identity, condition identity, branch, native alarm code, NC/PLC/HMI component/channel/axis, severity, active/cleared/acknowledged when observable, transition time, language/text if permitted, state known/partial/unknown after reconnect.

**PASS:** retransmissions idempotent; missing event ≠ no alarm; initial active state only marked synchronized with independently supported passive mechanism. Under no-method policy, document inability to invoke alarm refresh. **FAIL:** reconnect silently recreates missed historical transitions or assumes inactive; acknowledgment treated as machine command. **Tests:** active/clear, repeat, initial active, lost clear, multiple branch IDs, localized text and unsupported refresh. **Evidence:** documented version-specific Siemens event structure, passive snapshot availability and replay. **Code:** new event contract, `monitor.py`, `providers/replay.py:get_events`.

### SDC-11 — NC program messages vs CNC/PLC/HMI/OEM events (P0)

**Must distinguish:** NCK alarms, PLC and HMI messages, NC program message stream (version-matched example `/Channel/ProgramInfo/msg`), drive and OEM cell events. Program messages are **not automatically alarm notifications**; text may be confidential.

**PASS:** correct authorized source/channel/event type and safe text handling, with no invented mapping. **FAIL:** missing program message assumed to be no alarm or program names included without consent. **Tests:** only alarm, only program message, distinct NC channels, translated text, duplicate representation. **Evidence:** exact installed server mapping + approved sample. **Code:** new Siemens event mapper and provider event retrieval.

### SDC-12 — Independent axes, spindles, NC channels, PLC servers (P0)

**Must identify:** linear/rotary axes as configured (not necessarily every A/B/C), their setpoint/actual/frame, multiple spindle and NC-channel IDs, separate PLC, DMG MORI automation/pallet controllers and multi-server equivalent observations.

**PASS:** same NodeId under different server namespace maps to different sources; equivalent sensors deduped for evidential independence but retained with provenance. **FAIL:** duplicated load or different axis counted as one reading, rotary angles compared to linear distances, PLC mistaken for NCK. **Tests:** real-like five-axis fixture, multiple spindles, separate PLC and shared node ID, transformed coordinate frames. **Evidence:** qualified topology inventory and technician mapping. **Code:** `channel_map.py`, `providers/factory.py`, `contracts/observations.py`.

### SDC-13 — Installed versions, licenses and configuration drift (P0)

**Must report per capability:** `verified_supported`, `documentation_only`, `license_missing`, `permission_denied`, `not_exposed`, `unsupported`, `unknown` or `out_of_scope`. Firmware/namespace/PLC-program/OEM-mapping/license/certificate changes trigger affected requalification.

**PASS:** newest compatible software is treated as an assumption until serial-specific proof; no newer feature assigned to older hardware. **FAIL:** IEC/OPC UA support treated as evidence of license installation or a machine sensor. **Tests:** older 840D sl/828D mismatch, PU.5 option, ONE OEM server confusion, license disabled, namespace revision. **Evidence:** version/option/configuration capability ledger and applicable Siemens security advisories. **Code:** source profile, `pilot_preflight.py`, map/permission gate.

### SDC-14 — Restricted fields, text trust and provenance (P0)

**Must apply per-field approval:** program/job/customer data, raw program text, tool tables, PLC DB/GUD/R parameters, OEM configurations, alarm text and private source topology. Data minimization applies **at acquisition**, storage, replay, manual retrieval, analytics, logs and model prompts. Operator text/Siemens text is data, not agent instructions.

**PASS:** no unapproved bytes queried, persisted, emailed, logged or sent to an external model; each derived item retains allowed source lineage and can be revoked. **FAIL:** blanket machine-level consent extends to arbitrary PLC fields; remote model flag substitutes for shop authorization. **Tests:** sensitive approved/unapproved alarm, restricted variable, injection, privilege withdrawal and model-egress interception. **Evidence:** signed scopes, data-flow audit, per-run provider authorization. **Code:** `collector.py`, `privacy.py`, `agent/untrusted.py`, recorded CLI/model policy.

### SDC-15 — Durable capture and deterministic reconstruction (P0)

**Must preserve:** native records, statuses, loss markers, versioned manifest, consent/configuration provenance, rotation and restart identities, both event and receipt chronology and bounded indexed queries.

**PASS:** exact authorized as-known-at cutoff reconstruction with no fabricated measurements, MTConnect backward compatibility and truthful nonnumeric events. **FAIL:** unreadable lines silently disappear, overlong file exhausts RAM, post-cutoff record leaks, duplicate after restart, timestamp sorting loses original arrival order. **Tests:** partial write, corruption, out-of-order JSONL, same-time events, 7-day synthetic multi-channel soak, rotation, schema migration, restart. **Evidence:** content hashes/manifest, fixture report, query latency and peak RSS. **Code:** `channel_map.py:read_capture`, `monitoring/runner.py`, `providers/replay.py`.

### SDC-16 — Machine-state semantics (P0)

**Must derive only what observed data supports:** running, idle, stopped, hold, interrupted, fault, warmup, maintenance, unknown and optionally cutting/tool-change/rapid/dwell **when justified by multiple approved signals**.

**PASS:** state carries supporting evidence/time/uncertainty and is eligible for compatible baseline only. **FAIL:** non-ACTIVE automatically labelled idle, spindle rotation always considered cutting, multi-channel disagreement ignored. **Tests:** ACTIVE→hold, unavailable Execution, emergency stop, spindle without cut, tool change, warmup, channel disagreement. **Evidence:** technician-aligned cycle transitions and state test fixtures. **Code:** `providers/replay.py:list_machines`, SM-6 segmentation.

### SDC-17 — Numeric/statistical-anomaly eligibility (P0)

**Must require:** qualified source, mapping, license/permission, quality, finite type, units/frame, time quality, freshness, sufficient window coverage, matched machine/cycle/operation state, confirmed healthy reference and no unresolved mapping revision.

**PASS:** per-signal eligibility status and reason; unrelated healthy channels can still be scored independently when one is Bad. Unsupported context ⇒ `baseline_unavailable`/`insufficient_data`. **FAIL:** simulator healthy reference applied to Prestige; sparse/unknown signals produce positive machine-health assurance or specific mechanical cause. **Tests:** one sample per ten minutes, Bad mid-cut, changed tool/program, unit mismatch, missing baseline, firmware drift and absent axis temperature. **Evidence:** feature-window quality report + held-out normal cases. **Code:** `screening.py`, `time_stats.py`, monitoring and SM-6/SM-7.

### SDC-18 — Agent investigation evidence eligibility (P0)

**Must expose:** only approved **as-of** usable sensors/events and their actual source, units, timestamps, status, context, coverage, uncertainty and provenance. A mapping is not proof of current data or diagnostics. No physical control tools. No simulator fabricated settings/history.

**PASS:** allowed capabilities are identical across policy tool listing and provider dispatch, truthful refusal for unavailable data, hypotheses distinguished from confirmed faults, no model action can touch CNC. **FAIL:** future data leak, unobserved state/tool value inferred, simulated units/manual treated as Prestige. **Tests:** wrong machine, empty/expired signal, unsupported history, late alarm, malicious text, absent source context and end-to-end investigation with permitted evidence. **Evidence:** capability diff, prompt and source→evidence trace. **Code:** `recorded_investigation.py`, `replay_investigation.py`, `providers/factory.py`, `providers/replay.py`, `agent/model_policy.py`.

### SDC-19 — Completeness, coverage and eligibility reporting (P1)

**Must report by site/machine/server/signal:** approved expected data inventory, exposed/supported/unlicensed/unauthorized/unknown, Good/Uncertain/Bad counts and durations only when meaningful, sampling actual/revised, gaps, latency distribution, restart/overflow, source health versus machine health, operating state coverage, current feature/tool eligibility.

**PASS:** completeness denominator comes from approved expected signal set, unavailable never improves score, unknown denominator produces `not_measurable` not a percent. **FAIL:** "100% complete" because uncollected fields were excluded or silence labelled machine healthy. **Tests:** expected source absent, no clock sync, partial permissions, signal quality degradation. **Evidence:** machine-readable per-source acceptance report. **Code:** quality/preflight, new completeness reporting.

### SDC-20 — Installation-specific resource and reliability budgets (P1)

**Must define with IT/OT:** maximum session/subscription/monitored items, requested vs revised polling, CPU/network/disk/RAM, backlog and load shedding, per-signal freshness, max ingest lag, malformed/dropped data, allowed recovery, query p95/p99 and retention. **No universal invented thresholds**.

**PASS:** all approved measurable budgets have measured evidence; recorder fails closed/degrades without affecting CNC; smoke and soak tests run under approved envelope. **FAIL:** busy controller loses telemetry silently, unbounded query or broker buffer, overflow ignored, unauthorized retry or reboot. **Tests:** dense five-axis fixture, slow server, flow burst, network drop, queue overflow, seven-day soak, disk full and controlled shutdown. **Evidence:** resource budget sheet signed by IT/OT + benchmark traces. **Code:** collector, quality, storage, replay and monitor.

## Consolidated requirements-to-code-to-test register

Each SDC above **is** its functional specification. The register below provides the stable ID crosswalk, applicability, required license/source precondition, evidence owner and current verification status. For every entry the developer **must** produce both its named positive and negative tests above, explicit pass/fail evidence, and an updated module reference. Rows cannot be marked implemented on the basis of the PR being merged or a generic OPC UA client library.

| ID | Priority | Generation / source option | Existing module boundary | Required qualification / verification artifact | Current status |
|---|---|---|---|---|---|
| SDC-01 | P0 | ALL / selected end-customer, OEM, PLC or gateway | record, channel_map, preflight | Model/NCU/versions/license, trusted server and technician signoff | **Documented** |
| SDC-02 | P0 | ALL / only explicitly permitted endpoint, nodes and rights | collector, preflight, privacy | Signed node/attribute/event authorization + offline no-write/no-unapproved-acquisition test | **Documented** |
| SDC-03 | P0 | ALL / MTConnect compatibility + OPC UA DataValue | record | Native/canonical schema and round-trip/migration test report | **Documented** |
| SDC-04 | P0 | ALL / installed node mapping or approved export | channel_map, factory | Physical semantics/units/frame/index proof and collision tests | **Documented** |
| SDC-05 | P0 | ALL OPC UA / DataValue status and notifications | quality, time_stats, monitor | OPC StatusCode/subcode/info-bit vectors + inclusion/exclusion tests | **Documented** |
| SDC-06 | P0 | ALL / numeric and typed signals | record, observations, time_stats | Finite/value/array/enum conversion and negative tests | **Documented** |
| SDC-07 | P0 | ALL / controller/PLC/collector clocks | record, replay, time_stats | Clock and retrospective-as-of receipt-time tests | **Documented** |
| SDC-08 | P0 | ALL / authorized polling or subscriptions | quality, time_stats, collector | Rate/revision/freshness/hold expiry and queue tests | **Documented** |
| SDC-09 | P0 | ALL / session, subscription and source restart | record, monitor, replay | Epoch/loss/reconnect idempotency tests | **Documented** |
| SDC-10 | P0 | Applicable licensed Alarm & Condition/event source | monitor, replay.get_events | Alarm identity and activation/clear/reconnect event fixtures | **Documented** |
| SDC-11 | P0 | Version-specific part-program/PLC/HMI/OEM messages | event mapper, replay | Per-generation source mapping, consent and no-conflation tests | **Documented** |
| SDC-12 | P0 | Installed multi-axis/NCU/PLC topology | channel_map, observations | Independent axis/spindle/channel mapping, clock and duplicate tests | **Documented** |
| SDC-13 | P0 | 840D sl / older 828D / PU.5 / ONE per installed option | preflight, channel_map | Serial-specific version/option qualification and drift rejection tests | **Documented** |
| SDC-14 | P0 | All fields / individually approved sensitivity | privacy, collector, untrusted | Unauthorized-acquisition/egress and provenance proof | **Documented** |
| SDC-15 | P0 | Every selected recording source and legacy MTConnect | runner, read_capture, replay | Integrity manifest and deterministic replay/soak tests | **Documented** |
| SDC-16 | P0 | Per-machine observable state signals | replay.list_machines, SM-6 | Technician-validated state transition and ambiguity tests | **Documented** |
| SDC-17 | P0 | Eligible approved physical numeric signals | screening, time_stats, SM-7 | Feature-quality eligibility / baseline exclusion / held-out tests | **Documented** |
| SDC-18 | P0 | Eligible approved evidence/tool/event subsets | recorded_investigation, replay_investigation, factory | Advertised-vs-actual tool set, cutoff, no-control and provenance tests | **Documented** |
| SDC-19 | P1 | Expected approved sources/signals | preflight, quality, monitoring | Source-level completeness report with honest denominators | **Documented** |
| SDC-20 | P1 | Actual OEM/IT-approved resources, not universal numbers | collector, monitor, storage, replay | Signed rate/resource/retention budget + soak traces | **Documented** |

**Status vocabulary for future tracking:** `documented` = specified only; `implemented` = corresponding code exists; `offline_verified` = reproducible test evidence on exact versioned fixtures; `machine_verified` = authorized technician/IT/OT accepted a physical-machine test; `blocked` = unresolved source, license, permission, signal or test dependency. These states must refer to the **Siemens requirement**, not unrelated MTConnect/simulator functionality. Every row also needs explicit assigned owner, implementation target and test artifact link when work begins.

### Verified current implementation crosswalk (static source audit, no new test run)

- `capstone/ingestion/record.py`: `TelemetryRecord` is MTConnect-specific (mandatory `sequence`), with source and receipt times but without OPC UA StatusCode, server/source dual timestamps and typed Variant provenance. `number()` uses `float(value)` and does not reject nonfinite float values.
- `capstone/ingestion/channel_map.py`: human mapped channels depend on a hashed MTConnect `/probe`; observed counts and reported fields may key by data-item ID without full device/source qualification.
- `capstone/ingestion/quality.py`: stale limits by `data_item_id` alone; requires fully qualified source/channel. `time_stats.py` holds to next sample or gap-free run end with no separate maximum-freshness cutoff.
- `capstone/providers/replay.py`: relies on source timestamp and file order for cutoff, oversimplifies non-ACTIVE execution states; some real event/settings/maintenance tools refuse correctly until approved sources exist.
- `capstone/monitoring/monitor.py`: useful MTConnect condition/threshold alerts but no native OPC UA status, alarm lifecycle or production statistical feature/incident handoff.
- `capstone/recorded_investigation.py` versus `capstone/replay_investigation.py`: separate capability descriptions and cutoff logic; must converge on one canonical available-evidence contract.
- `capstone/providers/factory.py`: tool request/response validation and `MAX_ROWS=300` **already exist**; replay still constructs potentially unbounded intermediate lists. Preserve existing provider contracts for simulator and MTConnect regressions.
- `capstone/agent/model_policy.py` and `capstone/manual/sections.py`: simulator-first prompts and `SIM-CNC-001` manual; **real data must not inherit unsupported simulator state, settings, repairs or manual conclusions**.
- `capstone/memory/policy.py`: intentionally requires independently checked intervention outcomes; real triage must not auto-promote unverified diagnoses.

**No Siemens adapter, physical controller compatibility, authorized Siemens samples, node mapping, OPC UA security verification or green tests are asserted by this document.**

## Release/verification gates: each one is a stop/go decision

| Gate | Stop/go condition | Required evidence |
|---|---|---|
| **Data A — acquisition authorization** | Qualified exact machine/controller/software/license/endpoint/role and permitted data use. Missing approval = BLOCK. | Signed machine/source profile, approved field list, licensing and access checks. |
| **Data B — approved semantics** | Every selected signal or alarm has independently verified identity, physical meaning, unit/index and authorization. | Siemens/OEM reference, technician-reviewed map, signed permission. |
| **Data C — canonical fidelity** | Typed normalized data retains allowed native value, unit/scale, full quality/status and original/receipt time. | Schema migration, positive+negative round-trip fixtures for every type. |
| **Data D — unusable data quarantine** | Bad/Uncertain/stale/out-of-order/duplicate/gap events handled without false baseline health. | Fixture proofs for freshness, quality, source epoch, loss and duplicate suppression. |
| **Data E — offline reconstruction** | Storage/replay reproduce **only what was knowable as-of cutoff**, including late arrival and missing event state; MTConnect remains compatible. | Deterministic replay and multi-channel soak traces. |
| **Data F — downstream gating** | Tools/ML only receive currently eligible sources/capabilities; no unsupported historical data, simulator values or causal proof invented. | Tool list↔provider parity; source→feature→agent evidence and cutoff test. |
| **Data G — no control and privacy** | No live Write/Call/file/ack/command API; no off-allowlist read or remote model egress without independent approval; fail closed. | Offline negative I/O/egress/provenance tests and least-privilege review. |
| **Data H — actual machine acceptance** | Separately authorized IT/OT and technician confirm physical signals, state/alarms as they arise, minimal production impact and continued rights. | Signed live smoke/capture acceptance; unexposed fields explicitly unsupported. |

**Every gate is presently OPEN/UNVERIFIED** for Siemens. Generic MTConnect/simulator tests do not count as passing Siemens gates.

## Minimal mandatory test fixtures and reports

Implementers should define versioned fixtures for **840D sl**, **older 828D**, **828D PU.5** and **ONE**, including different NodeIds, options, end-customer/OEM/PLC servers and missing features; add **multi-axis/multi-spindle** and **DMG MORI cell/PLC** cases when the machine topology requires them. Include synthetic DataValues (Good, Uncertain, Bad and info-bit loss), bitfields, arrays, partial times, source/server clock skew, revised sample rates, queue overflow, session restart, active/cleared/missed alarms, part-program message separation, unauthorized/sensitive values, duplicate channel IDs, firmware/license drift and deterministic retrospective cutoff.

A gate report must record `requirement_id`, hardware/source configuration, test fixture hash, code/schema revision, license/precondition, exact positive/negative case, pass/fail result, measured metric, evidence location, reviewer and `documented/implemented/offline_verified/machine_verified/blocked` state. Never mark a gate "passed" from code existence or a successful OPC UA session.

**Quantitative criteria are site-specific:** maximum controller request rate, monitored items, sampling/notification rates, freshness/coverage, data loss, ingest lag, end-to-end query latency, memory/network/disk limits, recovery time and retention must be measured and approved by shop IT/OT rather than guessed.

## Reference documents and future-work alignment

- [OPC Foundation OPC UA Part 4 — DataValue and severity / time semantics](https://reference.opcfoundation.org/specs/OPC-10000-4/7.11) and [StatusCode descriptions](https://reference.opcfoundation.org/specs/OPC-10000-4/7.38) — complete StatusCode is mandatory; Good is not physical proof and Bad is unusable.
- [OPC Foundation OPC UA Part 4 — NotificationMessage](https://reference.opcfoundation.org/specs/OPC-10000-4/7.26) — per-subscription notification sequence, not machine data sequence.
- [Siemens SINUMERIK 840D sl/828D OPC UA manual](https://support.industry.siemens.com/cs/ww/en/view/109807257) and [SINUMERIK ONE/828D PU.5 OPC UA manual](https://support.industry.siemens.com/cs/ww/en/view/109994190). Match **installed** software/NCU and option revisions.
- [DMG MORI controls and data interfaces](https://us.dmgmori.com/products/controls) for existing shop-approved MTConnect/MDC/IoTconnector paths.

This document is the **authoritative SDC-01..SDC-20 acceptance contract** linked from `docs/MVP_SCOPE.md` S-0 / S-0/E2E. Existing exploratory audit notes remain context, not substitute criteria. **Success means accurate, permitted, traceable evidence and a trustworthy determination of whether the evidence may be used—never merely a connected OPC UA socket or a received number.**
