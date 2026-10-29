"""The machine manual and the search_manual tool, offline."""

import json
import re

import pytest

from capstone.agent.artifacts import VerificationCheck
from capstone.agent.investigation import manual_query, run_investigation
from capstone.agent.loop import InvestigationDeps
from capstone.agent.model_policy import render
from capstone.contracts.tools import ToolRequest
from capstone.evaluation.manual import build_manual_records
from capstone.manual.index import ChromaManualIndex, KeywordManualSearch
from capstone.manual.sections import (
    ManualSection,
    check_no_leaks,
    load_manual,
    parse_manual,
)
from capstone.memory.contracts import ReflectionCandidate
from capstone.memory.policy import MemoryPromotionPolicy, normalize
from capstone.providers.manual import (
    MANUAL_SPEC,
    MANUAL_TOOL,
    MAX_SEARCHES,
    REPEATED_SEARCH,
    SEARCHES_SPENT,
    ManualProvider,
)
from capstone.simulator.line import STANDARD_SPEEDS, STANDARD_TICKS_PER_JOB
from tests.helpers import ask, new_state
from tests.test_agent_verification import (
    Factory,
    compare_with_before,
    investigate,
    look_again,
    policy,
)
from tests.test_memory_policy import candidate_data

SECTIONS = load_manual()
LOOKUP = ask(MANUAL_TOOL, text="vibration spike alarm")


def manual_provider(factory=None, search=None):
    factory = factory or Factory()
    return ManualProvider(
        factory.provider, search or KeywordManualSearch(SECTIONS)
    ), factory


def manual_items(state):
    return [e for e in state.evidence if e.source_id == f"manual:{MANUAL_TOOL}"]


# --- the manual itself ------------------------------------------------------------


def test_the_manual_is_its_fifteen_numbered_sections_and_nothing_else():
    assert [s.section_id for s in SECTIONS] == [
        "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",
        "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13",
    ]  # fmt: skip
    speed = next(s for s in SECTIONS if s.section_id == "2.7")
    assert speed.title == "Spindle Speed Configuration and Machining Effects"
    assert speed.citation == "SIM-CNC-001 §2.7" and speed.revision == "1.1"
    text = " ".join(s.text for s in SECTIONS)
    assert "Document Provenance" not in text and "How to Use" not in text
    assert "**" not in text


def test_no_section_gives_a_stations_standard_speed_or_job_time():
    """The developer's choice "B": a wrong setting is found from its effects."""
    for section in SECTIONS:
        numbers = {
            float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", section.text)
        }
        assert not numbers & set(STANDARD_SPEEDS), section.section_id
        times = {int(t) for t in STANDARD_TICKS_PER_JOB}
        assert not numbers & times - {45, 10}, section.section_id  # repair durations


@pytest.mark.parametrize(
    "leak",
    ["bearing_degradation", "a wrong_setting case", "seed 42", "KA-03", "ground truth"],
)
def test_a_section_that_names_hidden_truth_is_refused(leak):
    sections = parse_manual(f"**Revision:** 9\n## §9.1 Bad\nThe answer is {leak}.\n")
    with pytest.raises(ValueError, match="§9.1"):
        check_no_leaks(sections)


# --- searching it -----------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected",
    [
        ("vibration spike alarm", "2.1"),
        ("bearing wear replacement", "2.2"),
        ("spindle speed setting wrong", "2.7"),
        ("inspection rejects by material batch", "2.9"),
        ("sensor false alarm dropout", "2.11"),
    ],
)
def test_a_symptom_finds_its_section_in_the_top_three(query, expected):
    found = KeywordManualSearch(SECTIONS).search(query, limit=3)
    assert expected in [s.section_id for s in found]


def test_words_the_manual_never_uses_find_nothing():
    assert KeywordManualSearch(SECTIONS).search("zzz qqq", limit=3) == ()


def test_the_chroma_index_returns_only_sections_the_manual_has():
    chromadb = pytest.importorskip("chromadb")
    from tests.test_memory_semantic import fake_embed

    collection = chromadb.EphemeralClient().create_collection(
        "manual_test",
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
    )
    index = ChromaManualIndex(collection, SECTIONS, fake_embed)
    assert index.build() == 15
    found = index.search("speed setting configuration", limit=3)
    assert len(found) == 3 and all(isinstance(s, ManualSection) for s in found)
    # An index built before a section was removed cannot hand it back.
    shorter = ChromaManualIndex(collection, SECTIONS[:2], fake_embed)
    assert {s.section_id for s in shorter.search("vibration", limit=15)} <= {
        "1.1",
        "1.2",
    }


# --- the tool ---------------------------------------------------------------------


