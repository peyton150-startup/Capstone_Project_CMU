from uuid import UUID

import pytest
from pydantic import ValidationError

from capstone.memory.contracts import (
    EpisodicMemory,
    MemoryQuery,
    RecalledMemory,
    ReflectionCandidate,
)
from capstone.memory.policy import MemoryPromotionPolicy
from capstone.memory.recall import recalled, search_memories, words
from capstone.memory.service import MemoryService
from tests.test_memory_policy import candidate_data, failure_data


def memory(data=None, *, number=2, tick=200, category="bearing", lesson=None):
    """An accepted memory, varied by investigation, check tick, category, lesson."""
    data = data or candidate_data()
    data["investigation"]["investigation_id"] = str(UUID(int=number))
    data["investigation"]["verification"]["observed_tick"] = tick
    for label in data["provenance"]:
        if label["evidence_id"] == "after":
            label["observed_tick"] = tick
    for item in data["investigation"]["evidence"]:
        if item["id"] == "after":
            item["observed_tick"] = tick
    data["category"] = category
    if lesson:
        data["lesson"]["text"] = lesson
    decision = MemoryPromotionPolicy().evaluate(
        ReflectionCandidate.model_validate(data)
    )
    assert decision.accepted, decision.reasons
    return decision.memory


SUCCESS = memory()
FAILURE = memory(failure_data(), number=3, tick=300)


class ListStore:
    """Holds memories in a list; enough to stand in for the SQL store."""

    def __init__(self, *memories: EpisodicMemory):
        self.memories = list(memories)
        self.queries: list[MemoryQuery] = []

    def insert(self, memory):
        raise NotImplementedError

    def retrieve(self, query):
        self.queries.append(query)
        return tuple(self.memories[: query.limit])


# --- the safe view ------------------------------------------------------------


def test_the_view_keeps_what_means_the_same_in_any_investigation():
    view = recalled(SUCCESS)
    assert isinstance(view, RecalledMemory)
    assert view.model_dump() == {
        "memory_id": SUCCESS.memory_id,
        "category": "bearing",
        "symptoms": ("rising vibration", "increasing temperature"),
        "diagnosis": "bearing degradation",
        "action": "replace_bearing",
        "machine_id": "CNC-02",
        "outcome": "resolved",
        "lesson": SUCCESS.lesson,
        "source_tick": 200,
    }


def test_the_view_carries_no_evidence_ids_or_provenance():
    text = recalled(SUCCESS).model_dump_json()
    for evidence_id in ("trend", "repair", "after"):
        assert f'"{evidence_id}"' not in text
    for field in ("evidence_ids", "provenance", "confidence", "fingerprint"):
        assert field not in text
    assert str(SUCCESS.investigation_id) not in text
    assert str(SUCCESS.run_id) not in text


def test_a_memory_with_no_action_has_none_to_show():
    """A stored memory without an action (one admitted before episodic-v3,
    which refuses them) still has a view. Built directly, since the gate no
    longer makes one."""
    stored = memory(number=4).model_copy(update={"intervention": None})
    view = recalled(stored)
    assert (view.action, view.machine_id) == (None, None)


# --- word search ---------------------------------------------------------------


def test_words_drop_filler_and_split_tool_names():
    assert words("The replace_bearing was tried for CNC-02") == {
        "replace",
        "bearing",
        "tried",
        "cnc",
        "02",
    }


def test_more_shared_words_rank_first():
    found = search_memories((FAILURE, SUCCESS), "rising vibration bearing compare")
    assert [m.memory_id for m in found] == [SUCCESS.memory_id, FAILURE.memory_id]


def test_no_shared_word_means_not_found():
    assert search_memories((SUCCESS, FAILURE), "conveyor jam") == ()
    assert search_memories((SUCCESS, FAILURE), "the was for and") == ()


def test_equal_scores_put_the_most_recent_first_and_repeat_exactly():
    older = memory(number=5, tick=100, lesson="Check bearing wear early.")
    newer = memory(number=6, tick=400, lesson="Check bearing wear late.")
    found = search_memories((older, newer), "bearing")
    assert [m.source_tick for m in found] == [400, 100]
    assert found == search_memories((newer, older), "bearing")


def test_the_limit_is_respected():
    many = [
        memory(number=10 + n, tick=n, lesson=f"Bearing lesson {chr(97 + n)}.")
        for n in range(4)
    ]
    assert len(search_memories(many, "bearing", limit=2)) == 2
    with pytest.raises(ValueError):
        search_memories(many, "bearing", limit=0)


def test_the_view_type_cannot_carry_anything_extra():
    with pytest.raises(ValidationError):
        RecalledMemory.model_validate(
            {**recalled(SUCCESS).model_dump(), "evidence_ids": ["E2"]}
        )


# --- through the service --------------------------------------------------------


def test_the_service_searches_what_the_store_holds():
    store = ListStore(SUCCESS, FAILURE)
    found = MemoryService(store).search("replace bearing CNC-02 unresolved")
    assert [m.memory_id for m in found] == [FAILURE.memory_id, SUCCESS.memory_id]
    assert all(isinstance(m, RecalledMemory) for m in found)
    assert store.queries == [MemoryQuery(limit=100)]
