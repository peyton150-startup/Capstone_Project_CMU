import json

import pytest

from capstone.agent.artifacts import VerificationCheck
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.contracts.tools import ToolRequest
from capstone.evaluation.memory import build_search_records
from capstone.learning import learn_from
from capstone.memory.contracts import ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy
from capstone.memory.service import MemoryService
from capstone.providers.recall import (
    MAX_SEARCHES,
    RECALL_SPEC,
    RECALL_TOOL,
    REPEATED_SEARCH,
    SEARCHES_SPENT,
    RecallingProvider,
)
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


# --- bounded searches (Future Work 1: repeat retrieval) ----------------------------


class Counting:
    """A store that counts the searches that reach it."""

    def __init__(self, service):
        self.service, self.searches = service, []

    def search(self, text, *, limit):
        self.searches.append(text)
        return self.service.search(text, limit=limit)


def counting_recaller(**options):
    factory = Factory()
    store = Counting(MemoryService(ListStore(SUCCESS)))
    return RecallingProvider(factory.provider, store, **options), store


def search(provider, text, **arguments):
    request = ToolRequest(name=RECALL_TOOL, arguments={"text": text, **arguments})
    return provider.call(request)


def test_the_same_search_twice_is_refused_and_never_reaches_the_store():
    provider, store = counting_recaller()
    assert search(provider, "Vibration alarm, CNC-02").success
    again = search(provider, "vibration   ALARM cnc 02")  # same words after normalize
    assert not again.success and again.error.code == "invalid_arguments"
    assert again.error.message == REPEATED_SEARCH
    assert store.searches == ["Vibration alarm, CNC-02"]


def test_the_same_words_with_a_different_limit_is_a_new_search():
    provider, store = counting_recaller()
    assert search(provider, "bearing").success
    assert search(provider, "bearing", limit=2).success
    assert len(store.searches) == 2


def test_only_max_searches_are_answered():
    provider, store = counting_recaller()
    assert MAX_SEARCHES == 3
    for text in ("bearing", "vibration", "spindle"):
        assert search(provider, text).success
    late = search(provider, "temperature")
    assert not late.success and late.error.message == SEARCHES_SPENT
    assert len(store.searches) == 3
    one, _ = counting_recaller(max_searches=1)
    assert search(one, "bearing").success and not search(one, "vibration").success
    with pytest.raises(ValueError):
        counting_recaller(max_searches=0)


def test_a_failed_search_does_not_spend_the_budget():
    class Flaky:
        def __init__(self):
            self.calls = 0

        def search(self, text, *, limit):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("down")
            return ()

    provider = RecallingProvider(Factory().provider, Flaky(), max_searches=1)
    assert search(provider, "bearing").error.code == "provider_error"
    assert search(provider, "bearing").success  # the same words, now answered


def test_the_tool_description_states_the_limits():
    assert f"At most {MAX_SEARCHES} searches" in RECALL_SPEC.description
    assert "refused" in RECALL_SPEC.description


def test_an_investigation_sees_the_refusal_and_its_searches_are_recorded():
    """A repeat at a later tick (after a wait) is still a repeat; the refusal
    reaches the next prompt; the search records say what each search got."""
    provider, factory = recaller()
    agent = policy()
    queue = agent.decisions["investigate"]
    queue[:0] = [
        RECALL,
        ask("wait", ticks=5),
        RECALL,  # same words at a later tick
        ask(RECALL_TOOL, text="spindle"),
        ask(RECALL_TOOL, text="temperature"),
        ask(RECALL_TOOL, text="load"),  # a fourth answered search: over budget
    ]
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=provider,
        policy=agent,
        clock=lambda: 0.0,
        human_review=factory.approve,
    )
    state = run_investigation(state, deps)
    records = build_search_records(state)
    assert [r.outcome for r in records] == [
        "answered",
        "repeated",
        "answered",
        "answered",
        "budget_spent",
    ]
    assert records[0].memory_ids == (SUCCESS.memory_id,)
    assert records[0].evidence_id is not None and records[1].evidence_id is None
    assert records[1].text == RECALL.request.arguments["text"]
    refused = [d for d in state.decisions if d.tool == RECALL_TOOL and d.error]
    assert [d.error.message for d in refused] == [REPEATED_SEARCH, SEARCHES_SPENT]
    assert REPEATED_SEARCH in render_with_failures(refused[:1])


def render_with_failures(decisions):
    from capstone.agent.model_policy import render

    state = new_state()
    state.decisions = list(decisions)
    return render(state)


def test_a_loop_level_repeat_is_recorded_as_repeated():
    provider, factory = recaller()
    agent = policy()
    agent.decisions["investigate"][:0] = [RECALL, RECALL]  # same tick: loop skips
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=provider,
        policy=agent,
        clock=lambda: 0.0,
        human_review=factory.approve,
    )
    state = run_investigation(state, deps)
    assert [r.outcome for r in build_search_records(state)][:2] == [
        "answered",
        "repeated",
    ]
