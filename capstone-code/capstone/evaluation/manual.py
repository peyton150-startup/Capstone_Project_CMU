# What a run looked up in the machine manual, rebuilt from its own records.
# Responsibility: one record per search_manual call, for the experimenter.
"""The manual searches of a finished investigation.

    records = build_manual_records(state)

Built after the run from the loop's decision records and evidence, like
recall's search records (`evaluation/memory.py`): what was asked, whether it
was answered, refused or failed, and which sections came back. Nothing from
the hidden truth. With them an experiment can say whether the agent looked
in the manual at all, how often, and which sections it was given; comparing
runs with and without `--manual` says whether that helped.
"""

import json

from pydantic import Field

from capstone.contracts import Contract
from capstone.evaluation.memory import SearchOutcome
from capstone.providers.manual import MANUAL_TOOL, REPEATED_SEARCH, SEARCHES_SPENT


class ManualSearchRecord(Contract):
    """One manual search an investigation made."""

    sequence: int = Field(ge=1)  # the decision record's number
    text: str | None = None  # None when the arguments were not usable
    outcome: SearchOutcome
    evidence_id: str | None = None
    sections: tuple[str, ...] = ()  # "§2.7", best match first
    # True: the manual step's search, made by the loop before planning; False:
    # one the agent chose. Older records read as False.
    automatic: bool = False


def build_manual_records(state) -> tuple[ManualSearchRecord, ...]:
    """One record per search_manual call, in order (see build_search_records)."""
    # Variables:
    #   state: The finished investigation state, read for its decision records.
    #   contents: The text of each piece of evidence, by id.
    #   records: One record per manual search, in order.
    #   text: What was searched for; None if the arguments were unusable.
    #   message: The tool's error message, if the call failed or was refused.
    #   evidence_id: The evidence that holds the answer, if there was one.
    #   sections: The manual sections returned, best match first.
    #   outcome: answered, repeated, budget_spent or failed.
    contents = {e.id: e.content for e in state.evidence}
    records = []
    for decision in state.decisions:
        if decision.tool != MANUAL_TOOL:
            continue
        text = decision.arguments.get("text")
        message = decision.error.message if decision.error is not None else None
        evidence_id, sections = None, ()
        if decision.outcome == "repeated_call" or message == REPEATED_SEARCH:
            outcome = "repeated"
        elif message == SEARCHES_SPENT:
            outcome = "budget_spent"
        elif decision.evidence_ids:
            outcome = "answered"
            [evidence_id] = decision.evidence_ids
            sections = tuple(
                item["section"] for item in json.loads(contents[evidence_id]) or ()
            )
        else:
            outcome = "failed"
        records.append(
            ManualSearchRecord(
                sequence=decision.sequence,
                text=text if isinstance(text, str) else None,
                outcome=outcome,
                evidence_id=evidence_id,
                sections=sections,
                # Only the manual step searches during observe.
                automatic=decision.phase == "observe",
            )
        )
    return tuple(records)
