from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

FaultKind = Literal[
    "bearing_degradation", "bad_material_batch", "wrong_setting", "false_alarm"
]
# The kinds of cause an agent can name. "false_alarm" means: nothing is wrong, no action needed.
FAULT_KINDS: tuple[str, ...] = get_args(FaultKind)


class Diagnosis(BaseModel):
    """The agent's final answer, handed back across the tool boundary.

    Its belief, not the truth: evaluation compares it with the ground
    truth afterwards. A fault is about a machine or, for a bad batch, a
    material batch.
    """

    model_config = ConfigDict(frozen=True)

    fault: FaultKind
    machine_id: str | None = None
    batch_id: int | None = None
    summary: str = ""
