# Prestige Manufacturing — first-machine discovery and read-only capture

**Status, 2026-11-10:** Visit date pending Naseem's confirmation. Exact CNC machine,
controller, protocol, approved fields and authorized collection method are
**unknown**. No site connection, signed permission, physical-machine test,
operator-labelled capture or seven-day collection has occurred.

**First visit success:** leave with one permitted, verified machine capture;
probe-derived field map; technician event notes aligned with timestamps; explicit
permission to continue collecting; **or** a dated technical/authorization
blocker and named next owner. This is an engineering acceptance gate, not a
promise of predictive maintenance or root-cause accuracy.

## A. Before scheduling and site access

1. **Wait for Naseem to confirm a visit date.** Only then ask which machine
   can be inspected: make, model, year, controller manufacturer/model and
   software revision, and whether the shop already uses MTConnect, an OEM
   data-collection interface, a read-only local export, or something else.
   Do not assume the controller is Haas.
2. Ask who owns IT/OT approvals, what onsite computer/network segment could
   be used, whether customer programs or export-controlled jobs run on that
   equipment, and whether the approved data must remain on site.
3. Prepare a private site inventory and approval record, and identify the
   authorized human who can stop collection. Agreement must specify machine,
   permitted data-item IDs, request rate, storage, retention/deletion,
   downstream uses (including any external LLM provider), access revocation
   and purpose. Agreement is not a code flag.
4. Use one independent collector process; the model's status/latency must
   never control collection, production machinery or the controller.
   No controller writes, resets, program transfers, cycle-start/stop,
   exposed ports to the public Internet, network scanning or bypassing IT/OT.

## B. Discovery at the shop

**Human confirmation first:** record the machine label and controller, obtain
specific read-only permission, ask about permitted poll rate, network path and
data list, confirm the clock/time zone against the operator log, and arrange
a low-impact trial while a shop technician observes the controller.

**If (and only if) an MTConnect agent is approved and supported:**

From the repository root with `uv sync --all-extras` complete, use paths
**outside the public Git checkout**:

```bash
uv run python -m capstone.ingestion.pilot_acceptance template \
  --out ../pilot-data/prestige-manifest.json
uv run python -m capstone.ingestion.visit_log template \
  --out ../pilot-data/operator-events.csv

# Replace URL, machine selection and rate only with IT/OT-approved values.
uv run python -m capstone.ingestion \
  --url http://APPROVED-LOCAL-AGENT:PORT \
  --save-probe ../pilot-data/probe.xml

uv run python -m capstone.ingestion.channel_map build \
  --probe ../pilot-data/probe.xml \
  --assign ../pilot-data/assignments.json \
  --out ../pilot-data/channel-map.json

uv run python -m capstone.ingestion \
  --url http://APPROVED-LOCAL-AGENT:PORT \
  --out ../pilot-data/telemetry.jsonl --interval 5

uv run python -m capstone.ingestion.channel_map check \
  --map ../pilot-data/channel-map.json \
  --capture ../pilot-data/telemetry.jsonl \
  --probe ../pilot-data/probe.xml
uv run python -m capstone.ingestion.visit_log check \
  --probe ../pilot-data/probe.xml \
  --capture ../pilot-data/telemetry.jsonl \
  --events ../pilot-data/operator-events.csv
```

**These are example invocations, not permission or a verified protocol.**
The 5-second interval is the existing collector default and proposed pilot
rate, not a universally safe rate. A human must map each allowed observed
data item to its correct physical meaning and sensor in
`assignments.json` after looking at the controller documentation; do not
guess temperatures, vibrations, motor current, units or meanings from names.
The CLI refuses writing real data into the repo.

If the controller does **not** expose an authorized MTConnect agent, do not
reuse MTConnect `/probe` instructions. Record the manufacturer-supported
read-only access/export and adapter requirements in the private manifest.
An approved offline export is an alternative path, but it is not yet covered
by the MTConnect-specific automatic acceptance checks.

## C. Capture and operator evidence

