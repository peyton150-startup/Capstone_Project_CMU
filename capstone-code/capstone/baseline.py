# A fixed-rule diagnostician: the yardstick the research agent is compared with.
# Responsibility: diagnose from the agent's own tools, by rule, with no model.
"""The rule-based baseline.

Why it exists: an LLM that reasons over evidence is only worth its cost if
it beats a few fixed rules over the same evidence. Kim (2026, "When LLMs Sit
Above Diagnostic Tools", arXiv 2610.05031) found that across industrial
fault-diagnosis datasets an LLM handed a specialist's answer often ended up
below that specialist alone, overriding correct judgements. So the agent's
results mean little without a deterministic baseline next to them. This is
that baseline. It is not given to the agent.

`diagnose` sees only what the agent sees: the observation tools and `wait`.
It never reads the simulator or the ground truth. The rules, in order:

1. A stopped machine: bearing wear, replace the bearing. An alarm names a
   machine. A sudden spike (the alarm reading at least twice the highest
   reading before it) that has fallen away a little later: a false alarm,
   leave it.
   A slow climb to the limit, or vibration that stays up: bearing wear.
2. Otherwise (rejects, or a routine check), compare each machine's recent
   job times with its first ones. One machine's jobs clearly quicker or
   slower: its speed setting is wrong, reset it.
3. Otherwise, wait for more inspections and blame the batch whose reject
   rate stands far above the rest of the line's. Leave the factory alone.
4. Rejects that no batch explains: a wrong setting somewhere, but with no
   machine standing out the rules cannot say where, so they ask for nothing.
5. Nothing at all stands out: a false alarm.

The thresholds were set by looking at seeds 1-20 only; `known` cases and
seeds from 21 on are the held-out check (see `docs/PROGRESS.md`, R4c).

    uv run python -m capstone.baseline --known
    uv run python -m capstone.baseline --seeds 21-60
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median

from capstone.agent.monitor import detect_anomaly
from capstone.evaluation.known_answers import KNOWN_CASES
from capstone.evaluation.scoring import Score, evaluate, format_summary, summarize
from capstone.faults import agent_side
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.diagnosis import Diagnosis
from capstone.tools.observation import ObservationTools

# Rule 1: how long to wait after an alarm, the stretches compared, how many
# times the earlier peak a spike must reach, and how far it must have fallen.
SETTLE_TICKS, WATCH_TICKS, BEFORE_TICKS = 30, 20, 100
SPIKE, FALLEN_TO = 2.0, 0.75
# Rule 2: jobs compared at each end, and how far their median time must move.
JOBS_COMPARED, SPEED_CHANGE = 4, 0.10
# Rule 3: how long to wait for more inspections (the longest wait allowed),
# how many rejects a batch needs, and how many times the rest's reject rate.
MORE_INSPECTIONS_TICKS, MIN_BATCH_FAILS, BATCH_STANDS_OUT = 480, 2, 3.0
# After a repair: how long to let it run before scoring, like the agent's check.
AFTER_WORK_TICKS = 200

# The repair the rules ask for, per fault: the fault packs' repair actions.
FIX = {side.kind: side.action for side in agent_side() if side.action is not None}


@dataclass
class Verdict:
    """What the rules concluded, the repair they ask for, and what they looked at."""

    diagnosis: Diagnosis
    action: str | None
    calls: list[tuple[str, dict]] = field(default_factory=list)


class _Looker:
    """The observation tools, keeping a list of each call for evidence scoring."""

    def __init__(self, look: ObservationTools, act: ActionTools):
        self._look, self._act = look, act
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, tool: str, **arguments):
        self.calls.append((tool, arguments))
        if tool == "wait":
            return self._act.wait(**arguments)
        return getattr(self._look, tool)(**arguments)

    def now(self) -> int:
        return self._look.get_time()["tick"]

    def peak_vibration(
        self, machine_id: str, from_tick: int, to_tick: int
    ) -> float | None:
        """The highest vibration reading in the stretch. Peaks, not means: an
        idle machine reads near zero, which would drag a mean down."""
        # Variables:
        #   rows: The vibration readings in the stretch.
        rows = self(
            "get_readings",
            machine_id=machine_id,
            sensor="vibration",
            from_tick=max(0, from_tick),
            to_tick=max(0, to_tick),
        )
        return max(r["value"] for r in rows) if rows else None


def diagnose(look: ObservationTools, act: ActionTools, anomaly) -> Verdict:
    """Apply the rules to what the tools show. May let time pass.

    `anomaly` is what `detect_anomaly` noticed (its kind, tick and machine).
    It is passed on without importing its type, which belongs to the agent.

    Every tool call it makes feeds a rule: none is made only to look
    thorough, so its "relevant evidence collected" score is not padded.
    """
    # Variables:
    #   look: The read-only tools; the rules see only what the agent sees.
    #   act: The tools that act; only wait is used here.
    #   anomaly: What monitoring noticed first: its kind, tick and machine.
    #   ask: Wraps the tools and keeps a list of each call, for scoring evidence.
    #   machine: The machine monitoring named, if any.
    #   now: The current tick.
    #   before: Highest vibration in the stretch before the alarm.
    #   at_alarm: Vibration at the alarm tick.
    #   after: Highest vibration in the stretch just before now.
    #   spike: True if the alarm reading is at least twice the earlier peak.
    #   gone: True if vibration has since fallen away.
    #   changed: For each machine, how its recent job times compare with its first ones.
    #   worst: The machine whose job times changed most.
    #   ratio: Its recent job time over its first.
    #   inspections: Pass-or-fail results so far.
    #   batch: The batch whose reject rate stands out, if any.
    ask = _Looker(look, act)
    machine = anomaly.machine_id

    def verdict(fault: str, *, machine_id=None, batch_id=None, why: str) -> Verdict:
        # Variables:
        #   why: One sentence for the record of what the rule saw.
        return Verdict(
            Diagnosis(
                fault=fault, machine_id=machine_id, batch_id=batch_id, summary=why
            ),
            FIX.get(fault),
            ask.calls,
        )

    if anomaly.kind == "status" and machine is not None:
        return verdict(
            "bearing_degradation", machine_id=machine, why=f"{machine} stopped"
        )

    if anomaly.kind == "alarm" and machine is not None:
        ask("wait", ticks=SETTLE_TICKS)
        now = ask.now()
        before = ask.peak_vibration(
            machine, anomaly.tick - BEFORE_TICKS, anomaly.tick - 1
        )
        at_alarm = ask.peak_vibration(machine, anomaly.tick, anomaly.tick)
        after = ask.peak_vibration(machine, now - WATCH_TICKS, now)
        if before and at_alarm and after:
            spike = at_alarm >= SPIKE * before
            gone = after < FALLEN_TO * at_alarm
            if spike and gone:
                return verdict(
                    "false_alarm",
                    machine_id=machine,
                    why=f"a spike to {at_alarm:.2f} from {before:.2f}, "
                    f"back to {after:.2f}",
                )
        return verdict(
            "bearing_degradation",
            machine_id=machine,
            why="vibration climbed to the alarm and stayed up",
        )

    now = ask.now()
    changed = _job_time_changes(ask("get_events", from_tick=0, to_tick=now))
    if changed:
        worst, ratio = max(changed.items(), key=lambda item: abs(item[1] - 1.0))
        if abs(ratio - 1.0) >= SPEED_CHANGE:
            return verdict(
                "wrong_setting",
                machine_id=worst,
                why=f"job times on {worst} changed by {ratio:.2f}x",
            )

    ask("wait", ticks=MORE_INSPECTIONS_TICKS)
    now = ask.now()
    inspections = ask("get_inspections", from_tick=0, to_tick=now)
    batch = _standout_batch(inspections)
    if batch is not None:
        return verdict(
            "bad_material_batch",
            batch_id=batch,
            why=f"rejects concentrated in batch {batch}",
        )
    if any(r["result"] == "failed" for r in inspections):
        return verdict(
            "wrong_setting", why="rejects spread over batches; no machine stands out"
        )
    return verdict("false_alarm", machine_id=machine, why="nothing stands out")


def _job_time_changes(events: list[dict]) -> dict[str, float]:
    """Per machine: median of its last few job times over its first few."""
    # Variables:
    #   events: The event log over the run.
    #   started: The tick each job began at each machine.
    #   times: Each machine's job durations in ticks, in order.
    started: dict[tuple, int] = {}
    times: dict[str, list[int]] = {}
    for e in events:
        if e["kind"] != "job":
            continue
        key = (e["machine_id"], e["job_id"])
        if e["message"].endswith("started"):
            started[key] = e["tick"]
        elif e["message"].endswith("finished") and key in started:
            times.setdefault(e["machine_id"], []).append(e["tick"] - started[key])
    return {
        m: median(t[-JOBS_COMPARED:]) / median(t[:JOBS_COMPARED])
        for m, t in times.items()
        if len(t) >= 2 * JOBS_COMPARED
    }


def _standout_batch(inspections: list[dict]) -> int | None:
    """The batch whose reject rate is far above the rest of the line's, if any."""
    # Variables:
    #   tally: For each batch, [rejects, inspections].
    #   best: The batch with the highest standout reject rate so far.
    #   best_rate: That batch's reject rate.
    #   rest_rate: The reject rate of all other batches, never zero.
    tally: dict[int, list[int]] = {}
    for row in inspections:
        fails, total = tally.setdefault(row["batch_id"], [0, 0])
        tally[row["batch_id"]] = [fails + (row["result"] == "failed"), total + 1]
    best, best_rate = None, 0.0
    for batch, (fails, total) in tally.items():
        rest_fails = sum(f for b, (f, _) in tally.items() if b != batch)
        rest_total = sum(n for b, (_, n) in tally.items() if b != batch)
        rest_rate = (rest_fails + 1) / (rest_total + 2)  # never zero
        rate = fails / total
        if fails >= MIN_BATCH_FAILS and rate >= BATCH_STANDS_OUT * rest_rate:
            if rate > best_rate:
                best, best_rate = batch, rate
    return best


