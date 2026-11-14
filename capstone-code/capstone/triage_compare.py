# Side-by-side comparison of triage runs (arms), for the Block 6 acceptance work.
# Responsibility: read finished records and tabulate them; never run or change a case.
"""Compare several triage runs, one column per arm.

`python -m capstone.experiment compare --results A B ... --labels all control`
reads each arm's `*.records.jsonl` (a file, or a run folder holding them) and
prints one table: what each arm's triages did (model questions by stage,
time, timeouts, how the reports ended, plan and investigate choices, the
evidence tests) and how safe they were against the truth (unsafe
clearances, wrong-machine answers, root causes judged).

This is the triage algorithm-first comparison against the frozen A0 baseline
(`docs/2026-11-13-schedule.md`, Block 6). It is kept apart from the A1-A4
experiment series and its report on purpose: the arms compared here are
whole triage configurations, not those hypotheses.

It reads the experiment records, which hold the truth, so it is
evaluator-side only: nothing here reaches the agent. A field an older record
lacks is shown as "-", never as 0, and a root cause nobody labelled is
counted as "not judged", never as right or wrong.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from capstone.evaluation.labels import Label
from capstone.evaluation.scoring import Score
from capstone.experiment import (
    ExperimentRecord,
    TriageRecord,
    labelled,
    nearest_rank,
    read_records,
)

# Shown where an arm has nothing recorded for a row (an older record, or no
# triage at all): unknown, which is not the same as zero.
MISSING = "-"
# The scenario with no fault: clearing it is the right answer.
NO_FAULT = "false_alarm"
REPORT_OUTCOMES = ("model_conclusion", "model_answer_refused", "no_model_answer")


@dataclass(frozen=True)
class Arm:
    """One run configuration: its name, its records and their judged scores."""

    label: str
    records: list[ExperimentRecord]
    scores: list[Score]

    @property
    def triages(self) -> list[TriageRecord]:
        return [r.triage for r in self.records if r.triage is not None]

    def triage_scores(self) -> list[tuple[TriageRecord, Score]]:
        """Each triage with its run's score, for rows judged against the truth."""
        return [
            (r.triage, s)
            for r, s in zip(self.records, self.scores, strict=True)
            if r.triage is not None
        ]


def records_in(path: Path) -> list[ExperimentRecord]:
    """The records of one arm: a records file, or every one in a run folder."""
    # Variables:
    #   files: The records files found, in name order so the result is stable.
    if path.is_dir():
        files = sorted(path.rglob("*.records.jsonl"))
        if not files:
            raise SystemExit(f"no *.records.jsonl in {path}")
        return [record for f in files for record in read_records(f)]
    return read_records(path)


def load_arms(
    paths: Sequence[Path],
    names: Sequence[str] | None = None,
    labels: dict[str, Label] | None = None,
) -> list[Arm]:
    """One Arm per path, named by `names` (default: the file or folder name)."""
    # Variables:
    #   names: The column headings, one per path; left out, each path's stem.
    #   labels: Hand labels by run key, which judge root causes; runs with
    #     none stay not judged.
    if names is not None and len(names) != len(paths):
        raise SystemExit(f"{len(names)} label(s) for {len(paths)} result path(s)")
    arms = []
    for i, path in enumerate(paths):
        records = records_in(path)
        name = names[i] if names else path.name.removesuffix(".records.jsonl")
        arms.append(Arm(name, records, labelled(records, labels or {})))
    return arms


def count(arm: Arm, pick: Callable[[TriageRecord], bool]) -> str:
    """How many of the arm's triages match; "-" when it has no triage."""
    triages = arm.triages
    return str(sum(pick(t) for t in triages)) if triages else MISSING


def seconds_at(arm: Arm, share: float) -> str:
    """The triages' wall seconds at `share` (0.5, 0.95); "-" without triages."""
    seconds = [t.seconds for t in arm.triages]
    return f"{nearest_rank(seconds, share):.0f} s" if seconds else MISSING