def test_a_search_is_answered_from_the_manual_with_section_numbers():
    provider, factory = manual_provider()
    result = provider.call(LOOKUP.request)
    assert result.success and result.source == "manual" and result.tool == MANUAL_TOOL
    assert result.tick == factory.sim.clock.tick
    first = result.data[0]
    assert first["section"] == "§2.1" and first["document"] == "SIM-CNC-001 rev 1.1"
    assert set(first) == {"section", "title", "text", "document"}
    assert len(result.data) == 3  # the default limit


def test_every_other_tool_goes_to_the_inner_provider_unchanged():
    provider, factory = manual_provider()
    request = ToolRequest(name="list_machines", arguments={})
    assert provider.call(request) == factory.provider.call(request)


@pytest.mark.parametrize("arguments", [{}, {"text": ""}, {"text": "x", "limit": 9}])
def test_bad_arguments_are_refused(arguments):
    provider, _ = manual_provider()
    result = provider.call(ToolRequest(name=MANUAL_TOOL, arguments=arguments))
    assert not result.success and result.error.code == "invalid_arguments"


def test_a_failing_index_says_nothing_about_why():
    class Broken:
        def search(self, text, *, limit):
            raise RuntimeError("C:/secret/path chroma failed")

    provider, _ = manual_provider(search=Broken())
    result = provider.call(LOOKUP.request)
    assert result.error.message == "Manual search failed."


def test_repeats_and_the_budget_are_refused():
    provider, _ = manual_provider()
    first = provider.call(
        ToolRequest(name=MANUAL_TOOL, arguments={"text": "Vibration!"})
    )
    again = provider.call(
        ToolRequest(name=MANUAL_TOOL, arguments={"text": "vibration"})
    )
    assert first.success and again.error.message == REPEATED_SEARCH
    for words in ("heat", "rejects"):
        assert provider.call(
            ToolRequest(name=MANUAL_TOOL, arguments={"text": words})
        ).success
    spent = provider.call(ToolRequest(name=MANUAL_TOOL, arguments={"text": "door"}))
    assert spent.error.message == SEARCHES_SPENT
    assert len(provider.searched) == MAX_SEARCHES == 3


def test_the_tool_description_says_what_the_manual_is_and_is_not():
    text = MANUAL_SPEC.description
    assert "SIM-CNC-001" in text and "§2.7" in text
    assert "not what is happening now" in text and "At most 3 searches" in text


# --- what the agent and the gate make of it ---------------------------------------


def with_lookup(agent, phase):
    agent.decisions[phase].insert(0, LOOKUP)
    return agent


def run_with(agent):
    factory = Factory()
    factory.provider = manual_provider(factory)[0]
    return investigate(agent, factory=factory)[0]


def test_manual_evidence_is_labelled_manual_and_marked_in_every_prompt():
    provider, factory = manual_provider()
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=provider,
        policy=with_lookup(policy(), "investigate"),
        clock=lambda: 0.0,
        human_review=factory.approve,
    )
    state = run_investigation(state, deps)
    [item] = manual_items(state)
    labels = {p.evidence_id: p.origin for p in state.provenance}
    assert labels.pop(item.id) == "manual"
    assert set(labels.values()) == {"observable"}
    assert f"{item.id} search_manual" in render(state)
    assert "[FROM THE MANUAL: general guidance for this machine model" in render(state)
    [record] = build_manual_records(state)
    assert (record.outcome, record.sections[0]) == ("answered", "§2.1")
    assert record.text == "vibration spike alarm"


def test_a_fix_cannot_be_verified_by_citing_the_manual():
    def cite_manual(state):
        [item] = manual_items(state)
        return VerificationCheck(
            outcome="resolved", prediction="x", evidence_ids=(item.id,)
        )

    agent = policy(verify=(ask("wait", ticks=300), LOOKUP), judge=cite_manual)
    assert run_with(agent).verification.outcome == "inconclusive"


def test_a_real_look_still_verifies_when_the_manual_is_also_cited():
    def both(state):
        check = compare_with_before(state)
        [item] = manual_items(state)
        return check.model_copy(update={"evidence_ids": (*check.evidence_ids, item.id)})

    agent = policy(verify=(ask("wait", ticks=300), LOOKUP, look_again), judge=both)
    assert run_with(agent).verification.outcome == "resolved"


