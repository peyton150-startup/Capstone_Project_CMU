# Follows one investigation in the terminal as it happens.
# Responsibility: print what is new in the agent's working state; the truth only after.
"""Watch one episode live: `python -m capstone.progress --seed 7`.

    uv run python -m capstone.progress --seed 7 --fault bearing_degradation
    uv run python -m capstone.progress --seed 7 --approve all --memory

Each step is printed as it happens: the anomaly, every tool call and what
came of it, the agent's beliefs when they change, its conclusion, the
proposal (then the approval question at the prompt, by default), and the
check afterwards. Only what the agent itself has is shown, read from copies
of its working state (`InvestigationDeps.watch`); the simulator is never
read while the run is going. The truth (the score) is printed once the run
is over, under its own heading.

This is the terminal view only. A later frontend (Future Work 8) would sit
on the same hook. Live runs need the model keys; `--memory` reads the
configured store but learns nothing (no audit log).
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import DecisionRecord, InvestigationState
from capstone.console import safe_console
from capstone.episode import (
    SCENARIO_KINDS,
    STANDARD,
    Approver,
    EpisodeResult,
    approve_all,
    ask_on_console,
    reject_all,
    run_episode,
)
from capstone.evaluation.scoring import Score
from capstone.simulator.generator import FAULTS

Write = Callable[[str], None]

# How much of an evidence item or an argument list fits on one line.
CONTENT_WIDTH = 90
TOP_BELIEFS = 3


def shorten(text: str, width: int = CONTENT_WIDTH) -> str:
    """One line, at most `width` characters, cut with "..." when longer."""
    # Variables:
    #   width: The longest the line may be.
    #   line: The text with newlines and extra spaces collapsed.
    line = " ".join(str(text).split())
    return line if len(line) <= width else line[: width - 3] + "..."


def call_text(decision: DecisionRecord) -> str:
    arguments = ", ".join(f"{k}={v}" for k, v in decision.arguments.items())
    return f"{decision.tool}({shorten(arguments, 60)})"


def step_line(decision: DecisionRecord, state: InvestigationState) -> list[str]:
    """The lines for one decision: what was asked, and what came of it."""
    # Variables:
    #   decision: One step the agent took.
    #   state: The agent's working state, read for the evidence the step produced.
    #   where: The step's number and phase, as the line's prefix.
    #   tick: The factory time of the step, if known.
    #   reason: Why the loop stopped, for a stop step.
    #   why: That reason in words.
    #   head: The first line: the prefix and the tool call.
    #   contents: The text of each piece of evidence, by id.
    #   origins: Where each piece of evidence came from.
    #   lines: Every line for this step.
    #   origin: Where this piece came from; anything but a look at the factory is
    #     marked.
    #   label: The mark shown for non-factory evidence.
    where = f"#{decision.sequence:<3} {decision.phase:<11}"
    tick = "" if decision.tick is None else f" t={decision.tick}"
    if decision.outcome == "stopped":
        reason = decision.termination_reason
        why = reason.value if reason is not None else "stopped"
        return [f"{where} stop: {why} ({decision.information_needed}){tick}"]
    if decision.tool is None:
        return [f"{where} {decision.outcome}: {decision.information_needed}{tick}"]
    head = f"{where} {call_text(decision)}{tick}"
    if decision.outcome == "repeated_call":
        return [f"{head}  -> skipped: already asked at this tick"]
    if decision.error is not None:
        return [f"{head}  -> failed: {shorten(decision.error.message, 70)}"]
    if not decision.evidence_ids:
        return [f"{head}  -> {decision.outcome}"]
    contents = {e.id: e.content for e in state.evidence}
    origins = {p.evidence_id: p.origin for p in state.provenance}
    lines = [head]
    for evidence_id in decision.evidence_ids:
        origin = origins.get(evidence_id, "observable")
        label = "" if origin == "observable" else f" [{origin}]"
        lines.append(
            f"       -> {evidence_id}{label}: {shorten(contents.get(evidence_id, ''))}"
        )
    return lines


class ProgressView:
    """Prints what is new in an investigation each time it is shown the state.

    Pass it as `watch` to `run_episode`. It keeps its own place (how many
    decisions it has printed, the last beliefs, conclusion, proposal and
    check it showed), so being shown the same state twice prints nothing.
    """

    def __init__(self, write: Write = print):
        # Variables:
        #   write: Where lines go; print by default, replaced in tests.
        #   started: Whether the opening line has been printed.
        #   decisions_shown: How many steps have been printed, so only new ones are.
        #   beliefs: The leading beliefs last printed.
        #   conclusion: The conclusion last printed.
        #   proposal: The proposal last printed.
        #   verification: The check last printed.
        #   critique: The critic's record last printed.
        self.write = write
        self.started = False
        self.decisions_shown = 0
        self.beliefs: tuple = ()
        self.conclusion = None
        self.proposal = None
        self.verification = None
        self.critique = None

    def __call__(self, state: InvestigationState) -> None:
        # Variables:
        #   state: A copy of the agent's working state; this view only reads it.
        #   anomaly: What monitoring noticed first.
        #   where: The machine named, or the factory as a whole.
        #   c: The agent's conclusion.
        #   proposal: The repair request, if one was made.
        #   check: The after-the-fix check, if one was made.
        if not self.started:
            self.started = True
            anomaly = state.anomaly
            where = anomaly.machine_id or "the factory"
            self.write(f"anomaly at t={anomaly.tick} on {where}: {anomaly.description}")
        for decision in state.decisions[self.decisions_shown :]:
            for line in step_line(decision, state):
                self.write(line)
        self.decisions_shown = len(state.decisions)
        self._beliefs(state)
        self._critique(state)
        if state.conclusion is not None and state.conclusion != self.conclusion:
            self.conclusion = state.conclusion
            c = state.conclusion
            self.write(
                f"CONCLUSION ({c.confidence:.2f}, {c.recommendation}): "
                f"{shorten(c.diagnosis, 200)}"
            )
        proposal = state.proposed_action
        if proposal is not None and proposal != self.proposal:
            self.proposal = proposal
            self.write(
                f"PROPOSAL {proposal.action} on {proposal.machine_id} "
                f"[{proposal.status}]: {shorten(proposal.reason, 120)}"
            )
        check = state.verification
        if check is not None and check != self.verification:
            self.verification = check
            self.write(f"CHECK: {check.outcome} ({shorten(check.prediction, 120)})")

    def _critique(self, state: InvestigationState) -> None:
        """The critic's verdict, printed once when it first appears."""
        # Variables:
        #   record: What the critic stage produced.
        #   r: The critic's reply, if there was a usable one.
        record = state.critique
        if record is None or record == self.critique:
            return
        self.critique = record
        r = record.result
        if r is None:
            self.write(f"CRITIC ({record.outcome}): no critique")
            return
        self.write(
            f"CRITIC ({record.outcome}): favoured {r.favoured}, {r.verdict}, "
            f"check: {shorten(r.discriminating_check, 120)}"
        )

    def _beliefs(self, state: InvestigationState) -> None:
        """The leading hypotheses, printed only when they changed."""
        # Variables:
        #   leading: The most confident hypotheses, at most TOP_BELIEFS.
        #   beliefs: Their id, claim and confidence; printed only if they differ from
        #     last time.
        leading = sorted(state.hypotheses, key=lambda h: -h.confidence)[:TOP_BELIEFS]
        beliefs = tuple((h.id, h.claim, round(h.confidence, 2)) for h in leading)
        if beliefs and beliefs != self.beliefs:
            self.beliefs = beliefs
            self.write("  beliefs:")
            for hypothesis_id, claim, confidence in beliefs:
                self.write(
                    f"    {hypothesis_id} {confidence:.2f}  {shorten(claim, 80)}"
                )


