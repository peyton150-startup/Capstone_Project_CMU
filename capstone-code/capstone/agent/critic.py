# The critic: a second model that judges the agent's hypotheses before it concludes.
# Responsibility: build its view, ask its one typed question, check the reply, keep its own call records.
"""A second look at the agent's explanations before every conclusion.

    critic = Critic(critic_client(settings), research_tools())
    result = critic.review(state, max_seconds=40)

The critic is shown the evidence the agent gathered (the same section the
agent's own questions get), every hypothesis the agent holds (up to
`SHOWN_HYPOTHESES`, most believed first, the leading one marked),
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

import hashlib
import random
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from capstone.agent.artifacts import CritiqueRecord, CritiqueResult, RecheckRecord
from capstone.agent.evidence_brief import evidence_brief
from capstone.agent.model_policy import (
    Client,
    ModelCall,
    evidence_section,
    tool_list,
)
from capstone.agent.state import InvestigationState
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.tools import ToolSpec
from capstone.manual.sections import ManualSection
from capstone.providers.chat import invalid_outcome

if TYPE_CHECKING:
    # Only for the type: the manual provider is not imported at run time.
    from capstone.providers.manual import ManualSearch

__all__ = [
    "CRITIC_SYSTEM",
    "Critic",
    "CritiqueRecord",
    "CritiqueResult",
    "RecheckRecord",
    "CRITIC_BLIND_SYSTEM",
    "blind_labels",
    "blind_order",
    "blind_verdict",
    "critique_view",
    "verdict_mismatch",
    "SHOWN_HYPOTHESES",
    "shown_hypotheses",
]

# The most hypotheses the critic is shown. All of them, in practice (the
# agent has held at most four in the saved runs); the cap keeps a small
# model's prompt short. KA-03's true cause was the agent's third hypothesis,
# which a top-two view hid.
SHOWN_HYPOTHESES = 5
# With a manual offered, code searches it on each shown hypothesis's claim
# (Option B, spec section "Let the critic use the machine manual") and shows
# the critic the sections found, at most this many per hypothesis.
MANUAL_PER_HYPOTHESIS = 2
PRUNED_NOTE = (
    "RULED OUT BEFORE TESTING (the agent's tree-of-thought step considered these "
    "and dropped them; they are not current hypotheses, so do not favour one, but "
    "if one deserves another look say so in an objection of kind alternative and "
    "aim the discriminating check at it):"
)
MANUAL_NOTE = (
    "MANUAL SECTIONS (general guidance for this model of machine, found by "
    "searching the manual on each hypothesis above; not a look at this factory, "
    "no evidence id, so never cite them as evidence):"
)

# The worked example is about something other than this factory, on purpose:
# it shows the steps without hinting at any answer.
CRITIC_SYSTEM = """\
You are a critic. An investigator has gathered evidence and holds several \
explanations. You are shown the evidence and the explanations it holds, most \
believed first; the first is its leading explanation. You cannot look anything \
up and cannot call any tool. Judge only what is shown.

Work through these steps, in order:
1. Read each hypothesis and the evidence ids it says support or contradict it.
2. For each hypothesis, list the evidence that fits it and the evidence that does not.
3. Pick the hypothesis the evidence supports best. It need not be proven; \
it must be the best fit. Pick none only if the evidence supports none of them.
4. Name one read-only call from the tool list, with its arguments, whose answer would \
separate your pick from the leading explanation (from the runner-up, if your \
pick is the leading one). Use only tools in the list. Also provide check_request \
with its exact name and arguments. Never use wait or an action: the check must \
not change the factory. Explain the expected contrasting outcomes in discriminating_check.
5. List objections. Each has a kind, one sentence, and the evidence ids it rests \
on. Cite only ids that are shown to you.
6. Give the verdict, and make it agree with your pick. no_objection: your pick \
is the leading explanation and nothing you found contradicts it or fits better; \
minor gaps (a check not yet made, a confidence a little high) are listed as \
objections but do not change the verdict. object: you pick another hypothesis \
or none, or you raise a contradiction or a better alternative against the \
leading explanation.

