"""The model-backed policy, with fake model clients and no network.

A fake client answers with JSON text, which is turned into the answer type
the same way the real client does it, so a reply that breaks the schema
fails here exactly as it would against a real model.
"""

import json
import re

import pytest

from capstone.agent.artifacts import AgentConclusion, ProposalRecord
from capstone.agent.model_policy import (
    MAX_EVIDENCE_CHARS,
    SYSTEM,
    ConcludeAnswer,
    Judgement,
    LessonAnswer,
    ModelPolicy,
    NextStep,
    PlanAnswer,
    render,
)
from capstone.agent.policy import CallTool, Interpretation, Stop
from capstone.agent.state import DecisionRecord, Question
from capstone.contracts.evidence import Evidence
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.provenance import ProvenanceReference
from capstone.contracts.tools import ToolError, ToolRequest
from capstone.episode import run_episode
from capstone.providers.chat import JOBS, ChatClient, FallbackClient
from capstone.providers.factory import research_tools
from capstone.providers.recall import RECALL_SPEC
from capstone.tools.diagnosis import FAULT_KINDS
from tests.helpers import new_state

ANSWER_TYPES = (PlanAnswer, NextStep, Interpretation, ConcludeAnswer, Judgement)


class FakeModel:
    """Answers each question from a queue of replies (JSON-able or callables
    of the prompt), and remembers what it was asked."""

    answered_by = "fake/model"
    attempts = ()

    def __init__(self, *replies):
        self.replies = list(replies)
        self.asked = []

    def ask(self, system, prompt, answer_type):
        self.asked.append((system, prompt, answer_type))
        reply = self.replies.pop(0)
        if callable(reply):
            reply = reply(prompt)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return answer_type.model_validate_json(text)


def policy(tools=None, **replies):
    clients = {job: FakeModel(*replies.get(job, ())) for job in JOBS}
    return ModelPolicy(clients, research_tools() if tools is None else tools)


def call(tool, question_id=None, **arguments):
    decision = {
        "information_needed": f"what {tool} shows",
        "request": {"name": tool, "arguments": arguments},
    }
    if question_id is not None:
        decision["question_id"] = question_id
    return {"decision": decision}


def state_with_evidence():
    state = new_state()
    state.last_tick = 914
    state.evidence = [
        Evidence(
            id="E1",
            source_id="simulator:get_sensor_summary",
            source_type="tool_result",
            content='{"mean": 3.1}',
            observed_tick=914,
        ),
        Evidence(
            id="E2",
            source_id="memory:recall_memories",
            source_type="tool_result",
            content='[{"lesson": "look at the trend"}]',
            observed_tick=914,
        ),
    ]
    state.provenance = [
        ProvenanceReference(
            evidence_id="E1",
            source_id="simulator:get_sensor_summary",
            source_type="tool_result",
            origin="observable",
            observed_tick=914,
        ),
        ProvenanceReference(
            evidence_id="E2",
            source_id="memory:recall_memories",
            source_type="tool_result",
            origin="memory",
            observed_tick=914,
        ),
    ]
    state.decisions = [
        DecisionRecord(
            sequence=1,
            phase="investigate",
            information_needed="vibration",
            tool="get_sensor_summary",
            arguments={"machine_id": "CNC-02", "from_tick": 614, "to_tick": 914},
            outcome="observed",
            evidence_ids=("E1",),
            confidence=0.0,
        ),
        DecisionRecord(
            sequence=2,
            phase="investigate",
            information_needed="raw vibration",
            tool="get_readings",
            arguments={"machine_id": "CNC-02", "from_tick": 0, "to_tick": 914},
            outcome="tool_error",
            confidence=0.0,
            error=ToolError(
                code="invalid_arguments", message="914 rows is more than 300"
            ),
        ),
    ]
    state.hypotheses = [
        Hypothesis(
            id="H1",
            claim="CNC-02 is wearing",
            confidence=0.6,
            supporting_evidence_ids=("E1",),
        )
    ]
    state.unanswered_questions = [
        Question(id="Q2", text="Is the rise gradual?", hypothesis_id="H1")
    ]
    return state


# --- what a model is shown ------------------------------------------------------


def test_the_view_shows_anomaly_questions_evidence_and_beliefs_with_their_ids():
    text = render(state_with_evidence())
    assert "ANOMALY (alarm on CNC-02, tick 10): High vibration" in text
    assert "NOW: tick 914" in text
    assert "- Q2: Is the rise gradual? [tests H1]" in text
    assert (
        '- E1 get_sensor_summary {"from_tick":614,"machine_id":"CNC-02",'
        '"to_tick":914} at tick 914: {"mean": 3.1}' in text
    )
    assert "- H1 (confidence 0.60): CNC-02 is wearing Supported by: E1." in text


