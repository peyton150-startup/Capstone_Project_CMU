# The policy that puts the seven questions to language models.
# Responsibility: show a model working memory and its tools; type and check its answers.
"""A `ReasoningPolicy` backed by language models, one client per question.

    policy = ModelPolicy(clients_for_jobs(), research_tools())
    policy = ModelPolicy(clients, (*research_tools(), RECALL_SPEC))  # with recall

Every question is shown the same view of working memory, `render(state)`:
the anomaly, the time and budget left, the open questions, the evidence
with the IDs the loop gave it, the hypotheses with their confidence and the
IDs they cite, and, once they exist, the conclusion and the action. It
shows no bookkeeping (decision records, counters) and no list of possible
causes: the model has to find the cause in the evidence.

Each question has its own system prompt and its own answer type. The
client puts that type's schema in the prompt and refuses a reply that does
not match it with a `ValueError`, which the loop records as an invalid
decision. This policy adds the one check a schema cannot express, also as
a `ValueError`: a decision may call only a tool it was shown.

The policy never changes `state`. What it keeps is its own record of each
model question (`calls`): the job, whether it was answered, and every
model tried with the reason each gave no answer.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, JsonValue

from capstone.agent.artifacts import AgentConclusion, VerificationCheck
from capstone.agent.policy import (
    ActionRequest,
    CallTool,
    Decision,
    Interpretation,
    Lesson,
    LoopPhase,
    Stop,
)
from capstone.agent.state import InvestigationState, Question
from capstone.contracts import Contract
from capstone.contracts.evidence import Evidence
from capstone.contracts.tools import ToolSpec
from capstone.providers.chat import JOBS, Attempt
from capstone.providers.factory import TOOL_DESCRIPTIONS

Answer = TypeVar("Answer", bound=BaseModel)

# The most of one piece of evidence a prompt shows. The factory already
# refuses answers over 300 rows; this keeps a prompt of many answers small.
MAX_EVIDENCE_CHARS = 2000
# How many of the latest failed calls a prompt shows, so they can be corrected.
RECENT_FAILURES = 3


class Client(Protocol):
    """Anything that asks one question and returns one typed answer."""

    def ask(self, system: str, prompt: str, answer_type: type[Answer]) -> Answer: ...


# --- the answer types a model fills in -----------------------------------------


class PlanAnswer(Contract):
    questions: tuple[Question, ...] = ()


class NextStep(Contract):
    decision: CallTool | Stop


class ConcludeAnswer(Contract):
    conclusion: AgentConclusion
    action: ActionRequest | None = None


class Judgement(Contract):
    """The model's verdict only. The prediction and the tick come from the loop."""

    outcome: Literal["resolved", "not_resolved", "inconclusive"]
    evidence_ids: tuple[str, ...] = ()


class LessonAnswer(Contract):
    lesson: str | None = None


class ModelCall(Contract):
    """One question put to a model, for the record. Not part of working memory."""

    job: str
    outcome: Literal["answered", "invalid_reply", "no_answer"]
    answered_by: str | None = None
    attempts: tuple[Attempt, ...] = ()


# --- what every question is shown ----------------------------------------------


def compact(value: JsonValue) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def shown(content: str) -> str:
    """Evidence content, cut to MAX_EVIDENCE_CHARS with a note saying so."""
    if len(content) <= MAX_EVIDENCE_CHARS:
        return content
    left = len(content) - MAX_EVIDENCE_CHARS
    return (
        f"{content[:MAX_EVIDENCE_CHARS]} ... [{left} more characters not shown; "
        "ask for a narrower range, a trend or a summary]"
    )


