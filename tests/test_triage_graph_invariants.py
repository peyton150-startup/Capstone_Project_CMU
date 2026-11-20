"""Whole-Graph invariants for deterministic triage (follow-ups to PR #324).

These run the real Pydantic Graph (Observe -> fixed Plan -> deterministic
Investigate -> Hypothesize -> Test -> Conclude), not the inner loop alone, so a
stage that reconciles requirements differently from the loop is caught.
"""

from dataclasses import replace

import pytest

from capstone.agent.artifacts import AgentConclusion, DetectedAnomaly, TerminationReason
from capstone.agent.investigation import run_investigation
from capstone.agent.triage_decide import choose_next_triage_read
from capstone.agent.triage_decide_contracts import TriageStopDecision
from capstone.providers.factory import tool_spec
from tests.helpers import START, FakeProvider, new_state
from tests.test_triage_deterministic_decide import (
    ALARM,
    NoDecideModel,
    answer,
    deps_for,
    state_for,
)

TOOLS = tuple(
    tool_spec(name)
    for name in (
        "get_sensor_summary",
        "get_events",
        "get_maintenance_history",
        "get_settings",
        "get_inspections",
        "get_job_history",
    )
)


class ConcludeOnly(NoDecideModel):
    """Answers only the conclusion, and always leaves it unresolved."""

    def conclude(self, state):
        self.asked.append("conclude")
        return (
            AgentConclusion(
                diagnosis="unresolved",
                confidence=0.4,
                recommendation="escalate",
                assessment="unresolved",
                evidence_ids=tuple(e.id for e in state.evidence[:1]),
            ),
            None,
        )


def respond(request):
    """Valid rows for every read the fixed alarm plan makes."""
    if request.name == "get_time":
        return {"tick": 45, "time": START.isoformat()}
    if request.name == "get_events":
        return [
            {
                "tick": 30,
                "machine_id": request.arguments.get("machine_id"),
                "kind": "note",
                "message": "m",
                "job_id": None,
            }
        ]
    return answer(request)


def check_invariants(state) -> None:
    """Question and requirement bookkeeping agree, at any point in the run."""
    # Variables:
    #   open_ids: Questions still unanswered.
    #   by_question: Each question's requirement ids.
    open_ids = {q.id for q in state.unanswered_questions}
    by_question: dict[str, list[str]] = {}
    for rid, requirement in state.triage_requirements.items():
        by_question.setdefault(requirement.question_id, []).append(rid)
    for question_id, ids in by_question.items():
        results = [state.triage_requirement_results.get(rid) for rid in ids]
        if question_id not in open_ids and question_id in state.answers:
            # Closed: every required part satisfied, and no gap left on it.
            assert all(r is not None and r.status == "satisfied" for r in results), (
                question_id
            )
            assert question_id not in state.triage_question_gaps, question_id
    # A gap is an open question's reason; it never sits on a closed one.
    for question_id in state.triage_question_gaps:
        assert question_id in open_ids, question_id
    assert state.triage_bookkeeping_anomalies == []
    if state.termination_reason is TerminationReason.EVIDENCE_SUFFICIENT:
        assert not open_ids
        assert all(
            r.status == "satisfied"
            for rid, r in state.triage_requirement_results.items()
            if state.triage_requirements[rid].required
        )


def graph_run(anomaly=ALARM, *, respond=respond, channels=None, watch=None):
    """One full deterministic triage Graph with the fake read-only provider."""
    state = new_state(max_tool_calls=12, max_iterations=24)
    state.mode = "triage"
    state.anomaly = anomaly
    state.triage_fixed_plan = True
    state.triage_packet_enabled = False
    provider = FakeProvider(respond, tick=45)
    deps = replace(
        deps_for(provider, tools=TOOLS),
        policy=ConcludeOnly(),
        triage_hypothesize="deterministic",
        screening_available=False,
        watch=watch,
    )
    if channels is not None:
        deps.triage_channels = channels
    run_investigation(state, deps)
    return state, deps, provider


def test_invariants_hold_at_every_published_state_and_at_the_end():
    seen = []
    state, deps, _ = graph_run(watch=seen.append)
    assert len(seen) > 3
    for snapshot in seen:
        check_invariants(snapshot)
    check_invariants(state)
    assert deps.policy.asked == ["conclude"]


