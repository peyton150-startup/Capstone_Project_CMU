"""Deterministic plan questions for a rapid triage (Block 1, TRIAGE_PLAN=fixed).

The plan question was the costliest model call in the triage runs: 37 s on
average over the 52 PR 251 runs of 2026-11-13, with its primary model cut off
by the question's time limit most of the time. With TRIAGE_PLAN=fixed a triage
asks no model to plan. Its first questions come from this table, picked by code
from what monitoring saw.

The table is keyed on the observed anomaly (an alarm's sensor, a stopped
machine, failed inspections), never on a fault: the agent cannot see the
cause, so neither can its plan. The questions name no cause; they ask for the
evidence that tells common causes apart, and they keep three possibilities
open: a passing spike (no fault), this machine alone, or more than one machine
(several faults). An anomaly the table does not recognise gets a generic list,
not a model call: the plan only says where to look first, and the hypothesize
and conclude stages, which do the reasoning, are still model calls.

Where a question can be settled by a measurement, it carries a `Predicate`
(Block 3): an alarm's first question asks whether the alarmed sensor stayed
past its limit around the alarm, and closes only on a measured "true"
(sustained) or "false" (a spike), never just because a tool answered.

Every list also asks what the line screening shows. With the evidence packet
on, Observe has read the screening before the plan exists, so the plan stage
answers that question with the screening already held (`screening_answer`),
but only when the screening scored every machine on the roster. A machine
that is missing or unscored leaves the question open: unknown, never normal.
"""

import re

from capstone.agent.artifacts import DetectedAnomaly
from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.state import Predicate, Question
from capstone.agent.triage_requirements import ReadRequirement
from capstone.contracts import Contract

# "alarm on CNC-02: vibration 4.58 mm/s above 4.50", from
# `simulator.events.ThresholdAlarm` and `agent.monitor.detect_anomaly`.
ALARM = re.compile(
    r"^alarm on \S+: (?P<sensor>\w+) \S+ \S+ (?P<side>above|below) (?P<limit>\S+)$"
)

# The words every fixed list's screening question carries, and only that one.
SCREENING_WORDS = "line screening"
SCREENING_TOOL = "get_line_screening"

# The ticks either side of the alarm the first question's predicate looks at,
# and the readings it needs before it gives a verdict.
SUSTAIN_TICKS = 20
SUSTAIN_SAMPLES = 10
# How close to the limit the mean around the alarm must stay to count as
# sustained. A mean exactly past the limit was false for every known case,
# real wear included: a reading that has just crossed its limit averages just
# short of it. A spike averages far short (offline probe, 2026-11-20: bearing
# 4.33 and 4.22 against 4.5; false alarms 2.9 and 2.2). A chosen default.
SUSTAIN_MARGIN = 0.10

# How far back the inspection reads that compare failed jobs look: "3 of the
# last 10 jobs" reaches about ten jobs back; 900 ticks is about 13 jobs. The
# job-time reads look back to tick 0 instead, because a setting changed early
# leaves no step to find inside a shorter window (KA-05, KA-06 offline).
RECORD_LOOKBACK_TICKS = 900

# The job whose station times are the pace to compare failed jobs against.
BASELINE_JOB = 1

# "3 of the last 10 jobs failed inspection (jobs 11, 13, 15)", from
# `agent.monitor.detect_anomaly`: the failed jobs the anomaly names.
FAILED_JOBS = re.compile(r"\(jobs (?P<jobs>\d+(?:, \d+)*)\)")

# A sensor's own follow-up: the readings or records most likely to move with it.
SENSOR_FOLLOW_UP = {
    "vibration": "Do {machine}'s temperature and motor load move with its vibration?",
    "following_error": (
        "Have parts made on {machine} started failing inspection since its "
        "following error rose?"
    ),
    "hydraulic_pressure": (
        "Have parts made on {machine} started failing inspection since its "
        "hydraulic pressure fell?"
    ),
}


