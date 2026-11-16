# Siemens OPC UA recorder monitor — local front-end design

**Status:** proposal only (docs-only, 2026-11-16). **Pilot:** one authorized Prestige CNC / Siemens OPC UA source. **No UI, status service, or physical-controller validation exists yet.** This is a recorder health interface, **not** an anomaly detector or CNC operator panel.

## Goal and scope

On the factory floor, answer within five seconds: (1) Is the *local recorder process* running? (2) Is it connected **and subscribed** to the approved server/nodes? (3) Are fresh, quality-eligible measurements arriving? (4) Are any approved channels stale or missing? (5) Is recording durably going to an approved private location without gaps or storage pressure?

**First version:** local-only, read-only status page backed by the laptop collector; starting/stopping the process stays in PowerShell (Ctrl+C to stop). No direct browser-to-CNC connection, write/Call/browse method, automatic LLM upload, remote dashboard, production-control button, or promise that the machine itself is safe. A simple CLI `--progress` summary is an acceptable first implementation before the browser UI.

## Verified existing foundation and missing pieces

| Exists on `main` | Still to implement / validate |
|---|---|
| `capstone/ingestion/siemens_opcua_adapter.py`: `--config`, `--out`, optional `--audit`; approved-node data-change subscriptions, reconnection attempts, flushed JSONL and connection audit | Local process/sink health telemetry, subscription *confirmed* marker/status, actual negotiated rate/monitored-item results, persistence/error reporting and UI service |
| `siemens_opcua_record.py`: `data_change` values/status/source/server/receipt times and `opcua_session` connected/heartbeat/disconnected/gap/stopped | Siemens v2 incremental monitor and quality/coverage aggregation; no invented uniform sampling |
| `capstone/monitoring`: MTConnect v1 file-following/alert rules | **Not** a Siemens v2 monitor; do not feed OPC UA JSONL into v1 `parse_line` |
| `ingestion/pilot_preflight.py` and MTConnect `visit_log.py` | Siemens-specific signal map, capture acceptance, operator-event alignment and machine verification |

Code references: [adapter](../capstone-code/capstone/ingestion/siemens_opcua_adapter.py), [v2 records](../capstone-code/capstone/ingestion/siemens_opcua_record.py), [legacy monitor](../capstone-code/capstone/monitoring/runner.py), [data acceptance](SIEMENS_DATA_ACCEPTANCE.md).

## Proposed screen (desktop, laptop at the machine)

```text
SIEMENS RECORDER MONITOR                          [LOCAL ONLY] [Session ID]
Authorized site / machine: [approved label]        Recording since [time]
Process: RUNNING        OPC UA: CONNECTED        Subscription: CONFIRMED
Measurements: RECEIVING / DEGRADED / NONE          Last qualified: [age]

[Received values] [Good among received] [Fresh eligible signals] [Gap count]
[Receive rate]    [Bad/Uncertain]       [Disk free / write health] [Clock warning]

APPROVED SIGNALS
Signal / axis       Last value + unit     Quality    Last change    Freshness
Spindle 1 speed     8,500 rpm             Good       1.2 s ago      Within policy
Spindle 1 load      42.1 %                Good       0.4 s ago      Within policy
Machine execution   Running               Good       34 s ago       Change-only
Temperature         —                     Unknown    Never          No samples

SESSION & DATA-QUALITY TIMELINE    [gaps | reconnects | bad values | warnings]
Recent collector/audit events and timestamps; inspect only approved metadata
File: local approved destination | size | last flushed | storage/retention
```

*All values above are fictitious layout examples.* No program names, customer IDs, raw alarm text, credentials or controller topology shown by default.

### UX behavior

- **Top banner** has *separate* process, connection, subscription and measurements states. A `connected` record occurs before `subscribe()` completes in today's code; **never** label it subscription confirmed until a successful monitored-item result is instrumented.
- **Data tiles** show counts and time windows, not an invented sampling percentage. Label `Good / received` with its denominator and window; display `N/A` when no data arrived. `Fresh eligible signals: N/M` is possible only with an explicitly approved expected-signal inventory and per-signal update/freshness policy; otherwise show `unknown`.
- **Signal rows** are keyed by `(server_uri, namespace_uri, identifier_type, identifier)`, with independently approved labels for machine, NC channel, spindle/axis, meaning and unit. Never infer spindle load or units from node names. Distinguish numeric, enum/boolean, and unsupported values.
- **Status semantics**: `Process stopped` / `Connecting` / `Connected, unconfirmed subscription` / `Subscribed, awaiting values` / `Receiving, quality eligible` / `Degraded` / `Unknown`. Good OPC UA status is necessary but not sufficient for analyzer eligibility; units, source mapping, time quality, operating state and gaps still gate downstream use.
- **Freshness** uses source-specific expectations: change-only machine state may remain silent normally; time-series load cannot be considered fresh indefinitely. A heartbeat establishes collector liveness only, **not** fresh telemetry, machine health or a successful subscription.
- **Timeline** separates session losses, missed subscription messages, queue overflows, Bad/Uncertain data, unsupported types and sink/storage errors. A gap never silently becomes zero loss. Display source/server/receipt times with the clock offset/uncertainty when known.
- **Visual design**: single-machine, large legible status, high-contrast typography, neutral for unknown, warning/error with text **and** icon (never color alone), keyboard accessible, adaptable to laptop width; no animation required.