def test_capability_loss_after_partial_evidence_survives_hypothesize_and_test():
    """A requirement with partial evidence that loses its channel stays denied.

    The temperature summary comes back with too few samples, then the
    temperature channel disappears. Every stage that reconciles must recompute
    authorization: the end-of-Test reconciliation once ran without `deps` and
    put the fresh partial verdict back over the denial.
    """
    channels = {"CNC-02": ["vibration", "temperature", "load"]}

    def losing_temperature(request):
        if (
            request.name == "get_sensor_summary"
            and request.arguments.get("sensor") == "temperature"
        ):
            channels["CNC-02"].remove("temperature")
            data = answer(request)
            return {**data, "sample_count": 1, "first_tick": data["last_tick"]}
        return respond(request)

    state, _, provider = graph_run(respond=losing_temperature, channels=channels)
    reads = [c for c in provider.calls if c.arguments.get("sensor") == "temperature"]
    assert len(reads) == 1
    result = state.triage_requirement_results["Q5:temperature"]
    assert result.status == "unavailable"
    assert result.evidence_ids, "the collected evidence is kept beside the denial"
    assert "channel_unavailable" in result.reason
    assert state.termination_reason is not TerminationReason.EVIDENCE_SUFFICIENT
    check_invariants(state)


def test_alarm_fixed_plan_cannot_claim_sufficiency_from_a_settings_snapshot():
    """Every read answered well: with no finished jobs, Q4 stays open, as Q5 does."""
    state, _, _ = graph_run()
    assert state.termination_reason is not TerminationReason.EVIDENCE_SUFFICIENT
    assert state.triage_requirement_results["Q4:cycle_time"].status != "satisfied"
    assert "Q5" in state.triage_question_gaps
    assert {"Q4", "Q5"} <= {q.id for q in state.unanswered_questions}
    check_invariants(state)


# Ticks of warm-up before the check: enough for every machine to be scored
# and for inspections inside the plan window (probed for these seeds).
@pytest.mark.parametrize(("seed", "waits"), [(1, 15), (4, 18)])
def test_routine_check_reaches_evidence_sufficient_on_the_real_simulator(
    seed, waits, monkeypatch
):
    """Positive completion is reachable through the whole Graph.

    A routine check after the line has warmed up: the screening scores every
    machine, the events and recent inspections qualify, and the controller
    stops with requirements_complete -> EVIDENCE_SUFFICIENT, using the model
    only to conclude.
    """
    import capstone.episode as episode
    from capstone.agent import monitor
    from capstone.settings import get_settings

    for key, value in {
        "TRIAGE_RUN_MODE": "deterministic",
        "TRIAGE": "on",
        "TRIAGE_THEN_DEEP": "off",
        "CRITIC": "off",
    }.items():
        monkeypatch.setenv(key, value)
    if hasattr(get_settings, "cache_clear"):
        get_settings.cache_clear()

    def routine(look, act, **_):
        for _ in range(waits):
            act.wait(100)
        return DetectedAnomaly(
            tick=look.get_time()["tick"],
            kind="routine_check",
            description=monitor.ROUTINE_CHECK,
        )

    monkeypatch.setattr(episode, "detect_anomaly", routine)
    policy = ConcludeOnly()
    try:
        result = episode.run_episode(seed, policy, triage=True)
    finally:
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()
    state = result.state
    assert state.mode == "triage"
    assert state.termination_reason is TerminationReason.EVIDENCE_SUFFICIENT
    assert state.unanswered_questions == []
    assert all(
        r.status == "satisfied" for r in state.triage_requirement_results.values()
    )
    assert [r.reason for r in state.triage_decide_trace if r.kind == "stop"][
        -1
    ] == "requirements_complete"
    assert not any(
        e.event == "triage.completion_converted" for e in state.triage_trace_events
    )
    assert policy.asked == ["conclude"]
    check_invariants(state)


def test_a_missing_cutoff_is_a_typed_stop_not_an_assert():
    """Corrupted or replayed state without a cutoff fails closed, even under -O."""
    state = state_for()
    state.triage_observation_cutoff_tick = None
    decision = choose_next_triage_read(state, deps_for(FakeProvider(answer)), "test")
    assert decision == TriageStopDecision(
        reason="data_insufficient",
        unresolved_requirement_ids=tuple(sorted(state.triage_requirements)),
    )
