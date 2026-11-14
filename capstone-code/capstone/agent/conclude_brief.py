# What the triage's concluding question is shown about its own testing (Block 5).
# Responsibility: list what was tested, measured and missing; never name a cause.
"""The TRIAGE CONCLUSION BRIEF: a short, bounded section for `conclude` only.

Shown to the concluding model in a triage with TRIAGE_CONCLUDE_BRIEF on,
beside the TRIAGE COVERAGE section. It lists:

- which live explanations a successful read or linked evidence tested, and
  which none did;
- each question predicate's verdict (`agent.evidence_tests.evaluate`), with
  its measured value and sample count when there is one;
- the evidence packet's missing channels, each with its reason.

Every line is built from identifiers, verdicts, counts and reasons: no record
text, no scores and no word about what is wrong. Missing or unsettled
evidence is always said to be unknown, never normal or absent. A deep run
never sees it.
"""

from capstone.agent.evidence_tests import evaluate
from capstone.agent.state import InvestigationState

# The most entries each list names; the rest are counted, so the section stays
# short however much the triage gathered.
MAX_BRIEF_ITEMS = 8
# Packet sources that are physical channels: a missing one is a channel
# nobody observed.
CHANNEL_SOURCES = frozenset({"live_sensor", "derived_screening"})


def capped(entries: list[str]) -> str:
    """The entries joined, with any past MAX_BRIEF_ITEMS counted, not named."""
    # Variables:
    #   extra: How many entries were left out.
    extra = len(entries) - MAX_BRIEF_ITEMS
    shown = "; ".join(entries[:MAX_BRIEF_ITEMS])
    return shown + (f"; and {extra} more" if extra > 0 else "")


def explanations_tested(state: InvestigationState) -> tuple[list[str], list[str]]:
    """Live explanations that were tested, as id (what), and those that were not."""
    # Variables:
    #   reads: Successful reads per hypothesis they were testing.
    #   tested, untested: The two lists, in the hypotheses' own order.
    reads: dict[str, int] = {}
    for decision in state.decisions:
        if decision.outcome == "observed" and decision.hypothesis_id is not None:
            reads[decision.hypothesis_id] = reads.get(decision.hypothesis_id, 0) + 1
    tested, untested = [], []
    for h in state.hypotheses:
        n, support, against = (
            reads.get(h.id, 0),
            len(h.supporting_evidence_ids),
            len(h.contradicting_evidence_ids),
        )
        if n or support or against:
            tested.append(
                f"{h.id} ({n} read(s) aimed at it, {support} supporting and "
                f"{against} contradicting evidence item(s))"
            )
        else:
            untested.append(h.id)
    return tested, untested


def predicate_lines(state: InvestigationState) -> list[str]:
    """Each question predicate and its measured verdict, as one entry each."""
    # Variables:
    #   p: The predicate: which sensor, window, statistic and threshold.
    #   result: Its verdict now, from the evidence gathered so far.
    #   measured: The value and sample count, or why there is no verdict.
    #   cited: The evidence ids the verdict rests on, so the model can check it.
    entries = []
    for question_id, p in sorted(state.question_predicates.items()):
        result = evaluate(p, state)
        if result.value is not None:
            measured = f"value {result.value:g} from {result.sample_count} sample(s)"
        else:
            measured = result.reason
        cited = f"; {', '.join(result.evidence_ids)}" if result.evidence_ids else ""
        entries.append(
            f"{question_id}: {p.statistic} of {p.sensor} on {p.machine_id}, ticks "
            f"{p.from_tick}-{p.to_tick}, {p.comparison} {p.threshold:g}: "
            f"{result.verdict} ({measured}{cited})"
        )
    return entries


def missing_channels(state: InvestigationState) -> list[str]:
    """The packet's unobserved physical channels, each with why; none without one."""
    # Variables:
    #   packet: The triage's Observe packet, the only record of what is missing.
    #   seen: Channels already listed, so a channel missing twice is named once.
    packet = state.triage_packet
    if packet is None:
        return []
    seen: dict[str, str] = {}
    for item in packet.items:
        if item.status != "missing" or item.source_type not in CHANNEL_SOURCES:
            continue
        where = item.physical_root or item.machine_id or "unknown channel"
        seen.setdefault(where, item.missing_reason or "not observed")
    return [f"{where} ({why})" for where, why in seen.items()]


def brief_lines(state: InvestigationState) -> list[str]:
    """The TRIAGE CONCLUSION BRIEF as prompt lines (TRIAGE_CONCLUDE_BRIEF)."""
    # Variables:
    #   tested, untested: Live explanations a read or linked evidence tested,
    #     and those nothing tested; untested is never ruled out.
    #   checks: The predicates' verdicts; an unsettled one is not evidence.
    #   missing: Channels the packet could not observe; unknown, not normal.
    tested, untested = explanations_tested(state)
    checks = predicate_lines(state)
    missing = missing_channels(state)
    lines = [
        "TRIAGE CONCLUSION BRIEF (what was tested and what was not; not a diagnosis):",
        f"Explanations tested: {capped(tested) if tested else 'none'}.",
        f"Explanations not tested: {capped(untested) if untested else 'none'}. "
        "An untested explanation is not ruled out.",
    ]
    if checks:
        lines.append(
            f"Measured checks: {capped(checks)}. Only true or false settles a "
            "check; insufficient, stale or unavailable is unknown, not normal."
        )
    else:
        lines.append("Measured checks: none attached to a question.")
    if state.triage_packet is None:
        lines.append(
            "Missing channels: not recorded (no evidence packet); "
            "unobserved channels are unknown, not normal."
        )
    else:
        lines.append(
            f"Missing channels: {capped(missing) if missing else 'none recorded'}. "
            "A missing channel was not observed; it is not known to be normal."
        )
    return lines
