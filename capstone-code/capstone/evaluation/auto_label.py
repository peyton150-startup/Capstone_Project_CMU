# Proposed diagnosis labels from a judgment model, checked against hand labels.
# Responsibility: read a conclusion, ask typed questions, propose a Label, measure agreement.
"""An evaluator model proposes the labels a person writes by hand (`labels.py`).

MVP_SCOPE.md's "evaluator model for diagnosis labels" candidate: experiments can score root
cause without labelling every run by hand, but only once the proposals
agree with the developer's hand labels. So proposals are kept in their own
file, never mixed with hand labels, and `agreement` reports how often they
match. Nothing here reaches the agent or memory, and the hidden truth is
never read: the model sees only the conclusion's words.

How a conclusion is read (one request, every question in parallel):

- one yes/no question per fault kind: "does the conclusion settle on this
  as the cause?" Several may be yes (a conclusion can name several causes);
- for each fault kind, which of the machines (or batches) the text mentions
  it blames. The candidates are found in the text by code, so the model
  selects an id and never writes one. Asked for every kind at once and read
  only for the kinds that were named.

A yes needs probability >= `YES`; a no needs <= `NO`; anything between, or
a weakly chosen machine, marks the proposal for review by a person. These
are TypeSafe's suggested starting points, not measured on this project.
"""

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from capstone.evaluation.labels import Label, LabelBook
from capstone.providers.typesafe import (
    Choice,
    ChoiceAnswer,
    JudgmentClient,
    Noul,
    NoulAnswer,
    judgment_client,
)
from capstone.settings import get_settings
from capstone.tools.diagnosis import FAULT_KINDS, Diagnosis

# The conclusion an investigation leaves when it could not give one.
UNDETERMINED = "undetermined"

YES = 0.7
NO = 0.3
# Below this, the chosen machine or batch is too uncertain to accept unread.
TARGET_CONFIDENCE = 0.5

NONE = "none"

# What each fault kind means, in words a reader of the conclusion would use.
CAUSES: dict[str, str] = {
    "bearing_degradation": (
        "a worn, failing or degrading bearing on a machine (a developing "
        "mechanical fault the conclusion attributes to bearing wear)"
    ),
    "bad_material_batch": (
        "a defective material batch: the raw material of one batch is bad, "
        "so parts made from it fail inspection"
    ),
    "wrong_setting": (
        "a machine setting or operating parameter (such as speed, feed or an "
        "offset) set to a wrong value"
    ),
    "servo_drive_wear": (
        "a worn servo drive on a machine's feed axis: the axis lags its "
        "commanded position, so parts come out off size"
    ),
    "hydraulic_leak": (
        "a leak in a machine's hydraulic system: pressure falls, the clamp "
        "holds parts loosely and they come out off size"
    ),
    "false_alarm": (
        "no real fault: the alarm or anomaly was transient, noise, a sensor "
        "glitch or ordinary variation, and nothing needs fixing"
    ),
}
assert set(CAUSES) == set(FAULT_KINDS)

_MACHINE = re.compile(r"\b[A-Z]{2,5}-\d{1,3}\b")
_BATCH = re.compile(r"\bbatch(?:es)?\s*#?\s*(\d+)\b", re.IGNORECASE)


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def machines_in(text: str) -> list[str]:
    """The machine ids the text mentions, in order of first mention."""
    return _unique(_MACHINE.findall(text))


def batches_in(text: str) -> list[int]:
    """The material batch numbers the text mentions, in order."""
    return [int(n) for n in _unique(_BATCH.findall(text))]


def cause_question(fault: str) -> Noul:
    return Noul(
        instructions=(
            "Does `conclusion` settle on the following as the cause of the "
            f"problem it investigated: {CAUSES[fault]}?"
        ),
        true=(
            "The conclusion names this as the cause or the most likely cause, "
            "even if hedged ('most consistent with', 'likely')."
        ),
        false=(
            "The conclusion does not name this, names it only to rule it out, "
            "lists it only as something still to check, or says the cause is "
            "unknown."
        ),
    )


def target_question(fault: str, machines: Sequence[str], batches: Sequence[int]):
    """Which mentioned id the conclusion blames for `fault`; None if none mentioned."""
    # Variables:
    #   machines: Machine ids the conclusion mentions.
    #   batches: Batch numbers the conclusion mentions.
    #   options: The ids the model may pick from, plus 'none' for no id named.
    #   subject: Whether the question is about a machine or a material batch.
    if fault == "bad_material_batch":
        if not batches:
            return None
        options = {f"batch {n}": None for n in batches}
        subject = "material batch"
    else:
        if not machines:
            return None
        options = {m: None for m in machines}
        subject = "machine"
    options[NONE] = f"the conclusion names no {subject} for this cause"
    return Choice(
        instructions=(
            f"Suppose `conclusion` names this as a cause: {CAUSES[fault]}. "
            f"Which {subject} does it say this applies to?"
        ),
        options=options,
    )