def test_a_memory_is_shown_as_a_past_belief_not_a_look_now():
    text = render(state_with_evidence())
    [line] = [line for line in text.splitlines() if line.startswith("- E2")]
    assert "FROM MEMORY" in line and "not a look at the factory now" in line


def test_a_failed_call_is_shown_with_what_to_correct():
    text = render(state_with_evidence())
    assert "RECENT FAILED CALLS" in text
    assert "invalid_arguments: 914 rows is more than 300" in text


def test_the_view_holds_no_bookkeeping():
    text = render(state_with_evidence())
    for word in ("sequence", "iteration_count", "seen_calls", "unproductive"):
        assert word not in text


def test_long_evidence_is_cut_with_a_note_saying_how_to_ask_for_less():
    state = state_with_evidence()
    state.evidence[0] = state.evidence[0].model_copy(
        update={"content": "x" * (MAX_EVIDENCE_CHARS + 500)}
    )
    text = render(state)
    assert "x" * (MAX_EVIDENCE_CHARS + 1) not in text
    assert "500 more characters not shown" in text


def test_no_prompt_or_answer_schema_lists_the_possible_causes():
    """The model must find the cause in the evidence, not pick it from a list."""
    texts = [*SYSTEM.values()]
    texts += [json.dumps(t.model_json_schema()) for t in ANSWER_TYPES]
    texts += [
        json.dumps(spec.model_dump()) for spec in (*research_tools(), RECALL_SPEC)
    ]
    texts.append(render(state_with_evidence()))
    joined = " ".join(texts).lower()
    assert not [kind for kind in FAULT_KINDS if kind in joined]
    assert not [kind for kind in FAULT_KINDS if kind.replace("_", " ") in joined]


def test_the_client_puts_the_answer_schema_in_the_system_prompt():
    sent = []

    def transport(url, headers, body, timeout):
        sent.append(json.loads(body))
        reply = {"choices": [{"message": {"content": '{"questions": []}'}}]}
        return json.dumps(reply).encode()

    client = ChatClient("https://example.test", "k", "m", transport=transport)
    ModelPolicy({job: client for job in JOBS}, research_tools()).plan(new_state())
    system = sent[0]["messages"][0]["content"]
    assert system.startswith(SYSTEM["plan"])
    assert '"questions"' in system


# --- each question, and its answer -----------------------------------------------


def test_a_plan_is_a_list_of_questions():
    agent = policy(plan=[{"questions": [{"id": "Q1", "text": "When did it start?"}]}])
    assert agent.plan(new_state()) == (Question(id="Q1", text="When did it start?"),)


def test_a_decision_is_a_tool_call_or_a_stop():
    agent = policy(
        decide=[
            call("get_sensor_trend", machine_id="CNC-02", sensor="vibration"),
            {"decision": {"reason": "evidence_sufficient"}},
        ]
    )
    first = agent.decide(new_state(), "investigate")
    assert isinstance(first, CallTool) and first.request.name == "get_sensor_trend"
    assert isinstance(agent.decide(new_state(), "investigate"), Stop)


def test_the_decision_prompt_names_the_stage_and_the_tools_with_their_schemas():
    agent = policy(decide=[{"decision": {"reason": "no_useful_action"}}])
    agent.decide(new_state(), "test")
    _, prompt, _ = agent.clients["decide"].asked[0]
    assert "STAGE: test." in prompt
    assert "- get_sensor_trend: " in prompt and '"bucket_ticks"' in prompt
    for procedure in ("propose_action", "execute_action", "get_proposals"):
        assert f"- {procedure}:" not in prompt
    assert "recall_memories" not in prompt


def test_recall_is_offered_only_when_given():
    agent = policy(
        tools=(*research_tools(), RECALL_SPEC),
        decide=[call("recall_memories", text="vibration alarm")],
    )
    decision = agent.decide(new_state(), "investigate")
    assert decision.request.name == "recall_memories"
    assert "- recall_memories: " in agent.clients["decide"].asked[0][1]


@pytest.mark.parametrize("tool", ["propose_action", "execute_action", "approve"])
def test_a_call_to_a_tool_not_offered_is_refused_and_counted_against_the_model(
    tool,
):
    agent = policy(decide=[call(tool, proposal_id=1)])
    with pytest.raises(ValueError, match="not a tool offered here"):
        agent.decide(new_state(), "investigate")
    assert agent.calls[-1].outcome == "invalid_reply"


