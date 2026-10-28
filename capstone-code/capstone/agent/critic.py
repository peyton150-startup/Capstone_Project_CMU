# The critic: a second model that judges the two leading hypotheses.
# Responsibility: build its view, ask its one typed question, check the reply, keep its own call records.
"""A second look at the agent's two best explanations, review only.

    critic = Critic(critic_client(settings), research_tools())
    result = critic.review(state, max_seconds=40)

The critic is shown the evidence the agent gathered (the same section the
agent's own questions get), the two hypotheses with the highest confidence,
and the names and descriptions of the agent's research tools as text. It
cannot call them. It never sees the scenario, the run, a score or any
hidden truth, because `critique_view` reads nothing but the state's anomaly,
evidence and hypotheses.

Its reply is a belief, not evidence. It is refused, as the policy's replies
are, when it favours a hypothesis it was not shown or cites evidence that
was never gathered. Every question is kept in `calls`, tagged
`agent="critic"`, apart from the research agent's own `ModelCall` records.

The critic never changes `state`.

Code outside `capstone.agent` imports the critic's records from here, never
from `agent.artifacts` (the rule `test_agent_artifacts` keeps).
"""

from collections.abc import Sequence

from capstone.agent.artifacts import CritiqueRecord, CritiqueResult
from capstone.agent.model_policy import (
    Client,
    ModelCall,
    evidence_section,
    tool_list,
)
from capstone.agent.state import InvestigationState
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.tools import ToolSpec
from capstone.providers.chat import invalid_outcome

__all__ = [
    "CRITIC_SYSTEM",
    "Critic",
    "CritiqueRecord",
    "CritiqueResult",
    "critique_view",
    "top_two",
]

# How many hypotheses the critic is shown.
SHOWN_HYPOTHESES = 2

# The worked example is about something other than this factory, on purpose:
# it shows the steps without hinting at any answer.
CRITIC_SYSTEM = """\
You are a critic. An investigator has gathered evidence and holds several \
explanations. You are shown the evidence and the two explanations it believes \
most. You cannot look anything up and cannot call any tool. Judge only what is shown.

Work through these steps, in order:
1. Read each hypothesis and the evidence ids it says support or contradict it.
2. For each hypothesis, list the evidence that fits it and the evidence that does not.
3. Pick the hypothesis the evidence supports better. It need not be proven; \
it must be the better fit. Pick none only if the evidence supports neither.
4. Name one call from the tool list, with its arguments, whose answer would \
separate the two hypotheses. Use only tools in the list.
5. List objections. Each has a kind, one sentence, and the evidence ids it rests \
on. Cite only ids that are shown to you.
6. Give the verdict: object if the investigator should doubt its leading \
hypothesis, no_objection if the evidence supports it and nothing undermines it.

Rules: cite only evidence ids shown. Favour only a hypothesis id shown, or none. \
Do not invent evidence. Reply with the JSON object in the schema and nothing else.

Worked example (a different subject, to show the steps only):
Anomaly: the leaves of a house plant are turning yellow.
Evidence: E1 soil moisture reading: wet, three days after the last watering. \
E2 light log: the plant sits by a bright window all day.
H1 (0.60): overwatering. Supported by E1. H2 (0.55): too little light. \
Contradicted by E2.
Steps: H1 fits E1 and does not conflict with E2. H2 conflicts with E2 and has \
nothing supporting it. Better supported: H1. A call that would separate them: \
the soil moisture history, to see whether the soil stays wet between waterings. \
Objection: missing_evidence, only one moisture reading was taken (E1).
Reply: favoured H1; why: wet soil three days on and plenty of light; \
discriminating_check: read the soil moisture history for the plant; \
objections: one missing_evidence citing E1; verdict: object; \
favoured_confidence 0.65; supports_action false."""


def top_two(state: InvestigationState) -> list[Hypothesis]:
    """The hypotheses with the highest confidence, best first; a tie keeps list order."""
    # Variables:
    #   state: The investigation so far; read only, never changed here.
    #   SHOWN_HYPOTHESES: How many hypotheses the critic gets to judge (two).
    return sorted(state.hypotheses, key=lambda h: -h.confidence)[:SHOWN_HYPOTHESES]


