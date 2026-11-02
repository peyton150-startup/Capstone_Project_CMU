# CNC Production-Line Maintenance & Diagnostic Manual

**Document ID:** SIM-CNC-001
**Revision:** 1.3 — October 31, 2026 (1.0 drafted by the developer; 1.1 removes the
station speed and cycle-time table from §1.1 and rewrites §2.7 to find a wrong
setting from its effects, the developer's choice "B"; 1.2 adds to §2.9 that a
bad lot raises the reject rate without failing every part; 1.3 adds §2.14 on the
feed-axis servo drive and §2.15 on hydraulic clamping, and brings §1.2 and
§2.13 up to date with their channels and repairs)
**Equipment:** Simulated CNC-01 through CNC-08 positions, when installed
**Purpose:** Fault finding, normal operation, maintenance decisions
**Status:** Training reference; not an OEM or safety-approved manual

This manual describes machine types and plausible failure mechanisms. It contains
no incident report, injected-fault selection, hidden state, scenario key, or
case-specific diagnosis. Physical service requires the actual equipment
manufacturer's procedures and site lockout/tagout practices.

Only the numbered sections (§1.1 to §2.15) are indexed for the agent's
`search_manual` tool. This cover, the directory and the provenance notes are not.

## How to Use This Manual

Look up a symptom, compare at least two plausible causes, collect current
observations, and record what rules explanations in or out. This reference
explains mechanisms. It does not establish which mechanism is present in a
particular run.

**Evidence order:** Treat current telemetry, machine settings, event and job
histories, inspections, and direct technician findings as observations. Treat
manual entries as general reference and past incident memories as historical
examples. Neither replaces current evidence.

**Terminology.** Tick: one minute under the default factory configuration.
Alarm: a threshold crossing, not a root-cause label. Inspection: a job-level
pass/fail outcome. Maintenance record: what was done or observed at a time, not
proof of current machine condition.

## §1.1 Equipment and Station Operating Reference

**When to consult:** Variable cycle times, station-to-station delays, differing
spindle speeds, occasional idle periods.

**Possible causes:** A normal process can differ by station; a bottleneck is not
automatically a mechanical fault.

**Recommended checks:** Identify the station and its running, idle or down state.
Each station has its own nominal spindle speed and typical processing time per
job, recorded on that station's setup sheet, which is kept with the machine and
not reproduced in this manual. Speeds differ from station to station, so a speed
means nothing without that station's own normal: judge a station against its own
earlier behaviour, not against another station. Review several jobs before
judging cycle time; single jobs naturally vary. Follow a job ID through the line
to distinguish machine processing from downstream blocking.

**How to interpret:** The line contains 3 to 8 stations. The second station has
the longest nominal processing time on the default line, so some waiting before
it is normal. Confirm the installed line size and current state before acting.

## §1.2 Measurements, Trends, Alarms and Evidence Quality

**When to consult:** A sensor exceeds an alarm value; averages disagree across
windows; a trend looks erratic or has gaps.

**Possible causes:** Operating changes, transient disturbances, instrument issues
or developing equipment problems.

**Recommended checks:** Compare vibration (mm/s), machine temperature (°F), motor
load (%), and factory air temperature (°F) over the same relevant time window.
Record ticks, sample counts, minimum and maximum, and a trend, not only the last
reading. Separate running from idle periods. Link alarms to the underlying sensor
readings and independent evidence.

**How to interpret:** The default line vibration alarm is triggered by a reading
above 4.5 mm/s. It is a monitoring setpoint, not a confirmed failure threshold.
Missing samples are unknown, never zero. A sensor reading and a maintenance note
are evidence; neither is a diagnosis.

