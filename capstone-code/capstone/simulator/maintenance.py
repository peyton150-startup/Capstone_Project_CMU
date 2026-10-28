# The maintenance the line had before the simulation starts.
# Responsibility: give each machine a seeded, plausible service history.
"""A small maintenance history from before the run (MVP_SCOPE.md section 1).

Every machine starts with one to four past service records from the six
months before the start: routine lubrication, coolant changes, calibrations,
inspections, sometimes a replaced part. They come from their own random
stream ("maintenance.history"), drawn before any fault is chosen and never
from it, so the history says nothing about which fault a run has. It is
background an investigator may read, and it can mislead: a spindle serviced
two months ago does not mean the spindle is fine now.

Maintenance done during the run is not here: it is in the event log, as
"maintenance" events, and `get_maintenance_history` shows both.
"""

import random
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

# (kind, what the technician wrote). Routine work is likelier than repairs.
ROUTINE = (
    ("lubrication", "spindle and way lubrication; no findings"),
    ("coolant change", "coolant drained and replaced; concentration in range"),
    ("calibration", "spindle speed checked against standard; within tolerance"),
    ("inspection", "spindle noise check; no abnormal noise"),
    ("sensor check", "vibration and temperature sensors checked; reading normally"),
)
REPAIRS = (
    ("spindle service", "spindle cartridge replaced after scheduled hours"),
    ("part replacement", "way cover replaced; chips had got under the old one"),
    ("setting change", "spindle speed set to standard after a tooling change"),
)
HISTORY_DAYS = 180


class MaintenanceRecord(BaseModel):
    """One past service visit. Background, not a cause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine_id: str
    performed_at: datetime
    kind: str = Field(min_length=1)
    note: str = Field(min_length=1)


def past_maintenance(
    machine_ids: list[str], start: datetime, rng: random.Random
) -> list[MaintenanceRecord]:
    """One to four records per machine before `start`, oldest first overall."""
    # Variables:
    #   rng: The maintenance-history stream, drawn before any fault so the history says
    #     nothing about the fault.
    #   days_before: How long before the start the visit happened.
    #   when: The date and hour of the visit.
    records = []
    for machine_id in machine_ids:
        for _ in range(rng.randint(1, 4)):
            kind, note = rng.choice(REPAIRS if rng.random() < 0.2 else ROUTINE)
            days_before = rng.randint(1, HISTORY_DAYS)
            hour = rng.randint(6, 17)
            when = (start - timedelta(days=days_before)).replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            records.append(
                MaintenanceRecord(
                    machine_id=machine_id, performed_at=when, kind=kind, note=note
                )
            )
    return sorted(records, key=lambda r: (r.performed_at, r.machine_id))
