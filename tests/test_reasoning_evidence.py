"""Reasoning aids use observed tool data, never simulator truth or a model API."""

import json

import pytest

from capstone.agent.artifacts import AgentConclusion, CritiqueRecord
from capstone.agent.evidence_brief import evidence_brief, verify_numeric_claims
from capstone.agent.investigation import check_conclusion, recheck
from capstone.agent.loop import InvestigationDeps, apply_interpretation
from capstone.agent.model_policy import render
from capstone.agent.policy import Interpretation
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis, NumericClaim
from capstone.contracts.provenance import ProvenanceReference
from capstone.contracts.tools import ToolRequest
from tests.helpers import (
    START,
    FakeCritic,
    FakeProvider,
    ScriptedPolicy,
    critique_result,
    new_state,
)


def observed(state, tool, data, *, origin="observable"):
    """Keep a tool observation with the same provenance shape as the loop."""
    evidence = Evidence(
        id=f"E{len(state.evidence) + 1}",
        source_id=f"factory:{tool}",
        source_type="tool_result",
        content=json.dumps(data),
        observed_tick=50,
        observed_at=START,
    )
    state.evidence.append(evidence)
    state.provenance.append(
        ProvenanceReference(
            evidence_id=evidence.id,
            source_id=evidence.source_id,
            source_type=evidence.source_type,
            origin=origin,
            observed_tick=50,
        )
    )
    return evidence


def test_machine_coverage_distinguishes_unchecked_from_normal():
    state = new_state()
    observed(
        state,
        "list_machines",
        [
            {"machine_id": "CNC-01", "status": "running", "job_id": 1},
            {"machine_id": "CNC-02", "status": "idle", "job_id": None},
        ],
    )
    observed(
        state,
        "get_readings",
        [
            {
                "machine_id": "CNC-01",
                "sensor": "vibration",
                "tick": 10,
                "value": 2.0,
                "unit": "mm/s",
            },
        ],
    )
    brief = evidence_brief(state)
    assert "CNC-01" in brief and "vibration" in brief and "E2" in brief
    assert "CNC-02: idle; sensors not checked" in brief
    assert "unknown is not normal" in brief


def test_brief_uses_complete_results_beyond_the_raw_prompt_cutoff():
    state = new_state()
    rows = [
        {
            "machine_id": "CNC-01",
            "sensor": "vibration",
            "tick": tick,
            "value": float(tick),
            "unit": "mm/s",
        }
        for tick in range(40)
    ]
    observed(state, "get_readings", rows)
    brief = evidence_brief(state)
    assert "ticks 0..39" in brief and "delta=39" in brief
    assert "sample_count=40" in brief
    assert "FACTUAL BRIEF" in render(state)
    assert len(brief) <= 8000


def test_manual_or_memory_cannot_create_machine_coverage_or_numeric_facts():
    state = new_state()
    observed(
        state,
        "get_readings",
        [
            {
                "machine_id": "FAKE",
                "sensor": "vibration",
                "tick": 1,
                "value": 99,
                "unit": "mm/s",
            },
        ],
        origin="manual",
    )
    assert "FAKE" not in evidence_brief(state)
    claim = NumericClaim(
        evidence_id="E1",
        machine_id="FAKE",
        sensor="vibration",
        metric="maximum",
        value=99,
        unit="mm/s",
    )
    assert verify_numeric_claims(state, (claim,)) == ("E1: unverified",)


def test_route_is_ordered_observed_visits_not_a_complete_inferred_route():
    state = new_state()
    observed(
        state,
        "get_job_history",
        [
            {"job_id": 4, "machine_id": "CNC-03", "tick": 30, "kind": "job_finished"},
            {"job_id": 4, "machine_id": "CNC-01", "tick": 10, "kind": "job_started"},
        ],
    )
    observed(
        state,
        "get_inspections",
        [
            {"job_id": 4, "batch_id": 1, "tick": 40, "result": "failed"},
        ],
    )
    brief = evidence_brief(state)
    assert brief.index("tick 10 CNC-01") < brief.index("tick 30 CNC-03")
    assert "job 4 batch 1 failed at tick 40 [E2]" in brief
    assert "observed events only; missing visits remain unknown" in brief


