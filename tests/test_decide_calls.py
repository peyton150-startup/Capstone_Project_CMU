"""DECIDE_CALLS: several tool calls in one decide answer, read in one question.

Scripted policies, a fake factory and fake model clients; no network or key.
"""

import json

import pytest
from pydantic import ValidationError

from capstone.agent.artifacts import TerminationReason
from capstone.agent.loop import InvestigationDeps, batch_steps, run_inner_loop
from capstone.agent.model_policy import (
    DECIDE_CALLS_NOTE,
    ModelPolicy,
    NextStep,
    NextSteps,
    StepAnswer,
    StepsAnswer,
)
from capstone.agent.policy import CallTool, CallTools, Interpretation, InterpretedStep
from capstone.experiment import format_batches
from capstone.progress import call_lines, run_header
from capstone.providers.chat import JOBS
from capstone.providers.factory import research_tools
from capstone.settings import Settings
from tests.helpers import FakeProvider, ScriptedPolicy, ask, new_state


def wait(ticks=10):
    return ask("wait", ticks=ticks)


def several(*steps):
    return CallTools(steps=steps)


class BatchPolicy(ScriptedPolicy):
    """Reads one result or several in one question, as a model-backed policy does."""

    def __init__(self, decisions):
        super().__init__(decisions)
        self.read: list[tuple[str, ...]] = []

    def interpret_and_decide(self, state, phase, step, evidence):
        self.read.append((evidence.id,))
        return InterpretedStep(
            interpretation=Interpretation(), decision=self.decide(state, phase)
        )

    def interpret_and_decide_many(self, state, phase, steps):
        self.read.append(tuple(evidence.id for _, evidence in steps))
        return InterpretedStep(
            interpretation=Interpretation(), decision=self.decide(state, phase)
        )

    def interpret(self, *args):
        pytest.fail("one-question mode must not ask a separate interpretation")


def run(decisions, *, calls=3, max_tool_calls=10):
    """Run one investigate loop with DECIDE_CALLS=`calls`; return what happened."""
    state = new_state(max_tool_calls=max_tool_calls)
    policy = BatchPolicy(decisions)
    provider = FakeProvider()
    reason = run_inner_loop(
        state,
        InvestigationDeps(
            provider, policy, clock=lambda: 0, step_questions=1, decide_calls=calls
        ),
        "investigate",
    )
    return state, policy, provider, reason


# --- which calls run ---------------------------------------------------------------


def test_one_call_is_untouched():
    assert batch_steps(ask("a"), 3, 10) == ([ask("a")], 0, 0, 0)


def test_a_list_runs_in_order_up_to_the_limit():
    steps, at_wait, over, for_budget = batch_steps(
        several(ask("a"), ask("b"), ask("c"), ask("d")), 3, 10
    )
    assert [s.request.name for s in steps] == ["a", "b", "c"]
    assert (at_wait, over, for_budget) == (0, 1, 0)


def test_a_wait_after_reads_is_cut_with_everything_after_it():
    steps, at_wait, _, _ = batch_steps(several(ask("a"), wait(), ask("b")), 3, 10)
    assert [s.request.name for s in steps] == ["a"]
    assert at_wait == 2


def test_a_wait_listed_first_runs_alone():
    steps, at_wait, _, _ = batch_steps(several(wait(), ask("a"), ask("b")), 3, 10)
    assert [s.request.name for s in steps] == ["wait"]
    assert at_wait == 2


def test_a_list_is_cut_to_the_budget_left_but_never_below_one_call():
    steps, _, _, for_budget = batch_steps(several(ask("a"), ask("b"), ask("c")), 3, 2)
    assert [s.request.name for s in steps] == ["a", "b"]
    assert for_budget == 1
    assert len(batch_steps(several(ask("a"), ask("b")), 3, 0)[0]) == 1


# --- the loop ----------------------------------------------------------------------


