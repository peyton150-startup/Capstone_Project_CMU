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

from pydantic import Field, model_validator

from capstone.agent.artifacts import RevaluationRecord
from capstone.agent.model_policy import COMMON, Client, ModelPolicy, render
from capstone.agent.policy import Interpretation, PrunedInterpretation
from capstone.agent.state import InvestigationState, PrunedCandidate, Question
from capstone.contracts import Contract
from capstone.contracts.hypotheses import Hypothesis
from capstone.contracts.tools import ToolSpec

# How many candidate explanations to ask for, and how many survive pruning.
DEFAULT_CANDIDATES = 5
DEFAULT_BREADTH = 3


class TreeOptions(Contract):
    """The tree's switches, kept on each experiment record so runs can be compared.

    The defaults are the depth-one tree every archived ToT run used.
    """

    candidates: int = Field(default=DEFAULT_CANDIDATES, ge=1)
    breadth: int = Field(default=DEFAULT_BREADTH, ge=1)
    # P1: top_k keeps the best `breadth`; evidence also keeps up to
    # `retain_extra` more that may be separate causes (`retain`).
    retain: Literal["top_k", "evidence"] = "top_k"
    retain_extra: int = Field(default=2, ge=0)
    retain_floor: float = Field(default=0.5, ge=0, le=1)
    # P4: confidence ranks by the model's confidence; evidence by the
    # transparent evidence rubric first (`evidence_strength`).
    rank: Literal["confidence", "evidence"] = "confidence"
    # P4: show the candidates to the rating question in a rotated order (by
    # the investigation id), so position effects can be measured across runs.
    rotate: bool = False
    # P3: decide from the agent's current beliefs whether to branch at all,
    # and whether to keep one more candidate (`branching`).
    adaptive: bool = False
    # P5: after the test stage, rate the kept explanations once more against
    # the new evidence (`TreeOfThoughtPolicy.revalue`). Depth two, no new
    # candidates.
    revalue: bool = False

    @model_validator(mode="after")
    def breadth_fits(self):
        if self.breadth > self.candidates:
            raise ValueError("breadth must be between 1 and the candidate count")
        return self


class Candidate(Contract):
    id: str = Field(min_length=1)  # C1, C2, ...
    claim: str = Field(min_length=1)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    expected_observations: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    unexplained_evidence_ids: tuple[str, ...] = ()
    discriminating_check: str | None = None


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
    # P1: candidates kept beyond the top `breadth`, by id, with why
    # (`retention_reason`). Empty with top-k retention and in older records.
    retained: dict[str, str] = Field(default_factory=dict)
    # P4: the candidate ids in the order the rating question listed them.
    # The generated order unless TOT_ROTATE; empty in older records, which
    # always listed them in generated order.
    shown_order: tuple[str, ...] = ()
    # P3: what adaptive branching chose. static: adaptive branching was off
    # (and older records). skipped: one clear explanation, so the ordinary
    # one-question step ran instead of a tree. default: the usual breadth.
    # wide: an ambiguous case, kept one more candidate.
    branching: Literal["static", "skipped", "default", "wide"] = "static"
    branching_reason: str | None = None


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

