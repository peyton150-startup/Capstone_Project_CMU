"""Replay other gap rules on finished runs, without asking any model.

The final check (`check_conclusion`) holds a diagnosis open, and lowers the
answer to "escalate", whenever it finds any gap. This module asks: had the
rule let some kinds of gap through as notes, what would each case have ended
as, and would that have been right? It only reads saved results files, so it
costs nothing and changes nothing.

Run: `python -m capstone.evaluation.gap_replay RESULTS.jsonl [...] [--cases]`

Results saved before the gap trace existed still replay, roughly: their gaps
are sorted by wording, the model's open questions cannot be told from the
questions it never answered (both count as "unlinked"), and the model's own
completion claim is assumed to be "supported" unless no gap explains the
"unresolved".
"""

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from capstone.agent.state import ConclusionTrace

NO_OBSERVABLE = "No current observable evidence was cited for this diagnosis."
SELECTED_CONFLICT = (
    "The selected hypothesis still has conflicting or unexplained evidence."
)
UNVERIFIED = re.compile(r"^E\d+: unverified$")
GROUNDING = {"no_observable_evidence", "selected_has_conflict", "unverified_number"}
QUESTIONS = {"model_question", "unanswered_question", "question"}


@dataclass(frozen=True)
class Gap:
    """One gap as the replay sees it: its kind and, for a question, its role."""

    kind: str
    role: str | None = None


@dataclass(frozen=True)
class Case:
    """What a rule needs from one finished case."""

    scenario_id: str
    model_recommendation: str
    model_self_unresolved: bool
    gaps: tuple[Gap, ...]
    wanted_action: str | None
    action_blocked: str | None
    # The fixes the true faults needed, as "action machine"; empty when
    # asking for no fix was right.
    needed: tuple[str, ...]
    # False for results saved before the gap trace existed.
    traced: bool


@dataclass(frozen=True)
class Rule:
    """A gap rule: which gaps hold the diagnosis open."""

    name: str
    meaning: str
    blocks: Callable[[Gap], bool]


RULES = (
    Rule("today", "every gap holds it open (the live rule)", lambda g: True),
    Rule(
        "grounding+rivals+unlinked",
        "grounding gaps, rival tests and questions with no known role",
        lambda g: g.kind in GROUNDING or g.role in ("rival_test", "unlinked"),
    ),
    Rule(
        "grounding+rivals",
        "grounding gaps and questions that test a rival explanation",
        lambda g: g.kind in GROUNDING or g.role == "rival_test",
    ),
    Rule(
        "grounding",
        "uncited observations, conflicts with the chosen cause, unverified numbers",
        lambda g: g.kind in GROUNDING,
    ),
    Rule(
        "numbers",
        "only numbers that could not be verified",
        lambda g: g.kind == "unverified_number",
    ),
    Rule("none", "no gap holds it open; only the model's own claim", lambda g: False),
)


def legacy_gap(text: str) -> Gap:
    """Sort one plain-text gap from an older results file by its wording."""
    if text == NO_OBSERVABLE:
        return Gap("no_observable_evidence")
    if text == SELECTED_CONFLICT:
        return Gap("selected_has_conflict")
    if UNVERIFIED.match(text):
        return Gap("unverified_number")
    return Gap("question", "unlinked")


def read_results(path: Path) -> list[dict]:
    """The records of one results file, as plain data.

    Read loosely on purpose: only the fields the replay needs are used, so
    results written by a branch with extra fields still replay.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def case_of(record: dict) -> Case | None:
    """The replay's view of one record; None when no answer survived to check."""
    # Variables:
    #   score: The case's score, which says what the true faults needed.
    #   trace: The gap trace saved by the final check, in newer results.
    #   lowered: Why an intervention was lowered, in older results; a reason
    #     that is not "investigation unresolved" came from the action rules.
    #   asked: The fixes the final answer asked for, in older results; one is
    #     the fix the model wanted when nothing lowered it.
    score = record.get("score") or {}
    needed = tuple(sorted(score.get("wanted_actions") or ()))
    scenario = record.get("scenario_id", "?")
    raw = record.get("conclusion_trace")
    if raw is not None:
        trace = ConclusionTrace.model_validate(raw)
        return Case(
            scenario_id=scenario,
            model_recommendation=trace.model_recommendation,
            model_self_unresolved=trace.model_assessment == "unresolved",
            gaps=tuple(Gap(g.kind, g.role) for g in trace.gaps),
            wanted_action=trace.wanted_action,
            action_blocked=trace.action_blocked,
            needed=needed,
            traced=True,
        )
    if record.get("policy_recommendation") is None:
        return None
    gaps = tuple(legacy_gap(t) for t in record.get("unresolved_questions") or ())
    lowered = record.get("recommendation_lowered")
    asked = score.get("recommended_actions") or []
    return Case(
        scenario_id=scenario,
        model_recommendation=record["policy_recommendation"],
        model_self_unresolved=record.get("assessment") == "unresolved" and not gaps,
        gaps=gaps,
        wanted_action=asked[0] if len(asked) == 1 else None,
        action_blocked=None
        if lowered is None or lowered.startswith("investigation unresolved")
        else lowered,
        needed=needed,
        traced=False,
    )


