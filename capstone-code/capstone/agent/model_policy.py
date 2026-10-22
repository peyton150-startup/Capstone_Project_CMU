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

The evidence section has a total size (`MAX_EVIDENCE_SECTION_CHARS`).
The newest evidence and evidence a belief cites are shown whole first, then
the rest newest first while they fit; what does not fit is listed by its
ID and call alone, with a note saying so. Everything else is always shown.

Each question has its own system prompt and its own answer type. The
client puts that type's schema in the prompt and refuses a reply that does
not match it with a `ValueError`, which the loop records as an invalid
decision. This policy adds the one check a schema cannot express, also as
a `ValueError`: a decision may call only a tool it was shown.

The policy never changes `state`. What it keeps is its own record of each
model question (`calls`): the job, whether it was answered, and every
model tried with the reason each gave no answer.

A question may take no longer than the time its stage has left, which the
loop writes on the copy of state it hands over (`seconds_for_question`):
the client is asked to stop waiting then. A question with no answer in
that time raises `ModelError`, and the loop, which owns the clock, decides
whether that was the clock or an outage.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, Field, JsonValue, model_validator

from capstone.agent.artifacts import (
    AgentConclusion,
    TerminationReason,
    VerificationCheck,
)
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
from capstone.contracts.tools import ToolRequest, ToolSpec
from capstone.providers.chat import JOBS, Attempt, invalid_outcome
from capstone.providers.factory import TOOL_DESCRIPTIONS

Answer = TypeVar("Answer", bound=BaseModel)

# The most of one piece of evidence a prompt shows. The factory already
# refuses answers over 300 rows; this keeps a prompt of many answers small.
MAX_EVIDENCE_CHARS = 2000
# The most the whole evidence section may take. About 3,000 tokens, so a
# prompt still fits a small model's context; an estimate, not yet measured.
MAX_EVIDENCE_SECTION_CHARS = 12_000
# How many of the latest failed calls a prompt shows, so they can be corrected.
RECENT_FAILURES = 3
# At or below this many research calls left, the prompt adds LOW_BUDGET_NOTE.
LOW_CALLS = 2
LOW_BUDGET_NOTE = (
    "NOTE: few calls remain; choose the one that best separates the hypotheses."
)

EVIDENCE_HEADER = "EVIDENCE (IDs are given by the system; cite only these):"
# How evidence that is not a look at the factory is marked in every prompt.
ORIGIN_LABELS = {
    "memory": " [FROM MEMORY: a past investigation's belief, not a look at the "
    "factory now]",
    "manual": " [FROM THE MANUAL: general guidance for this machine model, not a "
    "look at the factory now; confirm it with the factory's own data]",
}


class Client(Protocol):
    """Anything that asks one question and returns one typed answer."""

    def ask(
        self,
        system: str,
        prompt: str,
        answer_type: type[Answer],
        *,
        max_seconds: float | None = None,
    ) -> Answer: ...


# --- the answer types a model fills in -----------------------------------------


class PlanAnswer(Contract):
    questions: tuple[Question, ...] = ()