def fixed_plan(anomaly: DetectedAnomaly) -> tuple[Question, ...]:
    """The first questions for a triage of `anomaly`, without asking a model.

    Up to five questions, ids Q1 to Q5, as the model's plan gives. An alarm
    gets questions on its own sensor; a stopped machine and failed inspections
    get their own lists; anything else gets a generic list.
    """
    # Variables:
    #   anomaly: What monitoring noticed; its kind, machine and description
    #     pick the list, and its machine and sensor fill in the wording.
    #   machine: The machine the anomaly names, or "the alarmed machine" when
    #     it names none.
    #   alarm: The sensor, side and limit read from an alarm's description;
    #     None when the description is not in the alarm format.
    #   texts: The questions' wording, in order, before ids are given.
    #   direct: How many leading questions read the signal itself, so they
    #     are marked as direct evidence for the decide question's ranking.
    machine = anomaly.machine_id or "the alarmed machine"
    alarm = ALARM.match(anomaly.description) if anomaly.kind == "alarm" else None
    if alarm is not None:
        sensor = alarm["sensor"]
        label = sensor.replace("_", " ")
        texts = [
            f"Is {machine}'s {label} still {alarm['side']} {alarm['limit']}, and "
            "did it change steadily over the recent readings or in a single spike?",
            f"Does the line screening show any other machine with unusual {label} "
            f"or other readings, or is {machine} the only one?",
            f"What events, alarms or service records does {machine} show shortly "
            "before the alarm?",
            f"Did {machine}'s job times shift at one point before the alarm, as a "
            "changed setting would make them?",
            SENSOR_FOLLOW_UP.get(
                sensor, "Do {machine}'s other sensors move with its " + label + "?"
            ).format(machine=machine),
        ]
        direct = 2
    elif anomaly.kind == "status":
        texts = [
            f"What events and alarms did {machine} record shortly before it stopped?",
            f"How did {machine}'s sensor readings change before it stopped?",
            "Does the line screening show any other machine with unusual readings?",
            f"Was {machine} serviced recently, or did its job times shift at one "
            "point, as a changed setting would make them?",
        ]
        direct = 2
    elif anomaly.kind == "inspection_failures":
        texts = [
            "Which machines did the failed jobs pass through, and do the failures "
            "share one machine?",
            "Do the failed jobs share a material batch?",
            "Did one machine work the failed jobs at a different pace than the "
            "first job, as a changed setting would make it?",
            "Does the line screening show any machine with unusual readings?",
            "Did any events or alarms come shortly before the failures?",
        ]
        direct = 2
    else:
        texts = [
            "Does the line screening show any machine with unusual readings?",
            "What events and alarms were recorded recently?",
            "Have recent inspections started failing?",
        ]
        direct = 1
    return tuple(
        Question(
            id=f"Q{number}",
            text=text,
            signal_reliability="direct" if number <= direct else "indirect",
        )
        for number, text in enumerate(texts, start=1)
    )


def fixed_predicates(anomaly: DetectedAnomaly) -> dict[str, Predicate]:
    """Measured conditions that settle the fixed plan's questions, by question id.

    Only an alarm on a named machine with a readable limit gets one: Q1, whether
    the sensor's mean around the alarm stayed within `SUSTAIN_MARGIN` of the
    limit (or past it). True means the reading is sustained; false means it
    was a spike. Too few readings give "insufficient", which keeps Q1 open.
    """
    # Variables:
    #   alarm: The sensor, side and limit read from the alarm's description.
    #   limit: The alarm's own threshold.
    #   threshold: The limit moved back by the margin, toward normal: below it
    #     for an "above" alarm, above it for a "below" alarm.
    alarm = ALARM.match(anomaly.description) if anomaly.kind == "alarm" else None
    if alarm is None or anomaly.machine_id is None:
        return {}
    try:
        limit = float(alarm["limit"])
    except ValueError:
        return {}
    threshold = (
        limit * (1 - SUSTAIN_MARGIN)
        if alarm["side"] == "above"
        else limit * (1 + SUSTAIN_MARGIN)
    )
    return {
        "Q1": Predicate(
            machine_id=anomaly.machine_id,
            sensor=alarm["sensor"],
            from_tick=max(0, anomaly.tick - SUSTAIN_TICKS),
            to_tick=anomaly.tick + SUSTAIN_TICKS,
            statistic="mean",
            comparison=alarm["side"],
            threshold=round(threshold, 6),
            min_samples=SUSTAIN_SAMPLES,
        )
    }