def stage_calls(arm: Arm, stage: str) -> str:
    """Model questions asked in one stage over the arm's triages, with seconds."""
    # Variables:
    #   kept: The stage metrics of the triages that recorded them (PR 252);
    #     none means the arm predates them, shown "-".
    kept = [t.metrics for t in arm.triages if t.metrics is not None]
    if not kept:
        return MISSING
    calls = sum(m.calls_by_stage.get(stage, 0) for m in kept)
    seconds = sum(m.model_seconds_by_stage.get(stage, 0.0) for m in kept)
    return f"{calls} ({seconds:.0f} s)"


def report_count(arm: Arm, outcome: str | None) -> str:
    """Reports that ended with `outcome`; None counts triages with no report."""
    # Variables:
    #   reports: The read-only reports kept; none at all means an older arm.
    triages = arm.triages
    reports = [t.report for t in triages if t.report is not None]
    if not reports:
        return MISSING
    if outcome is None:
        return str(len(triages) - len(reports))
    return str(sum(r.outcome == outcome for r in reports))


def held_open(arm: Arm) -> str:
    """Reports the Python checks held open with at least one reason."""
    reports = [t.report for t in arm.triages if t.report is not None]
    return str(sum(bool(r.held_open_because) for r in reports)) if reports else MISSING


def cleared_without_model(arm: Arm) -> str:
    """Reports that cleared with no model conclusion behind them; must be 0."""
    reports = [t.report for t in arm.triages if t.report is not None]
    if not reports:
        return MISSING
    return str(
        sum(
            r.recommendation == "no_action" and r.outcome != "model_conclusion"
            for r in reports
        )
    )


def unsafe_clearances(arm: Arm) -> str:
    """Triages that cleared ("no_action") a case that had a fault (the truth)."""
    # Variables:
    #   pairs: Each triage with its run's score; the score holds the true fault.
    pairs = arm.triage_scores()
    if not pairs:
        return MISSING
    return str(
        sum(
            t.recommendation == "no_action" and s.true_fault != NO_FAULT
            for t, s in pairs
        )
    )


def wrong_machine(arm: Arm) -> str:
    """Scored answers naming a machine other than the true one, of those naming one.

    Read from the scored run (the deep run, or the triage when none followed).
    """
    # Variables:
    #   named: Scores where both the answer and the truth name a machine.
    named = [
        s
        for s in arm.scores
        if s.diagnosed_machine_id is not None and s.true_machine_id is not None
    ]
    if not arm.scores:
        return MISSING
    wrong = sum(s.diagnosed_machine_id != s.true_machine_id for s in named)
    return f"{wrong} of {len(named)}"


def root_causes(arm: Arm) -> str:
    """Root causes right, wrong and not judged (no label), over the arm's runs."""
    # Variables:
    #   judged: Each run's verdict: True, False, or None when nobody labelled it.
    if not arm.scores:
        return MISSING
    judged = Counter(s.fault_correct for s in arm.scores)
    return f"{judged[True]} right, {judged[False]} wrong, {judged[None]} not judged"


def plans(arm: Arm) -> str:
    """Triages planned from the fixed table vs by the model."""
    triages = arm.triages
    if not triages:
        return MISSING
    fixed = sum(t.fixed_plan for t in triages)
    return f"{fixed} fixed / {len(triages) - fixed} model"


def investigate(arm: Arm) -> str:
    """Investigate turns the compiler made vs those the model decided."""
    # Variables:
    #   kept: Each triage's compiler turns (TRIAGE_INVESTIGATE); None in every
    #     triage means the arm predates it, shown "-".
    #   advice: Every turn the request compiler ran, over the arm's triages.
    #   compiled: Turns where the compiled read replaced the model's decide.
    kept = [
        t.investigate_advice for t in arm.triages if t.investigate_advice is not None
    ]
    if not kept:
        return MISSING
    advice = [a for turns in kept for a in turns]
    compiled = sum(a.outcome == "compiled" for a in advice)
    return f"{compiled} compiled / {len(advice) - compiled} model"


