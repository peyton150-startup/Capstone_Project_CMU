import ast
from pathlib import Path
from uuid import UUID

import pytest

import capstone

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine

from capstone.agent.completion import AuditLog, complete
from capstone.agent.policy import Lesson
from capstone.learning import LearningOutcome, learn_from
from capstone.memory.contracts import MemoryQuery
from capstone.memory.policy import failure_lesson
from capstone.memory.repository import SQLMemoryRepository
from capstone.memory.schema import metadata
from capstone.memory.service import MemoryService
from tests.helpers import ScriptedPolicy, new_state
from tests.test_agent_verification import investigate, policy

ADVICE = "When vibration climbs steadily on one machine, replace its bearing."
AGENT = Path(capstone.__file__).parent / "agent"


@pytest.fixture
def memory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'memories.sqlite'}")
    metadata.create_all(engine)
    yield MemoryService(SQLMemoryRepository(engine))
    engine.dispose()


@pytest.fixture
def log(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


def run(number, agent=None, human="approve"):
    """One investigation through the real simulator, with its own ID."""
    state = new_state()
    state.investigation_id = UUID(int=100 + number)
    return investigate(agent or policy(), human, state=state)[0]


def writer(lesson=ADVICE):
    return ScriptedPolicy(lesson=lambda state: lesson and Lesson(text=lesson))


# --- end to end: investigation -> audit -> gate -> memory -------------------


def test_a_verified_fix_is_audited_and_its_advice_remembered(memory, log):
    state = run(1)
    model = writer()
    outcome = learn_from(state, model, memory, log)
    assert isinstance(outcome, LearningOutcome)
    assert outcome.lesson_requested and model.asked == ["lesson"]
    assert outcome.lesson == ADVICE
    assert outcome.decision.stored
    [kept] = memory.retrieve(MemoryQuery(category="alarm"))
    assert (kept.outcome, kept.lesson) == ("resolved", ADVICE)
    assert kept.investigation_id == state.investigation_id
    [line] = log.read()
    assert line.completed == complete(state)


def test_a_failed_fix_is_remembered_in_codes_words_without_asking(memory, log):
    state = run(2, policy(machine_id="CNC-01"))
    model = writer("The diagnosis was wrong.")
    outcome = learn_from(state, model, memory, log)
    assert not outcome.lesson_requested and model.asked == []
    assert outcome.decision.stored
    [kept] = memory.retrieve(MemoryQuery(category="alarm"))
    assert kept.outcome == "unresolved"
    assert kept.lesson == failure_lesson(complete(state))
    assert len(log.read()) == 1


def test_a_success_and_a_failure_live_side_by_side(memory, log):
    learn_from(run(1), writer(), memory, log)
    learn_from(run(2, policy(machine_id="CNC-01")), writer(), memory, log)
    kept = memory.retrieve(MemoryQuery(category="alarm"))
    assert sorted(m.outcome for m in kept) == ["resolved", "unresolved"]
    assert len(log.read()) == 2


def test_a_rejected_proposal_is_audited_but_not_remembered(memory, log):
    state = run(3, human="reject")
    model = writer()
    outcome = learn_from(state, model, memory, log)
    assert (outcome.lesson_requested, outcome.decision) == (False, None)
    assert model.asked == []
    assert memory.retrieve(MemoryQuery(category="alarm")) == ()
    assert len(log.read()) == 1


def test_the_same_investigation_is_remembered_once(memory, log):
    state = run(1)
    learn_from(state, writer(), memory, log)
    again = learn_from(state, writer(), memory, log)
    assert not again.decision.stored
    assert again.decision.reasons == ("duplicate_investigation",)
    assert len(memory.retrieve(MemoryQuery(category="alarm"))) == 1
    assert len(log.read()) == 2  # the log keeps every call


# --- the model may decline or fail; the record never depends on it ----------


def test_a_model_that_declines_leaves_no_memory(memory, log):
    outcome = learn_from(run(1), writer(None), memory, log)
    assert outcome.lesson_requested
    assert (outcome.lesson, outcome.decision) == (None, None)
    assert len(log.read()) == 1


def test_a_model_that_fails_leaves_no_memory(memory, log):
    def broken(state):
        raise RuntimeError("model unavailable")

    outcome = learn_from(run(1), ScriptedPolicy(lesson=broken), memory, log)
    assert outcome.lesson_requested
    assert (outcome.lesson, outcome.decision) == (None, None)
    assert len(log.read()) == 1


def test_the_audit_line_is_written_before_memory_is_tried(log):
    class DatabaseDown:
        def promote(self, candidate):
            raise ConnectionError("database unavailable")

    with pytest.raises(ConnectionError):
        learn_from(run(1), writer(), DatabaseDown(), log)
    assert len(log.read()) == 1


def test_an_unfinished_investigation_is_refused_and_nothing_written(memory, log):
    with pytest.raises(ValueError):
        learn_from(new_state(), writer(), memory, log)
    assert log.read() == ()


def test_learning_does_not_change_working_memory(memory, log):
    state = run(1)
    before = state.model_dump()
    learn_from(state, writer(), memory, log)
    assert state.model_dump() == before


def test_the_agent_package_does_not_reach_learning_or_memory():
    for path in AGENT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else []
            )
            assert not any(
                n.startswith(("capstone.learning", "capstone.memory")) for n in names
            ), path