def named_failed_jobs(anomaly: DetectedAnomaly) -> tuple[int, ...]:
    """The failed jobs a failed-inspections anomaly names, in its own order."""
    # Variables:
    #   found: The "(jobs 11, 13, 15)" part of the description, if present.
    if anomaly.kind != "inspection_failures":
        return ()
    found = FAILED_JOBS.search(anomaly.description)
    if found is None:
        return ()
    return tuple(int(job) for job in found["jobs"].split(", "))


# A sensor's follow-up question, as one read: the sensor summary or the
# inspections that answer it (TRIAGE_INVESTIGATE=on, `planned_reads`).
SENSOR_FOLLOW_UP_READ = {
    "vibration": ("get_sensor_summary", "temperature"),
    "following_error": ("get_inspections", None),
    "hydraulic_pressure": ("get_inspections", None),
}


class PlannedRead(Contract):
    """The one read that answers a fixed-plan question, named by the table.

    `tool` is the read; `machine_id` the machine it is about (None: the whole
    line); `sensor` the sensor, for a sensor summary only. Windowed reads run
    from before the anomaly to the latest observed tick; the compiler fills
    the ticks in, because only it knows the latest one.
    """

    tool: str
    machine_id: str | None = None
    sensor: str | None = None
    windowed: bool = True


def planned_reads(anomaly: DetectedAnomaly) -> dict[str, PlannedRead]:
    """The read that answers each fixed-plan question a sensor predicate does not.

    Keyed by question id, for the same lists `fixed_plan` writes. A question
    whose answer is no single read (how a stopped machine's sensors changed,
    which machines failed jobs passed through) or that the screening already
    answers is left out, so the model still chooses for it. Like the plan,
    every read is picked from what monitoring saw, never from a cause.
    """
    # Variables:
    #   machine: The machine the anomaly names; None leaves machine-specific
    #     reads out, since the compiler may not guess one.
    #   alarm: The alarm's sensor, side and limit, as in `fixed_plan`.
    #   follow: An alarm sensor's follow-up read (tool and sensor), if the
    #     table has one; other sensors' follow-up stays the model's call.
    machine = anomaly.machine_id
    alarm = ALARM.match(anomaly.description) if anomaly.kind == "alarm" else None
    reads: dict[str, PlannedRead] = {}
    if alarm is not None:
        if machine is None:
            return {}
        reads["Q3"] = PlannedRead(tool="get_events", machine_id=machine)
        reads["Q4"] = PlannedRead(tool="get_settings", windowed=False)
        follow = SENSOR_FOLLOW_UP_READ.get(alarm["sensor"])
        if follow is not None:
            tool, sensor = follow
            reads["Q5"] = PlannedRead(
                tool=tool,
                machine_id=machine if sensor else None,
                sensor=sensor,
            )
    elif anomaly.kind == "status":
        if machine is not None:
            reads["Q1"] = PlannedRead(tool="get_events", machine_id=machine)
            reads["Q4"] = PlannedRead(
                tool="get_maintenance_history", machine_id=machine, windowed=False
            )
    elif anomaly.kind == "inspection_failures":
        reads["Q2"] = PlannedRead(tool="get_inspections")
        reads["Q3"] = PlannedRead(tool="get_settings", windowed=False)
        reads["Q5"] = PlannedRead(tool="get_events")
    else:
        reads["Q2"] = PlannedRead(tool="get_events")
        reads["Q3"] = PlannedRead(tool="get_inspections")
    return reads


