"""The factory's ordinary monitoring: runs the line until something looks wrong.

Uses the agent-facing tools only, so it sees what the agent would see,
and names the symptom, never the cause.
"""

from capstone.tools.actions import ActionTools
from capstone.tools.observation import ObservationTools

FAILS_IN_WINDOW, WINDOW = 3, 10  # three failed inspections among the last ten jobs


def wait_for_anomaly(
    look: ObservationTools, act: ActionTools, *, max_ticks: int = 4000, step: int = 10
) -> str | None:
    """Advance the factory `step` ticks at a time until an alarm, a stopped machine, or a run of rejects."""
    checked = 0
    while look.get_time()["tick"] < max_ticks:
        act.wait(step)
        now = look.get_time()["tick"]
        for event in look.get_events(checked + 1, now):
            if event["kind"] == "alarm":
                return f"tick {event['tick']}: alarm on {event['machine_id']}: {event['message']}"
            if event["kind"] == "status":
                return f"tick {event['tick']}: {event['machine_id']} {event['message']}"
        recent = look.get_inspections(0, now)[-WINDOW:]
        failed = [r for r in recent if r["result"] == "failed"]
        if len(failed) >= FAILS_IN_WINDOW and failed[-1]["tick"] > checked:
            jobs = ", ".join(str(r["job_id"]) for r in failed)
            return f"tick {now}: {len(failed)} of the last {len(recent)} jobs failed inspection (jobs {jobs})"
        checked = now
    return None