## Local architecture and read model (proposed, not an existing API)

```text
Approved SINUMERIK OPC UA source
    -> existing read-only Siemens collector
        -> v2 raw JSONL + audit JSONL (private, append-only per session)
            -> bounded incremental v2 parser + process/disk/sink health adapter
                -> local snapshot/read-only HTTP endpoint on 127.0.0.1
                    -> single-page operator-visible health screen
```

The status service must **not** instantiate its own OPC UA client or contact the machine. Consume a bounded stream/offset, complete JSONL lines, and handle restart, truncation/rotation and file write errors. Never tail/reparse the full multi-day file on each refresh.

Suggested *derived* `RecorderHealthSnapshot` fields (names are design targets; not present today): `run_id`, `machine_label`, `config_map_revision`, `process_state`, `session_epoch`, `connection_state`, `subscription_state`, `measurement_state`, `last_receive_at`, `last_good_numeric_at`, `received_total`, `good_total`, `uncertain_total`, `bad_total`, `unsupported_total`, `gap_count`, `reconnect_count`, `sink_last_flush_at`, `output_bytes`, `disk_free_bytes`, `clock_warning`, and `signals[]` (approved identity, value if permitted, unit, type, quality, last source/receive timestamps, freshness policy/result, eligible/unknown reason).

**Derived vs missing:** v2 data records expose StatusCode, timestamps, value and node identity; session markers expose several connection/gap events; audit exposes connection attempts. Process liveness, confirmed subscription success, sink failure, disk metrics, expected-source inventory, qualified units and freshness policies require additional instrumentation/configuration. Missing inputs remain `unknown`, not healthy. Device or process restart must not reuse stale counters as a current run.

## Implementation order (smallest safe vertical slice)

1. **P0, before first physical capture:** Add CLI progress/live-health summary from v2 stream plus recorder process/sink heartbeat and confirmed subscription instrumentation. Alert locally if connected but no valid expected data, if disk writes fail or if monitoring stops. Preserve privacy and never block the underlying collector on slow UI rendering.
2. **P0, before multi-hour capture:** Add approved per-node mapping/freshness policy, Siemens v2 validator, explicit Good/Uncertain/Bad/unsupported counts, source/receipt clock checks, gaps and reasoned unknown states. Do not convert silence to a sample or count unapproved channels as coverage.
3. **P1, local front end:** Implement the screen with a read-only localhost endpoint; limited metadata and authorized sample values, local authentication/access restrictions appropriate to the host, no remote binding or cloud egress. Support simulated v2 fixtures first, then independently approved physical tests.
4. **P1, before seven-day unattended capture:** File rotation, free-space thresholds, a session manifest (code/config/schema versions and integrity hashes), durable restart and gap accounting, revocation/deletion procedure, offline export of capture-health scorecard.
5. **Later only if operator feedback supports it:** Lightweight trend sparkline for approved signals and downloadable **metadata-only** session summary; keep diagnosis, intervention controls and external model use out of this UI.

## Acceptance criteria / test cases for a future implementation

- Fixture with `connected` then subscription refusal is **not** labeled ready; real `data_change` increments counts only after receipt.
- Empty capture, heartbeat-only capture, silent change-only variable and known stale sampled variable have distinct, honest states.
- Bad/Uncertain, unsupported Variant type, missing source timestamp and non-finite numeric value never inflate quality-eligible count; no default zeros.
- Two axes with identical display labels remain separate by native identity; disallowed or unmapped nodes are not displayed as authorized.
- Reconnect, missed-message and overflow markers surface as explicit data-quality incidents; sequence wrap/reconnect does not invent lost measurements.
- Disk-full, log write failure, process crash, file rotation/truncation and malformed/partial JSONL become visible warnings; a frozen UI cannot stay green.
- Local-only endpoint cannot command CNC changes, open unexpected controller sessions or send factory data off-host. No hardcoded secrets or unapproved program/alarm text.
- Offline tests use synthetic v2 samples; physical-machine success is **unverified** until shop IT/OT approval and observed evidence. Record actual rates, load, false freshness alerts and technician usefulness before calling the UI pilot-ready.

## Explicit non-goals and decisions

This design does not change the collector, its OPC UA permissions or controller configuration; does not build a front end; does not assert that Siemens alarm-event subscriptions, real operating-state classification, diagnosis accuracy or usable baseline already exist; and does not turn a UI status into an industrial safety assurance. Existing [SDC-01–20](SIEMENS_DATA_ACCEPTANCE.md) and [RMI-01–07](REAL_MACHINE_INTELLIGENCE_ACCEPTANCE.md) release gates still apply.