def fixed_requirements(
    anomaly: DetectedAnomaly, cutoff_tick: int
) -> dict[str, ReadRequirement]:
    """The measurable parts of the fixed questions at one authorized cutoff.

    The existing single-read mapping remains for the hybrid compiler. The
    deterministic controller uses this fuller table, including complementary
    reads and requirements that a current snapshot cannot settle.
    """
    # Variables:
    #   cutoff_tick: The authorized source horizon, held constant across reads.
    #   window: One common interval for comparing sensor movement.
    #   lookback: The longer interval for inspection reads that compare the
    #     failed jobs an anomaly names.
    #   history: Everything observed so far, for job-time reads, so a station's
    #     jobs on both sides of an early change point are in the read.
    #   add: Adds a requirement whose stable id names its question and part.
    #   alarm: The observed alarm shape, never a hidden simulator cause.
    #   failed: The failed jobs the anomaly names; every one must be seen.
    window = (max(0, anomaly.tick - 60), cutoff_tick)
    lookback = (max(0, cutoff_tick - RECORD_LOOKBACK_TICKS), cutoff_tick)
    history = (0, cutoff_tick)
    failed = named_failed_jobs(anomaly)
    requirements: dict[str, ReadRequirement] = {}

    def add(
        question_id: str,
        part: str,
        tool: str,
        *,
        machine_id: str | None = None,
        sensor: str | None = None,
        windowed: bool = False,
        long: bool = False,
        since_start: bool = False,
        min_samples: int = 0,
        min_span_ticks: int = 0,
        qualification: str = "record",
        failed_job_ids: tuple[int, ...] = (),
        job_id: int | None = None,
    ) -> None:
        """Add one independently qualified source for a question."""
        # Variables:
        #   part: Stable label for the source within the question.
        #   windowed: Whether this tool accepts and needs the shared interval.
        #   long: Use the inspection lookback instead of the shared interval.
        #   since_start: Use everything observed so far (job-time reads).
        span = (
            history
            if since_start
            else lookback
            if long
            else window
            if windowed
            else (None, None)
        )
        requirement = ReadRequirement(
            requirement_id=f"{question_id}:{part}",
            question_id=question_id,
            tool=tool,
            machine_id=machine_id,
            sensor=sensor,
            from_tick=span[0],
            to_tick=span[1],
            min_samples=min_samples,
            min_span_ticks=min_span_ticks,
            qualification=qualification,
            failed_job_ids=failed_job_ids,
            job_id=job_id,
        )
        requirements[requirement.requirement_id] = requirement

    alarm = ALARM.match(anomaly.description) if anomaly.kind == "alarm" else None
    machine = anomaly.machine_id
    if alarm is not None and machine is not None:
        predicate = fixed_predicates(anomaly).get("Q1")
        if predicate is not None:
            requirements["Q1:trigger"] = ReadRequirement(
                requirement_id="Q1:trigger",
                question_id="Q1",
                tool="get_sensor_summary",
                machine_id=machine,
                sensor=predicate.sensor,
                from_tick=predicate.from_tick,
                to_tick=min(predicate.to_tick, cutoff_tick),
                min_samples=predicate.min_samples,
                # Count alone cannot establish sustained temporal coverage.
                min_span_ticks=min(
                    SUSTAIN_TICKS, max(0, cutoff_tick - predicate.from_tick)
                ),
                qualification="measurement",
            )
        add("Q3", "events", "get_events", machine_id=machine, windowed=True)
        add("Q3", "service", "get_maintenance_history", machine_id=machine)
        add(
            "Q4",
            "cycle_time",
            "get_events",
            machine_id=machine,
            since_start=True,
            qualification="cycle_time_shift",
        )
        if alarm["sensor"] == "vibration":
            for sensor in ("vibration", "temperature", "load"):
                add(
                    "Q5",
                    sensor,
                    "get_sensor_summary",
                    machine_id=machine,
                    sensor=sensor,
                    windowed=True,
                    min_samples=2,
                    min_span_ticks=1,
                    qualification="movement",
                )
        elif alarm["sensor"] in ("following_error", "hydraulic_pressure"):
            # "Have parts started failing?" is answered by the dated results,
            # including none failing; it does not need two failed jobs.
            add(
                "Q5",
                "inspections",
                "get_inspections",
                long=True,
                qualification="inspection_recent",
            )
    elif anomaly.kind == "status" and machine is not None:
        add("Q1", "events", "get_events", machine_id=machine, windowed=True)
        for sensor in ("vibration", "temperature", "load"):
            add(
                "Q2",
                sensor,
                "get_sensor_summary",
                machine_id=machine,
                sensor=sensor,
                windowed=True,
                min_samples=2,
                min_span_ticks=1,
                qualification="movement",
            )
        add("Q4", "service", "get_maintenance_history", machine_id=machine)
        add(
            "Q4",
            "cycle_time",
            "get_events",
            machine_id=machine,
            since_start=True,
            qualification="cycle_time_shift",
        )
    elif anomaly.kind == "inspection_failures":
        add(
            "Q1",
            "failed_jobs",
            "get_inspections",
            long=True,
            qualification="inspection_jobs",
            failed_job_ids=failed,
        )
        add(
            "Q2",
            "inspections",
            "get_inspections",
            long=True,
            qualification="inspection_batch",
            failed_job_ids=failed,
        )
        # The line's whole event history is too many rows for one read, so the
        # pace of each station is compared on the failed jobs (read for Q1)
        # against the first job, before most changes could have been made.
        add(
            "Q3",
            "baseline_job",
            "get_job_history",
            job_id=BASELINE_JOB,
            qualification="job_time_baseline",
        )
        add("Q5", "events", "get_events", windowed=True)
    else:
        add("Q2", "events", "get_events", windowed=True)
        add(
            "Q3",
            "inspections",
            "get_inspections",
            windowed=True,
            qualification="inspection_recent",
        )
    return requirements