Rules: cite only evidence ids shown. Favour only a hypothesis id shown, or none. \
Do not invent evidence. Candidates shown as ruled out are not hypotheses: never \
favour one; if the evidence says one was dropped wrongly, object with kind \
alternative and aim the discriminating check at it. \
Manual sections, when shown, describe this model of \
machine in general: use them for what a symptom can mean and which check would \
separate the hypotheses, never as proof of what this factory is doing, and never \
cite them as evidence. Reply with the JSON object in the schema and nothing else.

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
objections: one missing_evidence citing E1; verdict: no_objection (H1 is the \
leading explanation and nothing contradicts it; the missing reading is a minor \
gap); favoured_confidence 0.65; supports_action false. Had H2 fitted better, \
the pick would be H2 and the verdict object."""


# The blind view (opt-in, CRITIC_BLIND): the same job without the agent's
# ranking. Hypotheses come in a shuffled order under neutral labels, with no
# confidence and no "leading" mark, so the critic cannot anchor on the agent's
# choice. It still picks, names a check and lists objections; code sets the
# verdict from the pick (`blind_verdict`), because a critic that does not know
# which explanation leads cannot judge "against the leading explanation".
CRITIC_BLIND_SYSTEM = """\
You are a critic. An investigator has gathered evidence and holds several \
explanations. You are shown the evidence and the explanations, in no \
particular order and under neutral labels (X1, X2, ...). You are not told which \
one the investigator believes most, on purpose: judge them on the evidence \
alone. You cannot look anything up and cannot call any tool. Judge only what is shown.

Work through these steps, in order:
1. Read each hypothesis and the evidence ids it says support or contradict it.
2. For each hypothesis, list the evidence that fits it and the evidence that does not.
3. Pick the hypothesis the evidence supports best, by its label. It need not be \
proven; it must be the best fit. Pick none only if the evidence supports none of them.
4. Name one read-only call from the tool list, with its arguments, whose answer \
would separate your pick from the next best hypothesis. Use only tools in the \
list. Also provide check_request with its exact name and arguments. Never use \
wait or an action: the check must not change the factory. Explain the expected \
contrasting outcomes in discriminating_check.
5. List objections. Each has a kind, one sentence, and the evidence ids it rests \
on. Cite only ids that are shown to you.
6. Set verdict to no_objection; the investigator's code replaces it with a \
verdict worked out from your pick.

Rules: cite only evidence ids shown. Favour only a label shown, or none. \
Do not invent evidence. Candidates shown as ruled out are not hypotheses: never \
favour one; if the evidence says one was dropped wrongly, object with kind \
alternative and aim the discriminating check at it. \
Manual sections, when shown, describe this model of \
machine in general: use them for what a symptom can mean and which check would \
separate the hypotheses, never as proof of what this factory is doing, and never \
cite them as evidence. Reply with the JSON object in the schema and nothing else.

