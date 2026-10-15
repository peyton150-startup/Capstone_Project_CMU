import json

import pytest

from capstone.agent.artifacts import VerificationCheck
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.contracts.tools import ToolRequest
from capstone.learning import learn_from
from capstone.memory.contracts import ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy
from capstone.memory.service import MemoryService
from capstone.providers.recall import RECALL_TOOL, RecallingProvider
from tests.helpers import ask, new_state
from tests.test_agent_verification import (
    Factory,
    compare_with_before,
    investigate,
    look_again,
    policy,
)
from tests.test_learning import log, memory, writer  # noqa: F401  (fixtures)
from tests.test_memory_policy import candidate_data
from tests.test_memory_recall import SUCCESS, ListStore

RECALL = ask(RECALL_TOOL, text="vibration alarm CNC-02 bearing")


def recaller(*memories, factory=None):
    factory = factory or Factory()
    service = MemoryService(ListStore(*(memories or (SUCCESS,))))
    return RecallingProvider(factory.provider, service), factory


def with_recall(agent, phase, position=None):
    """The same scripted agent, with one recall added to a phase."""
    queue = agent.decisions[phase]
    queue.insert(len(queue) if position is None else position, RECALL)
    return agent


def recalled_items(state):
    return [e for e in state.evidence if e.source_id == f"memory:{RECALL_TOOL}"]


def origins(state):
    return {p.evidence_id: p.origin for p in state.provenance}


# --- the tool ------------------------------------------------------------------


def test_recall_is_answered_from_memory_at_the_factorys_current_tick():
    provider, factory = recaller()
    result = provider.call(RECALL.request)
    assert result.success and result.source == "memory"
    assert result.tool == RECALL_TOOL
    assert result.tick == factory.sim.clock.tick
    [view] = result.data
    assert view["memory_id"] == str(SUCCESS.memory_id)
    assert view["outcome"] == "resolved"
    assert "evidence_ids" not in view


def test_every_other_tool_goes_to_the_factory_unchanged():
    provider, factory = recaller()
    request = ToolRequest(name="list_machines", arguments={})
    assert provider.call(request) == factory.provider.call(request)


@pytest.mark.parametrize(
    "arguments",
    [
        {"text": ""},
        {"text": "bearing", "limit": 0},
        {"text": "bearing", "limit": 11},
        {"text": "bearing", "machine_id": "CNC-02"},
        {},
    ],
)
def test_bad_recall_arguments_are_refused(arguments):
    provider, _ = recaller()
    result = provider.call(ToolRequest(name=RECALL_TOOL, arguments=arguments))
    assert not result.success
    assert result.error.code == "invalid_arguments"


def test_a_failing_memory_store_says_nothing_about_why():
    class Broken:
        def search(self, text, *, limit):
            raise RuntimeError("postgres://user:secret@host")

    factory = Factory()
    result = RecallingProvider(factory.provider, Broken()).call(RECALL.request)
    assert not result.success
    assert result.error.code == "provider_error"
    assert "secret" not in result.model_dump_json()


def test_nothing_found_is_an_empty_answer_not_an_error():
    provider, _ = recaller()
    result = provider.call(ToolRequest(name=RECALL_TOOL, arguments={"text": "jam"}))
    assert result.success and result.data == []


# --- the label -------------------------------------------------------------------


def test_recalled_evidence_is_labelled_memory_and_the_rest_observable():
    provider, factory = recaller()
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=provider,
        policy=with_recall(policy(), "investigate"),
        clock=lambda: 0.0,
        human_review=factory.approve,
    )
    state = run_investigation(state, deps)
    [item] = recalled_items(state)
    labels = origins(state)
    assert labels.pop(item.id) == "memory"
    assert set(labels.values()) == {"observable"}
    assert json.loads(item.content)[0]["lesson"] == SUCCESS.lesson


# --- guard 1: a memory is never a look at the factory -----------------------------


def run_with(agent):
    provider, factory = recaller()
    factory.provider = provider
    return investigate(agent, factory=factory)[0]


def cite_last_recall(state):
    [item] = recalled_items(state)
    return VerificationCheck(
        outcome="resolved", prediction="x", evidence_ids=(item.id,)
    )


def test_a_fix_cannot_be_verified_by_citing_a_memory():
    agent = policy(verify=(ask("wait", ticks=300), RECALL), judge=cite_last_recall)
    state = run_with(agent)
    [item] = recalled_items(state)
    assert item.observed_tick > state.action_finish_tick  # dated after the work
    assert state.verification.outcome == "inconclusive"


def test_a_real_look_still_verifies_when_a_memory_is_also_cited():
    def both(state):
        check = compare_with_before(state)
        [item] = recalled_items(state)
        return check.model_copy(update={"evidence_ids": (*check.evidence_ids, item.id)})

    agent = policy(verify=(ask("wait", ticks=300), RECALL, look_again), judge=both)
    state = run_with(agent)
    assert state.verification.outcome == "resolved"


# --- guard 2: a new lesson cannot rest on a memory --------------------------------


def with_memory_item(cited):
    data = candidate_data()
    data["investigation"]["evidence"].append(
        {
            "id": "recalled",
            "source_id": f"memory:{RECALL_TOOL}",
            "source_type": "tool_result",
            "content": "[a recalled memory]",
            "observed_tick": 120,
        }
    )
    data["provenance"].append(
        {
            "evidence_id": "recalled",
            "source_id": f"memory:{RECALL_TOOL}",
            "source_type": "tool_result",
            "origin": "memory",
            "observed_tick": 120,
        }
    )
    if cited:
        data["investigation"]["conclusion"]["evidence_ids"].append("recalled")
    return ReflectionCandidate.model_validate(data)


def test_the_gate_refuses_a_lesson_that_cites_a_memory():
    decision = MemoryPromotionPolicy().evaluate(with_memory_item(cited=True))
    assert not decision.accepted
    assert "rests_on_memory" in decision.reasons


def test_a_memory_that_only_guided_where_to_look_is_allowed():
    decision = MemoryPromotionPolicy().evaluate(with_memory_item(cited=False))
    assert decision.accepted, decision.reasons


def test_end_to_end_a_conclusion_citing_a_memory_is_not_remembered(memory, log):  # noqa: F811
    agent = policy()
    agent.decisions["investigate"].append(RECALL)  # becomes E3, cited below
    state = run_with(agent)
    assert origins(state)["E3"] == "memory"
    assert "E3" in state.conclusion.evidence_ids
    outcome = learn_from(state, writer(), memory, log)
    assert state.verification.outcome == "resolved"
    assert not outcome.decision.accepted
    assert "rests_on_memory" in outcome.decision.reasons
