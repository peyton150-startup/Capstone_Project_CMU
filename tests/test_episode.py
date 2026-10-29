"""One episode end to end, with a scripted policy and no model.

The policy reads only working memory (the anomaly, the evidence), never
the simulator, so these runs exercise every stage the real agent will:
monitoring, research, a proposal the human decides, the work, the look
again, the audit and memory gate, and scoring against the hidden truth.
"""

import json

import pytest

from capstone.agent.artifacts import AgentConclusion, VerificationCheck
from capstone.agent.completion import AuditLog
from capstone.agent.policy import ActionRequest, Interpretation, Lesson
from capstone.contracts.hypotheses import Hypothesis
from capstone.episode import reject_all, rescore, run_episode
from capstone.evaluation.scoring import format_summary, summarize
from capstone.providers.chat import ModelError
from capstone.tools.diagnosis import Diagnosis
from tests.helpers import FakeCritic, ScriptedPolicy, ask

SEED, MACHINE = 6, "CNC-02"  # seed 6 puts the fault on CNC-02
ADVICE = "When vibration climbs steadily on one machine, replace its bearing."


def summary_of(state, machine, from_tick, to_tick, **extra):
    return ask(
        "get_sensor_summary",
        machine_id=machine,
        sensor="vibration",
        from_tick=from_tick,
        to_tick=to_tick,
        **extra,
    )


def before(state):
    """The 300 ticks up to the alarm on the machine it named."""
    a = state.anomaly
    return summary_of(state, a.machine_id, a.tick - 300, a.tick)


def trend(state):
    a = state.anomaly
    return ask(
        "get_sensor_trend",
        hypothesis_id="H1",
        machine_id=a.machine_id,
        sensor="vibration",
        from_tick=a.tick - 600,
        to_tick=a.tick,
        bucket_ticks=100,
    )


def after(state):
    """The same machine since the work finished (or since concluding)."""
    since = state.action_finish_tick or state.concluded_tick
    return summary_of(state, state.anomaly.machine_id, since + 1, state.last_tick)


def mean(state, evidence_id):
    [found] = [e for e in state.evidence if e.id == evidence_id]
    return json.loads(found.content)["mean"]


def compare(state):
    latest = state.evidence[-1].id
    fell = mean(state, latest) < mean(state, "E2") - 0.5
    return VerificationCheck(
        outcome="resolved" if fell else "not_resolved",
        prediction="x",
        evidence_ids=("E2", latest),
    )


def wear_policy(recommendation="intervene"):
    def believe(confidence, *evidence_ids):
        return Interpretation(
            hypotheses=(
                Hypothesis(
                    id="H1",
                    claim="the bearing on the alarmed machine is wearing",
                    confidence=confidence,
                    supporting_evidence_ids=evidence_ids,
                ),
            )
        )

    def interpret(state, step, evidence):
        if step.hypothesis_id is None:
            return Interpretation()
        return believe(0.95, "E2", evidence.id)

    def conclude(state):
        machine = state.anomaly.machine_id
        concluded = AgentConclusion(
            diagnosis=f"bearing wear on {machine}: vibration climbed in every block",
            confidence=0.95,
            recommendation=recommendation,
            hypothesis_id="H1",
            evidence_ids=("E2", "E3"),
        )
        if recommendation != "intervene":
            return concluded, None
        return concluded, ActionRequest(
            machine_id=machine,
            action="replace_bearing",
            reason="vibration has climbed for hundreds of ticks",
            prediction=f"vibration on {machine} falls back to its earlier level",
        )

    return ScriptedPolicy(
        {
            "investigate": [before],
            "test": [trend],
            "verify": [ask("wait", ticks=300), after],
        },
        interpret,
        hypothesize=lambda state: believe(0.6, "E2"),
        conclude=conclude,
        judge=compare,
        lesson=lambda state: Lesson(text=ADVICE),
    )


def hand_label(text):
    """What a person reading the conclusion would write down."""
    if "bearing wear on" in text:
        return Diagnosis(fault="bearing_degradation", machine_id=text.split()[3][:-1])
    return None