def evidence_tests(arm: Arm) -> str:
    """Triages with TRIAGE_EVIDENCE_TESTS on, and the records those rules kept."""
    # Variables:
    #   kept: Triages that recorded whether the rules were on.
    #   kinds: How many records of each kind they left.
    kept = [t for t in arm.triages if t.evidence_tests is not None]
    if not kept:
        return MISSING
    on = [t for t in kept if t.evidence_tests]
    kinds = Counter(rec.kind for t in on for rec in t.test_records or ())
    return (
        f"on {len(on)}/{len(kept)}; withheld "
        f"{kinds['support_withheld_rival_question'] + kinds['support_withheld_shared_root']}"
        f", held {kinds['rival_question_gap']}, kept open "
        f"{kinds['question_kept_open']}, closed {kinds['question_closed']}"
    )


def stages_of(arms: Sequence[Arm]) -> list[str]:
    """Every stage any arm asked a model question in, in name order."""
    return sorted(
        {
            stage
            for arm in arms
            for t in arm.triages
            if t.metrics is not None
            for stage in t.metrics.calls_by_stage
        }
    )


def rows(arms: Sequence[Arm]) -> list[tuple[str, list[str]]]:
    """The table's rows: a name, then one cell per arm."""
    # Variables:
    #   table: (row name, how to compute one arm's cell) in display order;
    #     stage rows are added for every stage any arm used.
    table: list[tuple[str, Callable[[Arm], str]]] = [
        ("runs", lambda a: str(len(a.records))),
        ("triages", lambda a: str(len(a.triages))),
    ]
    table += [
        (f"model calls: {stage}", lambda a, s=stage: stage_calls(a, s))
        for stage in stages_of(arms)
    ]
    table += [
        ("triage seconds p50", lambda a: seconds_at(a, 0.5)),
        ("triage seconds p95", lambda a: seconds_at(a, 0.95)),
        ("timeouts", lambda a: count(a, lambda t: t.termination_reason == "timeout")),
        (
            "no model answered",
            lambda a: count(a, lambda t: t.termination_reason == "model_unavailable"),
        ),
        ("report: model conclusion", lambda a: report_count(a, "model_conclusion")),
        ("report: refused", lambda a: report_count(a, "model_answer_refused")),
        ("report: no model answer", lambda a: report_count(a, "no_model_answer")),
        ("report: none kept", lambda a: report_count(a, None)),
        ("held open by checks", held_open),
        ("cleared without model (must be 0)", cleared_without_model),
        ("unsafe clearances (truth)", unsafe_clearances),
        ("wrong-machine answers (truth)", wrong_machine),
        ("root cause (labels)", root_causes),
        ("deep run asked for", lambda a: count(a, lambda t: t.deep_recommended)),
        ("plan: fixed / model", plans),
        ("investigate: compiled / model", investigate),
        ("evidence tests", evidence_tests),
    ]
    return [(name, [cell(arm) for arm in arms]) for name, cell in table]


def compare(arms: Sequence[Arm]) -> str:
    """The comparison as a plain-text table, one column per arm."""
    # Variables:
    #   body: The rows, each a name and its cells.
    #   first: The row-name column's width.
    #   widths: Each column's width: the longest of its heading and cells.
    #   header: The arm names, aligned over their columns.
    body = rows(arms)
    first = max(len(name) for name, _ in body)
    widths = [
        max([len(arm.label), *(len(cells[i]) for _, cells in body)])
        for i, arm in enumerate(arms)
    ]
    header = (
        " " * first
        + " | "
        + " | ".join(arm.label.ljust(w) for arm, w in zip(arms, widths, strict=True))
    )
    lines = [
        "triage comparison (Block 6; separate from the A1-A4 series). "
        '"-" = not recorded in that arm.',
        header,
        "-" * len(header),
    ]
    lines += [
        name.ljust(first)
        + " | "
        + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True))
        for name, cells in body
    ]
    return "\n".join(line.rstrip() for line in lines)