def final_recommendation(case: Case, rule: Rule) -> str:
    """What the case would have ended as under this rule."""
    # Variables:
    #   case.model_self_unresolved: The model held it open itself; no rule
    #     overrides that.
    #   case.action_blocked: The action rules (confidence, evidence, a named
    #     fix) refuse the fix whatever the gaps, so it still escalates.
    if case.model_self_unresolved or any(rule.blocks(g) for g in case.gaps):
        return "escalate"
    if case.model_recommendation == "intervene" and case.action_blocked:
        return "escalate"
    return case.model_recommendation


def outcome(case: Case, recommendation: str) -> str:
    """Judge an ending against what the true faults needed."""
    # Variables:
    #   case.needed: The fixes the true faults needed; empty means asking for
    #     no fix was right.
    #   case.wanted_action: The fix the model asked for; None when an older
    #     record did not keep it, judged "fix_unknown".
    if recommendation == "escalate":
        return "held_fault" if case.needed else "held_no_fault"
    if recommendation == "no_action":
        return "missed_fault" if case.needed else "closed_right"
    if not case.needed:
        return "unneeded_fix"
    if case.wanted_action is None:
        return "fix_unknown"
    return "right_fix" if (case.wanted_action,) == case.needed else "wrong_fix"


HARMFUL = ("missed_fault", "wrong_fix", "unneeded_fix")
RIGHT = ("right_fix", "closed_right")
HELD = ("held_fault", "held_no_fault")


def replay(cases: Sequence[Case], rules: Sequence[Rule] = RULES) -> dict[str, Counter]:
    """Count each outcome under each rule."""
    return {
        rule.name: Counter(outcome(c, final_recommendation(c, rule)) for c in cases)
        for rule in rules
    }


def format_table(
    counts: dict[str, Counter], rules: Sequence[Rule] = RULES
) -> list[str]:
    """One line per rule: right, harmful and held, then the detail."""
    # Variables:
    #   width: Room for the longest rule name, so the columns line up.
    width = max(len(r.name) for r in rules)
    lines = [f"{'rule':{width}}  right  harmful  held  detail"]
    for rule in rules:
        c = counts[rule.name]
        detail = ", ".join(f"{k} {c[k]}" for k in sorted(c))
        lines.append(
            f"{rule.name:{width}}  {sum(c[k] for k in RIGHT):5}  "
            f"{sum(c[k] for k in HARMFUL):7}  {sum(c[k] for k in HELD):4}  {detail}"
        )
    return lines


def case_lines(cases: Sequence[Case], rules: Sequence[Rule] = RULES) -> list[str]:
    """One line per case: its outcome under each rule."""
    # Variables:
    #   ends: The case's judged ending under every rule, side by side.
    #   mark: Flags a case from older results, replayed only roughly.
    lines = []
    for case in cases:
        ends = " ".join(
            f"{rule.name}={outcome(case, final_recommendation(case, rule))}"
            for rule in rules
        )
        mark = "" if case.traced else " (untraced)"
        lines.append(
            f"{case.scenario_id}{mark}: model={case.model_recommendation} {ends}"
        )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    """Read results files and print what each gap rule would have done."""
    # Variables:
    #   cases: The cases with an answer that reached the final check.
    #   skipped: Cases where no answer survived (no model, out of time,
    #     refused), which no gap rule could change.
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--cases", action="store_true", help="show every case")
    options = parser.parse_args(argv)
    records = [r for path in options.results for r in read_results(path)]
    cases = [c for c in (case_of(r) for r in records) if c is not None]
    skipped = len(records) - len(cases)
    untraced = sum(not c.traced for c in cases)
    out = [
        f"{len(cases)} cases replayed, {skipped} skipped (no answer reached the check)",
    ]
    if untraced:
        out.append(
            f"{untraced} have no gap trace (older results): their questions count "
            "as 'unlinked' and the model's own claim is assumed 'supported'"
        )
    out += format_table(replay(cases))
    out += [f"  {r.name}: {r.meaning}" for r in RULES]
    if options.cases:
        out += case_lines(cases)
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