def run_baseline(seed: int, fault: str | None = None) -> Score:
    """One seeded episode with the rules in place of the agent, scored.

    Holds the simulator (to build and score it) the way `capstone.episode`
    does; `diagnose` gets only the tools. The repair it asks for is approved
    and carried out, as `approve_all` does for the agent in experiments.
    """
    # Variables:
    #   sim: The factory with its hidden fault, used only to build and score the run.
    #   desk: The approval desk; the rules' request is approved automatically.
    #   found: What the rules concluded and the repair they ask for.
    #   target: The machine the rules blame.
    #   proposal: The repair request made to the desk.
    sim = build_scenario(seed, fault=fault)
    desk = ApprovalDesk(sim)
    look, act = ObservationTools(sim), ActionTools(sim, desk)
    anomaly = detect_anomaly(look, act)
    start_tick = sim.clock.tick
    found = diagnose(look, act, anomaly)
    target = found.diagnosis.machine_id
    if found.action is not None and target is not None:
        proposal = act.propose_action(target, found.action, found.diagnosis.summary)
        desk.approve(proposal["id"], "approved")
        act.execute_action(proposal["id"])
    act.wait(AFTER_WORK_TICKS)
    return evaluate(
        sim,
        found.diagnosis,
        desk.proposals(),
        tool_calls=len(found.calls),
        start_tick=start_tick,
        calls=found.calls,
    )


def _seeds(text: str) -> list[int]:
    if "-" in text:
        low, high = text.split("-")
        return list(range(int(low), int(high) + 1))
    return [int(s) for s in text.split(",")]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m capstone.baseline")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--known", action="store_true", help="the known-answer cases")
    which.add_argument("--seeds", help='seeds, "21-60" or "1,4,9"; every fault each')
    args = parser.parse_args(argv)
    if args.known:
        cases = [(c.scenario_id, c.seed, c.fault) for c in KNOWN_CASES]
    else:
        cases = [(f"seed-{s}/{f}", s, f) for s in _seeds(args.seeds) for f in FAULTS]
    scores = []
    for name, seed, fault in cases:
        score = run_baseline(seed, fault)
        scores.append(score)
        print(
            f"{name:28} said={score.diagnosed_fault:20} right={score.fault_correct!s:5} "
            f"target={score.target_correct!s:5} resolved={score.resolved!s:5} "
            f"miss={score.miss_kind or '-'}"
        )
    print(format_summary(summarize(scores)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