class Proposal(BaseModel):
    """A label proposed by a model, with the numbers behind it. Evaluator-side."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: Label
    needs_review: bool
    # Why a person should read it; empty when the answers were clear.
    review_reasons: list[str] = Field(default_factory=list)
    # The probability that the conclusion names each fault kind.
    cause_probabilities: dict[str, float] = Field(default_factory=dict)
    # The id chosen for each named fault kind, and how confidently.
    targets: dict[str, str] = Field(default_factory=dict)
    target_confidence: dict[str, float] = Field(default_factory=dict)


def propose(run_key: str, conclusion: str, client: JudgmentClient) -> Proposal:
    """The label `client` proposes for one conclusion (one request at most).

    An undetermined conclusion names no cause by definition: it is labelled
    None without asking.
    """
    # Variables:
    #   run_key: Which run the conclusion came from.
    #   conclusion: The agent's free-text conclusion to be labelled.
    #   client: The judgment service that answers the typed questions.
    #   labelled_by: Who to credit with the label, for the label file.
    #   machines: Machine ids mentioned in the conclusion.
    #   batches: Batch numbers mentioned in the conclusion.
    #   questions: Every question for the service: one per fault kind, plus a target
    #     question where an id was mentioned.
    #   judgments: The service's typed answers.
    #   reasons: Why a person should read the proposal; empty if the answers were clear.
    #   probabilities: For each fault kind, how likely it is that the conclusion names
    #     it.
    #   targets: The machine or batch chosen for each named fault.
    #   confidence: How sure the service was of each chosen target.
    #   named: The causes the conclusion is judged to name.
    #   machine_id: The machine chosen for this fault, if any.
    #   batch_id: The batch chosen for this fault, if any.
    #   answer: The yes-or-no probability for one fault kind.
    #   target: The service's choice of machine or batch for one fault.
    #   diagnosis: None, one cause, or a list, as the label format needs.
    labelled_by = f"typesafe/{client.model}"
    if conclusion.strip().lower() == UNDETERMINED:
        return Proposal(
            label=Label(run_key=run_key, diagnosis=None, labelled_by=labelled_by),
            needs_review=False,
        )
    machines, batches = machines_in(conclusion), batches_in(conclusion)
    questions: dict = {f"cause/{f}": cause_question(f) for f in FAULT_KINDS}
    for fault in FAULT_KINDS:
        target = target_question(fault, machines, batches)
        if target is not None:
            questions[f"target/{fault}"] = target
    judgments = client.ask({"conclusion": conclusion}, questions)

    reasons: list[str] = []
    probabilities: dict[str, float] = {}
    targets: dict[str, str] = {}
    confidence: dict[str, float] = {}
    named: list[Diagnosis] = []
    for fault in FAULT_KINDS:
        answer = judgments.answers[f"cause/{fault}"]
        assert isinstance(answer, NoulAnswer)
        probabilities[fault] = answer.noul
        if NO < answer.noul < YES:
            reasons.append(f"unclear whether it names {fault} ({answer.noul:.2f})")
        if answer.noul < YES:
            continue
        machine_id = batch_id = None
        target = judgments.answers.get(f"target/{fault}")
        if isinstance(target, ChoiceAnswer):
            targets[fault] = target.choice
            confidence[fault] = target.confidence
            if target.confidence < TARGET_CONFIDENCE:
                reasons.append(
                    f"unsure which id {fault} is about ({target.confidence:.2f})"
                )
            if target.choice != NONE and fault == "bad_material_batch":
                batch_id = int(target.choice.removeprefix("batch "))
            elif target.choice != NONE:
                machine_id = target.choice
        named.append(Diagnosis(fault=fault, machine_id=machine_id, batch_id=batch_id))

    diagnosis: Diagnosis | list[Diagnosis] | None
    diagnosis = None if not named else named[0] if len(named) == 1 else named
    return Proposal(
        label=Label(
            run_key=run_key,
            diagnosis=diagnosis,
            labelled_by=f"typesafe/{judgments.model}",
        ),
        needs_review=bool(reasons),
        review_reasons=reasons,
        cause_probabilities=probabilities,
        targets=targets,
        target_confidence=confidence,
    )


def _causes(diagnosis: Diagnosis | list[Diagnosis] | None) -> frozenset:
    if diagnosis is None:
        return frozenset()
    items = diagnosis if isinstance(diagnosis, list) else [diagnosis]
    return frozenset((d.fault, d.machine_id, d.batch_id) for d in items)


class Agreement(BaseModel):
    """How the proposals compare with the hand labels for the same runs."""

    compared: int
    agreed: int
    # The runs where they differ: run_key -> (proposed, by hand), as text.
    disagreements: dict[str, tuple[str, str]]
    # Agreement among the proposals not marked for review.
    unreviewed_compared: int
    unreviewed_agreed: int


def _describe(diagnosis: Diagnosis | list[Diagnosis] | None) -> str:
    causes = sorted(_causes(diagnosis), key=str)
    if not causes:
        return "no cause"
    return "; ".join(
        f + (f" {m}" if m else "") + (f" batch {b}" if b is not None else "")
        for f, m, b in causes
    )


def agreement(proposals: Sequence[Proposal], hand: dict[str, Label]) -> Agreement:
    """Compare each proposal with the hand label of its run, where there is one.

    Two labels agree when they name the same causes with the same machine or
    batch; the summary text is ignored.
    """
    # Variables:
    #   proposals: The labels proposed by the model.
    #   hand: The labels written by a person, by run key.
    #   compared: How many runs have both a proposal and a hand label.
    #   agreed: How many of those name the same causes.
    #   unreviewed_compared: Compared runs whose proposal was not marked for review.
    #   unreviewed_agreed: How many of those agreed.
    #   disagreements: The runs where the two differ, as text.
    #   key: The run being compared.
    #   same: True if both name the same causes with the same machine or batch.
    compared = agreed = unreviewed_compared = unreviewed_agreed = 0
    disagreements: dict[str, tuple[str, str]] = {}
    for proposal in proposals:
        key = proposal.label.run_key
        if key not in hand:
            continue
        same = _causes(proposal.label.diagnosis) == _causes(hand[key].diagnosis)
        compared += 1
        agreed += same
        if not proposal.needs_review:
            unreviewed_compared += 1
            unreviewed_agreed += same
        if not same:
            disagreements[key] = (
                _describe(proposal.label.diagnosis),
                _describe(hand[key].diagnosis),
            )
    return Agreement(
        compared=compared,
        agreed=agreed,
        disagreements=disagreements,
        unreviewed_compared=unreviewed_compared,
        unreviewed_agreed=unreviewed_agreed,
    )


def conclusions(paths: Sequence[Path]) -> dict[str, str]:
    """run_key -> conclusion, from experiment results files. The latest row wins.

    Reads only these two fields, so the score (which holds the truth) is
    never looked at.
    """
    # Variables:
    #   paths: Experiment result files to read.
    #   found: Each run's conclusion; a later row replaces an earlier one.
    found: dict[str, str] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                if row.get("conclusion"):
                    found[row["run_key"]] = row["conclusion"]
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m capstone.evaluation.auto_label",
        description="Propose diagnosis labels with TypeSafe's Jev and compare "
        "them with hand labels. Needs TYPESAFE_API_KEY.",
    )
    parser.add_argument("results", nargs="+", type=Path, help="experiment results")
    parser.add_argument("--out", type=Path, required=True, help="proposals file")
    parser.add_argument("--hand", type=Path, help="hand labels to compare with")
    args = parser.parse_args(argv)

    client = judgment_client(get_settings())
    proposals = []
    with args.out.open("a", encoding="utf-8", newline="\n") as out:
        for run_key, conclusion in conclusions(args.results).items():
            proposal = propose(run_key, conclusion, client)
            proposals.append(proposal)
            out.write(proposal.model_dump_json() + "\n")
            flag = "  REVIEW: " + "; ".join(proposal.review_reasons)
            print(
                f"{run_key}: {_describe(proposal.label.diagnosis)}"
                + (flag if proposal.needs_review else "")
            )
    print(f"{len(proposals)} proposals written to {args.out}")
    if args.hand is not None:
        result = agreement(proposals, LabelBook(args.hand).read())
        print(
            f"agree with hand labels: {result.agreed} of {result.compared} "
            f"({result.unreviewed_agreed} of {result.unreviewed_compared} "
            "among those not marked for review)"
        )
        for key, (proposed, by_hand) in result.disagreements.items():
            print(f"  {key}: proposed {proposed!r}, by hand {by_hand!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
