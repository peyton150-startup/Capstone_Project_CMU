# An opt-in tree-of-thought hypothesis step for the model-backed policy.
# Responsibility: generate many candidate explanations, have them valued, prune in code.
"""Tree-of-thought hypotheses: branch wide, value each branch, keep the best.

    policy = TreeOfThoughtPolicy(clients_for_jobs(), research_tools())

Off by default. It changes one of the seven questions, `hypothesize`, and
nothing else: the loop, the stages, the other six questions and every
check stay as they are.

The ordinary policy asks one model question for two to four hypotheses.
This one follows Tree of Thoughts (Yao et al., 2023, arXiv 2305.10601),
at depth one, with breadth-first search:

1. generate  one question for up to `candidates` (default 5) distinct
             candidate explanations, each citing evidence, including ones
             that need no change to the factory;
2. value     a second question rates every candidate against the evidence:
             "sure", "likely" or "impossible" with a confidence, and one
             question whose answer would tell it apart from the others;
3. prune     code, not the model, keeps at most `breadth` (default 3):
             candidates rated impossible, citing evidence that was never
             gathered, or never rated are dropped, and the rest are ranked
             by confidence (ties by candidate order). "Impossible" drops a
             candidate only when factory evidence against it is cited (by
             the rating or the candidate): a model's say-so is not a
             contradiction, and neither is the manual or a memory, which
             describe the machine type or a past run, not this factory now.
             Without such evidence it is ranked like the rest.

The kept candidates become the hypotheses (H1, H2, ... in rank order) with
the valued confidence, and their questions become open questions that
test them, so the test stage expands the surviving branches with real
evidence. Deeper expansion by the model alone is not done: here a branch
grows by looking at the factory, not by more thinking.

Both questions go to the `hypothesize` job's client, so the job table is
unchanged; the record of model questions shows two `hypothesize` calls.
What the tree looked like is kept in `thoughts` for the experimenter (the
candidates, their ratings, what was kept and why the rest were dropped).
The dropped candidates are also handed back with the hypotheses
(`PrunedInterpretation.pruned`), so the loop keeps them in the state's trace
(`state.pruned_candidates`) and the critic sees what was ruled out.
The policy still never changes `state`.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field

from capstone.agent.model_policy import COMMON, Client, ModelPolicy, render
from capstone.agent.policy import Interpretation, PrunedInterpretation
from capstone.agent.state import InvestigationState, PrunedCandidate, Question
from capstone.contracts import Contract
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.tools import ToolSpec

# How many candidate explanations to ask for, and how many survive pruning.
DEFAULT_CANDIDATES = 5
DEFAULT_BREADTH = 3


class Candidate(Contract):
    id: str = Field(min_length=1)  # C1, C2, ...
    claim: str = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()


class Candidates(Contract):
    candidates: tuple[Candidate, ...] = ()


class Rating(Contract):
    candidate_id: str = Field(min_length=1)
    verdict: Literal["sure", "likely", "impossible"]
    confidence: float = Field(ge=0, le=1)
    question: str | None = None  # what would tell this one apart
    # For "impossible": the evidence that rules the candidate out.
    contradicting_evidence_ids: tuple[str, ...] = ()


class Ratings(Contract):
    ratings: tuple[Rating, ...] = ()


class Thought(Contract):
    """One hypothesize step's tree, for the record. Not shown to any model."""

    candidates: tuple[Candidate, ...]
    ratings: tuple[Rating, ...]
    kept: tuple[str, ...]  # candidate ids, in rank order
    # candidate id -> why it was dropped
    dropped: dict[str, str]
    # Kept candidates whose rating said "impossible" with no factory evidence
    # against them: kept, ranked last, at a neutral confidence. Empty in older
    # records.
    unresolved: tuple[str, ...] = ()


GENERATE = (
    f"{COMMON}\n\nYour job: propose up to {{count}} distinct candidate explanations "
    "for the evidence so far, with ids C1, C2, ..., each citing the evidence IDs "
    "that support or contradict it. Make them genuinely different: other "
    "machines, other kinds of cause, and explanations that need no change to "
    "the factory as well as ones that do. Do not rate them yet."
)

VALUE = (
    f"{COMMON}\n\nYour job: rate every candidate explanation listed under "
    "CANDIDATES against the evidence. For each, give its candidate_id, a verdict "
    "(sure: the evidence settles it; likely: consistent but not settled; "
    "impossible: the evidence rules it out), a confidence between 0 and 1, and "
    "one question whose answer would tell it apart from the others. For "
    "impossible, list in contradicting_evidence_ids the evidence IDs that rule "
    "it out; without them it is not ruled out. Only the factory's own readings "
    "and records can rule a candidate out: manual sections and memories cannot."
)