def test_duplicate_measurements_are_not_presented_as_independent_support():
    state = new_state()
    row = {
        "machine_id": "CNC-01",
        "sensor": "vibration",
        "tick": 10,
        "value": 2.0,
        "unit": "mm/s",
    }
    observed(state, "get_readings", [row])
    observed(state, "get_readings", [row])
    assert "1 repeated measurement" in evidence_brief(state)


def test_numeric_verifier_checks_values_units_and_windows_without_judging_causes():
    state = new_state()
    observed(
        state,
        "get_readings",
        [
            {
                "machine_id": "CNC-01",
                "sensor": "temperature",
                "tick": tick,
                "value": value,
                "unit": "F",
            }
            for tick, value in [(10, 70), (20, 72)]
        ],
    )
    claim = NumericClaim(
        evidence_id="E1",
        machine_id="CNC-01",
        sensor="temperature",
        metric="delta",
        value=2,
        unit="F",
        from_tick=10,
        to_tick=20,
    )
    assert verify_numeric_claims(state, (claim,)) == ()
    with pytest.raises(ValueError, match="numeric claim"):
        verify_numeric_claims(state, (claim.model_copy(update={"value": 30}),))
    with pytest.raises(ValueError, match="unit"):
        verify_numeric_claims(state, (claim.model_copy(update={"unit": "C"}),))
    outside = claim.model_copy(update={"from_tick": 30, "to_tick": 40})
    assert verify_numeric_claims(state, (outside,)) == ("E1: unverified",)


def test_hypothesis_comparison_is_visible_and_invalid_gap_citations_are_refused():
    state = new_state()
    observed(state, "get_time", {"tick": 50})
    hypothesis = Hypothesis(
        id="H1",
        claim="a cause",
        confidence=0.6,
        expected_observations=("signal persists across jobs",),
        assumptions=("operating conditions comparable",),
        unexplained_evidence_ids=("E1",),
        discriminating_check="compare before and after the job",
    )
    apply_interpretation(state, Interpretation(hypotheses=(hypothesis,)))
    view = render(state)
    assert "signal persists across jobs" in view
    assert "operating conditions comparable" in view
    assert "Unexplained: E1" in view
    with pytest.raises(ValueError, match="not gathered"):
        apply_interpretation(
            state,
            Interpretation(
                hypotheses=(
                    hypothesis.model_copy(
                        update={"unexplained_evidence_ids": ("E999",)}
                    ),
                )
            ),
        )


def test_completion_cannot_claim_supported_with_unresolved_diagnostic_questions():
    from capstone.agent.state import Question

    state = new_state()
    observed(state, "get_time", {"tick": 50})
    state.hypotheses = [Hypothesis(id="H1", claim="a cause", confidence=0.95)]
    state.unanswered_questions = [
        Question(id="Q1", text="check the other machine", hypothesis_id="H1")
    ]
    answer = AgentConclusion(
        diagnosis="a cause",
        confidence=0.95,
        recommendation="no_action",
        hypothesis_id="H1",
        evidence_ids=("E1",),
        assessment="supported",
    )
    deps = InvestigationDeps(provider=FakeProvider(), policy=ScriptedPolicy())
    checked, action = check_conclusion(state, deps, answer, None)
    assert checked.assessment == "unresolved"
    assert checked.recommendation == "escalate" and action is None
    assert "check the other machine" in checked.unresolved_questions
    assert checked.diagnosis == "a cause"


def test_no_available_repair_does_not_erase_the_diagnosis():
    state = new_state()
    observed(state, "get_readings", {"tick": 10, "value": 70, "sensor": "temperature"})
    answer = AgentConclusion(
        diagnosis="a measured fault without an available repair",
        confidence=0.8,
        recommendation="escalate",
        assessment="supported",
        action_rationale="available actions do not address this fault",
        evidence_ids=("E1",),
    )
    deps = InvestigationDeps(provider=FakeProvider(), policy=ScriptedPolicy())
    checked, action = check_conclusion(state, deps, answer, None)
    assert checked.diagnosis == answer.diagnosis and checked.assessment == "supported"
    assert checked.recommendation == "escalate" and action is None