def test_a_reply_that_breaks_the_answer_type_is_refused():
    agent = policy(decide=['{"decision": {"reason": "i am done"}}'])
    with pytest.raises(ValueError):
        agent.decide(new_state(), "investigate")
    assert agent.calls[-1].outcome == "invalid_reply"


def test_interpreting_is_told_which_call_was_just_made():
    agent = policy(interpret=[{"hypotheses": None}])
    step = CallTool(
        information_needed="whether vibration rose gradually",
        request=ToolRequest(name="get_sensor_trend", arguments={"to_tick": 914}),
        hypothesis_id="H1",
    )
    state = state_with_evidence()
    assert agent.interpret(state, step, state.evidence[0]) == Interpretation()
    prompt = agent.clients["interpret"].asked[0][1]
    assert 'JUST ASKED: get_sensor_trend {"to_tick":914}' in prompt
    assert "testing H1" in prompt and "Its answer is E1 above." in prompt


def test_a_conclusion_comes_with_an_action_or_none():
    concluded = {
        "diagnosis": "CNC-02 is wearing",
        "confidence": 0.9,
        "recommendation": "no_action",
    }
    agent = policy(conclude=[{"conclusion": concluded}])
    conclusion, action = agent.conclude(state_with_evidence())
    assert conclusion == AgentConclusion(**concluded) and action is None
    assert "replace_bearing" in SYSTEM["conclude"]  # the actions, not the causes


def test_a_judgement_keeps_the_prediction_recorded_before_the_action():
    state = state_with_evidence()
    state.predicted_effect = "vibration falls"
    agent = policy(judge_verification=[{"outcome": "resolved", "evidence_ids": ["E1"]}])
    check = agent.judge_verification(state)
    assert (check.outcome, check.prediction, check.evidence_ids) == (
        "resolved",
        "vibration falls",
        ("E1",),
    )


@pytest.mark.parametrize("lesson", [None, "", "   "])
def test_no_lesson_is_none(lesson):
    agent = policy(write_lesson=[{"lesson": lesson}])
    assert agent.write_lesson(new_state()) is None


def test_the_policy_never_changes_the_state_it_is_shown():
    state = state_with_evidence()
    before = state.model_dump()
    agent = policy(
        plan=[{"questions": []}],
        hypothesize=[{"hypotheses": None}],
        write_lesson=[LessonAnswer(lesson="x").model_dump()],
    )
    agent.plan(state)
    agent.hypothesize(state)
    agent.write_lesson(state)
    assert state.model_dump() == before


def test_every_job_needs_a_client():
    with pytest.raises(ValueError, match="no model client for decide"):
        ModelPolicy({job: FakeModel() for job in JOBS if job != "decide"}, ())


# --- the record of each model question -------------------------------------------


def test_each_question_records_the_models_tried_and_why_each_failed():
    from tests.test_chat_client import UNREACHABLE, chat, client

    groq, _ = client(UNREACHABLE, UNREACHABLE, model="groq")
    mistral, _ = client(chat('{"questions": []}'), model="mistral")
    fallback = FallbackClient([groq, mistral], sleep=lambda s: None)
    clients = {job: FakeModel() for job in JOBS} | {"plan": fallback}
    agent = ModelPolicy(clients, ())
    agent.plan(new_state())
    [made] = agent.calls
    assert (made.job, made.outcome, made.answered_by) == ("plan", "answered", "mistral")
    assert [(a.model, a.outcome) for a in made.attempts] == [
        ("groq", "the model service could not be reached"),
        ("groq", "the model service could not be reached"),
        ("mistral", "answered"),
    ]


# --- a whole episode through the model policy -------------------------------------


def number(pattern, prompt):
    return int(re.search(pattern, prompt).group(1))


def latest_evidence(prompt):
    return max(int(n) for n in re.findall(r"^- E(\d+) ", prompt, re.MULTILINE))


def verify_look(prompt):
    since = number(r"finished at tick (\d+)", prompt)
    now = number(r"NOW: tick (\d+)", prompt)
    return call(
        "get_sensor_summary",
        machine_id="CNC-02",
        sensor="vibration",
        from_tick=since + 1,
        to_tick=now,
    )


def judge(prompt):
    return {
        "outcome": "resolved",
        "evidence_ids": ["E2", f"E{latest_evidence(prompt)}"],
    }