def candidate_lines(candidates: Sequence[Candidate]) -> str:
    lines = ["CANDIDATES:"]
    for c in candidates:
        supported = ", ".join(c.supporting_evidence_ids) or "none"
        contradicted = ", ".join(c.contradicting_evidence_ids) or "none"
        lines.append(
            f"- {c.id}: {c.claim} Supported by: {supported}. "
            f"Contradicted by: {contradicted}."
        )
    return "\n".join(lines)


def unproven_confidence(confidence: float) -> float:
    """A neutral score for an "impossible" verdict nothing factual backs.

    The rating's confidence is confidence that the candidate is false; it says
    little either way about the candidate being true, so the score never
    exceeds 0.5 and falls as the model grows surer it is false.
    """
    return min(confidence, 1 - confidence)


def unproven_rating(rating: Rating) -> Rating:
    """The rating a kept, unproven "impossible" is ranked and believed by."""
    return rating.model_copy(
        update={"confidence": unproven_confidence(rating.confidence)}
    )


def prune(
    candidates: Sequence[Candidate],
    ratings: Sequence[Rating],
    evidence_ids: set[str],
    breadth: int,
    observed_ids: set[str] | None = None,
) -> tuple[list[tuple[Candidate, Rating]], dict[str, str]]:
    """The candidates to keep, best first, and why each other one was dropped.

    Deterministic: the same candidates and ratings always keep the same ones.
    The first rating of a candidate counts; a rating of an unknown id is ignored.
    "Impossible" drops a candidate only with a cited contradiction the factory
    answered (`observed_ids`). Otherwise the candidate stays in the running
    but ranks below every sure or likely one, with the neutral score
    `unproven_confidence`, which the kept rating carries (so the hypothesis made
    from it carries it too).
    """
    # Variables:
    #   breadth: How many candidates may survive.
    #   evidence_ids: Ids of evidence that really exists; a candidate citing any other
    #     is dropped.
    #   observed_ids: Ids of evidence the factory answered, the only kind that can
    #     rule a candidate out; None treats all gathered evidence as observed.
    #   rated: The first rating for each candidate id; later duplicates are ignored.
    #   dropped: Why each removed candidate was dropped, by id.
    #   alive: Candidates still in the running, with their original position to break
    #     ties.
    #   seen: Candidate ids already handled, to catch a repeated id.
    #   factual: The evidence that can rule a candidate out: `observed_ids`.
    #   against: Factory evidence cited against a candidate, by its rating or itself.
    #   unproven: Candidates rated impossible with no such evidence, so not dropped
    #     for it.
    factual = evidence_ids if observed_ids is None else evidence_ids & observed_ids
    rated: dict[str, Rating] = {}
    for rating in ratings:
        rated.setdefault(rating.candidate_id, rating)
    dropped: dict[str, str] = {}
    alive: list[tuple[int, Candidate, Rating]] = []
    seen: set[str] = set()
    unproven: set[str] = set()
    for order, candidate in enumerate(candidates):
        if candidate.id in seen:
            dropped.setdefault(candidate.id, "a repeated candidate id")
            continue
        seen.add(candidate.id)
        cited = {
            *candidate.supporting_evidence_ids,
            *candidate.contradicting_evidence_ids,
        }
        rating = rated.get(candidate.id)
        if not cited <= evidence_ids:
            dropped[candidate.id] = "cites evidence that was not gathered"
        elif rating is None:
            dropped[candidate.id] = "not rated"
        elif rating.verdict == "impossible":
            against = {
                *rating.contradicting_evidence_ids,
                *candidate.contradicting_evidence_ids,
            } & factual
            if against:
                dropped[candidate.id] = "rated impossible"
            else:
                unproven.add(candidate.id)
                alive.append((order, candidate, rating))
        else:
            alive.append((order, candidate, rating))
    # An unproven "impossible" keeps its place in the running, but its rating's
    # confidence is how sure the model is that it is FALSE: ranked by that, an
    # "impossible, 0.95" would lead at 0.95. So it ranks below every sure or
    # likely candidate, and is scored `unproven_confidence` instead.
    alive = [
        (order, candidate, unproven_rating(rating))
        if candidate.id in unproven
        else (order, candidate, rating)
        for order, candidate, rating in alive
    ]
    alive.sort(
        key=lambda entry: (entry[1].id in unproven, -entry[2].confidence, entry[0])
    )
    for _, candidate, _ in alive[breadth:]:
        ranked = f"ranked below the best {breadth}"
        dropped[candidate.id] = (
            f"rated impossible with no factory evidence against it; {ranked}"
            if candidate.id in unproven
            else ranked
        )
    return [(c, r) for _, c, r in alive[:breadth]], dropped