def critique_view(state: InvestigationState, tools: Sequence[ToolSpec]) -> str:
    """What the critic is shown, built from the anomaly, evidence and two hypotheses."""
    # Variables:
    #   tools: The agent's research tools, shown as text only so the critic can name
    #     a check the agent could make; the critic cannot call them.
    #   lines: The prompt, built up section by section and joined at the end.
    #   supported, contradicted: The evidence ids a shown hypothesis says back it or
    #     count against it, so the critic can check those claims.
    anomaly = state.anomaly
    where = f" on {anomaly.machine_id}" if anomaly.machine_id else ""
    lines = [
        f"ANOMALY ({anomaly.kind}{where}, tick {anomaly.tick}): {anomaly.description}",
        "",
        *evidence_section(state),
        "",
        "HYPOTHESES SHOWN TO YOU:",
    ]
    for h in top_two(state):
        supported = ", ".join(h.supporting_evidence_ids) or "none"
        contradicted = ", ".join(h.contradicting_evidence_ids) or "none"
        lines.append(
            f"- {h.id} (confidence {h.confidence:.2f}): {h.claim} "
            f"Supported by: {supported}. Contradicted by: {contradicted}."
        )
    lines += [
        "",
        "TOOLS THE AGENT CAN CALL (you cannot call them):",
        tool_list(tools),
    ]
    return "\n".join(lines)


class Critic:
    """Asks the one critique question and keeps its own record of each ask."""

    def __init__(self, client: Client, tools: Sequence[ToolSpec]):
        # Variables:
        #   client: Asks the critic's model chain one typed question; a fake in tests.
        #   tools: The agent's research tools, shown to the critic as text.
        #   calls: This critic's own record of every question it asked, kept apart
        #     from the research agent's calls and tagged agent="critic".
        self.client = client
        self.tools = tuple(tools)
        self.calls: list[ModelCall] = []

    def review(
        self, state: InvestigationState, *, max_seconds: float
    ) -> CritiqueResult:
        """Judge the two leading hypotheses within `max_seconds`.

        A `ModelError` (no answer in time) passes up, recorded as `no_answer`.
        A reply that breaks the type, or cites what it was not shown, raises
        `ValueError`, recorded as `invalid_reply`.
        """
        # Variables:
        #   max_seconds: The most this one question may take, retries and fallback
        #     included; past it the client gives up and raises ModelError.
        #   shown: The ids of the hypotheses the critic was shown, so a reply naming
        #     any other can be refused.
        #   answer: The critic's typed reply, kept only if it passes `_problem`.
        shown = [h.id for h in top_two(state)]
        try:
            answer = self.client.ask(
                CRITIC_SYSTEM,
                critique_view(state, self.tools),
                CritiqueResult,
                max_seconds=max_seconds,
            )
        except ValueError:
            self._record("invalid_reply")
            raise
        except BaseException:
            self._record("no_answer")
            raise
        self._record("answered")
        reason = self._problem(answer, shown, state)
        if reason is not None:
            self._refuse(reason)
        return answer

    def _problem(
        self, answer: CritiqueResult, shown: list[str], state: InvestigationState
    ) -> str | None:
        """Why a well-formed reply cannot be used, or None if it can."""
        # Variables:
        #   shown: The hypothesis ids the critic saw; `favoured` must be one of them
        #     or "none", because it cannot have weighed a hypothesis it was not shown.
        #   known: The ids of all evidence the agent gathered, the only ids an
        #     objection may cite.
        #   cited: Every evidence id the critic's objections point to.
        #   missing: Cited ids that were never gathered, made up by the critic.
        if answer.favoured != "none" and answer.favoured not in shown:
            return f"favoured {answer.favoured!r} was not a hypothesis shown"
        known = {e.id for e in state.evidence}
        cited = {i for o in answer.objections for i in o.evidence_ids}
        missing = sorted(cited - known)
        if missing:
            return f"cited evidence that was never gathered: {', '.join(missing)}"
        return None

    def _record(self, outcome: str) -> None:
        """Keep one record of the question just asked."""
        # Variables:
        #   outcome: answered, invalid_reply or no_answer; recorded on every ask.
        #   client: Read for which model answered and every model it tried, which
        #     the client keeps from its latest question.
        client = self.client
        self.calls.append(
            ModelCall(
                job="critique",
                agent="critic",
                outcome=outcome,
                answered_by=getattr(client, "answered_by", None)
                if outcome == "answered"
                else None,
                attempts=tuple(getattr(client, "attempts", ())),
            )
        )

    def _refuse(self, reason: str) -> None:
        """Mark the question just asked invalid, with the reason, and raise."""
        # Variables:
        #   reason: Why the reply cannot be used; kept in the record, never shown to
        #     the critic.
        #   call: The record of the question just asked, rewritten as an invalid reply.
        #   attempts: Every model tried, with the one that answered also marked invalid
        #     so the reason is on the model that gave the reply.
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