def test_question_priority_rewards_distinguishing_rivals_without_using_confidence():
    from capstone.agent.state import Question

    state = new_state()
    state.hypotheses = [
        Hypothesis(id=hid, claim=hid, confidence=0.95) for hid in ("H1", "H2")
    ]
    state.unanswered_questions = [
        Question(id="Q1", text="more detail about favourite", hypothesis_id="H1"),
        Question(
            id="Q2",
            text="compare alternatives",
            hypothesis_id="H1",
            distinguishes_hypothesis_ids=("H1", "H2"),
            signal_reliability="direct",
        ),
    ]
    view = render(state)
    assert view.index("- Q2:") < view.index("- Q1:")


def test_numeric_mismatch_cannot_be_applied_as_a_new_belief():
    state = new_state()
    observed(
        state,
        "get_readings",
        [
            {
                "machine_id": "CNC-01",
                "sensor": "temperature",
                "tick": 10,
                "value": 70,
                "unit": "F",
            },
        ],
    )
    wrong = NumericClaim(
        evidence_id="E1",
        machine_id="CNC-01",
        sensor="temperature",
        metric="maximum",
        value=100,
        unit="F",
    )
    with pytest.raises(ValueError, match="numeric claim"):
        apply_interpretation(
            state,
            Interpretation(
                hypotheses=(
                    Hypothesis(
                        id="H1",
                        claim="a cause",
                        confidence=0.9,
                        numeric_claims=(wrong,),
                    ),
                )
            ),
        )
    assert not state.hypotheses


def test_critic_check_runs_despite_high_confidence_and_spent_research_budget():
    state = new_state(max_tool_calls=1)
    state.tool_call_count = 1
    state.hypotheses = [Hypothesis(id="H1", claim="a cause", confidence=0.95)]
    reply = critique_result("no_objection").model_dump() | {
        "check_request": {
            "name": "get_settings",
            "arguments": {"machine_id": "CNC-01"},
        },
    }
    from capstone.agent.artifacts import CritiqueResult

    state.critique = CritiqueRecord(
        outcome="answered",
        result=CritiqueResult(**reply),
        shown_hypotheses=("H1",),
        seconds=1,
    )
    provider = FakeProvider()
    deps = InvestigationDeps(
        provider=provider,
        policy=ScriptedPolicy(),
        critic=FakeCritic(),
        critic_followup=True,
        clock=lambda: 0,
    )
    recheck(state, deps)
    assert [call.name for call in provider.calls] == ["get_settings"]
    assert state.recheck.outcome == "observed"
    assert state.critic_tool_calls_used == 1 and state.research_tool_calls == 1
    assert state.followup_tool_calls_used == 0
    recheck(state, deps)
    assert len(provider.calls) == 1


def test_critic_check_never_executes_wait_or_an_action():
    from capstone.agent.artifacts import CritiqueResult

    for name in ("wait", "propose_action", "read_ground_truth"):
        state = new_state()
        state.hypotheses = [Hypothesis(id="H1", claim="a cause", confidence=0.8)]
        reply = critique_result().model_dump() | {
            "check_request": {"name": name, "arguments": {}}
        }
        state.critique = CritiqueRecord(
            outcome="answered",
            result=CritiqueResult(**reply),
            shown_hypotheses=("H1",),
            seconds=1,
        )
        provider = FakeProvider()
        deps = InvestigationDeps(
            provider=provider,
            policy=ScriptedPolicy(),
            critic=FakeCritic(),
            critic_followup=True,
            clock=lambda: 0,
        )
        recheck(state, deps)
        assert provider.calls == [] and state.recheck.outcome == "invalid_decision"


