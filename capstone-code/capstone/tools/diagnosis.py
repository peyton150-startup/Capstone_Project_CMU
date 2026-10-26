from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

from capstone.faults import FAULT_KINDS as _PACK_KINDS

# The kinds of cause an agent can name, from the fault packs' agent side
# (`capstone/faults.py`). "false_alarm" means: nothing is wrong, no action needed.
FaultKind = Literal[_PACK_KINDS]
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