def is_screening_question(question: Question) -> bool:
    """Whether a question asks what the line screening shows."""
    # Variables:
    #   question.text: The question's wording; the fixed lists name the line
    #     screening in exactly one question each.
    return SCREENING_WORDS in question.text.lower()


def screening_answer(packet: EvidencePacket | None) -> tuple[str | None, str]:
    """The evidence that answers a screening question, or None, with the reason.

    The screening read in Observe answers "does the line screening show any
    machine with unusual readings?" only when it scored every machine on the
    verified roster: each one has at least one scored sensor and none left
    unscored. Otherwise the answer is None and the question stays open, so a
    missing or unscored machine is never read as normal.
    """
    # Variables:
    #   packet: The triage's Observe packet; None when it was not built.
    #   screening: The packet's ledger entry for the mandatory screening read;
    #     its evidence id is the answer when the read qualified.
    #   scored: Roster machines with at least one scored screening sensor.
    #   unscored: Roster machines with any screening item left missing, or with
    #     no scored sensor at all; any one keeps the question open.
    if packet is None:
        return None, "no_packet"
    screening = next(
        (c for c in packet.calls if c.tool == SCREENING_TOOL and c.qualified), None
    )
    if screening is None or screening.evidence_id is None:
        return None, "no_screening"
    if not packet.roster_verified or not packet.roster:
        return None, "roster_unverified"
    items = [i for i in packet.items if i.source_type == "derived_screening"]
    scored = {i.machine_id for i in items if i.status == "qualified"}
    missing = {i.machine_id for i in items if i.status == "missing"}
    unscored = [
        m
        for m in packet.roster
        if m not in scored or m in missing or m in packet.absent_from_screening
    ]
    if unscored:
        return None, "unscored: " + ", ".join(unscored)
    return screening.evidence_id, "every roster machine scored"
