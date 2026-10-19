from pathlib import Path

import pytest
from pydantic import ValidationError

import capstone.memory.contracts as memory_contracts
from capstone.agent.artifacts import AgentConclusion, VerificationCheck
from capstone.agent.investigation import run_investigation
from capstone.agent.loop import InvestigationDeps, run_inner_loop
from capstone.agent.policy import (
    ActionRequest,
    CallTool,
    Interpretation,
    Stop,
)
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.provenance import ProvenanceReference
from capstone.providers.factory import SimulatorFactoryProvider
from capstone.simulator.line import build_line
from capstone.simulator.scenarios import BearingDegradation
from capstone.tools.actions import ActionTools, ApprovalDesk
from capstone.tools.observation import ObservationTools
from tests.helpers import FakeProvider, ScriptedPolicy, ask, new_state

CAPSTONE = Path(__file__).parent.parent / "capstone"


def gather(decisions, *, respond=None, interpret=None):
    state = new_state()
    policy = ScriptedPolicy(decisions, interpret)
    deps = InvestigationDeps(
        provider=FakeProvider(respond), policy=policy, clock=lambda: 0.0
    )
    run_inner_loop(state, deps, "investigate")
    return state, policy


def whole_investigation():
    """A real investigation: research, an approved repair, and a check afterwards."""
    sim = build_line(42, machines=3)
    sim.add_scenario(
        BearingDegradation(
            "bearing", sim.rng, machine_id="CNC-02", start_tick=100, rate=0.0006
        )
    )
    for _ in range(600):
        sim.step()
    desk = ApprovalDesk(sim)
    provider = SimulatorFactoryProvider(ObservationTools(sim), ActionTools(sim, desk))

    def summary(from_tick, to_tick, **extra):
        return ask(
            "get_sensor_summary",
            machine_id="CNC-02",
            sensor="vibration",
            from_tick=from_tick,
            to_tick=to_tick,
            **extra,
        )

    def wear(confidence, *supporting):
        return Hypothesis(
            id="H1",
            claim="CNC-02 is wearing",
            confidence=confidence,
            supporting_evidence_ids=supporting,
        )

    def interpret(state, step, evidence):
        if step.hypothesis_id is None:
            return Interpretation()
        return Interpretation(hypotheses=(wear(0.95, "E2", evidence.id),))

    concluded = AgentConclusion(
        diagnosis="wear on CNC-02",
        confidence=0.95,
        recommendation="intervene",
        hypothesis_id="H1",
        evidence_ids=("E2", "E3"),
    )
    request = ActionRequest(
        machine_id="CNC-02",
        action="replace_bearing",
        reason="vibration has climbed",
        prediction="vibration returns to its earlier level",
    )
    policy = ScriptedPolicy(
        {
            "investigate": [summary(400, 600)],
            "test": [summary(0, 600, hypothesis_id="H1")],
            "verify": [
                ask("wait", ticks=300),
                lambda state: summary(state.action_finish_tick + 1, state.last_tick),
            ],
        },
        interpret,
        hypothesize=lambda state: Interpretation(hypotheses=(wear(0.6, "E2"),)),
        conclude=lambda state: (concluded, request),
        judge=lambda state: VerificationCheck(
            outcome="resolved", prediction="x", evidence_ids=(state.evidence[-1].id,)
        ),
    )
    state = new_state()
    state.last_tick = None
    deps = InvestigationDeps(
        provider=provider,
        policy=policy,
        clock=lambda: 0.0,
        human_review=lambda proposal: desk.approve(proposal.proposal_id, note="ok"),
    )
    return run_investigation(state, deps)


# --- one definition --------------------------------------------------------


def test_provenance_is_defined_once_in_the_shared_contracts():
    defining = [
        path.relative_to(CAPSTONE).as_posix()
        for path in CAPSTONE.rglob("*.py")
        if "class ProvenanceReference(" in path.read_text(encoding="utf-8")
    ]
    assert defining == ["contracts/provenance.py"]