def with_manual_item(only_manual):
    data = candidate_data()
    item = {
        "source_id": f"manual:{MANUAL_TOOL}",
        "source_type": "tool_result",
        "observed_tick": 120,
    }
    data["investigation"]["evidence"].append(
        {"id": "manual", "content": json.dumps([{"section": "§2.2"}]), **item}
    )
    data["provenance"].append({"evidence_id": "manual", "origin": "manual", **item})
    conclusion = data["investigation"]["conclusion"]
    conclusion["evidence_ids"] = (
        ["manual"] if only_manual else [*conclusion["evidence_ids"], "manual"]
    )
    if only_manual:  # every citation: conclusion, action, check, lesson
        data["investigation"]["proposed_action"]["evidence_ids"] = ["manual"]
        data["investigation"]["verification"]["evidence_ids"] = ["manual"]
        data["lesson"]["evidence_ids"] = ["manual"]
        data["useful_evidence_ids"] = ["manual"]
    return ReflectionCandidate.model_validate(data)


def test_the_gate_refuses_a_lesson_that_rests_on_the_manual_alone():
    decision = MemoryPromotionPolicy().evaluate(with_manual_item(only_manual=True))
    assert "rests_on_manual" in decision.reasons


def test_a_lesson_may_cite_the_manual_beside_what_was_seen():
    decision = MemoryPromotionPolicy().evaluate(with_manual_item(only_manual=False))
    assert "rests_on_manual" not in decision.reasons


# --- the manual step: one search on the anomaly before the agent plans --------


def run_stepped(agent, *, manual_step=True, search=None):
    provider, factory = manual_provider(search=search)
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=provider,
        policy=agent,
        clock=lambda: 0.0,
        human_review=factory.approve,
        manual_step=manual_step,
    )
    return run_investigation(state, deps), provider


def test_the_manual_step_is_off_by_default():
    state, provider = run_stepped(policy(), manual_step=False)
    assert manual_items(state) == [] and provider.searched == []


def test_the_manual_step_searches_on_the_anomaly_before_the_plan():
    seen = []
    agent = policy()
    plain_plan = agent.plan
    agent.plan = lambda state: seen.append(manual_items(state)) or plain_plan(state)
    state, provider = run_stepped(agent)

    [item] = manual_items(state)
    [record] = build_manual_records(state)
    assert record.automatic and record.outcome == "answered" and record.sections
    assert record.text == manual_query(state)
    assert provider.searched == [(normalize(manual_query(state)), 3)]
    # The plan was asked with the sections already in its view.
    assert seen == [[item]]
    # Labelled as the manual, never as a look at the factory.
    labels = {p.evidence_id: p.origin for p in state.provenance}
    assert labels[item.id] == "manual"
    phases = [d.phase for d in state.decisions]
    assert phases.index("observe") < phases.index("plan")
    manual_decision = next(d for d in state.decisions if d.tool == MANUAL_TOOL)
    assert manual_decision.phase == "observe"


def test_the_tool_stays_open_after_the_step():
    state, _ = run_stepped(with_lookup(policy(), "investigate"))
    records = build_manual_records(state)
    assert [r.automatic for r in records] == [True, False]
    assert all(r.outcome == "answered" for r in records)


def test_the_step_uses_one_of_the_manual_s_searches():
    agent = policy()
    for words in ("one", "two", "three"):
        agent.decisions["investigate"].insert(
            0, ask(MANUAL_TOOL, text=f"spindle {words}")
        )
    state, _ = run_stepped(agent)
    outcomes = [r.outcome for r in build_manual_records(state)]
    assert outcomes[0] == "answered"  # the step
    assert outcomes.count("answered") == MAX_SEARCHES
    assert outcomes[-1] == "budget_spent"


def test_the_query_is_the_anomaly_s_kind_and_words_only():
    state = new_state()
    query = manual_query(state)
    assert query.startswith(state.anomaly.kind.replace("_", " ") + ": ")
    assert query.endswith(state.anomaly.description)


def test_old_manual_records_read_as_chosen_by_the_agent():
    from capstone.evaluation.manual import ManualSearchRecord

    old = {"sequence": 3, "text": "x", "outcome": "answered", "sections": ["§2.1"]}
    assert ManualSearchRecord.model_validate(old).automatic is False


def test_an_episode_runs_the_step_only_when_it_offers_a_manual(monkeypatch):
    from capstone.episode import run_episode
    from tests.test_episode import wear_policy

    monkeypatch.setenv("MANUAL_STEP", "on")
    plain = run_episode(
        6, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0
    )
    assert all(d.tool != MANUAL_TOOL for d in plain.state.decisions)
    offered = run_episode(
        6,
        wear_policy(),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        manual=KeywordManualSearch(SECTIONS),
    )
    [record] = build_manual_records(offered.state)
    assert record.automatic and record.outcome == "answered"
    monkeypatch.setenv("MANUAL_STEP", "off")
    quiet = run_episode(
        6,
        wear_policy(),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        manual=KeywordManualSearch(SECTIONS),
    )
    assert build_manual_records(quiet.state) == ()