def test_long_measurements_cannot_hide_routes_or_inspections_in_the_brief():
    state = new_state()
    for number in range(100):
        observed(
            state,
            "get_readings",
            [
                {
                    "machine_id": "CNC-01",
                    "sensor": f"signal-{number}",
                    "tick": number,
                    "value": number,
                    "unit": "unit",
                }
            ],
        )
    observed(
        state,
        "get_job_history",
        [{"job_id": 4, "machine_id": "CNC-03", "tick": 30, "kind": "job_finished"}],
    )
    observed(
        state,
        "get_inspections",
        [{"job_id": 4, "batch_id": 1, "tick": 40, "result": "failed"}],
    )
    brief = evidence_brief(state)
    assert "tick 30 CNC-03 job_finished" in brief
    assert "job 4 batch 1 failed" in brief
    assert len(brief) <= 8000


def test_unknown_units_cannot_be_declared_wrong_by_the_numeric_verifier():
    state = new_state()
    observed(
        state,
        "get_readings",
        [{"machine_id": "CNC-01", "sensor": "temperature", "tick": 10, "value": 70}],
    )
    claim = NumericClaim(
        evidence_id="E1",
        machine_id="CNC-01",
        sensor="temperature",
        metric="maximum",
        value=70,
        unit="F",
    )
    assert verify_numeric_claims(state, (claim,)) == ("E1: unverified",)


def test_an_exact_current_tick_critic_check_reuses_observations_without_a_call():
    from capstone.agent.artifacts import CritiqueResult
    from capstone.agent.state import DecisionRecord

    state = new_state()
    observed(state, "get_settings", {"machine_id": "CNC-01", "speed_rpm": 900})
    state.last_tick = 50
    state.hypotheses = [Hypothesis(id="H1", claim="a cause", confidence=0.95)]
    request = ToolRequest(name="get_settings", arguments={"machine_id": "CNC-01"})
    state.decisions = [
        DecisionRecord(
            sequence=1,
            phase="test",
            tick=50,
            information_needed="read the setting",
            tool=request.name,
            arguments=request.arguments,
            outcome="observed",
            evidence_ids=("E1",),
            confidence=0.95,
        )
    ]
    reply = critique_result().model_dump() | {"check_request": request}
    state.critique = CritiqueRecord(
        outcome="answered",
        result=CritiqueResult(**reply),
        shown_hypotheses=("H1",),
        seconds=1,
    )
    provider = FakeProvider()
    deps = InvestigationDeps(
        provider=provider,
        policy=ScriptedPolicy(),
        critic=FakeCritic(),
        critic_followup=True,
        clock=lambda: 0,
    )
    recheck(state, deps)
    assert not provider.calls and state.critic_tool_calls_used == 0
    assert (
        state.recheck.outcome == "already_answered"
        and state.recheck.evidence_id == "E1"
    )
    assert not state.unanswered_questions


def test_completion_gap_is_recorded_as_the_reason_an_intervention_was_lowered():
    from capstone.agent.investigation import conclude
    from capstone.agent.policy import ActionRequest
    from capstone.agent.state import Question

    state = new_state()
    observed(state, "get_time", {"tick": 50})
    state.hypotheses = [Hypothesis(id="H1", claim="a cause", confidence=0.95)]
    state.unanswered_questions = [
        Question(id="Q1", text="check the other machine", hypothesis_id="H1")
    ]
    answer = AgentConclusion(
        diagnosis="a cause",
        confidence=0.95,
        recommendation="intervene",
        assessment="supported",
        hypothesis_id="H1",
        evidence_ids=("E1",),
    )
    request = ActionRequest(
        machine_id="CNC-01",
        action="replace_bearing",
        reason="a cause",
        prediction="signal normalizes",
    )
    policy = ScriptedPolicy(conclude=lambda state: (answer, request))
    conclude(
        state,
        InvestigationDeps(provider=FakeProvider(), policy=policy, clock=lambda: 0),
    )
    assert state.conclusion.recommendation == "escalate"
    assert state.policy_recommendation == "intervene"
    assert "check the other machine" in state.recommendation_lowered
