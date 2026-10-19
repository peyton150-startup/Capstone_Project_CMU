# The fixed seeded cases every change to the agent is measured against.
# Responsibility: name each case and pin what the evaluator expects of it.
"""The known-answer regression cases (MVP_SCOPE.md section 9, Future Work 7).

Each case is a fixed seed with its fault forced, so the same case always
builds the same factory with the same hidden fault. Two cases per fault, on
different machines or batches. What each case's truth is, and what monitoring
notices first, is pinned by `tests/test_known_answers.py`, so a change to the
simulator that moves a case shows up as a failing test, not as a silent
change in results.

Evaluator-side only. Nothing here may reach a prompt, a tool answer or
memory: the case names its fault.
"""

from dataclasses import dataclass

from capstone.simulator.generator import FAULTS


@dataclass(frozen=True)
class KnownCase:
    scenario_id: str
    seed: int
    fault: str


KNOWN_CASES: tuple[KnownCase, ...] = (
    KnownCase("KA-01-bearing", 6, "bearing_degradation"),
    KnownCase("KA-02-bearing", 9, "bearing_degradation"),
    KnownCase("KA-03-batch", 7, "bad_material_batch"),
    KnownCase("KA-04-batch", 8, "bad_material_batch"),
    KnownCase("KA-05-setting", 9, "wrong_setting"),
    KnownCase("KA-06-setting", 10, "wrong_setting"),
    KnownCase("KA-07-false-alarm", 8, "false_alarm"),
    KnownCase("KA-08-false-alarm", 11, "false_alarm"),
)

assert {case.fault for case in KNOWN_CASES} == set(FAULTS)
assert len({case.scenario_id for case in KNOWN_CASES}) == len(KNOWN_CASES)