def test_three_reads_in_one_answer_run_in_order_and_are_read_in_one_question():
    state, policy, provider, _ = run([several(ask("a"), ask("b"), ask("c"))])
    assert [c.name for c in provider.calls] == ["a", "b", "c"]
    # One question read all three results; the next answer stopped.
    assert policy.read == [("E1", "E2", "E3")]
    assert state.tool_call_count == 3
    # The three calls used one turn; the second turn was the stop.
    assert state.iteration_count == 2
    observed = [d for d in state.decisions if d.tool is not None]
    assert [(d.batch, d.batch_position) for d in observed] == [(1, 1), (1, 2), (1, 3)]
    trace = state.decide_batches
    assert (trace.answers, trace.chosen, trace.run, trace.read_together) == (1, 3, 3, 1)


def test_a_wait_in_a_list_does_not_run_and_the_reads_before_it_do():
    state, _, provider, _ = run([several(ask("a"), wait(), ask("b"))])
    assert [c.name for c in provider.calls] == ["a"]
    assert provider.tick == 10  # the factory did not move
    assert state.decide_batches.cut_at_wait == 2


def test_a_wait_listed_first_moves_the_factory_and_nothing_else_runs():
    state, _, provider, _ = run([several(wait(10), ask("a"))])
    assert [c.name for c in provider.calls] == ["wait"]
    assert provider.tick == 20
    assert state.decide_batches.cut_at_wait == 1


def test_a_list_never_spends_more_calls_than_the_budget():
    state, _, provider, reason = run(
        [several(ask("a"), ask("b"), ask("c"))], max_tool_calls=2
    )
    assert [c.name for c in provider.calls] == ["a", "b"]
    assert reason is TerminationReason.MAX_TOOL_CALLS
    assert state.decide_batches.cut_for_budget == 1


def test_a_repeat_inside_a_list_costs_no_call_and_is_not_read():
    state, policy, provider, _ = run([several(ask("a"), ask("a"), ask("b"))])
    assert [c.name for c in provider.calls] == ["a", "b"]
    assert state.repeated_calls == 1
    assert policy.read == [("E1", "E2")]


def test_with_the_default_of_one_a_list_runs_only_its_first_call_and_leaves_no_trace():
    state, policy, provider, _ = run([several(ask("a"), ask("b"))], calls=1)
    assert [c.name for c in provider.calls] == ["a"]
    assert state.decide_batches is None
    assert all(d.batch is None for d in state.decisions)
    assert policy.read == [("E1",)]


class OneAtATime(ScriptedPolicy):
    """Reads one result per question, and cannot read several together."""

    def interpret_and_decide(self, state, phase, step, evidence):
        raise AssertionError("not asked in this test")


def test_batching_in_one_question_mode_needs_a_policy_that_reads_several():
    with pytest.raises(ValueError, match="interpret_and_decide_many"):
        InvestigationDeps(
            FakeProvider(),
            OneAtATime([]),
            step_questions=1,
            decide_calls=3,
        )


def test_decide_calls_is_limited_to_the_documented_range():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, DECIDE_CALLS=6)
    assert Settings(_env_file=None).decide_calls == 1


# --- what the model is asked ---------------------------------------------------------


class FakeModel:
    """Answers from a queue and remembers each system prompt and answer type."""

    answered_by = "fake/model"
    attempts = ()

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = []

    def ask(self, system, prompt, answer_type, *, max_seconds=None):
        self.asked.append((system, prompt, answer_type))
        return answer_type.model_validate_json(json.dumps(self.replies.pop(0)))


def model_policy(*replies):
    clients = {job: FakeModel() for job in JOBS}
    clients["decide"] = FakeModel(*replies)
    return ModelPolicy(clients, research_tools())


def listed(*tools):
    return {
        "choice": "call_tools",
        "information_needed": "readings to compare",
        "calls": [
            {"tool": tool, "arguments": {}, "information_needed": f"what {tool} shows"}
            for tool in tools
        ],
    }


def one_call(tool):
    return {"choice": "call_tool", "information_needed": "x", "tool": tool}


def test_with_one_call_per_answer_the_question_is_exactly_as_before():
    p = model_policy(one_call("get_events"))
    state = new_state()
    decision = p.decide(state, "investigate")
    [(system, _, answer_type)] = p.clients["decide"].asked
    assert answer_type is NextStep
    assert DECIDE_CALLS_NOTE.split("{")[0] not in system
    assert isinstance(decision, CallTool)


