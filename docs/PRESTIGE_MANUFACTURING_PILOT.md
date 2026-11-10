# Prestige Manufacturing — first-machine visit and read-only pilot runbook

**Status: awaiting a date and controller details from Naseem (2026-11-10).**
This is a controller-agnostic field-readiness plan; it is not evidence of
manufacturer consent, a scheduled visit, a connected machine, or a completed
seven-day pilot.

## Objective and success criteria

The first visit should answer **Can we read it? Can we interpret it? Can a
technician confirm what the readings mean?** A good result is one authorized
machine with a saved capability inventory, an approved recording of several
normal cycles, explicit field mapping and units, a timestamp-matched operator
event log and a concrete permission decision for any follow-on collection.

An approved short capture is **not** approval for a seven-day installation.
A saved file is **not** proof that a component is failing. The CPU-based
anomaly detector's simulator reference must never be reused as real-machine
normal behavior.

## What to ask Naseem once the visit date is agreed

1. Which exact machine will we examine: manufacturer, model, approximate
   year, controller make/generation and software revision?
2. Who handles IT/OT access, and is there an existing approved
   **read-only** controller interface or historical export?
3. Which operational fields may be read or exported? A machine's endpoint
   may expose confidential program names, customer information or other
   restricted metadata in addition to load, RPM and execution state.
4. Can a technician observe several normal cycles and note tool/program
   changes, alarms, maintenance, warm-up and anything unusual?
5. Is there permission for a short on-site connectivity/recording smoke test?
   If that works, would a separately approved seven-day collection
   pilot be acceptable? Can the data remain on the shop's PC?
6. Is any work subject to export-control, confidentiality or customer
   restrictions that prohibit capture or sending telemetry to an LLM?

If the controller is unknown or there is no safe approved path, the first
visit is a discovery session. Do **not** scan the network, enable ports,
change the CNC settings or bring unapproved sensors. Ask whether an offline
export can be provided later.

## Approval and confidentiality boundary

A facility manager/owner and IT/OT authority must approve the precise
machine, connection method, fields, polling frequency, duration, storage,
retention/deletion, withdrawal process and permitted uses **in writing**.
The local preflight's approval fields are a checklist of documents a person
must verify, not signatures or a substitute for legal review. Do not send
shop readings to an external model unless that specific transfer and provider
are authorized; collection approval alone is insufficient.

**Important limitation:** the current MTConnect collector reads the source's
returned data items; it does not implement per-item privacy filtering during
collection. If the shop authorizes only a subset, arrange a **shop-filtered
offline export before acquisition**, or obtain explicit authorization for
the entire returned stream. The preflight can find unapproved fields in a
saved file, but that is not permission to collect them in the first place.

Keep probe XML, controller metadata, raw JSONL, operator notes, credentials
and model output in a private directory **outside every Git checkout**.
Do not commit them to the public repository. Verify the machine/PC clocks
agree, and establish an immediate stop/revocation contact.

## Preparation with no machine access

From the repository's Python project working directory, create the blank
private plan. Leave unknown controller and approvals blank:

~~~bash
uv run python -m capstone.ingestion.pilot_preflight template --out ../pilot-data/plan.json
uv run python -m capstone.ingestion.pilot_preflight check --plan ../pilot-data/plan.json --stage discovery
uv run python -m capstone.ingestion.visit_log template --out ../pilot-data/events.csv
~~~

Edit the private JSON only when each field has been confirmed by the shop.
The check returns a nonzero exit code for missing readiness facts. It
does not infer a controller brand.

If and only if the shop approves a compatible MTConnect endpoint, a
read-only probe/recording may be authorized from an approved local PC
(example URL below is a **placeholder**, not a discovered endpoint):

~~~bash
uv run python -m capstone.ingestion --url http://APPROVED-LOCAL-AGENT:8082 --save-probe ../pilot-data/probe.xml
uv run python -m capstone.ingestion.channel_map build --probe ../pilot-data/probe.xml --assign ../pilot-data/assignments.json --out ../pilot-data/channel-map.json
uv run python -m capstone.ingestion --url http://APPROVED-LOCAL-AGENT:8082 --out ../pilot-data/telemetry.jsonl --interval 5
~~~

The assignments file must be manually built from the machine's probe and
manual; do not guess units or convert a field into vibration/temperature
without evidence. The five-second example poll rate is not automatically
approved. Never run the third command if the controller would return
unapproved fields. For non-MTConnect controllers, do **not** use this collector:
identify an authorized adapter or shop-provided normalized export first.

During approved normal cycles, a technician fills the private event CSV
with timezone-aware timestamps for tool/program changes, warm-up, stops,
maintenance and unusual behavior.

## Acceptance after a short authorized capture

~~~bash
uv run python -m capstone.ingestion.channel_map check --map ../pilot-data/channel-map.json --probe ../pilot-data/probe.xml --capture ../pilot-data/telemetry.jsonl
uv run python -m capstone.ingestion.visit_log check --probe ../pilot-data/probe.xml --capture ../pilot-data/telemetry.jsonl --events ../pilot-data/events.csv
uv run python -m capstone.ingestion.pilot_preflight check --plan ../pilot-data/plan.json --stage capture --probe ../pilot-data/probe.xml --map ../pilot-data/channel-map.json --capture ../pilot-data/telemetry.jsonl --events ../pilot-data/events.csv
~~~

The last check requires a machine identifier, written permissions, exact
approved fields, approved collection method, retention/stop plan, probe/map
agreement, a capture limited to the one target machine, actual numeric
mapped readings, matched technician event times, manually confirmed normal
cycles and checked clocks. It blocks if any recorded field was not approved.

To use an external LLM on the data, first confirm separate provider-transfer
approval and review the separate replay-investigation change ([draft PR
#221](https://github.com/peyton150-startup/Capstone_Project_CMU/pull/221)).
No AI diagnosis or machine action is necessary for the initial visit.

## Optional seven-day follow-on (separate permission)

A **second** decision authorizes any week-long collector. The plan must
identify the restart/stop contact, approved storage and file rotation,
retention/deletion path, IT/OT network controls and approved poll rate.

~~~bash
uv run python -m capstone.ingestion.pilot_preflight check --plan ../pilot-data/plan.json --stage week --probe ../pilot-data/probe.xml --map ../pilot-data/channel-map.json --capture ../pilot-data/telemetry.jsonl --events ../pilot-data/events.csv
~~~

A passing preflight indicates paperwork and initial evidence only. It does
**not** prove seven days of uptime, no machine impact, reliable diagnoses,
safe unattended operation or existence of spool/upload infrastructure. Keep
the deterministic collector, monitor and watchdog independent of any LLM.
Review missing/late samples, sequence gaps, uptime, data deletion and
technician confirmations before extending the experiment.

## What we should implement only after receiving the real data

1. SM-6: segment observable machine operating states and compare against
   the technician's time-stamped notes.
2. SM-7: build a **separate** healthy reference for this exact machine,
   using operator-confirmed normal cycles, not simulator data.
3. Validate SM-5 gaps and time-weighted statistics for the controller's
   actual reporting mode.
4. Finish real-world CPU anomaly detection: state-aware baseline,
   quality-gated signal features, calibrated alert thresholds and
   technician-reviewed false positives before incident triggering.
5. Run the read-only replay investigation with a capability-filtered tool
   list only when the data transfer is allowed. An inconclusive answer is
   acceptable; part-level diagnosis needs technician-confirmed labels.