def test_the_memory_gate_and_the_loop_use_the_very_same_class():
    assert memory_contracts.ProvenanceReference is ProvenanceReference


# --- written by the loop when the answer arrives ---------------------------


def test_every_piece_of_evidence_gets_a_matching_label_when_it_arrives():
    state, _ = gather([ask("get_events", from_tick=0, to_tick=10), ask("get_time")])
    assert [p.model_dump() for p in state.provenance] == [
        {
            "evidence_id": "E1",
            "source_id": "fake:get_events",
            "source_type": "tool_result",
            "origin": "observable",
            "observed_tick": 10,
        },
        {
            "evidence_id": "E2",
            "source_id": "fake:get_time",
            "source_type": "tool_result",
            "origin": "observable",
            "observed_tick": 10,
        },
    ]


def test_the_label_is_already_there_when_the_policy_first_sees_the_evidence():
    seen = []

    def interpret(state, step, evidence):
        seen.append([p.evidence_id for p in state.provenance])
        return Interpretation()

    gather([ask("a"), ask("b")], interpret=interpret)
    assert seen == [["E1"], ["E1", "E2"]]


@pytest.mark.parametrize(
    "bad_answer",
    ["error", RuntimeError("boom"), None],
    ids=["tool error", "provider raises", "no data"],
)
def test_an_answer_that_is_not_evidence_gets_no_label(bad_answer):
    state, _ = gather([ask("get_events")], respond=lambda request: bad_answer)
    assert state.evidence == [] and state.provenance == []


def test_a_good_answer_the_policy_could_not_interpret_keeps_its_label():
    def interpret(state, step, evidence):
        raise ValueError("could not read this")

    state, _ = gather([ask("get_events")], interpret=interpret)
    assert [p.evidence_id for p in state.provenance] == ["E1"]


# --- never by the policy ---------------------------------------------------


def test_the_policy_cannot_change_the_labels():
    def tamper(state):
        state.provenance.clear()
        state.provenance.append(
            ProvenanceReference(
                evidence_id="E1",
                source_id="made up",
                source_type="document",
                origin="human",
            )
        )
        return ask("b")

    state, _ = gather([ask("a"), tamper])
    assert [(p.evidence_id, p.source_id, p.origin) for p in state.provenance] == [
        ("E1", "fake:a", "observable"),
        ("E2", "fake:b", "observable"),
    ]


def test_nothing_a_policy_returns_has_a_place_to_state_an_origin():
    returned = (
        CallTool,
        Stop,
        Interpretation,
        ActionRequest,
        AgentConclusion,
        VerificationCheck,
        Hypothesis,
    )
    for model in returned:
        fields = set(model.model_fields)
        assert not fields & {"origin", "provenance", "source_id", "source_type"}, model


def test_a_label_cannot_be_edited_after_it_is_written():
    state, _ = gather([ask("a")])
    with pytest.raises(ValidationError):
        state.provenance[0].origin = "human"


# --- across a whole real investigation -------------------------------------


def test_labels_match_the_evidence_one_to_one_through_a_whole_investigation():
    state = whole_investigation()
    assert state.verification.outcome == "resolved"  # every stage ran
    assert len(state.evidence) == len(state.provenance) == 9
    for evidence, label in zip(state.evidence, state.provenance, strict=True):
        assert (
            label.evidence_id,
            label.source_id,
            label.source_type,
            label.observed_tick,
        ) == (
            evidence.id,
            evidence.source_id,
            evidence.source_type,
            evidence.observed_tick,
        )
    assert {p.origin for p in state.provenance} == {"observable"}
    assert {p.source_id.split(":")[0] for p in state.provenance} == {"simulator"}


def test_evidence_cited_by_the_conclusion_and_the_check_all_have_labels():
    state = whole_investigation()
    labelled = {p.evidence_id for p in state.provenance}
    cited = set(state.conclusion.evidence_ids) | set(state.verification.evidence_ids)
    assert cited and cited <= labelled