def test_above_one_the_model_may_list_calls_and_is_told_the_limit():
    p = model_policy(listed("get_events", "get_inspections"))
    state = new_state()
    state.decide_calls = 3
    decision = p.decide(state, "investigate")
    [(system, _, answer_type)] = p.clients["decide"].asked
    assert answer_type is NextSteps
    assert "You may list up to 3 tool calls" in system
    assert isinstance(decision, CallTools)
    assert [s.request.name for s in decision.steps] == [
        "get_events",
        "get_inspections",
    ]


def test_a_list_of_one_becomes_a_single_call():
    p = model_policy(listed("get_events"))
    state = new_state()
    state.decide_calls = 3
    assert isinstance(p.decide(state, "investigate"), CallTool)


def test_a_list_naming_a_tool_not_offered_is_refused():
    p = model_policy(listed("get_events", "replace_everything"))
    state = new_state()
    state.decide_calls = 3
    with pytest.raises(ValueError, match="not a tool offered here"):
        p.decide(state, "investigate")


def test_a_stop_may_not_list_calls():
    with pytest.raises(ValidationError):
        NextSteps.model_validate(
            {
                "choice": "stop",
                "stop_reason": "evidence_sufficient",
                "information_needed": "x",
                "calls": [{"tool": "get_events", "information_needed": "x"}],
            }
        )


def test_several_results_are_named_in_one_numbered_question():
    from capstone.contracts.evidence import Evidence

    reply = listed("get_events") | {"interpretation": {}}
    p = model_policy(reply)
    state = new_state()
    state.decide_calls = 3
    evidence = [
        Evidence(
            id=f"E{n}",
            source_id="simulator:x",
            source_type="tool_result",
            content="{}",
            observed_tick=10,
        )
        for n in (1, 2)
    ]
    state.evidence = list(evidence)
    pairs = ((ask("get_events"), evidence[0]), (ask("get_inspections"), evidence[1]))
    p.interpret_and_decide_many(state, "investigate", pairs)
    [(system, prompt, answer_type)] = p.clients["decide"].asked
    assert answer_type is StepsAnswer
    assert "JUST ASKED, in this order, before you saw any answer:" in prompt
    assert "1. get_events" in prompt and "Its answer is E1 above." in prompt
    assert "2. get_inspections" in prompt and "Its answer is E2 above." in prompt


def test_the_single_combined_question_is_unchanged_with_the_default():
    from capstone.contracts.evidence import Evidence

    p = model_policy(one_call("get_events") | {"interpretation": {}})
    state = new_state()
    evidence = Evidence(
        id="E1",
        source_id="simulator:x",
        source_type="tool_result",
        content="{}",
        observed_tick=10,
    )
    state.evidence = [evidence]
    p.interpret_and_decide(state, "investigate", ask("get_events"), evidence)
    [(system, prompt, answer_type)] = p.clients["decide"].asked
    assert answer_type is StepAnswer
    assert "JUST ASKED: get_events" in prompt
    assert "You may list up to" not in system


# --- the trace ----------------------------------------------------------------------


def test_the_live_view_names_each_calls_answer_and_place():
    state, _, _, _ = run([several(ask("a"), ask("b"))])
    first = next(d for d in state.decisions if d.tool == "b")
    assert "[batch 1.2]" in call_lines(first, state)[0]


class Kept:
    def __init__(self, trace):
        self.decide_batches = trace


def test_the_report_line_sums_the_batches():
    state, _, _, _ = run([several(ask("a"), ask("b"), wait())])
    line = format_batches([Kept(state.decide_batches), Kept(None)])
    assert line.startswith("decide batches: 1 run(s), 1 answers chose 3 calls")
    assert "ran 2 (2.0 per answer)" in line
    assert "cut 1 at a wait" in line
    assert format_batches([Kept(None)]) is None


class HeaderSettings:
    critic = False
    critic_blind = False
    critic_followup = False
    manual_step = False
    embedding_model = "e"

    def __init__(self, calls=1):
        self.decide_calls = calls


def test_the_run_header_names_the_limit_only_above_one():
    assert len(run_header(HeaderSettings(), manual=None)) == 2
    assert run_header(HeaderSettings(3), manual=None)[2] == (
        "RUN: up to 3 tool calls per decide answer"
    )