def render(state: InvestigationState) -> str:
    """Working memory as a model reads it. The same view for every question."""
    anomaly = state.anomaly
    where = f" on {anomaly.machine_id}" if anomaly.machine_id else ""
    now = "unknown" if state.last_tick is None else str(state.last_tick)
    lines = [
        f"ANOMALY ({anomaly.kind}{where}, tick {anomaly.tick}): {anomaly.description}",
        f"NOW: tick {now}",
        f"BUDGET LEFT: {state.remaining_tool_calls} research tool calls, "
        f"{state.remaining_iterations} turns, {state.remaining_followup_tool_calls} "
        "calls for checking after an action",
        "",
        "OPEN QUESTIONS:",
    ]
    for question in state.unanswered_questions:
        tests = f" [tests {question.hypothesis_id}]" if question.hypothesis_id else ""
        lines.append(f"- {question.id}: {question.text}{tests}")
    if not state.unanswered_questions:
        lines.append("(none)")

    # Which call produced each piece of evidence, from the loop's own records.
    asked: dict[str, tuple[str, dict]] = {}
    for decision in state.decisions:
        if decision.tool is not None:
            for evidence_id in decision.evidence_ids:
                asked.setdefault(evidence_id, (decision.tool, decision.arguments))
    origins = {p.evidence_id: p.origin for p in state.provenance}
    lines += ["", "EVIDENCE (IDs are given by the system; cite only these):"]
    for evidence in state.evidence:
        tool, arguments = asked.get(
            evidence.id, (evidence.source_id.split(":")[-1], {})
        )
        call = f"{tool} {compact(arguments)}" if arguments else tool
        memory = (
            " [FROM MEMORY: a past investigation's belief, not a look at the "
            "factory now]"
            if origins.get(evidence.id) == "memory"
            else ""
        )
        lines.append(
            f"- {evidence.id} {call} at tick {evidence.observed_tick}{memory}: "
            f"{shown(evidence.content)}"
        )
    if not state.evidence:
        lines.append("(none)")

    lines += ["", "HYPOTHESES:"]
    for h in state.hypotheses:
        supported = ", ".join(h.supporting_evidence_ids) or "none"
        contradicted = ", ".join(h.contradicting_evidence_ids) or "none"
        lines.append(
            f"- {h.id} (confidence {h.confidence:.2f}): {h.claim} "
            f"Supported by: {supported}. Contradicted by: {contradicted}."
        )
    if not state.hypotheses:
        lines.append("(none)")

    if state.conclusion is not None:
        c = state.conclusion
        lines += [
            "",
            f"CONCLUSION (tick {state.concluded_tick}): {c.diagnosis} "
            f"(confidence {c.confidence:.2f}, recommendation {c.recommendation}, "
            f"citing {', '.join(c.evidence_ids) or 'nothing'})",
        ]
    if state.proposed_action is not None:
        p = state.proposed_action
        lines.append(f"ACTION: {p.action} on {p.machine_id}, {p.status}.")
        if state.action_started_tick is not None:
            lines.append(
                f"WORK: started at tick {state.action_started_tick}, finished at "
                f"tick {state.action_finish_tick}."
            )
    if state.predicted_effect is not None:
        lines.append(f"PREDICTED: {state.predicted_effect}")

    failed = [d for d in state.decisions if d.outcome == "tool_error" and d.error][
        -RECENT_FAILURES:
    ]
    if failed:
        lines += ["", "RECENT FAILED CALLS (correct these; do not repeat them):"]
        for d in failed:
            lines.append(
                f"- {d.tool} {compact(d.arguments)}: {d.error.code}: {d.error.message}"
            )
    return "\n".join(lines)


def without_titles(schema: JsonValue) -> JsonValue:
    """A JSON schema without its "title" entries, which only repeat names."""
    if isinstance(schema, dict):
        return {
            key: without_titles(value)
            for key, value in schema.items()
            if key != "title" or not isinstance(value, str)
        }
    if isinstance(schema, list):
        return [without_titles(value) for value in schema]
    return schema


def tool_list(tools: Sequence[ToolSpec]) -> str:
    return "\n".join(
        f"- {t.name}: {t.description} Arguments: {compact(without_titles(t.arguments))}"
        for t in tools
    )


# --- one system prompt per question --------------------------------------------

COMMON = (
    "You are one step of an agent investigating an anomaly on a simulated factory "
    "production line. You see only what the factory's tools have returned, listed "
    "as evidence with IDs (E1, E2, ...). The system assigns those IDs: cite only "
    "IDs that appear in the evidence list and never invent one. One tick is one "
    "simulated minute. Every belief must rest on the evidence; when the evidence "
    "does not settle something, say so rather than guess."
)

SYSTEM = {
    "plan": (
        f"{COMMON}\n\nYour job: list the first things worth finding out about this "
        "anomaly, as up to five questions with ids Q1, Q2, ... Do not name a cause yet."
    ),
    "decide": (
        f"{COMMON}\n\nYour job: choose the next single tool call, or stop. Use only "
        "the tools listed, with arguments matching each one's schema. Do not repeat "
        "a call whose answer is already in the evidence. Set question_id when the "
        "call answers an open question, and hypothesis_id when it tests a "
        "hypothesis. Stop with evidence_sufficient when the evidence answers what "
        "this stage needs, or no_useful_action when no listed tool would help."
    ),
    "interpret": (
        f"{COMMON}\n\nYour job: say what the newest evidence means. Give the full "
        "revised set of hypotheses (keep each one's id, set its confidence between "
        "0 and 1, and list the evidence IDs that support and that contradict it), "
        "or null for hypotheses to leave them unchanged. Add new questions only if "
        "this evidence raises them."
    ),
    "hypothesize": (
        f"{COMMON}\n\nYour job: propose two to four candidate explanations for the "
        "evidence so far, with ids H1, H2, ..., each with a confidence and the "
        "evidence IDs that support or contradict it. Consider explanations that "
        "need no change to the factory as well as ones that do. Add questions, "
        "each with the hypothesis_id it tests, whose answers would tell the "
        "explanations apart."
    ),
    "conclude": (
        f"{COMMON}\n\nYour job: state the final diagnosis in plain words: what is "
        "wrong, where it is, and the evidence for it, with your confidence. "
        "Recommend intervene only if a change a human can approve would fix it, and "
        "then give that action with a prediction an operator could check "
        "afterwards. Recommend no_action if nothing needs changing, or escalate if "
        "you cannot tell. The changes a human can approve: "
        f"{TOOL_DESCRIPTIONS['propose_action']}"
    ),
    "judge_verification": (
        f"{COMMON}\n\nYour job: judge whether the factory changed as predicted "
        "after the work. Compare evidence whose data comes from after the work "
        "finished with evidence from before it. Answer resolved, not_resolved or "
        "inconclusive, and cite the evidence IDs you compared. Evidence from "
        "before the work, or recalled from memory, cannot show the result."
    ),
    "write_lesson": (
        f"{COMMON}\n\nThe change made in this investigation was checked and it "
        "worked. Your job: write one sentence of advice for a future investigation "
        "of a similar anomaly: what to look at and what it showed. No evidence IDs "
        "or ticks. Give null if nothing is worth keeping."
    ),
}