Record at least three *technician-confirmed* normal operating cycles, if
production safely allows this. Include representative idle, warm-up, spindle
running and cutting states when observable. Operators should timestamp
program, tool and batch changes; warm-up, maintenance, alarms and anything
unusual, using the existing CSV columns:
`at,event_type,note,logged_by,until`. Timestamps require a UTC offset.
Do not photograph restricted programs or copy customer/job-identifiable
data without written permission.

Review these independent questions before deciding what to implement:

| Question | Required evidence | If missing |
|---|---|---|
| Can it be read? | Authorized interface, saved probe or explicitly supported export, real captured records | Record machine/controller and access blocker; no network workaround |
| Can it be interpreted? | Units, manually verified channel map, observable state/cycle transitions, source clock and data quality | Leave unavailable fields unavailable; build adapter/SM-6 only after a probe |
| Can it be checked? | Time-aligned operator events, normal-cycle confirmation, requested prior alarms and maintenance records | No root-cause or detection-accuracy claim |
| Can collection continue? | Dated owner + IT/OT permission, approved field list/rate, local storage, stop/revocation and retention | End after discovery; never leave unattended collection |
| Can the agent use it? | Replay provider, capability-filtered tools, private audit and separate **explicit** external model permission | Analyze locally only, or defer model calls |

When the shop permits collection for seven days, agree on measurable collection
uptime, explained gaps, no production impact, daily disk usage, operator
feedback and a named shutdown contact. The 95%-uptime and unexplained-gap
targets in `MVP_SCOPE.md` are proposals to agree with the shop, not commitments.
Collecting predominantly normal signals can validate the collector and
state-conditioned reference, but cannot establish diagnosis accuracy.

## D. Offline acceptance report (no model, network or controller access)

Edit the private manifest (fields are initially null/false), after the shop
actually supplies the facts and permissions. Set `approved_channels` to the
**exact MTConnect data-item IDs permitted**, including any Execution channel.
Confirm normal cycles and impact with the technician; the software cannot
prove them independently. Then run:

```bash
uv run python -m capstone.ingestion.pilot_acceptance check \
  --manifest ../pilot-data/prestige-manifest.json \
  --probe ../pilot-data/probe.xml \
  --map ../pilot-data/channel-map.json \
  --capture ../pilot-data/telemetry.jsonl \
  --events ../pilot-data/operator-events.csv \
  --out ../pilot-data/acceptance.json
```

This local check reports `blocked`, `pending_capture`, or
`capture_verified`, with exact outstanding items. An acceptance report only
proves that the files match the stated criteria and human confirmations,
not that the source permissions are legally valid or a machine is safe.
Keep every artifact private. If no physical capture was approved, generate
a blocked/pending report with the controller/approval issue instead.

## E. After the visit: engineering decisions

1. Verify the saved probe and map against the actual captured fields, preserving
   missing data and instrument units. Never use the simulator's healthy
   reference file against the real machine.
2. Run [recorded-data replay](../capstone-code/capstone/providers/replay.py) and
   (after review) the read-only, consent-gated
   [investigator entry point](../capstone-code/capstone/recorded_investigation.py).
   This is preliminary triage, not an approved maintenance action.
3. Build **SM-6** operating-state segmentation and **SM-7** technician-confirmed
   healthy baseline using only supported, comparable machine states and jobs.
4. Complete the **real-world portion of the CPU statistical anomaly detector**
   only after sufficient normal data and event context exists. Evaluate
   false alerts, missed labels, missing-data abstention, duplicate incidents,
   and model/tool time before automated alert routing.
5. Request retrospective technician-confirmed fault cases if available, under
   the shop's permission. Without labels, report collection/detection features,
   not a validated diagnosis rate.

**Out of scope for the first visit:** physical interventions, diagnostic moves,
independent cameras/microphones, speculative support for unknown controllers,
cloud collectors/ports, automated diagnosis claims and publication of shop data.

Related requirements: [single-machine track](MVP_SCOPE.md#fw-sm-track),
[shop visit evidence](MVP_SCOPE.md#fw-sm-visit-log),
[real telemetry plan](MVP_SCOPE.md#fw-haas-live-pilot), and
[real-world detector gate](MVP_SCOPE.md#fw-cpu-anomaly-detector).