def run(**options):
    return run_episode(
        SEED, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0, **options
    )


# --- the whole chain ----------------------------------------------------------


def test_a_bearing_fault_is_found_fixed_checked_and_scored_in_full():
    result = run(judge=hand_label)
    state, score = result.state, result.score
    assert state.anomaly.kind == "alarm" and state.anomaly.machine_id == MACHINE
    assert state.proposed_action.status == "approved" and state.action_carried_out
    assert state.verification.outcome == "resolved"
    assert result.conclusion.startswith(f"bearing wear on {MACHINE}")
    assert (
        score.fault_correct,
        score.target_correct,
        score.action_correct,
        score.resolved,
    ) == (True, True, True, True)
    assert score.actions_taken == [f"replace_bearing {MACHINE}"]
    assert score.tool_calls == state.tool_call_count > 0


def test_without_a_judge_the_diagnosis_is_unjudged_but_the_action_is_scored():
    score = run().score
    assert (score.fault_correct, score.target_correct) == (None, None)
    assert score.action_correct and score.resolved
    assert format_summary(summarize([score])).startswith(
        "0/0 root causes correctly identified (1 not judged)"
    )


def test_a_label_added_afterwards_scores_the_same_run():
    result = run()
    labelled = rescore(result, hand_label(result.conclusion))
    assert labelled.fault_correct and labelled.target_correct
    assert labelled.actions_taken == result.score.actions_taken
    assert rescore(result, None).fault_correct is False


def test_a_human_who_refuses_leaves_the_fault_in_place():
    result = run(approver=reject_all, judge=hand_label)
    assert result.state.proposed_action.status == "rejected"
    assert not result.state.action_carried_out
    score = result.score
    assert score.fault_correct and score.actions_taken == []
    assert not score.action_correct and not score.resolved


def test_the_same_seed_gives_the_same_episode():
    first, second = run(judge=hand_label), run(judge=hand_label)
    assert first.score == second.score
    assert [e.content for e in first.state.evidence] == [
        e.content for e in second.state.evidence
    ]


def test_the_agent_never_holds_the_answer_key():
    result = run(judge=hand_label)
    text = result.state.model_dump_json().lower()
    hidden = ("bearing_health", "ground_truth", "true_fault", "standard_speed")
    assert not [word for word in hidden if word in text]


# --- learning, when memory is given -------------------------------------------


@pytest.fixture
def memory(tmp_path):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from capstone.memory.repository import SQLMemoryRepository
    from capstone.memory.schema import metadata
    from capstone.memory.service import MemoryService

    engine = sqlalchemy.create_engine(f"sqlite:///{tmp_path / 'memories.sqlite'}")
    metadata.create_all(engine)
    yield MemoryService(SQLMemoryRepository(engine))
    engine.dispose()