Worked example (a different subject, to show the steps only):
Anomaly: the leaves of a house plant are turning yellow.
Evidence: E1 soil moisture reading: wet, three days after the last watering. \
E2 light log: the plant sits by a bright window all day.
X1: too little light. Contradicted by E2. X2: overwatering. Supported by E1.
Steps: X2 fits E1 and does not conflict with E2. X1 conflicts with E2 and has \
nothing supporting it. Better supported: X2. A call that would separate them: \
the soil moisture history, to see whether the soil stays wet between waterings. \
Objection: missing_evidence, only one moisture reading was taken (E1).
Reply: favoured X2; why: wet soil three days on and plenty of light; \
discriminating_check: read the soil moisture history for the plant; \
objections: one missing_evidence citing E1; verdict: no_objection (set by code \
afterwards); favoured_confidence 0.65; supports_action false."""


def blind_order(state: InvestigationState) -> list[Hypothesis]:
    """The shown hypotheses in a shuffled order that repeats on replay.

    The order comes from a seed made from the anomaly and the hypothesis ids,
    never from the simulator's random streams, so shuffling moves no factory
    draw and the same state always gives the same order.
    """
    # Variables:
    #   hypotheses: The ones the critic is shown, most believed first (the cap
    #     and the set are the anchored view's; only the order changes).
    #   key: Text fixed by the investigation so far; the same state, the same key.
    #   seed: A number from the key's hash; Python's own `hash` of a str changes
    #     between processes, so it is not used.
    hypotheses = shown_hypotheses(state)
    anomaly = state.anomaly
    key = "|".join(
        [anomaly.kind, anomaly.machine_id or "", str(anomaly.tick)]
        + sorted(h.id for h in hypotheses)
    )
    seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
    return random.Random(seed).sample(hypotheses, len(hypotheses))


def blind_labels(order: Sequence[Hypothesis]) -> dict[str, str]:
    """Neutral label for each hypothesis id, in the shown order: X1, X2, ..."""
    return {h.id: f"X{n}" for n, h in enumerate(order, start=1)}


def _rename(text: str, names: dict[str, str]) -> str:
    """`text` with each whole-word key of `names` replaced by its value."""
    # Variables:
    #   names: Old name to new name, e.g. {"H1": "X2"} into the blind view, or
    #     {"X2": "H1"} back out of the critic's reply.
    if not names:
        return text
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, names)) + r")\b")
    return pattern.sub(lambda m: names[m.group(1)], text)


def blind_verdict(favoured: str, leading: str | None) -> str:
    """The verdict code sets for a blind critic: object unless it picked the leader."""
    # Variables:
    #   favoured: The critic's pick, already mapped back to a hypothesis id, or
    #     "none".
    #   leading: The agent's leading hypothesis id, which the critic was not told.
    return "no_objection" if favoured == leading else "object"


# Objection kinds that argue against the leading explanation itself; the
# others (a check not yet made, a confidence a little high) are minor gaps.
SERIOUS_OBJECTIONS = frozenset({"contradiction", "alternative"})


def verdict_mismatch(result: CritiqueResult, leading: str | None) -> str | None:
    """Where the critic's verdict disagrees with its own pick, in words; else None.

    Found in the 2026-10-30 runs: "object" while favouring the leading
    explanation with only minor gaps, and "no_objection" while favouring
    another one. Recorded, never corrected: the reply stays as the critic gave
    it, so the prompt's effect can be measured.
    """
    # Variables:
    #   leading: The id of the leading explanation the critic was shown first.
    #   serious: Whether any objection is a contradiction or a better alternative.
    if leading is None:
        return None
    favoured = result.favoured
    if result.verdict == "no_objection" and favoured not in ("none", leading):
        return f"no_objection while favouring {favoured}, not the leading {leading}"
    serious = any(o.kind in SERIOUS_OBJECTIONS for o in result.objections)
    if result.verdict == "object" and favoured == leading and not serious:
        return (
            f"object while favouring the leading {leading}, with no "
            "contradiction or alternative raised"
        )
    return None


def shown_hypotheses(state: InvestigationState) -> list[Hypothesis]:
    """The hypotheses the critic judges: most believed first, a tie in list order.

    The first is the agent's leading one (`leading_hypothesis` picks the same).
    """
    # Variables:
    #   state: The investigation so far; read only, never changed here.
    #   SHOWN_HYPOTHESES: The most the critic is shown.
    return sorted(state.hypotheses, key=lambda h: -h.confidence)[:SHOWN_HYPOTHESES]


def manual_sections(
    manual: "ManualSearch | None", hypotheses: Sequence[Hypothesis]
) -> tuple[ManualSection, ...]:
    """The manual sections for the critic: a search on each hypothesis's claim.

    Best match first for each hypothesis in the order given, a section shown
    once even when several claims find it. No manual, or a search that fails,
    gives none: the critic then judges without it, as before.
    """
    # Variables:
    #   manual: The run's manual search; None when the run offers no manual.
    #   found: The sections so far, in order, each once.
    #   seen: Section ids already in `found`.
    #   hits: The sections one hypothesis's claim found, best match first.
    if manual is None:
        return ()
    found: list[ManualSection] = []
    seen: set[str] = set()
    for hypothesis in hypotheses:
        try:
            hits = manual.search(hypothesis.claim, limit=MANUAL_PER_HYPOTHESIS)
        except Exception:
            continue  # a failed search (e.g. the index is down) shows nothing
        for section in hits:
            if section.section_id not in seen:
                seen.add(section.section_id)
                found.append(section)
    return tuple(found)


def critique_view(
    state: InvestigationState,
    tools: Sequence[ToolSpec],
    sections: Sequence[ManualSection] = (),
    *,
    blind: bool = False,
) -> str:
    """What the critic is shown: the anomaly, the evidence, the hypotheses and,
    with a manual, the sections found for them.

    With `blind`, the hypotheses come in `blind_order` under `blind_labels`,
    with no confidence and no "leading" mark; everything else is the same.
    """
    # Variables:
    #   tools: The agent's research tools, shown as text only so the critic can name
    #     a check the agent could make; the critic cannot call them.
    #   sections: Manual sections found on the shown hypotheses' claims; empty
    #     without a manual. Guidance, never evidence: they carry no evidence id.
    #   state.pruned_candidates: What tree-of-thought ruled out, and why; shown so
    #     the critic can say if a dropped cause deserves another look.
    #   rated: A pruned candidate's rating, in words, if it was rated.
    #   lines: The prompt, built up section by section and joined at the end.
    #   supported, contradicted: The evidence ids a shown hypothesis says back it or
    #     count against it, so the critic can check those claims.
    #   evidence_brief: Arithmetic, coverage and routes derived from observable results.
    #   blind: Hide the agent's ranking: shuffled order, neutral labels, no
    #     confidence, no leading mark.
    #   order: The hypotheses in the order shown.
    #   labels: The name each hypothesis is shown under: its id, or X1, X2, ...
    #   ranked: Its confidence and, for the first, the leading mark; empty when blind.
    anomaly = state.anomaly
    where = f" on {anomaly.machine_id}" if anomaly.machine_id else ""
    lines = [
        f"ANOMALY ({anomaly.kind}{where}, tick {anomaly.tick}): {anomaly.description}",
        "",
        evidence_brief(state),
        *evidence_section(state),
        "",
        "HYPOTHESES SHOWN TO YOU:",
    ]
    order = blind_order(state) if blind else shown_hypotheses(state)
    labels = blind_labels(order) if blind else {h.id: h.id for h in order}
    for rank, h in enumerate(order):
        leading = ", the agent's leading explanation" if rank == 0 else ""
        ranked = "" if blind else f" (confidence {h.confidence:.2f}{leading})"
        supported = ", ".join(h.supporting_evidence_ids) or "none"
        contradicted = ", ".join(h.contradicting_evidence_ids) or "none"
        shown = [
            f"- {labels[h.id]}{ranked}: {h.claim} "
            f"Supported by: {supported}. Contradicted by: {contradicted}.",
            f"Expected: {h.expected_observations}; assumptions: {h.assumptions}; "
            f"unexplained evidence: {h.unexplained_evidence_ids}; check: {h.discriminating_check}",
        ]
        lines += [_rename(line, labels) for line in shown] if blind else shown
    if state.pruned_candidates:
        lines += ["", PRUNED_NOTE]
        for p in state.pruned_candidates:
            rated = (
                "" if p.verdict is None else f" (rated {p.verdict}, {p.confidence:.2f})"
            )
            supported = ", ".join(p.supporting_evidence_ids) or "none"
            contradicted = ", ".join(p.contradicting_evidence_ids) or "none"
            lines.append(
                f"- {p.id}{rated}: {p.claim} Dropped ({p.status}): {p.reason}. "
                f"Supported by: {supported}. Contradicted by: {contradicted}."
            )
    if sections:
        lines += ["", MANUAL_NOTE]
        lines += [f"- §{s.section_id} {s.title}: {s.text}" for s in sections]
    lines += [
        "",
        "TOOLS THE AGENT CAN CALL (you cannot call them):",
        tool_list(tools),
    ]
    return "\n".join(lines)


class Critic:
    """Asks the one critique question and keeps its own record of each ask."""

    def __init__(
        self,
        client: Client,
        tools: Sequence[ToolSpec],
        *,
        manual: "ManualSearch | None" = None,
        blind: bool = False,
    ):
        # Variables:
        #   client: Asks the critic's model chain one typed question; a fake in tests.
        #   tools: The agent's research tools, shown to the critic as text.
        #   manual: The run's manual search, used by code before the question
        #     (Option B); None when the run offers no manual.
        #   blind: Show the hypotheses without the agent's ranking (CRITIC_BLIND);
        #     code then sets the verdict from the pick.
        #   calls: This critic's own record of every question it asked, kept apart
        #     from the research agent's calls and tagged agent="critic".
        #   last_sections: The ids of the manual sections shown at the latest
        #     review, for the record; None without a manual.
        #   last_order: The hypothesis ids in the order the blind critic saw them
        #     at the latest review, for the record; None when not blind.
        self.client = client
        self.tools = tuple(tools)
        self.manual = manual
        self.blind = blind
        self.calls: list[ModelCall] = []
        self.last_sections: tuple[str, ...] | None = None
        self.last_order: tuple[str, ...] | None = None

    def review(
        self, state: InvestigationState, *, max_seconds: float
    ) -> CritiqueResult:
        """Judge the agent's hypotheses within `max_seconds`.

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
        #   hypotheses: The hypotheses the critic is shown, most believed first.
        #   sections: The manual sections found on their claims; the search runs
        #     here, inside the critic's window, so its time counts as the critic's.
        #   labels: Blind only: each hypothesis id's neutral label, so the reply's
        #     labels can be turned back into ids before it is checked.
        hypotheses = shown_hypotheses(state)
        shown = [h.id for h in hypotheses]
        sections = manual_sections(self.manual, hypotheses)
        self.last_sections = (
            None if self.manual is None else tuple(f"§{s.section_id}" for s in sections)
        )
        labels: dict[str, str] = {}
        self.last_order = None
        if self.blind:
            order = blind_order(state)
            labels = blind_labels(order)
            self.last_order = tuple(h.id for h in order)
        try:
            answer = self.client.ask(
                CRITIC_BLIND_SYSTEM if self.blind else CRITIC_SYSTEM,
                critique_view(state, self.tools, sections, blind=self.blind),
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
        if self.blind:
            answer = self._unblind(answer, labels, shown)
        reason = self._problem(answer, shown, state)
        if reason is not None:
            self._refuse(reason)
        return answer

    def _unblind(
        self, answer: CritiqueResult, labels: dict[str, str], shown: list[str]
    ) -> CritiqueResult:
        """The blind reply in hypothesis ids, with the verdict code works out.

        Labels are turned back into ids in every text field, so the follow-up
        and the record read as the anchored critic's do. A label never shown
        stays as it is and is refused by `_problem`.
        """
        # Variables:
        #   back: Label to hypothesis id, the reverse of `labels`.
        #   favoured: The pick as an id, or "none", or an unknown label left alone.
        #   leading: The agent's leading hypothesis (first in `shown`), which the
        #     critic was not told.
        back = {label: hid for hid, label in labels.items()}
        favoured = back.get(answer.favoured, answer.favoured)
        leading = shown[0] if shown else None
        return answer.model_copy(
            update={
                "favoured": favoured,
                "why": _rename(answer.why, back),
                "discriminating_check": _rename(answer.discriminating_check, back),
                "objections": tuple(
                    o.model_copy(update={"text": _rename(o.text, back)})
                    for o in answer.objections
                ),
                "verdict": blind_verdict(favoured, leading),
            }
        )

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
