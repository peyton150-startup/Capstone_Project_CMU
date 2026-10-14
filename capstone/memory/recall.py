# Finds the memories that match a description, and shows them safely.
# Responsibility: word-overlap search and the view a later investigation may see.
"""Recall by shared words. No embeddings and no model.

A memory matches when the query shares words with its category, symptoms,
action, machine or lesson. More shared words rank first; equal scores put
the most recent first, then the memory ID, so a query always returns the
same list. Words differently spelled ("shaking" for "vibration") do not
match: that is the known limit of this search.
"""

from collections.abc import Iterable

from capstone.memory.contracts import EpisodicMemory, RecalledMemory
from capstone.memory.policy import normalize

# Words that would match nearly every memory, including the fixed failure sentence.
FILLER = frozenset(
    "a an and are as at be by for from in is it of on or the to was were with".split()
)


def words(text: str) -> set[str]:
    """The searchable words of a text. Tool names split: replace_bearing -> two."""
    return set(normalize(text).replace("_", " ").split()) - FILLER


def recalled(memory: EpisodicMemory) -> RecalledMemory:
    """The view of one memory that is safe to hand to another investigation."""
    action = memory.intervention
    return RecalledMemory(
        memory_id=memory.memory_id,
        category=memory.category,
        symptoms=memory.symptoms,
        diagnosis=memory.diagnosis,
        action=action.action if action else None,
        machine_id=action.machine_id if action else None,
        outcome=memory.outcome,
        lesson=memory.lesson,
        source_tick=memory.source_tick,
    )


def search_memories(
    memories: Iterable[EpisodicMemory], text: str, *, limit: int = 5
) -> tuple[RecalledMemory, ...]:
    """The best matches for `text`, as safe views. Nothing matches no shared word."""
    if limit < 1:
        raise ValueError("limit must be at least one")
    wanted = words(text)
    scored = []
    for memory in memories:
        view = recalled(memory)
        searchable = " ".join(
            (
                view.category,
                *view.symptoms,
                view.action or "",
                view.machine_id or "",
                view.lesson,
            )
        )
        score = len(wanted & words(searchable))
        if score:
            scored.append((-score, -view.source_tick, str(view.memory_id), view))
    scored.sort(key=lambda entry: entry[:3])
    return tuple(view for *_, view in scored[:limit])