PHASE = {
    "investigate": (
        "STAGE: investigate. Gather evidence about the anomaly and answer the open "
        "questions."
    ),
    "test": (
        "STAGE: test. Choose calls whose answers would tell the hypotheses apart: "
        "evidence that would raise one and lower another."
    ),
    "verify": (
        "STAGE: verify. The work has finished (see WORK above), or the conclusion "
        "was that nothing needed doing. Look again to see whether the prediction "
        "came true. Only data from after that point counts: let time pass with "
        "wait if needed, then ask for a tick range that starts after it."
    ),
}


class ModelPolicy:
    """The seven policy questions, each put to its own model client."""

    def __init__(self, clients: Mapping[str, Client], tools: Sequence[ToolSpec]):
        missing = [job for job in JOBS if job not in clients]
        if missing:
            raise ValueError(f"no model client for {', '.join(missing)}")
        self.clients = dict(clients)
        self.tools = tuple(tools)
        self.calls: list[ModelCall] = []

    def _ask(self, job: str, prompt: str, answer_type: type[Answer]) -> Answer:
        """Ask one question and record it, whatever happens."""
        client = self.clients[job]
        outcome = "no_answer"
        try:
            answer = client.ask(SYSTEM[job], prompt, answer_type)
            outcome = "answered"
            return answer
        except ValueError:
            outcome = "invalid_reply"
            raise
        finally:
            self.calls.append(
                ModelCall(
                    job=job,
                    outcome=outcome,
                    answered_by=getattr(client, "answered_by", None)
                    if outcome == "answered"
                    else None,
                    attempts=tuple(getattr(client, "attempts", ())),
                )
            )

    def _refuse(self, reason: str) -> None:
        """A reply that matched its schema but cannot be used: the model's mistake."""
        self.calls[-1] = self.calls[-1].model_copy(update={"outcome": "invalid_reply"})
        raise ValueError(reason)

    def plan(self, state: InvestigationState) -> tuple[Question, ...]:
        return self._ask("plan", render(state), PlanAnswer).questions

    def decide(self, state: InvestigationState, phase: LoopPhase) -> Decision:
        prompt = (
            f"{render(state)}\n\n{PHASE[phase]}\n\n"
            f"TOOLS YOU MAY CALL:\n{tool_list(self.tools)}"
        )
        decision = self._ask("decide", prompt, NextStep).decision
        offered = {t.name for t in self.tools}
        if isinstance(decision, CallTool) and decision.request.name not in offered:
            self._refuse(f"{decision.request.name} is not a tool offered here")
        return decision

    def interpret(
        self, state: InvestigationState, step: CallTool, evidence: Evidence
    ) -> Interpretation:
        testing = f", testing {step.hypothesis_id}" if step.hypothesis_id else ""
        prompt = (
            f"{render(state)}\n\nJUST ASKED: {step.request.name} "
            f"{compact(step.request.arguments)}, to learn: "
            f"{step.information_needed}{testing}. Its answer is {evidence.id} above."
        )
        return self._ask("interpret", prompt, Interpretation)

    def hypothesize(self, state: InvestigationState) -> Interpretation:
        return self._ask("hypothesize", render(state), Interpretation)

    def conclude(
        self, state: InvestigationState
    ) -> tuple[AgentConclusion, ActionRequest | None]:
        answer = self._ask("conclude", render(state), ConcludeAnswer)
        return answer.conclusion, answer.action

    def judge_verification(self, state: InvestigationState) -> VerificationCheck:
        verdict = self._ask("judge_verification", render(state), Judgement)
        return VerificationCheck(
            outcome=verdict.outcome,
            prediction=state.predicted_effect or "no prediction was recorded",
            evidence_ids=verdict.evidence_ids,
        )

    def write_lesson(self, state: InvestigationState) -> Lesson | None:
        text = self._ask("write_lesson", render(state), LessonAnswer).lesson
        return Lesson(text=text.strip()) if text and text.strip() else None