Observable channels and records: vibration (mm/s per station; speed, load and
instruments affect readings); temperature (°F per station; thermal lag, compare
factory air); load (% per station; active machining against idle matters); air
temperature (°F, factory-wide; door and daily variation); power (kW per station;
cutting load and speed, plus friction or a straining drive); following error (µm
per station, the feed axis's lag behind its commanded path; §2.14); hydraulic
pressure (bar, only on stations fitted with hydraulics; §2.15); events and job history
(alarms, job movement, stops; events record observations, not causes);
inspections (job, batch, pass or fail; outcomes are statistical); settings and
maintenance (the current speed only, and service notes; service history is not
present health).

## §2.1 Abnormal Vibration: Spike, Step Change or Gradual Rise

**When to consult:** One high vibration alarm; recurring peaks; a sustained
increase in mm/s during production.

**Possible causes:** Heavier workpiece load, speed change, spindle-bearing
deterioration, imbalance, loose mounting, alignment, cutting chatter, or sensor
disturbance.

**Recommended checks:** Check whether the machine was running. Compare several
consecutive readings and trend windows at similar loads and spindle speeds; look
for changes in temperature or load. Check nearby stations for shared effects.
Review operating events, setting changes, and prior maintenance. Request a
physical inspection when telemetry does not separate mechanical vibration from
sensor movement.

**How to interpret:** A single spike without corroboration does not justify a
repair. A persistent change across independent signals merits deeper
investigation. Do not diagnose a bearing by vibration alone. See §2.2, §2.4 and
§2.11.

## §2.2 Spindle Bearing: Wear Assessment and Replacement

**When to consult:** Increasing vibration, elevated operating temperature, longer
machining time, worsening finish, unusual noise or a machine stop.

**Possible causes:** Bearing wear or damage, excessive load or speed, improper
lubrication, incorrect installation, and similar-looking faults elsewhere.

**Recommended checks:** Compare vibration and temperature during like-for-like
operating periods; check current speed, motor load and cycle-time trends. Review
the maintenance record, but do not assume a recently serviced bearing is healthy.
A technician may verify play, noise, lubrication state and physical bearing
condition under a safe lockout procedure.

**How to interpret:** If the evidence supports bearing damage and intervention is
warranted, request approved replacement. A running machine may require less
downtime than an already failed one: planned replacement takes roughly 45 ticks
and repair after a breakdown roughly 135 ticks. Verify after the work that
behaviour improves under comparable production conditions. A bearing inspection
after removal is stronger evidence than an alarm.

## §2.3 Lubrication Condition and Contamination

**When to consult:** Spindle heating, rubbing sounds, increasing resistance,
premature bearing wear, intermittent chatter.

**Possible causes:** Low supply, incorrect lubricant, degraded grease or oil,
contaminated lubrication, blocked distribution or excessive fill.

**Recommended checks:** Consult service history and the lubrication schedule.
When a technician can access the machine, check lubricant identity, condition,
levels, delivery points and contamination under the plant safety procedure.
Compare symptoms against load, speed and thermal behaviour before assigning
cause. Record what was actually observed rather than assuming the lubrication
circuit is defective.

**How to interpret:** The provided sensor list does not establish oil pressure,
grease flow or chemistry. Lack of an oil-pressure alarm is not evidence that
lubrication is sound. Do not authorize adding lubricant, opening guards or
running a dry machine solely from a model inference.

## §2.4 Alignment, Mounting Looseness and Rotor Imbalance

**When to consult:** Repeated vibration, finish variation, speed-dependent noise
or a change after tooling or spindle service.

**Possible causes:** Shaft or coupling misalignment, imbalanced workholding, loose
foundation or mounting hardware, excessive runout, damaged tooling.

**Recommended checks:** Compare vibration at comparable motor loads and speed
settings. Review whether behaviour began after maintenance, tool changes or
workholding adjustments. If a technician is available, check alignment, runout,
fastener condition and rotating balance with suitable instruments while
following lockout procedures.

**How to interpret:** A scalar vibration trend cannot identify frequency bands,
harmonics, direction or runout. Treat this as a candidate cause until an
appropriate physical measurement distinguishes it from bearing wear, cutting
chatter or sensor error.

## §2.5 Machine Temperature: Thermal Lag and Rising Heat

**When to consult:** Machine temperature increases over many readings;
temperature is high shortly after a workload shift; temperature drops after
shutdown.

**Possible causes:** Normal motor and spindle heating, ambient air changes,
increased load or speed, bearing friction, inadequate coolant flow or sensor
error.

**Recommended checks:** Compare machine temperature with factory air temperature,
motor load, machine status and spindle speed over a sufficiently long interval.
A stopped machine cools toward ambient; a running machine typically runs warmer.
Check whether the temperature change follows a load change or begins during
idle. Assess trend direction rather than reacting to one measurement.

**How to interpret:** Thermal response is delayed. A persistent temperature rise
with independent vibration or quality changes has different implications from a
matched rise in factory air. Do not interpret every warm machine as a failed
bearing.

## §2.6 Coolant Supply, Circulation and Machining Heat

**When to consult:** Poor surface finish, workpiece heat damage, chip
accumulation, abnormal machining temperature or recurring heat-related defects.

**Possible causes:** Insufficient or misdirected coolant, depleted tank, pump or
filter trouble, incorrect mixture, obstructed nozzle, leakage or normal load
changes.

**Recommended checks:** Request a maintenance check of tank level, fluid
condition, flow at the cutting zone, nozzle aim, filtration and leakage.
Correlate with machine temperature, tool condition, motor load and inspection
outcomes. Compare products made with the same material and similar cutting
conditions.

**How to interpret:** A general machine temperature sensor cannot establish
coolant flow. No dedicated coolant-flow or coolant-pressure observation should
be assumed. Record suspected causes as unconfirmed until physical checks support
them.

## §2.7 Spindle Speed Configuration and Machining Effects

**When to consult:** Cycle times or quality change on one station; more or less
vibration or heat after a setup; unexpectedly fast or slow work at one station.

**Possible causes:** Incorrect program or setup speed, operator setting mistake,
incorrect tooling recommendation, speed variation under load or mechanical drag.

**Recommended checks:** The settings record shows a station's current speed only;
its nominal speed is on the station's setup sheet, not in the shared records. So
find a wrong setting from its effects. First, look for a change point: on one
station, job times, temperature and inspection rejects shift at about the same
moment and then stay at their new level, unlike wear, which keeps getting worse.
Second, read the direction: a speed set too high shortens jobs and adds a little
vibration and heat; a speed set too low lengthens jobs and takes a little
vibration and heat away; either way, more jobs fail inspection. A worn bearing,
by contrast, lengthens jobs while vibration rises. Third, compare with the other
stations: a material problem spreads across stations that handle the same batch,
a setting stays on one station. Verify that a slow cycle is not simply a
downstream blockage (§2.8).

**How to interpret:** A change point with these effects on one station is a
configuration clue, not proof that it caused every anomaly. The corrective action
is an approved setting reset, which stops the station for about 10 ticks and
returns it to its nominal speed. Because it is short and reversible, it is also a
test: if job times, temperature and rejects return to their earlier levels
afterwards, the setting was the cause; if not, look again.

## §2.8 Motor Load, Cycle Time, Throughput and Blocking

**When to consult:** Elevated motor load, slower output, idle stations, queues,
repeated blocked jobs or sudden stoppage.

**Possible causes:** Normal job-to-job load variation, high cutting demand, speed
selection, friction, tool wear, an upstream or downstream hold, or equipment
breakdown.

**Recommended checks:** Compare load during active work, not across long idle
periods. Follow a specific job across station event records. Compare realized
processing time with that station's usual cycle time, then identify whether
completed work is waiting for the next station. Review running, idle and down
states before blaming the machine with the visible queue.

**How to interpret:** On this sequential line, a finished job can remain at one
station until the next accepts it. A downstream bottleneck can create upstream
delay without any upstream hardware fault. The second station has a relatively
long nominal cycle and can be a normal bottleneck.

## §2.9 Material Batch Quality and Lot Traceability

**When to consult:** Inspection rejects cluster by batch or appear on jobs
processed across several otherwise stable machines.

**Possible causes:** Incoming stock variation, material hardness or
contamination, a supplier or heat-treatment issue, cutting conditions, tooling,
machine settings, or inspection randomness.

**Recommended checks:** Group pass/fail results by batch ID; compare multiple jobs
and adjacent batches. Trace representative rejected jobs through the line and
check whether the same station or setting coincides with rejects. When possible,
request material certificates, dimensional checks and receiving inspection
rather than treating the lot number as an answer.

**How to interpret:** Batch IDs connect material and finished jobs; a defect rate
is statistical, so one failed inspection is weak evidence. A bad lot raises the
share of rejects; it does not make every part fail, so jobs from that lot that
pass inspection do not clear it, and an alternating or other pattern among a few
jobs is usually chance. Judge a batch by its reject rate against other batches
run through the same stations: a clearly higher rate in one batch points at the
material even when some of its jobs pass. Material can be suspect even if
equipment sensor trends remain normal, but also consider machine or inspection
causes.

## §2.10 Tool Wear, Workholding and Cutting-Process Problems

**When to consult:** Declining surface finish, unstable cut, increased scrap,
rising motor load or recurring vibration during particular jobs.

**Possible causes:** Dull or damaged cutting tool, incorrect tool geometry, loose
fixture, excessive feed, poor chip evacuation, material changes or spindle
problems.

**Recommended checks:** Compare results for different jobs, shifts and material
batches; check operating speed, load and inspections. Request physical
tool-edge, holder, fixture and chip-clearance inspections. Distinguish a
cutting-only symptom from a mechanical problem that persists when the machine is
not cutting.

**How to interpret:** The available scalar sensors do not directly measure tool
flank wear, cutting forces, surface roughness or fixture clamp force. Treat such
diagnoses as possibilities until direct inspection or added instrumentation
confirms them.

## §2.11 Sensor Drift, Dropout, Loose Probes and False Alarms

**When to consult:** Sudden single-sensor alarm, offset reading, gradually
inconsistent sensor, intermittent missing samples, or a spike not shared by
other measurements.

**Possible causes:** Loose sensor mount, calibration drift, intermittent cable,
communications loss, environmental interference, actual process upset or
ordinary noise.

**Recommended checks:** Count samples and inspect adjacent ticks: a missing point
is not a zero reading. Compare the affected channel against its previous
readings, parallel machine channels, factory air readings and event history. Ask
whether independent measures (temperature, motor load, quality and status)
corroborate the change. A technician may check sensor mounting, wiring and
calibration.

**How to interpret:** Do not equate an alarm with physical damage. A short
disturbance that disappears and leaves other evidence stable may warrant
observation rather than intervention. Repeated disagreement merits instrument
investigation, not an automatic bearing replacement.

## §2.12 Ambient Air, Loading-Door and Shared Thermal Changes

**When to consult:** Several machines warm or cool together, or machine
temperature changes around loading-door activity or daily operating periods.

**Possible causes:** Factory air-temperature cycle, external weather or door
exchange, ventilation changes, workload variation or independent machine faults.

**Recommended checks:** Read the factory air thermometer and compare it with
multiple machine temperatures in the same window. Check facility event records
for door open and closed activity and compare machine status and load. Remember
machine temperatures typically respond more slowly than surrounding air.

**How to interpret:** A shared factory-level air change is a competing
explanation for a machine temperature change. Do not diagnose a common bearing
fault from several similar temperature changes without independent mechanical
evidence.

## §2.13 Inspection Rejects, Maintenance Decisions and Verification

**When to consult:** Pass/fail outcomes worsen; alarms persist; a proposed fix is
uncertain; a recent maintenance action appears not to help.

**Possible causes:** Material or process changes, equipment wear, speed error,
tool or fixture faults, inspection variation, or coincidental multiple causes.

**Recommended checks:** Build a time-aligned record: affected machine and job
IDs, batches, speeds, sensor trends, alarms, prior service and inspection
results. State competing explanations and what evidence would separate them.
Select an available action only when the expected improvement and potential
downtime are justified; obtain human approval before execution. After
maintenance, compare the same operating signals and inspection outcomes over a
meaningful subsequent window.

**How to interpret:** On this line, the only state-changing interventions are
four approved repairs: a spindle-bearing replacement (§2.2), a speed-setting
reset (§2.7), a feed-axis servo drive replacement (§2.14) and a hydraulic seal
repair on a station fitted with hydraulics (§2.15). Each fixes one mechanism
only; none repairs material, tooling or an instrument. Other physical checks may
require a technician and are not available as actions. "Insufficient evidence"
or "continue observing" are legitimate conclusions when the evidence does not
separate the causes, but a fault that keeps worsening does not clear by being
watched: wear and leaks progress until repaired. Completion of work is not proof
the root cause was correct.

## §2.14 Feed-Axis Servo Drive: Following Error, Wear and Replacement

**When to consult:** A following-error alarm; following error rising over many
readings on one station; parts from one station failing inspection for size while
its vibration and temperature stay normal.

**Possible causes:** A wearing feed-axis servo drive (amplifier, motor or its
feedback), a heavy cut, a faster speed setting, a binding axis, or an instrument
fault on the axis channel.

**Recommended checks:** Following error is how far the feed axis lags behind the
position the controller commands, measured by the servo controller itself on
every move. A healthy drive keeps it small, a few micrometres at normal load; a
heavier cut or a faster speed adds a little; while a station is idle or stopped
the drive only holds the axis still and the lag falls to about one micrometre, so
compare running periods only. The alarm fires above 20 µm. A wearing drive adds
lag that grows slowly at first and then faster, and only while the station runs:
a harder job wears it faster. Read the trend on the affected station over a long
running window, and compare it with the same channel on other stations. Check
power on the same station: a straining drive draws a little more. Check vibration,
temperature and job times: a worn drive leaves them unchanged, while a worn
spindle bearing raises vibration and heat and lengthens jobs (§2.2), and a wrong
speed changes job times at one moment and then holds them steady (§2.7). Group
inspection results by the station each failed job passed through: a drive fault
follows the station across material batches, while a bad lot follows the batch
across stations (§2.9).

**How to interpret:** A lagging axis cuts parts off size, so more jobs from that
station fail inspection, and the share grows as the drive wears; as with any
defect rate, some of its jobs still pass (§2.9). A following error that keeps
rising during production does not recover by itself and is not a transient: it
keeps worsening until the drive is replaced, and an alarm that briefly clears is
not evidence the drive is sound. The corrective action is an approved servo drive
replacement, which takes the station out of service for about an hour; the
maintenance record of the work states the condition of the drive removed, which
is direct evidence of whether it was worn. Afterwards, following error during
running work should return to a few micrometres and that station's rejects should
fall back; if they do not, look again (an instrument, a binding axis or a second
fault).

## §2.15 Hydraulic Clamping: Pressure Loss, Seal Leaks and Repair

**When to consult:** A low hydraulic-pressure alarm; hydraulic pressure falling
over many readings on one station; workpieces shifting or parts failing
inspection on a station fitted with hydraulics.

**Possible causes:** Leaking hydraulic seals, a weakening pump, a sticking relief
valve, an instrument fault on the pressure transducer, or normal draw during a
heavy cut.

**Recommended checks:** Only some stations have hydraulics; the machine list
shows which. The pump holds a steady pressure whenever the station is powered,
running or idle, and cutting draws only a few bar from it, so a sound system reads
nearly flat. When a station is down, its hydraulic unit and transducer are
switched off and send no readings: missing samples then are not a pressure loss.
A seal leak lowers the pressure slowly at first and then faster, and unlike wear
on the spindle or the feed axis it keeps growing while the station sits idle,
because the pump keeps running. The low-pressure alarm fires when a reading falls
below its setpoint, which the alarm event states. Read the pressure trend over a
long window that includes idle periods, and compare idle readings with idle
readings: a fall that persists while the station is not cutting is a leak, not a
heavy cut. A pressure loss does not change vibration, temperature, following
error or job times, which separates it from a bearing (§2.2), a drive (§2.14) or
a speed setting (§2.7). Group inspection results by station and by batch as in
§2.14. An erratic reading with gaps and no matching quality change points at the
transducer instead (§2.11).

**How to interpret:** Low clamping pressure lets the workpiece shift in the cut,
so more jobs from that station fail inspection, and the share grows as the leak
does; some of its jobs still pass (§2.9). A falling pressure does not recover by
itself, and readings that briefly return above the setpoint during idle or light
work do not clear it: the leak keeps growing until the seals are replaced. The
corrective action is an approved hydraulic repair, possible only on a station
fitted with hydraulics, which takes it out of service for about 40 ticks to
replace the seals; the maintenance record of the work states the condition of the
seals removed. Afterwards the pressure should return to its steady level and that
station's rejects should fall back; if they do not, look again.

## Document Provenance and Use Limits

A synthetic, scenario-independent training manual, drafted by the developer on
2026-10-22 from the line's ordinary capabilities and general manufacturing
diagnostic reasoning, and checked against the code at commit `4c62fa6`: the
alarm setpoint (4.5 mm/s) and the action durations (45, 135 and 10 ticks) match
`simulator/line.py` and `simulator/simulator.py`. Revision 1.3 (§2.14, §2.15) was
written on 2026-10-31 by the coding assistant at the developer's request, from
`simulator/sensors.py`, `simulator/scenarios.py` and `simulator/line.py`: the
following-error alarm (20 µm), the idle holding lag (about 1 µm), the drive
replacement (about an hour) and the seal repair (40 ticks). The pressure setpoint
and the normal pressure are left to the alarm event and the readings, because
their values equal stations' job times, which this manual does not give (§1.1). It was not generated from a
particular experiment, seed, incident result or hidden ground-truth record. No
OEM-approved torque values, lubrication grades, vibration acceptance classes,
runout tolerances, coolant concentrations, calibration intervals or lockout
steps are claimed.
