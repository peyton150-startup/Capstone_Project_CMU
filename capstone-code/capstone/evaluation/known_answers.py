# The fixed seeded cases every change to the agent is measured against.
# Responsibility: name each case and pin what the evaluator expects of it.
"""The known-answer regression cases (MVP_SCOPE.md section 9, Future Work 7).

Each case is a fixed seed with its fault forced, so the same case always
builds the same factory with the same hidden fault. Two cases per fault, on
different machines or batches, and one compound challenge (kind
"challenge", `simulator/challenge.py`): two true faults on one machine and
three distractors, so it has no single `fault`. What each case's truth is, and what monitoring
notices first, is pinned by `tests/test_known_answers.py`, so a change to the
simulator that moves a case shows up as a failing test, not as a silent
change in results.

Besides the four faults a seed draws by itself (`FAULTS`), two that are only
ever forced: a wearing servo drive and a hydraulic leak (KA-10 to KA-13).
Both keep getting worse until their one repair is made, so "it went away,
leave it" is never right for them: the agent has to choose a fix.

Evaluator-side only. Nothing here may reach a prompt, a tool answer or
memory: the case names its fault.
"""

from dataclasses import dataclass

from capstone.faults import FAULT_KINDS
from capstone.simulator.generator import FAULTS


@dataclass(frozen=True)
class KnownCase:
    scenario_id: str
    seed: int
    fault: str | None
    # "standard" (one forced fault) or "challenge"; see capstone.episode.
    kind: str = "standard"


KNOWN_CASES: tuple[KnownCase, ...] = (
    KnownCase("KA-01-bearing", 6, "bearing_degradation"),
    KnownCase("KA-02-bearing", 9, "bearing_degradation"),
    KnownCase("KA-03-batch", 7, "bad_material_batch"),
    KnownCase("KA-04-batch", 8, "bad_material_batch"),
    KnownCase("KA-05-setting", 9, "wrong_setting"),
    KnownCase("KA-06-setting", 10, "wrong_setting"),
    KnownCase("KA-07-false-alarm", 8, "false_alarm"),
    KnownCase("KA-08-false-alarm", 11, "false_alarm"),
    KnownCase("KA-09-challenge", 3, None, kind="challenge"),
    # Seeds chosen offline on 2026-10-31 from 0-24, unused by the cases above,
    # for an alarm on a different machine in each pair at a tick like the others'.
    KnownCase("KA-10-servo", 16, "servo_drive_wear"),
    KnownCase("KA-11-servo", 13, "servo_drive_wear"),
    KnownCase("KA-12-hydraulic", 4, "hydraulic_leak"),
    KnownCase("KA-13-hydraulic", 15, "hydraulic_leak"),
)

# Every fault a seed draws has its cases; a forced-only fault may have them too.
assert set(FAULTS) <= {case.fault for case in KNOWN_CASES if case.kind == "standard"}
assert {case.fault for case in KNOWN_CASES if case.kind == "standard"} <= set(
    FAULT_KINDS
)
assert all(case.fault is None for case in KNOWN_CASES if case.kind != "standard")
assert len({case.scenario_id for case in KNOWN_CASES}) == len(KNOWN_CASES)

# The one-fault cases: what the single-fault checks use.
STANDARD_CASES: tuple[KnownCase, ...] = tuple(
    case for case in KNOWN_CASES if case.kind == "standard"
)

# The one-fault cases the rule baseline has rules for: the four faults a seed
# draws. It has none for a servo drive or a hydraulic leak.
BASELINE_CASES: tuple[KnownCase, ...] = tuple(
    case for case in STANDARD_CASES if case.fault in FAULTS
)