def pruned_trace(
    candidates: Sequence[Candidate],
    ratings: Sequence[Rating],
    dropped: Mapping[str, str],
) -> tuple[PrunedCandidate, ...]:
    """The dropped candidates as the state's trace keeps them, in candidate order.

    A candidate dropped for citing evidence never gathered is left out: its
    citations point at nothing the critic could check.
    """
    # Variables:
    #   rated: The first rating of each candidate, as `prune` counts it.
    #   seen: Candidate ids already added, so a repeated id appears once.
    rated: dict[str, Rating] = {}
    for rating in ratings:
        rated.setdefault(rating.candidate_id, rating)
    trace, seen = [], set()
    for candidate in candidates:
        reason = dropped.get(candidate.id)
        if (
            reason is None
            or candidate.id in seen
            or reason == "cites evidence that was not gathered"
        ):
            continue
        seen.add(candidate.id)
        rating = rated.get(candidate.id)
        trace.append(
            PrunedCandidate(
                id=candidate.id,
                claim=candidate.claim,
                reason=reason,
                # Only a factory contradiction rules a candidate out; anything
                # else (ranked out, unrated) leaves it untested, not false.
                status="contradicted" if reason == "rated impossible" else "deferred",
                verdict=None if rating is None else rating.verdict,
                confidence=None if rating is None else rating.confidence,
                supporting_evidence_ids=candidate.supporting_evidence_ids,
                contradicting_evidence_ids=candidate.contradicting_evidence_ids,
            )
        )
    return tuple(trace)


class TreeOfThoughtPolicy(ModelPolicy):
    """The model-backed policy with a generate-value-prune hypothesize step."""

    def __init__(
        self,
        clients: Mapping[str, Client],
        tools: Sequence[ToolSpec],
        *,
        candidates: int = DEFAULT_CANDIDATES,
        breadth: int = DEFAULT_BREADTH,
    ):
        if not 1 <= breadth <= candidates:
            raise ValueError("breadth must be between 1 and the candidate count")
        super().__init__(clients, tools)
        self.candidates = candidates
        self.breadth = breadth
        self.thoughts: list[Thought] = []

    def hypothesize(self, state: InvestigationState) -> Interpretation:
        # Variables:
        #   view: The same working-memory text every question is shown.
        #   generated: The candidate explanations the model proposed, capped at the
        #     candidate count.
        #   ratings: The model's verdict and confidence for each candidate.
        #   kept: The best candidates after pruning, each with its rating, best first.
        #   dropped: Why each other candidate was removed, kept for the record.
        #   hypotheses: The kept candidates turned into hypotheses H1, H2 and so on.
        #   questions: One question per kept candidate that would tell it apart from the
        #     rest.
        view = render(state)
        generated = self._ask(
            "hypothesize",
            state,
            view,
            Candidates,
            system=GENERATE.format(count=self.candidates),
        ).candidates[: self.candidates]
        if not generated:
            self.thoughts.append(
                Thought(candidates=(), ratings=(), kept=(), dropped={})
            )
            return Interpretation()
        ratings = self._ask(
            "hypothesize",
            state,
            f"{view}\n\n{candidate_lines(generated)}",
            Ratings,
            system=VALUE,
        ).ratings
        observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
        kept, dropped = prune(
            generated,
            ratings,
            {e.id for e in state.evidence},
            self.breadth,
            observed_ids=observed,
        )
        self.thoughts.append(
            Thought(
                candidates=tuple(generated),
                ratings=tuple(ratings),
                kept=tuple(c.id for c, _ in kept),
                dropped=dropped,
                # Every kept "impossible" is unproven: a proven one was dropped.
                unresolved=tuple(c.id for c, r in kept if r.verdict == "impossible"),
            )
        )
        hypotheses, questions = [], []
        for rank, (candidate, rating) in enumerate(kept, start=1):
            hypothesis_id = f"H{rank}"
            hypotheses.append(
                Hypothesis(
                    id=hypothesis_id,
                    claim=candidate.claim,
                    confidence=rating.confidence,
                    supporting_evidence_ids=candidate.supporting_evidence_ids,
                    contradicting_evidence_ids=candidate.contradicting_evidence_ids,
                )
            )
            if rating.question and rating.question.strip():
                questions.append(
                    Question(
                        id=f"T{rank}",
                        text=rating.question.strip(),
                        hypothesis_id=hypothesis_id,
                    )
                )
        return PrunedInterpretation(
            hypotheses=tuple(hypotheses) or None,
            new_questions=tuple(questions),
            pruned=pruned_trace(generated, ratings, dropped),
        )
