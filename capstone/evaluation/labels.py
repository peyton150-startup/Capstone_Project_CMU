# Hand labels for the agent's free-text diagnoses, kept in a file.
# Responsibility: store who said which cause a conclusion names, and apply it.
"""The agent concludes in words; a person decides which cause those words name.

Decided 2026-10-12: root causes are scored from hand labels first. A label
is written once per run, in an append-only JSON-lines file kept apart from
the agent. `apply_label` turns a label into the root-cause columns of a
`Score` using only the truth already in that row, so a run can be scored
long after it ended, without its simulator.

A label of `diagnosis=None` means the conclusion names no recognisable
cause; that counts as wrong, not as unjudged.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from capstone.evaluation.scoring import Score
from capstone.tools.diagnosis import Diagnosis


class Label(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_key: str = Field(min_length=1)
    diagnosis: Diagnosis | None
    labelled_by: str = Field(min_length=1)
    note: str = ""


class LabelBook:
    """An append-only file of labels. The latest label for a run wins."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def add(self, label: Label) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(label.model_dump_json() + "\n")

    def read(self) -> dict[str, Label]:
        if not self.path.exists():
            return {}
        labels = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line:
                label = Label.model_validate_json(line)
                labels[label.run_key] = label
        return labels


def apply_label(score: Score, diagnosis: Diagnosis | None) -> Score:
    """The same row with its root cause judged from `diagnosis`."""
    if diagnosis is None:
        update = {
            "diagnosed_fault": None,
            "diagnosed_machine_id": None,
            "diagnosed_batch_id": None,
            "fault_correct": False,
            "target_correct": False,
        }
        return score.model_copy(update=update)
    if score.true_fault == "bad_material_batch":
        target_correct = diagnosis.batch_id == score.true_batch_id
    else:
        target_correct = diagnosis.machine_id == score.true_machine_id
    return score.model_copy(
        update={
            "diagnosed_fault": diagnosis.fault,
            "diagnosed_machine_id": diagnosis.machine_id,
            "diagnosed_batch_id": diagnosis.batch_id,
            "fault_correct": diagnosis.fault == score.true_fault,
            "target_correct": target_correct,
        }
    )