def truth_lines(score: Score) -> list[str]:
    """The evaluator's side, for after the run: what was really wrong and how it went."""
    # Variables:
    #   score: The scored run, which holds the hidden truth.
    #   causes: The true faults in words.
    #   asked: Everything the agent asked for.

    def target(machine_id, batch_id) -> str:
        # Variables:
        #   machine_id: The machine a fault was on, if it was on one.
        #   batch_id: The batch a fault was in, if it was a batch.
        return f"batch {batch_id}" if batch_id is not None else str(machine_id)

    if score.causes:
        causes = "; ".join(
            f"{c.fault} on {target(c.machine_id, c.batch_id)}" for c in score.causes
        )
    else:
        causes = f"{score.true_fault} on {target(score.true_machine_id, score.true_batch_id)}"
    asked = ", ".join(score.recommended_actions) or "nothing"
    return [
        "--- after the run: the truth (the agent never saw this) ---",
        f"true cause: {causes}",
        f"asked for: {asked} "
        f"({'right' if score.recommendation_correct else 'not the needed fix'})",
        f"resolved: {'yes' if score.resolved else 'no'}; "
        f"tool calls: {score.tool_calls}; stop: {score.termination_reason}",
        "root cause not judged here: label it with `python -m capstone.experiment "
        "label` to score it",
    ]


def watch_episode(
    seed: int,
    policy: ReasoningPolicy,
    *,
    write: Write = print,
    **options,
) -> EpisodeResult:
    """Run one episode with the view attached; print the truth only at the end.

    Other options go to `run_episode` (fault, kind, approver, memory, ...).
    """
    # Variables:
    #   seed: Decides the whole factory.
    #   policy: The decision-maker.
    #   write: Where lines go.
    #   options: Passed on to the episode, such as fault, kind or approver.
    #   result: The finished episode; its truth is printed only now, after the run.
    result = run_episode(seed, policy, watch=ProgressView(write), **options)
    for line in truth_lines(result.score):
        write(line)
    return result


APPROVERS: dict[str, Approver] = {
    "console": ask_on_console,
    "all": approve_all,
    "none": reject_all,
}


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()  # a conclusion with "→" must not stop the run
    parser = argparse.ArgumentParser(prog="python -m capstone.progress")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--fault", choices=FAULTS, help="default: the seed's own")
    parser.add_argument("--kind", choices=SCENARIO_KINDS, default=STANDARD)
    parser.add_argument(
        "--approve",
        choices=list(APPROVERS),
        default="console",
        help="console: ask at the prompt (default); all / none: decide for you",
    )
    parser.add_argument("--memory", action="store_true", help="recall, learn nothing")
    parser.add_argument("--manual", choices=["keyword", "semantic"])
    parser.add_argument("--hazards", action="store_true", help="unreliable tools")
    args = parser.parse_args(argv)

    from capstone.experiment import model_policy_factory, open_manual, open_memory

    memory = open_memory() if args.memory else None
    manual = open_manual(args.manual) if args.manual else None
    policy = model_policy_factory(
        with_recall=memory is not None, with_manual=manual is not None
    )()
    watch_episode(
        args.seed,
        policy,
        fault=args.fault,
        kind=args.kind,
        approver=APPROVERS[args.approve],
        memory=memory,
        hazards=args.hazards,
        manual=manual,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
