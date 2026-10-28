"""Configurable, evaluator-side comparison of complete agent episodes.

Run from the repository root with ``uv run python -m capstone.evals``.
The scenario config and report contain hidden truth; neither is passed to a
policy or a tool. Free-text conclusions require a separate diagnosis label.
"""

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from capstone.agent.critic import Critic
from capstone.evaluation.auto_label import Proposal, propose
from capstone.evaluation.labels import Label, LabelBook, apply_label
from capstone.experiment import (
    AgentStep,
    Case,
    ExperimentRecord,
    append_records,
    model_policy_factory,
    read_records,
    run_experiment,
)
from capstone.providers.typesafe import judgment_client
from capstone.settings import get_settings
from capstone.simulator.generator import FAULTS


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    seed: int = Field(ge=0)
    kind: str = "standard"
    fault: str | None = None

    @model_validator(mode="after")
    def valid_factory(self):
        if self.kind == "challenge":
            if self.fault is not None:
                raise ValueError("challenge cases choose their own faults")
        elif self.kind != "standard" or self.fault not in FAULTS:
            raise ValueError("standard cases must force a supported fault")
        return self

    def as_case(self) -> Case:
        return Case(self.id, self.seed, self.fault, self.kind)


class ScenarioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: tuple[Scenario, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario ids must be unique")
        return self


def load_scenarios(path: Path) -> ScenarioConfig:
    return ScenarioConfig.model_validate_json(path.read_text(encoding="utf-8"))


def reserve_raw_output(path: Path) -> None:
    """Claim a result path before model calls so parallel runs cannot mix rows."""
    with path.open("x", encoding="utf-8"):
        pass


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    run_key: str
    expected_faults: tuple[str, ...]
    final_diagnosis: str | None
    diagnosis_label: Label | None
    label_needs_review: bool = False
    correct: bool | None
    target_correct: bool | None
    tool_calls: int
    runtime_seconds: float | None
    agent_steps: list[AgentStep]
    # The critic, review only. None: no critic ran (or no usable answer).
    critic_outcome: str | None = None
    critic_verdict: str | None = None
    critic_favoured: str | None = None
    # Whether the critic's pick names the true cause, from its own label.
    # None: no label for the pick (none favoured, or the label needs review).
    critic_pick_correct: bool | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    cases: list[EvalCase]
    judged: int
    overall_accuracy: float | None
    accuracy_by_fault: dict[str, float | None]
    steps_by_agent: dict[str, int]


class CaseDifference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    before_correct: bool | None
    after_correct: bool | None
    tool_calls_change: int
    runtime_seconds_change: float | None


class EvalComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    before: str
    after: str
    accuracy_change: float | None
    accuracy_by_fault_change: dict[str, float | None]
    average_tool_calls_change: float
    average_runtime_seconds_change: float | None
    steps_by_agent_before: dict[str, int]
    steps_by_agent_after: dict[str, int]
    cases: list[CaseDifference]


def compare_reports(before: EvalReport, after: EvalReport) -> EvalComparison:
    """Compare matching scenario runs; unjudged accuracy stays unknown."""
    old = {case.scenario_id: case for case in before.cases}
    new = {case.scenario_id: case for case in after.cases}
    if len(old) != len(before.cases) or len(new) != len(after.cases):
        raise ValueError("a report contains duplicate scenarios")
    if old.keys() != new.keys():
        raise ValueError("reports must use the same scenarios")
    differences = []
    for scenario_id in old:
        left, right = old[scenario_id], new[scenario_id]
        if left.expected_faults != right.expected_faults:
            raise ValueError(f"expected faults changed for {scenario_id}")
        differences.append(
            CaseDifference(
                scenario_id=scenario_id,
                before_correct=left.correct,
                after_correct=right.correct,
                tool_calls_change=right.tool_calls - left.tool_calls,
                runtime_seconds_change=(
                    right.runtime_seconds - left.runtime_seconds
                    if left.runtime_seconds is not None
                    and right.runtime_seconds is not None
                    else None
                ),
            )
        )
    runtimes = [
        case.runtime_seconds_change
        for case in differences
        if case.runtime_seconds_change is not None
    ]
    faults = before.accuracy_by_fault.keys() | after.accuracy_by_fault.keys()
    return EvalComparison(
        before=before.name,
        after=after.name,
        accuracy_change=(
            after.overall_accuracy - before.overall_accuracy
            if before.overall_accuracy is not None
            and after.overall_accuracy is not None
            else None
        ),
        accuracy_by_fault_change={
            fault: (
                after.accuracy_by_fault[fault] - before.accuracy_by_fault[fault]
                if before.accuracy_by_fault.get(fault) is not None
                and after.accuracy_by_fault.get(fault) is not None
                else None
            )
            for fault in sorted(faults)
        },
        average_tool_calls_change=sum(case.tool_calls_change for case in differences)
        / len(differences),
        average_runtime_seconds_change=(
            sum(runtimes) / len(runtimes) if len(runtimes) == len(differences) else None
        ),
        steps_by_agent_before=before.steps_by_agent,
        steps_by_agent_after=after.steps_by_agent,
        cases=differences,
    )


def report_of(
    name: str,
    records: Sequence[ExperimentRecord],
    labels: dict[str, Label],
    *,
    needs_review: set[str] | None = None,
    critic_labels: dict[str, Label] | None = None,
) -> EvalReport:
    """Score labels against saved simulator truth without rerunning an agent.

    `critic_labels` label the hypothesis the critic favoured, by run key; they
    score the critic's pick only, never the agent's accuracy.
    """
    needs_review = needs_review or set()
    critic_labels = critic_labels or {}
    cases = []
    by_fault: dict[str, list[bool]] = defaultdict(list)
    agents: Counter[str] = Counter()
    for record in records:
        label = labels.get(record.run_key)
        uncertain = record.run_key in needs_review
        scored = (
            apply_label(record.score, label.diagnosis)
            if label is not None and not uncertain
            else record.score
        )
        correct = scored.fully_right if label is not None and not uncertain else None
        truth = tuple(cause.fault for cause in record.score.causes)
        if not truth:
            truth = (record.score.true_fault,)
        for fault in set(truth):
            by_fault[fault]
        if correct is not None:
            for fault in set(truth):
                by_fault[fault].append(correct)
        steps = record.agent_steps or []
        critique = record.critique
        result = None if critique is None else critique.result
        critic_label = critic_labels.get(record.run_key)
        agents.update(step.agent for step in steps)
        cases.append(
            EvalCase(
                scenario_id=record.scenario_id,
                run_key=record.run_key,
                expected_faults=truth,
                final_diagnosis=record.conclusion,
                diagnosis_label=label,
                label_needs_review=uncertain,
                correct=correct,
                target_correct=(
                    scored.target_correct
                    if label is not None and not uncertain
                    else None
                ),
                tool_calls=record.score.tool_calls,
                runtime_seconds=record.wall_seconds,
                agent_steps=steps,
                critic_outcome=None if critique is None else critique.outcome,
                critic_verdict=None if result is None else result.verdict,
                critic_favoured=None if result is None else result.favoured,
                critic_pick_correct=(
                    None
                    if critic_label is None
                    else apply_label(record.score, critic_label.diagnosis).fully_right
                ),
            )
        )
    judged = sum(case.correct is not None for case in cases)
    return EvalReport(
        name=name,
        cases=cases,
        judged=judged,
        overall_accuracy=(
            sum(case.correct is True for case in cases) / judged if judged else None
        ),
        accuracy_by_fault={
            fault: sum(values) / len(values) if values else None
            for fault, values in sorted(by_fault.items())
        },
        steps_by_agent=dict(sorted(agents.items())),
    )


def run_cases(
    config: ScenarioConfig,
    *,
    name: str,
    make_policy: Callable | None = None,
    on_record: Callable[[ExperimentRecord], None] | None = None,
    watch: Callable[[str], None] | None = None,
    start: int = 1,
    make_critic: Callable[[], Critic] | None = None,
) -> list[ExperimentRecord]:
    """Use the normal episode runner; the config is evaluator-side only."""
    return run_experiment(
        [scenario.as_case() for scenario in config.cases],
        make_policy or model_policy_factory(False),
        name=name,
        on_record=on_record,
        watch=watch,
        start=start,
        make_critic=make_critic,
    )


def check_resume(
    config: ScenarioConfig, name: str, records: Sequence[ExperimentRecord]
) -> None:
    """Only resume a prefix of exactly this named scenario run."""
    if len(records) > len(config.cases):
        raise ValueError("more saved episodes than configured scenarios")
    for number, (scenario, record) in enumerate(zip(config.cases, records), start=1):
        expected = f"{name}/{number}/{scenario.id}"
        if (
            record.run_key != expected
            or record.scenario_id != scenario.id
            or record.seed != scenario.seed
            or (
                scenario.fault is not None and record.score.true_fault != scenario.fault
            )
        ):
            raise ValueError(f"saved episode {number} is not {expected}")


def critic_labels(
    records: Sequence[ExperimentRecord],
    proposer: Callable[[str, str], Proposal],
) -> dict[str, Label]:
    """Labels for the hypothesis each critic favoured, read as a cause.

    Only answered critiques that favoured a hypothesis are labelled. A
    proposal that needs review is left out, so that pick stays unjudged.
    """
    # Variables:
    #   records: The saved runs; each holds the claim the critic favoured, if any.
    #   proposer: Reads one claim as a named cause (in production, the Jev
    #     auto-labeller); a function so tests need no model.
    #   proposal: The proposed label and whether a person should read it first.
    #   labels: Run key to label, only for picks the proposer was sure of.
    labels = {}
    for record in records:
        if record.critic_favoured_claim is None:
            continue
        proposal = proposer(record.run_key, record.critic_favoured_claim)
        if not proposal.needs_review:
            labels[record.run_key] = proposal.label
    return labels


def automatic_labels(
    records: Sequence[ExperimentRecord],
) -> tuple[dict[str, Label], set[str], dict[str, Label]]:
    """Reuse the existing evaluator; uncertain proposals stay unjudged.

    Also labels each critic's favoured hypothesis (`critic_labels`).
    """
    client = judgment_client(get_settings())
    labels = {}
    review = set()
    for record in records:
        if record.conclusion is None:
            labels[record.run_key] = Label(
                run_key=record.run_key,
                diagnosis=None,
                labelled_by="no_conclusion",
            )
            continue
        proposal = propose(record.run_key, record.conclusion, client)
        labels[record.run_key] = proposal.label
        if proposal.needs_review:
            review.add(record.run_key)
    picks = critic_labels(
        records, lambda run_key, claim: propose(run_key, claim, client)
    )
    return labels, review, picks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m capstone.evals")
    parser.add_argument("--config", type=Path, default=Path("evals/scenarios.json"))
    parser.add_argument("--name", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--labels", type=Path, help="existing hand labels")
    parser.add_argument(
        "--auto-label", action="store_true", help="provisional TypeSafe labels"
    )
    parser.add_argument("--records", type=Path, help="read existing experiment JSONL")
    parser.add_argument(
        "--raw-out", type=Path, help="save raw episodes for later labelling"
    )
    parser.add_argument(
        "--resume", action="store_true", help="continue saved raw episodes"
    )
    parser.add_argument("--compare-before", type=Path, help="prior eval report")
    parser.add_argument("--watch", action="store_true", help="show live agent progress")
    args = parser.parse_args(argv)
    if args.labels and args.auto_label:
        parser.error("choose hand labels or automatic labels")
    if args.resume and args.records:
        parser.error("--resume continues a run; --records only rescores it")
    config = load_scenarios(args.config)
    if args.records:
        records = read_records(args.records)
    else:
        raw_path = args.raw_out or args.out.with_suffix(".records.jsonl")
        if args.resume:
            if not raw_path.exists():
                parser.error(f"no raw result to resume: {raw_path}")
            records = read_records(raw_path)
            try:
                check_resume(config, args.name, records)
            except ValueError as error:
                parser.error(str(error))
        else:
            try:
                reserve_raw_output(raw_path)
            except FileExistsError:
                parser.error(f"raw result path already exists: {raw_path}")
            records = []

        def save_record(record: ExperimentRecord) -> None:
            append_records(raw_path, [record])
            print(f"completed {record.scenario_id}", flush=True)

        def show_progress(message: str) -> None:
            print(message, flush=True)

        if len(records) < len(config.cases):
            remaining = ScenarioConfig(cases=config.cases[len(records) :])
            records += run_cases(
                remaining,
                name=args.name,
                on_record=save_record,
                watch=show_progress if args.watch else None,
                start=len(records) + 1,
            )
    wanted = [scenario.id for scenario in config.cases]
    if [record.scenario_id for record in records] != wanted:
        parser.error("record scenarios must match config in order")
    labels, review, picks = {}, set(), {}
    if args.labels:
        labels = LabelBook(args.labels).read()
    elif args.auto_label:
        labels, review, picks = automatic_labels(records)
    report = report_of(
        args.name, records, labels, needs_review=review, critic_labels=picks
    )
    args.out.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    if args.compare_before:
        before = EvalReport.model_validate_json(
            args.compare_before.read_text(encoding="utf-8")
        )
        comparison = compare_reports(before, report)
        comparison_path = args.out.with_suffix(".comparison.json")
        comparison_path.write_text(
            comparison.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "cases": len(report.cases),
                "judged": report.judged,
                "overall_accuracy": report.overall_accuracy,
                "accuracy_by_fault": report.accuracy_by_fault,
                "steps_by_agent": report.steps_by_agent,
                "out": str(args.out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
