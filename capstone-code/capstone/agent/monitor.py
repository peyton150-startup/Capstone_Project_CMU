"""The factory's ordinary monitoring: runs the line until something looks wrong.

Uses the agent-facing tools only, so it sees what the agent would see,
and names the symptom, never the cause. What it noticed becomes the
investigation's `DetectedAnomaly`; code outside `capstone.agent` passes
that record on without importing it.
"""

from capstone.agent.artifacts import DetectedAnomaly
from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools

FAILS_IN_WINDOW, WINDOW = 3, 10  # three failed inspections among the last ten jobs

ROUTINE_CHECK = (
    "no alarm, but the shift supervisor asks for a routine check of the line"
)


def detect_anomaly(
    look: ObservationTools, act: ActionTools, *, max_ticks: int = 4000, step: int = 10
) -> DetectedAnomaly:
    """Advance the factory `step` ticks at a time until an alarm, a stopped
    machine, or a run of rejects. With none by `max_ticks`, a routine check."""
    # Variables:
    #   look: The read-only tools, the same ones the agent would have.
    #   act: The tool that lets time pass; it is the only change this makes.
    #   max_ticks: When to give up and report a routine check.
    #   step: How many ticks to advance between looks.
    #   checked: The last tick already searched, so nothing is looked at twice.
    #   now: The factory's tick after the latest wait.
    #   recent: The latest inspections, at most WINDOW.
    #   failed: The inspections among them that failed.
    checked = 0
    while look.get_time()["tick"] < max_ticks:
        act.wait(step)
        now = look.get_time()["tick"]
        for event in look.get_events(checked + 1, now):
            if event["kind"] in ("alarm", "status"):
                machine = event["machine_id"]
                said = (
                    f"alarm on {machine}: {event['message']}"
                    if event["kind"] == "alarm"
                    else f"{machine} {event['message']}"
                )
                return DetectedAnomaly(
                    tick=event["tick"],
                    machine_id=machine,
                    kind=event["kind"],
                    description=said,
                )
        recent = look.get_inspections(0, now)[-WINDOW:]
        failed = [r for r in recent if r["result"] == "failed"]
        if len(failed) >= FAILS_IN_WINDOW and failed[-1]["tick"] > checked:
            jobs = ", ".join(str(r["job_id"]) for r in failed)
            return DetectedAnomaly(
                tick=now,
                kind="inspection_failures",
                description=(
                    f"{len(failed)} of the last {len(recent)} jobs failed "
                    f"inspection (jobs {jobs})"
                ),
            )
        checked = now
    return DetectedAnomaly(
        tick=look.get_time()["tick"], kind="routine_check", description=ROUTINE_CHECK
    )