def test_a_verified_fix_is_audited_and_remembered(memory, tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    result = run(memory=memory, log=log)
    assert result.learning.lesson == ADVICE and result.learning.decision.stored
    assert len(log.read()) == 1
    [recalled] = memory.search("vibration bearing", limit=5)
    assert ADVICE in recalled.model_dump_json()


def test_without_an_audit_log_nothing_is_learned(memory):
    assert run(memory=memory).learning is None


# --- what monitoring hands over -----------------------------------------------


def test_monitoring_names_a_symptom_and_no_machine_for_a_run_of_rejects():
    from capstone.agent.monitor import detect_anomaly
    from capstone.simulator.generator import build_scenario
    from capstone.tools.actions import ActionTools, ApprovalDesk
    from capstone.tools.observation import ObservationTools

    sim = build_scenario(SEED, fault="wrong_setting")
    found = detect_anomaly(ObservationTools(sim), ActionTools(sim, ApprovalDesk(sim)))
    assert (found.kind, found.machine_id) == ("inspection_failures", None)
    assert "failed inspection" in found.description
    assert "setting" not in found.description  # a symptom, never the cause
    assert found.tick == sim.clock.tick


def test_a_whole_episode_records_the_section_nine_fields():
    score = run(judge=hand_label).score
    assert score.recommended_actions == [f"replace_bearing {MACHINE}"]
    assert score.recommendation_status == ["approved"]
    assert score.recommendation_correct
    assert f"vibration of {MACHINE}" in score.relevant_evidence_collected
    assert set(score.relevant_evidence_collected) <= set(score.relevant_evidence)
    assert score.iterations > 0 and score.termination_reason is not None
    assert not score.model_unavailable


# --- which factory an episode is run on -----------------------------------------


def test_the_standard_world_is_the_one_fault_scenario():
    from capstone.episode import build_world
    from capstone.simulator.generator import build_scenario

    world = build_world(SEED, fault="bearing_degradation")
    assert (
        world.ground_truth()
        == build_scenario(SEED, fault="bearing_degradation").ground_truth()
    )


def test_the_challenge_world_is_the_compound_challenge():
    from capstone.episode import CHALLENGE, build_world
    from capstone.simulator.challenge import build_challenge

    world = build_world(3, kind=CHALLENGE, machines=4)
    assert world.ground_truth() == build_challenge(3, machines=4).ground_truth()
    assert len(world.ground_truth()) == 5


def test_the_challenge_takes_no_fault_and_an_unknown_kind_is_refused():
    from capstone.episode import CHALLENGE, build_world

    with pytest.raises(ValueError, match="chooses its own faults"):
        build_world(3, kind=CHALLENGE, fault="wrong_setting")
    with pytest.raises(ValueError, match="unknown scenario kind"):
        build_world(3, kind="nightmare")


def test_an_episode_on_the_challenge_is_scored_with_several_causes():
    from capstone.episode import CHALLENGE

    result = run_episode(3, wear_policy(), kind=CHALLENGE, clock=lambda: 0.0)
    assert result.score.true_fault == "compound"
    assert len(result.score.causes) == 2
    # Monitoring is unchanged: it notices the harmless spike on another machine.
    assert result.state.anomaly.machine_id == "CNC-03"


# --- the critic, review only -----------------------------------------------


def test_critic_off_by_default_keeps_results(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    result = run_episode(
        SEED, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0
    )
    assert result.critic_calls == ()
    assert result.state.critique is None


def test_critic_on_without_model_fails_before_running(monkeypatch):
    monkeypatch.setenv("CRITIC", "on")
    monkeypatch.setenv("CRITIC_MODEL", "")
    reads = []

    def clock():
        reads.append(1)
        return 0.0

    with pytest.raises(ModelError, match="CRITIC_MODEL"):
        run_episode(SEED, wear_policy(), fault="bearing_degradation", clock=clock)
    assert reads == []


def test_critic_followup_setting_reaches_the_run(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.setenv("CRITIC_FOLLOWUP", "on")
    result = run_episode(
        SEED,
        wear_policy(),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        critic=FakeCritic(),
    )
    assert result.state.recheck is not None


def test_critic_followup_off_by_default(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    monkeypatch.delenv("CRITIC_FOLLOWUP", raising=False)
    result = run_episode(
        SEED,
        wear_policy(),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        critic=FakeCritic(),
    )
    assert result.state.recheck is None


def test_passed_critic_is_used(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    critic = FakeCritic()
    result = run_episode(
        SEED,
        wear_policy(),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        critic=critic,
    )
    assert result.state.critique.outcome == "answered"
    assert result.critic_calls == tuple(critic.calls)
    assert len(critic.reviewed) == 1


def test_a_critic_does_not_change_the_episode(monkeypatch):
    monkeypatch.setenv("CRITIC", "off")
    plain = run_episode(
        SEED, wear_policy(), fault="bearing_degradation", clock=lambda: 0.0
    )
    critiqued = run_episode(
        SEED,
        wear_policy(),
        fault="bearing_degradation",
        clock=lambda: 0.0,
        critic=FakeCritic(),
    )
    assert critiqued.state.conclusion == plain.state.conclusion
    assert critiqued.state.decisions == plain.state.decisions
    assert critiqued.score == plain.score