# Flat on purpose. Asked for `CallTool | Stop`, a model answered with the
# definition's name as a key ({"CallTool": {...}}), which is refused, not
# repaired; plain named fields leave nothing to nest. This is a comment, not
# the docstring, because the docstring goes into the schema the model reads.
class NextStep(Contract):
    """The next step: a tool call (choice call_tool) or a stop (choice stop)."""

    choice: Literal["call_tool", "stop"]
    information_needed: str = Field(min_length=1)
    tool: str | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    question_id: str | None = None
    hypothesis_id: str | None = None
    stop_reason: (
        Literal[
            TerminationReason.EVIDENCE_SUFFICIENT, TerminationReason.NO_USEFUL_ACTION
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def one_kind_of_step(self):
        """What a schema cannot say: each choice has its own fields."""
        if self.choice == "call_tool":
            if not self.tool:
                raise ValueError("a call_tool step must name a tool")
            if self.stop_reason is not None:
                raise ValueError("a call_tool step gives no stop_reason")
        else:
            if self.stop_reason is None:
                raise ValueError("a stop step must give a stop_reason")
            used = (self.tool, self.question_id, self.hypothesis_id)
            if any(value is not None for value in used) or self.arguments:
                raise ValueError(
                    "a stop step names no tool, arguments, question_id or hypothesis_id"
                )
        return self

    def decision(self) -> Decision:
        if self.choice == "stop":
            return Stop(
                reason=self.stop_reason, information_needed=self.information_needed
            )
        return CallTool(
            information_needed=self.information_needed,
            request=ToolRequest(name=self.tool, arguments=self.arguments),
            question_id=self.question_id,
            hypothesis_id=self.hypothesis_id,
        )


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


def cited_ids(state: InvestigationState) -> set[str]:
    """Evidence a belief rests on: cited by a hypothesis, the conclusion or the check."""
    cited = set()
    for h in state.hypotheses:
        cited.update(h.supporting_evidence_ids, h.contradicting_evidence_ids)
    if state.conclusion is not None:
        cited.update(state.conclusion.evidence_ids)
    if state.verification is not None:
        cited.update(state.verification.evidence_ids)
    return cited


def shortened_note(ids: Sequence[str]) -> str:
    return (
        f"(Listed by ID and call only, to keep this prompt short: {', '.join(ids)}. "
        "The same call at the same tick is refused as a repeat; to see more, ask "
        "a narrower question: a shorter tick range, a trend or a summary.)"
    )


def evidence_section(state: InvestigationState) -> list[str]:
    """The evidence lines, within MAX_EVIDENCE_SECTION_CHARS where that can be.

    Each piece starts as one short line (ID, call, tick) and is shown whole,
    in this order, while the section stays under the limit: the newest
    piece (always), the pieces a belief cites, then the rest, newest first.
    Lines keep the order the evidence arrived in. Only IDs that exist are
    written, so a model cannot be shown an ID to cite that was never given.
    """
    if not state.evidence:
        return [EVIDENCE_HEADER, "(none)"]
    # Which call produced each piece of evidence, from the loop's own records.
    asked: dict[str, tuple[str, dict]] = {}
    for decision in state.decisions:
        if decision.tool is not None:
            for evidence_id in decision.evidence_ids:
                asked.setdefault(evidence_id, (decision.tool, decision.arguments))
    origins = {p.evidence_id: p.origin for p in state.provenance}
    full: dict[str, str] = {}
    short: dict[str, str] = {}
    for evidence in state.evidence:
        tool, arguments = asked.get(
            evidence.id, (evidence.source_id.split(":")[-1], {})
        )
        call = f"{tool} {compact(arguments)}" if arguments else tool
        memory = ORIGIN_LABELS.get(origins.get(evidence.id), "")
        head = f"- {evidence.id} {call} at tick {evidence.observed_tick}{memory}: "
        full[evidence.id] = head + shown(evidence.content)
        short[evidence.id] = (
            head + f"[{len(evidence.content)} characters, not shown here]"
        )

    ids = [e.id for e in state.evidence]
    newest, cited = ids[-1], cited_ids(state)
    older = list(reversed(ids[:-1]))
    priority = [newest] + [i for i in older if i in cited]
    priority += [i for i in older if i not in cited]
    # Room for the header, the line breaks and the longest note there could be.
    size = len(EVIDENCE_HEADER) + len(shortened_note(ids)) + len(ids) + 2
    size += sum(len(line) for line in short.values())
    whole = set()
    for evidence_id in priority:
        extra = len(full[evidence_id]) - len(short[evidence_id])
        if evidence_id == newest or size + extra <= MAX_EVIDENCE_SECTION_CHARS:
            whole.add(evidence_id)
            size += extra
    lines = [EVIDENCE_HEADER]
    lines += [full[i] if i in whole else short[i] for i in ids]
    left_out = [i for i in ids if i not in whole]
    if left_out:
        lines.append(shortened_note(left_out))
    return lines


def render(state: InvestigationState) -> str:
    """Working memory as a model reads it. The same view for every question."""
    anomaly = state.anomaly
    where = f" on {anomaly.machine_id}" if anomaly.machine_id else ""
    now = "unknown" if state.last_tick is None else str(state.last_tick)
    budget = (
        f"BUDGET LEFT: {state.remaining_tool_calls} research tool calls, "
        f"{state.remaining_iterations} turns, {state.remaining_followup_tool_calls} "
        "calls for checking after an action"
    )
    # A model cannot sense time passing, so the stage's time left is a number.
    if state.seconds_for_question is not None:
        budget += f", about {int(state.seconds_for_question)} seconds for this stage"
    lines = [
        f"ANOMALY ({anomaly.kind}{where}, tick {anomaly.tick}): {anomaly.description}",
        f"NOW: tick {now}",
        budget,
    ]
    # Only when research calls are nearly spent, so no turn is primed to hurry.
    if state.conclusion is None and state.remaining_tool_calls <= LOW_CALLS:
        lines.append(LOW_BUDGET_NOTE)
    lines += ["", "OPEN QUESTIONS:"]
    for question in state.unanswered_questions:
        tests = f" [tests {question.hypothesis_id}]" if question.hypothesis_id else ""
        lines.append(f"- {question.id}: {question.text}{tests}")
    if not state.unanswered_questions:
        lines.append("(none)")

    lines += ["", *evidence_section(state)]

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
    "does not settle something, say so rather than guess. "
    "The investigation has a fixed budget of tool calls, turns and time, shown "
    "under BUDGET LEFT. Spend it where it can change the answer: prefer the call "
    "most likely to confirm or rule out a hypothesis over one that only adds "
    "detail. Being thorough matters more than being fast, but once more evidence "
    "would not change the diagnosis, the work is done."
)

SYSTEM = {
    "plan": (
        f"{COMMON}\n\nYour job: list the first things worth finding out about this "
        "anomaly, as up to five questions with ids Q1, Q2, ... Do not name a cause yet."
    ),
    "decide": (
        f"{COMMON}\n\nYour job: choose the next single tool call, or stop. For a "
        "call, set choice to call_tool, tool to one of the tools listed and "
        "arguments to match that tool's schema. Do not repeat a call whose answer "
        "is already in the evidence. Set question_id when the call answers an open "
        "question, and hypothesis_id when it tests a hypothesis. To stop, set "
        "choice to stop and stop_reason to evidence_sufficient when the evidence "
        "answers what this stage needs, or when the remaining budget is better "
        "saved than spent on a call unlikely to change your view, or "
        "no_useful_action when no listed tool would help."
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

    def _ask(
        self,
        job: str,
        state: InvestigationState,
        prompt: str,
        answer_type: type[Answer],
        *,
        system: str | None = None,
    ) -> Answer:
        """Ask one question within the time state allows, and record it.

        `system` replaces the job's own system prompt, for a policy that asks
        one job more than one kind of question (`tree_of_thought.py`).
        """
        client = self.clients[job]
        outcome = "no_answer"
        try:
            answer = client.ask(
                SYSTEM[job] if system is None else system,
                prompt,
                answer_type,
                max_seconds=state.seconds_for_question,
            )
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
        """A reply that matched its schema but cannot be used: the model's mistake.

        The question is marked invalid, and so is the attempt that answered
        it, with the reason, so the record says why as for any other refusal.
        """
        call = self.calls[-1]
        attempts = list(call.attempts)
        if attempts and attempts[-1].outcome == "answered":
            attempts[-1] = attempts[-1].model_copy(
                update={"outcome": invalid_outcome(ValueError(reason))}
            )
        self.calls[-1] = call.model_copy(
            update={"outcome": "invalid_reply", "attempts": tuple(attempts)}
        )
        raise ValueError(reason)

    def plan(self, state: InvestigationState) -> tuple[Question, ...]:
        return self._ask("plan", state, render(state), PlanAnswer).questions

    def decide(self, state: InvestigationState, phase: LoopPhase) -> Decision:
        prompt = (
            f"{render(state)}\n\n{PHASE[phase]}\n\n"
            f"TOOLS YOU MAY CALL:\n{tool_list(self.tools)}"
        )
        decision = self._ask("decide", state, prompt, NextStep).decision()
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
        return self._ask("interpret", state, prompt, Interpretation)

    def hypothesize(self, state: InvestigationState) -> Interpretation:
        return self._ask("hypothesize", state, render(state), Interpretation)

    def conclude(
        self, state: InvestigationState
    ) -> tuple[AgentConclusion, ActionRequest | None]:
        answer = self._ask("conclude", state, render(state), ConcludeAnswer)
        return answer.conclusion, answer.action

    def judge_verification(self, state: InvestigationState) -> VerificationCheck:
        verdict = self._ask("judge_verification", state, render(state), Judgement)
        return VerificationCheck(
            outcome=verdict.outcome,
            prediction=state.predicted_effect or "no prediction was recorded",
            evidence_ids=verdict.evidence_ids,
        )

    def write_lesson(self, state: InvestigationState) -> Lesson | None:
        text = self._ask("write_lesson", state, render(state), LessonAnswer).lesson
        return Lesson(text=text.strip()) if text and text.strip() else None