def believe(confidence, *evidence_ids):
    return {
        "hypotheses": [
            {
                "id": "H1",
                "claim": "the alarmed machine is wearing",
                "confidence": confidence,
                "supporting_evidence_ids": list(evidence_ids),
            }
        ]
    }


def scripted_models():
    """Replies a model might give on seed 6, worked out from the prompt alone."""
    return policy(
        plan=[{"questions": [{"id": "Q1", "text": "How has vibration changed?"}]}],
        decide=[
            lambda p: call(
                "get_sensor_summary",
                question_id="Q1",
                machine_id="CNC-02",
                sensor="vibration",
                from_tick=number(r"tick (\d+)\):", p) - 300,
                to_tick=number(r"tick (\d+)\):", p),
            ),
            {"decision": {"reason": "evidence_sufficient"}},
            lambda p: call(
                "get_sensor_trend",
                machine_id="CNC-02",
                sensor="vibration",
                from_tick=number(r"NOW: tick (\d+)", p) - 600,
                to_tick=number(r"NOW: tick (\d+)", p),
                bucket_ticks=100,
            ),
            call("wait", ticks=300),
            verify_look,
            {"decision": {"reason": "evidence_sufficient"}},
        ],
        interpret=[
            {"hypotheses": None},
            believe(0.95, "E2", "E3"),
            {"hypotheses": None},
            {"hypotheses": None},
        ],
        hypothesize=[believe(0.6, "E2")],
        conclude=[
            {
                "conclusion": {
                    "diagnosis": "the spindle bearing on CNC-02 is wearing",
                    "confidence": 0.95,
                    "recommendation": "intervene",
                    "hypothesis_id": "H1",
                    "evidence_ids": ["E2", "E3"],
                },
                "action": {
                    "machine_id": "CNC-02",
                    "action": "replace_bearing",
                    "reason": "vibration climbed in every block",
                    "prediction": "vibration on CNC-02 falls back",
                },
            }
        ],
        judge_verification=[judge],
    )


def test_a_whole_episode_runs_on_model_replies_alone():
    agent = scripted_models()
    result = run_episode(6, agent, fault="bearing_degradation", clock=lambda: 0.0)
    state = result.state
    assert state.proposed_action == ProposalRecord(
        proposal_id=1,
        machine_id="CNC-02",
        action="replace_bearing",
        reason="vibration climbed in every block",
        status="approved",
    )
    assert state.verification.outcome == "resolved"
    assert result.score.action_correct and result.score.resolved
    assert [c.job for c in agent.calls] == [
        "plan",
        "decide",
        "interpret",
        "decide",
        "hypothesize",
        "decide",
        "interpret",
        "conclude",
        "decide",
        "interpret",
        "decide",
        "interpret",
        "decide",
        "judge_verification",
    ]
    assert all(c.outcome == "answered" for c in agent.calls)
    # The check looked at data from after the work, which the view had shown.
    check_prompt = agent.clients["judge_verification"].asked[0][1]
    assert f"finished at tick {state.action_finish_tick}" in check_prompt


class Slow:
    """Wraps a model client so that every answer takes `seconds` on `clock`."""

    def __init__(self, client, clock, seconds):
        self.client, self.clock, self.seconds = client, clock, seconds
        self.answered_by, self.attempts = client.answered_by, client.attempts
        self.asked = client.asked

    def ask(self, system, prompt, answer_type):
        self.clock[0] += self.seconds
        return self.client.ask(system, prompt, answer_type)


def slow_episode(seconds_per_answer, **budgets):
    from capstone.agent.state import Budgets

    clock = [0.0]
    agent = scripted_models()
    agent.clients = {
        job: Slow(client, clock, seconds_per_answer)
        for job, client in agent.clients.items()
    }
    return run_episode(
        6,
        agent,
        fault="bearing_degradation",
        clock=lambda: clock[0],
        budgets=Budgets(**budgets),
    )


def test_the_default_budget_fits_a_whole_episode_at_eight_seconds_an_answer():
    result = slow_episode(8.0)
    assert result.state.termination_reason != "timeout"
    assert result.state.verification.outcome == "resolved"
    assert result.score.resolved


def test_the_old_sixty_second_budget_did_not():
    """At 8 s an answer, 60 s ran out after two tool calls, with nothing found."""
    result = slow_episode(8.0, timeout_seconds=60.0, followup_seconds=20.0)
    state = result.state
    assert state.termination_reason == "timeout"
    assert state.conclusion.diagnosis == "undetermined"
    assert state.proposed_action is None and not result.score.resolved