REVALUE = (
    f"{VALUE}\n\nThe candidates are the explanations kept after the first rating, "
    "by their hypothesis ids (H1, H2, ...). The test stage has since gathered "
    "more evidence: rate each one again in its light."
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


# P3's thresholds. A clear case: a leading explanation at CLEAR_CONFIDENCE or
# more, ahead of the next by CLEAR_MARGIN, backed by CLEAR_SUPPORT factory
# readings, with nothing against it or left unexplained. An ambiguous case:
# nothing believed yet, a leader under AMBIGUOUS_CONFIDENCE, a runner-up within
# AMBIGUOUS_MARGIN, or a leader with evidence against it or left unexplained.
CLEAR_CONFIDENCE = 0.8
CLEAR_MARGIN = 0.3
CLEAR_SUPPORT = 2
AMBIGUOUS_CONFIDENCE = 0.5
AMBIGUOUS_MARGIN = 0.15


def branching(
    state: InvestigationState, options: TreeOptions
) -> tuple[Literal["skipped", "default", "wide"], int, str]:
    """Whether to branch, how many to keep, and why, from what the agent holds (P3).

    Reads only the agent's beliefs and the provenance of its evidence: the same
    observable state every question is shown, never the truth. Returns
    ("skipped", 0, why) for a clear case, ("wide", breadth + 1, why) for an
    ambiguous one (never above the candidate count), else ("default", breadth, why).
    """
    # Variables:
    #   ranked: The agent's hypotheses, most believed first.
    #   leading: The most believed one.
    #   runner_up: The next one's confidence, 0 with only one.
    #   backed: How many of the leader's supporters the factory answered.
    #   wider: The breadth for an ambiguous case.
    breadth = options.breadth
    wider = min(options.candidates, breadth + 1)
    ranked = sorted(state.hypotheses, key=lambda h: -h.confidence)
    if not ranked:
        return "wide", wider, "no explanation is held yet"
    leading = ranked[0]
    runner_up = ranked[1].confidence if len(ranked) > 1 else 0.0
    if leading.contradicting_evidence_ids or leading.unexplained_evidence_ids:
        return "wide", wider, "the leading explanation has evidence against it or gaps"
    if leading.confidence < AMBIGUOUS_CONFIDENCE:
        return "wide", wider, f"the leading explanation is at {leading.confidence:.2f}"
    if leading.confidence - runner_up < AMBIGUOUS_MARGIN:
        return "wide", wider, "the two leading explanations are close"
    observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
    backed = len(set(leading.supporting_evidence_ids) & observed)
    if (
        leading.confidence >= CLEAR_CONFIDENCE
        and leading.confidence - runner_up >= CLEAR_MARGIN
        and backed >= CLEAR_SUPPORT
    ):
        return (
            "skipped",
            0,
            (
                f"one clear explanation at {leading.confidence:.2f}, "
                f"backed by {backed} factory readings"
            ),
        )
    return "default", breadth, "neither clear nor ambiguous"


def rotated(candidates: Sequence[Candidate], offset: int) -> list[Candidate]:
    """The candidates starting at `offset` (wrapping round), for the rating question.

    A rotation, not a shuffle: every candidate keeps its neighbours, so across
    runs each one is shown first, second and so on equally often, and nothing
    random is needed. Ties are still broken by the generated order.
    """
    # Variables:
    #   offset: Where the listing starts; taken modulo the count.
    if not candidates:
        return []
    start = offset % len(candidates)
    return [*candidates[start:], *candidates[:start]]


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


# Sensor tools give views of the same readings (a summary, a trend and the raw
# values of one sensor are not three separate findings), so the evidence
# rubric counts them as one family; every other tool is its own family.
SENSOR_TOOLS = frozenset(
    {
        "get_readings",
        "get_sensor_trend",
        "get_factory_readings",
        "get_sensor_summary",
        "get_line_screening",
    }
)
# The order of the verdicts in the evidence rubric: settled first.
VERDICT_TIER = {"sure": 2, "likely": 1, "impossible": 0}


class Ranked(Contract):
    """One candidate still in the running after the hard drops, with its rating.

    `rating` is the one it is believed by (an unproven "impossible" carries the
    neutral score), and `order` its place in the model's list, for ties.
    """

    order: int
    candidate: Candidate
    rating: Rating
    unproven: bool = False


def evidence_family(source_id: str) -> str:
    """The family a piece of evidence counts in for the rubric: "sensor" or its tool."""
    # Variables:
    #   tool: The tool part of a source id such as "simulator:get_readings".
    tool = source_id.rsplit(":", 1)[-1]
    return "sensor" if tool in SENSOR_TOOLS else tool


def evidence_strength(
    entry: Ranked, families: Mapping[str, str], observed_ids: set[str]
) -> tuple[int, int, int]:
    """The rubric's score for one candidate: (verdict tier, net support, -gaps).

    Net support is the number of evidence families among the factory evidence
    supporting the candidate, less the factory evidence cited against it (by the
    candidate or its rating). Gaps are the evidence it says it leaves
    unexplained. Higher is better in every part; parts are compared in order.
    Only factory answers count: a manual section or a memory supports nothing here.
    """
    # Variables:
    #   families: Evidence id -> its family (`evidence_family`), for gathered evidence.
    #   observed_ids: Ids the factory answered; nothing else counts as support.
    #   supported: The families of the factory evidence for the candidate.
    #   against: The factory evidence cited against it.
    candidate, rating = entry.candidate, entry.rating
    supported = {
        families[e]
        for e in candidate.supporting_evidence_ids
        if e in observed_ids and e in families
    }
    against = {
        *candidate.contradicting_evidence_ids,
        *rating.contradicting_evidence_ids,
    } & observed_ids
    tier = 0 if entry.unproven else VERDICT_TIER[rating.verdict]
    return tier, len(supported) - len(against), -len(candidate.unexplained_evidence_ids)


def rank_candidates(
    candidates: Sequence[Candidate],
    ratings: Sequence[Rating],
    evidence_ids: set[str],
    observed_ids: set[str] | None = None,
    *,
    rank: Literal["confidence", "evidence"] = "confidence",
    families: Mapping[str, str] | None = None,
) -> tuple[list[Ranked], dict[str, str]]:
    """Every candidate still in the running, best first, and why the others went.

    The hard drops come first and do not depend on rank: a repeated id, evidence
    that was never gathered, no rating, or "impossible" with factory evidence
    against it. The rest are ordered by `rank`:

        confidence  unproven "impossible" last, then the model's confidence,
                    then the model's order (the depth-one tree's rule)
        evidence    the evidence rubric (`evidence_strength`) first, then the
                    model's confidence, then the model's order (P4)
    """
    # Variables:
    #   evidence_ids: Ids of evidence that really exists; a candidate citing any other
    #     is dropped.
    #   observed_ids: Ids of evidence the factory answered, the only kind that can
    #     rule a candidate out; None treats all gathered evidence as observed.
    #   rank: Which ordering to use, as above.
    #   families: Evidence id -> family, needed by the evidence rubric; None
    #     counts every id as its own family.
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
    entries = [
        Ranked(
            order=order,
            candidate=candidate,
            rating=unproven_rating(rating) if candidate.id in unproven else rating,
            unproven=candidate.id in unproven,
        )
        for order, candidate, rating in alive
    ]
    if rank == "evidence":
        known = families or {e: e for e in evidence_ids}
        entries.sort(
            key=lambda e: (
                tuple(-part for part in evidence_strength(e, known, factual)),
                -e.rating.confidence,
                e.order,
            )
        )
    else:
        entries.sort(key=lambda e: (e.unproven, -e.rating.confidence, e.order))
    return entries, dropped


def ranked_out(entry: Ranked, breadth: int) -> str:
    """Why a candidate below the cut was dropped, in the words the trace keeps."""
    # Variables:
    #   entry: The candidate below the cut; `unproven` marks an "impossible"
    #     rating with no factory evidence, which the reason then says.
    #   breadth: Where the cut was, for the reason's wording.
    ranked = f"ranked below the best {breadth}"
    if entry.unproven:
        return f"rated impossible with no factory evidence against it; {ranked}"
    return ranked


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
    from it carries it too). The best `breadth` are kept (`rank_candidates`).
    """
    # Variables:
    #   breadth: How many candidates may survive.
    #   ranked: Every candidate still in the running, best first.
    #   dropped: Why each removed candidate was dropped, by id.
    ranked, dropped = rank_candidates(candidates, ratings, evidence_ids, observed_ids)
    for entry in ranked[breadth:]:
        dropped[entry.candidate.id] = ranked_out(entry, breadth)
    return [(e.candidate, e.rating) for e in ranked[:breadth]], dropped


# Why a candidate below the cut was kept anyway (P1), as `Thought.retained` says.
INDEPENDENT = "independent factory evidence"
UNTESTED = "an untested alternative with a check"


def retention_reason(
    entry: Ranked, kept: Sequence[Ranked], observed_ids: set[str], floor: float
) -> str | None:
    """Why a candidate ranked below the cut should be kept as well, or None.

    Only a sure or likely candidate at `floor` confidence or more qualifies,
    and only for one of two reasons:

    - independent factory evidence: it cites factory evidence no kept candidate
      cites, so it may be a second, simultaneous cause (bearing wear and a wrong
      setting on one machine, say), not a rewording of a kept one;
    - an untested alternative: it cites no supporting evidence at all but names
      a check, so it points where nobody has looked yet (another machine), and
      one tool call can test it. The audit's KA-09 lost its CNC-07 candidates
      this way.
    """
    # Variables:
    #   floor: The least confidence an extra candidate needs.
    #   cited: Factory evidence the kept candidates already cite.
    #   own: The candidate's own factory support.
    #   check: The question that would test it, from the rating or the candidate.
    candidate, rating = entry.candidate, entry.rating
    if entry.unproven or rating.verdict == "impossible" or rating.confidence < floor:
        return None
    cited = {e for k in kept for e in k.candidate.supporting_evidence_ids}
    own = set(candidate.supporting_evidence_ids) & observed_ids
    if own - cited:
        return INDEPENDENT
    check = candidate.discriminating_check or rating.question
    if not candidate.supporting_evidence_ids and check and check.strip():
        return UNTESTED
    return None


def retain(
    ranked: Sequence[Ranked],
    breadth: int,
    observed_ids: set[str],
    *,
    extra: int,
    floor: float,
    calls_left: int,
) -> tuple[list[Ranked], dict[str, str]]:
    """The best `breadth`, plus up to `extra` more that may be separate causes (P1).

    The top-k cut is kept as it is; this only adds to it, so a run with
    retention keeps everything the depth-one tree would have kept. Each kept
    candidate needs at least one research call to be tested, so no more are
    kept than `calls_left` allows: the reserve of calls is the cap.
    Returns the kept entries, best first, and why each extra one was kept.
    """
    # Variables:
    #   extra: The most candidates kept beyond `breadth`.
    #   floor: The least confidence an extra candidate needs.
    #   calls_left: Research tool calls still available; one per kept candidate.
    #   kept: The top-k, then the extras in rank order.
    #   why: Extra candidate id -> why it was kept (`retention_reason`).
    kept = list(ranked[:breadth])
    room = min(extra, max(0, calls_left - len(kept)))
    why: dict[str, str] = {}
    for entry in ranked[breadth:]:
        if len(why) >= room:
            break
        reason = retention_reason(entry, kept, observed_ids, floor)
        if reason is not None:
            kept.append(entry)
            why[entry.candidate.id] = reason
    return kept, why


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
        options: TreeOptions | None = None,
    ):
        # Variables:
        #   candidates, breadth: The tree's size; ignored when `options` is given,
        #     which carries its own.
        #   options: Every switch of the tree, kept for the experiment record.
        if options is None:
            if not 1 <= breadth <= candidates:
                raise ValueError("breadth must be between 1 and the candidate count")
            options = TreeOptions(candidates=candidates, breadth=breadth)
        super().__init__(clients, tools)
        self.options = options
        self.candidates = options.candidates
        self.breadth = options.breadth
        self.thoughts: list[Thought] = []

    def select(
        self,
        state: InvestigationState,
        generated: Sequence[Candidate],
        ratings: Sequence[Rating],
        breadth: int | None = None,
    ) -> tuple[list[tuple[Candidate, Rating]], dict[str, str], dict[str, str]]:
        """Rank and cut the rated candidates as the options say.

        Returns the kept candidates with their ratings, best first; why each
        other one was dropped; and why each one kept beyond `breadth` was kept.
        """
        # Variables:
        #   breadth: How many the top-k cut keeps; None uses the options' breadth.
        #   observed: Ids of evidence the factory answered, the only kind that
        #     can rule a candidate out or count as support.
        #   families: Evidence id -> family, for the evidence rubric.
        #   ranked: Every candidate still in the running, best first.
        #   chosen: The kept entries: the top-k, then any extras (P1).
        #   retained: Extra candidate id -> why it was kept.
        options = self.options
        breadth = options.breadth if breadth is None else breadth
        observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
        families = {e.id: evidence_family(e.source_id) for e in state.evidence}
        ranked, dropped = rank_candidates(
            generated,
            ratings,
            set(families),
            observed_ids=observed,
            rank=options.rank,
            families=families,
        )
        if options.retain == "evidence":
            chosen, retained = retain(
                ranked,
                breadth,
                observed,
                extra=options.retain_extra,
                floor=options.retain_floor,
                calls_left=state.remaining_tool_calls,
            )
        else:
            chosen, retained = list(ranked[:breadth]), {}
        kept_ids = {e.candidate.id for e in chosen}
        for entry in ranked:
            if entry.candidate.id not in kept_ids:
                dropped[entry.candidate.id] = ranked_out(entry, breadth)
        return [(e.candidate, e.rating) for e in chosen], dropped, retained

    def hypothesize(self, state: InvestigationState) -> Interpretation:
        # Variables:
        #   view: The same working-memory text every question is shown.
        #   mode, breadth, why: What adaptive branching chose (P3): skip the tree,
        #     the usual breadth or one more; "static" with the usual breadth
        #     when it is off.
        #   generated: The candidate explanations the model proposed, capped at the
        #     candidate count.
        #   shown: The candidates in the order the rating question lists them:
        #     rotated by the investigation id with TOT_ROTATE (P4), else as generated.
        #   ratings: The model's verdict and confidence for each candidate.
        #   kept: The best candidates after pruning, each with its rating, best first.
        #   retained: Candidates kept beyond the breadth, with why (P1).
        #   dropped: Why each other candidate was removed, kept for the record.
        #   hypotheses: The kept candidates turned into hypotheses H1, H2 and so on.
        #   questions: One question per kept candidate that would tell it apart from the
        #     rest.
        view = render(state)
        mode, breadth, why = "static", self.breadth, None
        if self.options.adaptive:
            mode, breadth, why = branching(state, self.options)
            if mode == "skipped":
                self.thoughts.append(
                    Thought(
                        candidates=(),
                        ratings=(),
                        kept=(),
                        dropped={},
                        branching=mode,
                        branching_reason=why,
                    )
                )
                # One clear explanation: the ordinary one-question step.
                return super().hypothesize(state)
        generated = self._ask(
            "hypothesize",
            state,
            view,
            Candidates,
            system=GENERATE.format(count=self.candidates),
        ).candidates[: self.candidates]
        if not generated:
            self.thoughts.append(
                Thought(
                    candidates=(),
                    ratings=(),
                    kept=(),
                    dropped={},
                    branching=mode,
                    branching_reason=why,
                )
            )
            return Interpretation()
        shown = (
            rotated(generated, state.investigation_id.int + len(self.thoughts))
            if self.options.rotate
            else list(generated)
        )
        ratings = self._ask(
            "hypothesize",
            state,
            f"{view}\n\n{candidate_lines(shown)}",
            Ratings,
            system=VALUE,
        ).ratings
        kept, dropped, retained = self.select(state, generated, ratings, breadth)
        self.thoughts.append(
            Thought(
                candidates=tuple(generated),
                ratings=tuple(ratings),
                kept=tuple(c.id for c, _ in kept),
                dropped=dropped,
                # Every kept "impossible" is unproven: a proven one was dropped.
                unresolved=tuple(c.id for c, r in kept if r.verdict == "impossible"),
                retained=retained,
                shown_order=tuple(c.id for c in shown),
                branching=mode,
                branching_reason=why,
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
                    expected_observations=candidate.expected_observations,
                    assumptions=candidate.assumptions,
                    unexplained_evidence_ids=candidate.unexplained_evidence_ids,
                    discriminating_check=candidate.discriminating_check
                    or rating.question,
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

    def revalue(
        self, state: InvestigationState
    ) -> tuple[PrunedInterpretation, RevaluationRecord]:
        """Rate the kept explanations once more, after the test stage (P5).

        No new candidates are generated: the hypotheses are shown under their
        own ids and rated again with what the test stage found. Code, as in the
        first pass, decides what the ratings change: a rated hypothesis takes
        its new confidence; one rated "impossible" is removed only with factory
        evidence against it (otherwise it keeps its confidence); one left
        unrated is left alone. The question goes to the `value` client when
        VALUE_MODEL gave one, else to the `hypothesize` client.
        """
        # Variables:
        #   job: The client the question goes to, and the name it is recorded under.
        #   shown: The hypotheses as candidates, under their own ids.
        #   rated: Hypothesis id -> its first rating in the reply.
        #   observed: Ids of evidence the factory answered, the only kind that
        #     can remove a hypothesis.
        #   against: The factory evidence a hypothesis rated impossible is
        #     contradicted by, from the rating and the hypothesis.
        #   kept, removed: The hypotheses that stay, and the trace of those removed.
        job = "value" if "value" in self.clients else "hypothesize"
        shown = [
            Candidate(
                id=h.id,
                claim=h.claim,
                supporting_evidence_ids=h.supporting_evidence_ids,
                contradicting_evidence_ids=h.contradicting_evidence_ids,
            )
            for h in state.hypotheses
        ]
        ratings = self._ask(
            job,
            state,
            f"{render(state)}\n\n{candidate_lines(shown)}",
            Ratings,
            system=REVALUE,
        ).ratings
        rated: dict[str, Rating] = {}
        for rating in ratings:
            rated.setdefault(rating.candidate_id, rating)
        observed = {p.evidence_id for p in state.provenance if p.origin == "observable"}
        kept, removed, dropped = [], [], {}
        for h in state.hypotheses:
            rating = rated.get(h.id)
            if rating is None:
                kept.append(h)
                continue
            if rating.verdict == "impossible":
                against = (
                    set(rating.contradicting_evidence_ids)
                    | set(h.contradicting_evidence_ids)
                ) & observed
                if against:
                    dropped[h.id] = "rated impossible"
                    removed.append(
                        PrunedCandidate(
                            id=h.id,
                            claim=h.claim,
                            reason="rated impossible after testing",
                            status="contradicted",
                            verdict=rating.verdict,
                            confidence=rating.confidence,
                            supporting_evidence_ids=h.supporting_evidence_ids,
                            contradicting_evidence_ids=tuple(sorted(against)),
                        )
                    )
                    continue
                kept.append(h)  # a say-so is not a contradiction
                continue
            kept.append(h.model_copy(update={"confidence": rating.confidence}))
        record = RevaluationRecord(
            outcome="revalued",
            confidence_before={h.id: h.confidence for h in state.hypotheses},
            confidence_after={h.id: h.confidence for h in kept},
            dropped=dropped,
            unrated=tuple(h.id for h in state.hypotheses if h.id not in rated),
        )
        return (
            PrunedInterpretation(hypotheses=tuple(kept), pruned=tuple(removed)),
            record,
        )
