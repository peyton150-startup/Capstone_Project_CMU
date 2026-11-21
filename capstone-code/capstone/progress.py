# Follows one investigation in the terminal as it happens.
# Responsibility: print what is new in the agent's working state; the truth only after.
"""Watch one episode live: `python -m capstone.progress --seed 7`.

    uv run python -m capstone.progress --seed 7 --fault bearing_degradation
    uv run python -m capstone.progress --seed 7 --approve all --memory

Each step is printed as it happens: the anomaly, every tool call and what
came of it, the agent's beliefs when they change, its conclusion, the
proposal (then the approval question at the prompt, by default), and the
check afterwards. Only what the agent itself has is shown, read from copies
of its working state (`InvestigationDeps.watch`); the simulator is never
read while the run is going. The truth (the score) is printed once the run
is over, under its own heading.

This is the terminal view only. A later frontend (Future Work 8) would sit
on the same hook. Live runs need the model keys; `--memory` reads the
configured store but learns nothing (no audit log).
"""

import argparse
import os
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence

from capstone.agent.evidence_packet import EvidencePacket
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import (
    DecisionRecord,
    InvestigateAdvice,
    InvestigationState,
    Predicate,
    TriageTestRecord,
)
from capstone.agent.triage_report import TriageReport
from capstone.agent.triage_trace import TriageTraceEvent, requirement_reason_code
from capstone.console import safe_console
from capstone.episode import (
    SCENARIO_KINDS,
    STANDARD,
    Approver,
    EpisodeResult,
    approve_all,
    ask_on_console,
    reject_all,
    run_episode,
)
from capstone.evaluation.manual import manual_search_record
from capstone.evaluation.scoring import Score
from capstone.providers.manual import MANUAL_TOOL
from capstone.simulator.generator import FAULTS

Write = Callable[[str], None]

# How much of an evidence item or an argument list fits on one line.
CONTENT_WIDTH = 90
TOP_BELIEFS = 3


# The most missing items the packet line names; the rest are counted.
MAX_PACKET_MISSING = 8


# The most reasons the triage report line lists; the rest are counted.
MAX_REPORT_REASONS = 4


def predicate_text(predicate: Predicate) -> str:
    """A question predicate in one phrase, as the progress view prints it."""
    # Variables:
    #   p: The measured condition that settles one question.
    p = predicate
    return (
        f"{p.statistic} {p.sensor} on {p.machine_id} over t={p.from_tick}-"
        f"{p.to_tick} {p.comparison} {p.threshold:g} (at least {p.min_samples} "
        "readings)"
    )


def fixed_plan_lines(state: InvestigationState) -> list[str]:
    """TRIAGE_PLAN=fixed: the table's questions and their predicates, no model."""
    # Variables:
    #   screening: The plan stage's records of the screening questions:
    #     answered from the packet's screening, or kept open and why.
    #   ids: Every question the table gave, in order, open or already answered.
    #   predicates: The measured conditions that settle some of them, by id.
    screening = [r for r in state.triage_test_records if r.stage == "plan"]
    ids = sorted(
        {q.id for q in state.unanswered_questions}
        | {qid for r in screening for qid in r.question_ids},
        key=lambda qid: (len(qid), qid),
    )
    predicates = state.question_predicates
    lines = [
        f"PLAN fixed table (no model call): {len(ids)} question(s) "
        f"{', '.join(ids) or 'none'}; {len(predicates)} with a predicate"
    ]
    for qid, predicate in predicates.items():
        lines.append(f"  predicate {qid}: {predicate_text(predicate)}")
    for r in screening:
        done = (
            f"answered by {', '.join(r.evidence_ids)}"
            if r.kind == "question_closed"
            else "kept open"
        )
        lines.append(f"  screening {', '.join(r.question_ids)}: {done} ({r.reason})")
    return lines


def report_lines(report: TriageReport) -> list[str]:
    """The read-only triage report: outcome, decision, why held open, summary."""
    # Variables:
    #   held: Why the Python checks held the answer open, at most
    #     MAX_REPORT_REASONS of them.
    #   more: How many reasons were left out of the line.
    lines = [
        f"TRIAGE REPORT {report.outcome}: {report.assessment}, "
        f"{report.recommendation} (model said {report.model_recommendation or '-'})"
        f", confidence {report.confidence:.2f}, deep run "
        f"{'recommended' if report.deep_recommended else 'not needed'}; "
        f"{len(report.findings)} finding(s)"
    ]
    if report.refused_because:
        lines.append(f"  refused: {shorten(report.refused_because, 120)}")
    held = report.held_open_because[:MAX_REPORT_REASONS]
    more = len(report.held_open_because) - len(held)
    for reason in held:
        lines.append(f"  held open: {shorten(reason, 120)}")
    if more:
        lines.append(f"  held open: ... and {more} more")
    lines.append(f"  summary: {shorten(report.summary, 200)}")
    return lines


def ranking_lines(state: InvestigationState) -> list[str]:
    """The checked two-candidate ranking: verdict, attempts, then each pick.

    Empty when TRIAGE_RANKING was off. Confidences are the model's own,
    uncalibrated beliefs; the ranking never changed the report above.
    """
    # Variables:
    #   verdict: The checked ranking; its picks are ordered most plausible first.
    #   families: What each TC id meant in the snapshot the model was shown.
    #   detail: A rejected attempt's field and wrong ids, printed after the
    #     picks so a batch log shows why an answer failed.
    verdict = state.triage_ranking
    if verdict is None:
        return []
    snapshot = state.triage_ranking_snapshot
    families = {c.id: c.family for c in snapshot.candidates} if snapshot else {}
    lines = [
        f"TRIAGE RANKING {verdict.status} ({verdict.reason}); "
        f"{state.triage_ranking_requests} request(s), attempts "
        f"{' -> '.join(state.triage_ranking_attempts)}; "
        f"snapshot {verdict.snapshot_fingerprint}"
        + (f", {len(snapshot.candidates)} candidate(s)" if snapshot else "")
    ]
    for n, pick in enumerate(verdict.picks, start=1):
        lines.append(
            f"  {n}. {pick.candidate_id} {families.get(pick.candidate_id, '?')} "
            f"belief {pick.confidence:.2f} (uncalibrated): "
            f"{shorten(pick.rationale, 120)}"
        )
    if verdict.abstain_reason:
        lines.append(f"  abstained: {verdict.abstain_reason}")
    for n, (reason, detail) in enumerate(
        zip(state.triage_ranking_attempts, state.triage_ranking_details), start=1
    ):
        if detail is not None:
            lines.append(
                f"  attempt {n} {reason} at {detail.field}"
                + (
                    f": {', '.join(detail.offending_ids)}"
                    if detail.offending_ids
                    else ""
                )
                + (
                    f" (named {', '.join(detail.named_ids)})"
                    if detail.named_ids
                    else ""
                )
            )
    return lines


def evidence_test_line(record: TriageTestRecord) -> str:
    """One TRIAGE_EVIDENCE_TESTS record as a line: what the triage rule did."""
    # Variables:
    #   parts: The record's kind, then whichever of its fields are set.
    parts = [f"EVIDENCE TEST {record.kind}"]
    if record.hypothesis_id:
        parts.append(f"hypothesis {record.hypothesis_id}")
    if record.question_ids:
        parts.append(f"question {', '.join(record.question_ids)}")
    if record.roots:
        parts.append(f"sources {', '.join(record.roots)}")
    if record.verdict:
        parts.append(f"verdict {record.verdict}")
    if record.reason:
        parts.append(shorten(record.reason, 120))
    return "; ".join(parts)


def trace_event_line(event: TriageTraceEvent) -> str:
    """One deterministic triage trace event as a line, for --trace.

    The event holds fixed codes, identifiers and counts only (never tool
    payloads or model text), so printing it shows nothing hidden.
    """
    # Variables:
    #   parts: The event's sequence, phase and name, then whichever of its
    #     diagnostic fields are set, in a fixed order.
    parts = [f"TRACE #{event.sequence} {event.phase} {event.event}"]
    parts.append(f"reason {event.reason_code}")
    if event.status:
        parts.append(f"status {event.status}")
    if event.tool:
        parts.append(f"tool {event.tool}")
    if event.requirement_ids:
        parts.append(f"requirements {', '.join(event.requirement_ids)}")
    if event.question_ids:
        parts.append(f"questions {', '.join(event.question_ids)}")
    if event.evidence_ids:
        parts.append(f"evidence {', '.join(event.evidence_ids)}")
    if event.request_hash:
        parts.append(f"request {event.request_hash}")
    if event.remaining_tool_calls is not None:
        parts.append(f"calls left {event.remaining_tool_calls}")
    if event.duration_ms is not None:
        parts.append(f"{event.duration_ms:.0f} ms")
    return "; ".join(parts)


VALIDATION_EVENTS = ("triage.evidence_accepted", "triage.evidence_rejected")


def read_chains(events: Sequence[TriageTraceEvent]) -> list[dict]:
    """Each deterministic read, joined across its events by request hash.

    One read is selected, validated, completed and then reconciled into the
    requirement ledger. Those are separate trace events; this joins them by
    `request_hash` (selection to completion) and by position (the requirement
    evaluations recorded after the read and before the next selection), so a
    failed read shows the exact step where it failed.
    """
    # Variables:
    #   chains: One entry per selected read, in the order selected.
    #   current: The read whose events are being collected; requirement
    #     evaluations after it belong to it until the next read is selected.
    #   by_hash_attempt: Finds a read's entry from a later event with the same
    #     request hash and attempt.
    chains: list[dict] = []
    by_hash_attempt: dict[tuple[str, int | None], dict] = {}
    current: dict | None = None
    for event in events:
        if event.event == "decide.selected" and event.request_hash:
            current = {
                "sequence": event.sequence,
                "phase": event.phase,
                "tool": event.tool,
                "request_hash": event.request_hash,
                "attempt": event.attempt,
                "requirement_ids": event.requirement_ids,
                "validation": None,
                "failure": None,
                "completed": None,
                "duration_ms": None,
                "evidence_ids": (),
                "reconciled": [],
            }
            chains.append(current)
            by_hash_attempt[(event.request_hash, event.attempt)] = current
            continue
        chain = (
            by_hash_attempt.get((event.request_hash, event.attempt))
            if event.request_hash
            else None
        )
        if chain is not None:
            if event.event in VALIDATION_EVENTS:
                chain["validation"] = event.reason_code
            elif event.event == "triage.read_failed":
                chain["failure"] = event.reason_code
            elif event.event == "tool.completed":
                chain["completed"] = event.status or event.reason_code
                chain["duration_ms"] = event.duration_ms
                chain["evidence_ids"] = event.evidence_ids
            continue
        if event.event == "triage.requirement_evaluated" and current is not None:
            touched = set(event.requirement_ids) & set(current["requirement_ids"])
            shared = set(event.evidence_ids) & set(current["evidence_ids"])
            if touched or shared:
                for rid in event.requirement_ids:
                    current["reconciled"].append(f"{rid} {event.status}")
    return chains


def read_ok(chain: dict) -> bool:
    """Whether a read was accepted and completed without a failure."""
    return chain["failure"] is None and chain["validation"] in (None, "accepted")


def read_lines(events: Sequence[TriageTraceEvent], *, every: bool) -> list[str]:
    """One line per read, joined by request hash; only failed ones unless `every`."""
    # Variables:
    #   chains: The reads, from `read_chains`.
    #   steps: What happened to one read, in order: validation or failure,
    #     completion and time, then the requirement results it changed.
    lines = []
    for chain in read_chains(events):
        if not every and read_ok(chain):
            continue
        steps = [f"READ {chain['request_hash']} {chain['phase']} {chain['tool']}"]
        if chain["attempt"] and chain["attempt"] > 1:
            steps[0] += f" attempt {chain['attempt']}"
        steps[0] += f" [{', '.join(chain['requirement_ids'])}]"
        if chain["failure"]:
            steps.append(f"failed {chain['failure']}")
        if chain["validation"]:
            steps.append(f"validation {chain['validation']}")
        if chain["completed"]:
            took = (
                ""
                if chain["duration_ms"] is None
                else f" ({chain['duration_ms']:.0f} ms)"
            )
            steps.append(f"completed {chain['completed']}{took}")
        else:
            steps.append("no completion recorded")
        if chain["reconciled"]:
            steps.append("ledger " + ", ".join(chain["reconciled"]))
        lines.append("  " + " -> ".join(steps))
    if lines:
        lines.insert(0, "READS:" if every else "FAILED READS:")
    return lines


def conversion_line(event: TriageTraceEvent) -> str:
    """A `triage.completion_converted` event: a completion claim was refused."""
    # Variables:
    #   event: The conversion; its requirement and question ids are what was
    #     still unresolved when the controller tried to claim completion.
    parts = [
        f"COMPLETION CONVERTED ({event.phase}): requirements_complete -> "
        f"{event.reason_code}"
    ]
    if event.requirement_ids:
        parts.append(f"unresolved {', '.join(event.requirement_ids)}")
    if event.question_ids:
        parts.append(f"open questions {', '.join(event.question_ids)}")
    return "; ".join(parts)


def requirement_ledger_lines(state: InvestigationState) -> list[str]:
    """The end-of-triage requirement ledger: every requirement and its status.

    One count line, then one line per requirement in id order with its stable
    reason code (`requirement_reason_code`) and how many evidence items back
    it, so a run that stops short shows which requirement held it back.
    """
    # Variables:
    #   results: The triage's requirement results, by requirement id.
    #   counts: How many requirements ended in each status.
    results = state.triage_requirement_results
    if not results:
        return []
    counts = Counter(result.status for result in results.values())
    lines = [
        "REQUIREMENTS: "
        + ", ".join(f"{status} {n}" for status, n in sorted(counts.items()))
    ]
    for rid, result in sorted(results.items()):
        code = requirement_reason_code(result.status, result.reason)
        lines.append(
            f"  {rid}: {result.status} ({code}; {len(result.evidence_ids)} evidence)"
        )
    return lines


def triage_profile_line(settings) -> str | None:
    """The effective triage profile in one line, or None if it is unknown.

    Reads `Settings.effective_triage`, so it shows what the run will really
    do after TRIAGE_RUN_MODE overrides the per-stage settings.
    """
    # Variables:
    #   profile: The resolved TriageExecutionProfile.
    #   models: The triage stages that call a model under this profile.
    try:
        profile = settings.effective_triage
    except AttributeError:
        return None
    models = ["conclude"]
    if profile.plan == "model":
        models.append("plan")
    if profile.investigate != "deterministic":
        models.append("investigate")
    if profile.hypothesize == "model":
        models.append("hypothesize")
    if profile.critic:
        models.append("critic")
    return (
        f"RUN: triage profile {profile.run_mode}: plan {profile.plan}, "
        f"investigate {profile.investigate}, hypothesize {profile.hypothesize}, "
        f"evidence tests {'on' if profile.evidence_tests else 'off'}, "
        f"critic {'on' if profile.critic else 'off'}; "
        f"model-backed stages: {', '.join(models)}"
    )


def print_progress(line: str) -> None:
    """Print a progress line with color on interactive terminals."""
    # Variables:
    #   line: The unchanged progress text to show.
    #   color: ANSI color for the line's label or stage, or None for plain text.
    color = None
    if re.match(r"^\s*beliefs:", line):
        color = "95"
    elif re.match(r"^\s*H\d+\s", line):
        color = "96"
    elif re.match(r"^#\d+\s+observe\b", line):
        color = "92"
    elif re.match(
        r"^#\d+\s+(plan|investigate|research|hypothesize|test|decide|verify)\b", line
    ):
        color = "93"
    elif re.match(
        r"^(RUN|CONCLUSION|PROPOSAL|CHECK|CRITIC|FOLLOW-UP|REQUIREMENTS|READS|FAILED READS"
        r"|COMPLETION CONVERTED|TIMING|REPLAY|  why:|  confidence "
        r"|  tried for |  assessment:|  calls:)",
        line,
    ):
        color = "95"
    elif re.match(r"^\s*->", line):
        color = "36"
    elif line.startswith("TRACE #"):
        color = "90"
    if color and sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        print(f"\033[{color}m{line}\033[0m", flush=True)
    else:
        print(line, flush=True)


def shorten(text: str, width: int = CONTENT_WIDTH) -> str:
    """One line, at most `width` characters, cut with "..." when longer."""
    # Variables:
    #   width: The longest the line may be.
    #   line: The text with newlines and extra spaces collapsed.
    line = " ".join(str(text).split())
    return line if len(line) <= width else line[: width - 3] + "..."


def call_text(decision: DecisionRecord) -> str:
    arguments = ", ".join(f"{k}={v}" for k, v in decision.arguments.items())
    return f"{decision.tool}({shorten(arguments, 60)})"


def step_line(decision: DecisionRecord, state: InvestigationState) -> list[str]:
    """The lines for one decision: what was asked, and what came of it.

    A manual search gets one more line saying how it went (answered, failed,
    repeated or out of searches) and which sections came back, since a manual
    being offered does not mean a search worked.
    """
    # Variables:
    #   lines: The call and its result, from `call_lines`.
    lines = call_lines(decision, state)
    if decision.tool == MANUAL_TOOL:
        lines.append(manual_line(decision, state))
    return lines


def manual_line(decision: DecisionRecord, state: InvestigationState) -> str:
    """How one manual search went, as the saved manual record would say it."""
    # Variables:
    #   record: The search classified as the experiment's records classify it.
    #   who: Whether the loop's manual step made the search or the agent chose it.
    #   found: The sections returned, or a note that none matched.
    record = manual_search_record(decision, {e.id: e.content for e in state.evidence})
    who = "manual step" if record.automatic else "agent's search"
    if record.outcome != "answered":
        # A failure's own message (if any) is on the line above; the tool does
        # not record the cause, so this line does not guess one.
        return f"       manual ({who}): {record.outcome.replace('_', ' ')}"
    found = ", ".join(record.sections) or "no section matched"
    return f"       manual ({who}): answered, sections {found}"


def call_lines(decision: DecisionRecord, state: InvestigationState) -> list[str]:
    """The call one decision made and what came of it."""
    # Variables:
    #   decision: One step the agent took.
    #   state: The agent's working state, read for the evidence the step produced.
    #   where: The step's number and phase, as the line's prefix.
    #   tick: The factory time of the step, if known.
    #   reason: Why the loop stopped, for a stop step.
    #   why: That reason in words.
    #   head: The first line: the prefix and the tool call, then the decide
    #     answer it came from ("batch 3.2": answer 3, second call) when batching.
    #   contents: The text of each piece of evidence, by id.
    #   origins: Where each piece of evidence came from.
    #   lines: Every line for this step.
    #   origin: Where this piece came from; anything but a look at the factory is
    #     marked.
    #   label: The mark shown for non-factory evidence.
    where = f"#{decision.sequence:<3} {decision.phase:<11}"
    tick = "" if decision.tick is None else f" t={decision.tick}"
    if decision.outcome == "stopped":
        reason = decision.termination_reason
        why = reason.value if reason is not None else "stopped"
        return [f"{where} stop: {why} ({decision.information_needed}){tick}"]
    if decision.tool is None:
        return [f"{where} {decision.outcome}: {decision.information_needed}{tick}"]
    head = f"{where} {call_text(decision)}{tick}"
    if decision.batch is not None:
        head += f"  [batch {decision.batch}.{decision.batch_position}]"
    if decision.outcome == "repeated_call":
        return [f"{head}  -> skipped: already asked at this tick"]
    if decision.error is not None:
        return [f"{head}  -> failed: {shorten(decision.error.message, 70)}"]
    if not decision.evidence_ids:
        return [f"{head}  -> {decision.outcome}"]
    contents = {e.id: e.content for e in state.evidence}
    origins = {p.evidence_id: p.origin for p in state.provenance}
    lines = [head]
    for evidence_id in decision.evidence_ids:
        origin = origins.get(evidence_id, "observable")
        label = "" if origin == "observable" else f" [{origin}]"
        lines.append(
            f"       -> {evidence_id}{label}: {shorten(contents.get(evidence_id, ''))}"
        )
    return lines


class ProgressView:
    """Prints what is new in an investigation each time it is shown the state.

    Pass it as `watch` to `run_episode`. It keeps its own place (how many
    decisions it has printed, the last beliefs, conclusion, proposal and
    check it showed), so being shown the same state twice prints nothing.
    """

    def __init__(self, write: Write = print_progress, *, trace: bool = False):
        # Variables:
        #   write: Where lines go; colored terminal output by default, replaced in tests.
        #   trace: With --trace, also print every deterministic triage trace
        #     event (`trace_event_line`) as it is recorded.
        #   trace_shown: How many trace events were printed, so each is shown once.
        #   ledger_shown: Whether the requirement ledger has been printed; it is
        #     printed once, with the triage report, followed by the reads (all
        #     of them with trace, else only the failed ones).
        #   events_seen: How many trace events were checked for a completion
        #     conversion, which is printed even without trace.
        #   started: Whether the opening line has been printed.
        #   decisions_shown: How many steps have been printed, so only new ones are.
        #   beliefs: The leading beliefs last printed.
        #   pruned_shown: How many tree-of-thought candidates were printed, so
        #     each is shown once.
        #   conclusion: The conclusion last printed.
        #   proposal: The proposal last printed.
        #   verification: The check last printed.
        #   critique: The critic's record last printed.
        #   recheck: The critic follow-up's record last printed.
        #   packet_shown: Whether the triage evidence packet has been printed.
        #   advice_shown: How many TRIAGE_INVESTIGATE records were printed, so
        #     each is shown once.
        #   tests_shown: How many TRIAGE_EVIDENCE_TESTS records were printed,
        #     so each is shown once.
        #   plan_shown: Whether the TRIAGE_PLAN=fixed plan has been printed.
        #   report: The triage report last printed.
        self.write = write
        self.started = False
        self.decisions_shown = 0
        self.beliefs: tuple = ()
        self.pruned_shown = 0
        self.conclusion = None
        self.proposal = None
        self.verification = None
        self.critique = None
        self.recheck = None
        self.packet_shown = False
        self.advice_shown = 0
        self.tests_shown = 0
        self.plan_shown = False
        self.report = None
        self.trace = trace
        self.trace_shown = 0
        self.ledger_shown = False
        self.events_seen = 0

    def __call__(self, state: InvestigationState) -> None:
        # Variables:
        #   state: A copy of the agent's working state; this view only reads it.
        #   anomaly: What monitoring noticed first.
        #   where: The machine named, or the factory as a whole.
        #   c: The agent's conclusion.
        #   proposal: The repair request, if one was made.
        #   check: The after-the-fix check, if one was made.
        if not self.started:
            self.started = True
            anomaly = state.anomaly
            where = anomaly.machine_id or "the factory"
            self.write(f"anomaly at t={anomaly.tick} on {where}: {anomaly.description}")
        for decision in state.decisions[self.decisions_shown :]:
            for line in step_line(decision, state):
                self.write(line)
        self.decisions_shown = len(state.decisions)
        if state.fixed_plan_used and not self.plan_shown:
            self.plan_shown = True
            for line in fixed_plan_lines(state):
                self.write(line)
        if state.triage_packet is not None and not self.packet_shown:
            self.packet_shown = True
            for line in packet_lines(state.triage_packet):
                self.write(line)
        for advice in state.investigate_advice[self.advice_shown :]:
            self.write(advice_line(advice))
        self.advice_shown = len(state.investigate_advice)
        for record in state.triage_test_records[self.tests_shown :]:
            self.write(evidence_test_line(record))
        self.tests_shown = len(state.triage_test_records)
        if self.trace:
            for event in state.triage_trace_events[self.trace_shown :]:
                self.write(trace_event_line(event))
            self.trace_shown = len(state.triage_trace_events)
        for event in state.triage_trace_events[self.events_seen :]:
            if event.event == "triage.completion_converted":
                self.write(conversion_line(event))
        self.events_seen = len(state.triage_trace_events)
        self._beliefs(state)
        self._pruned(state)
        self._critique(state)
        self._recheck(state)
        if state.conclusion is not None and state.conclusion != self.conclusion:
            self.conclusion = state.conclusion
            c = state.conclusion
            self.write(
                f"CONCLUSION ({c.confidence:.2f}, {c.recommendation}): "
                f"{shorten(c.diagnosis, 200)}"
            )
            for line in assessment_lines(c):
                self.write(line)
            self.write(calls_line(state))
        if state.triage_report is not None and state.triage_report != self.report:
            self.report = state.triage_report
            for line in report_lines(state.triage_report):
                self.write(line)
            for line in ranking_lines(state):
                self.write(line)
            if not self.ledger_shown:
                self.ledger_shown = True
                for line in requirement_ledger_lines(state):
                    self.write(line)
                for line in read_lines(state.triage_trace_events, every=self.trace):
                    self.write(line)
        proposal = state.proposed_action
        if proposal is not None and proposal != self.proposal:
            self.proposal = proposal
            self.write(
                f"PROPOSAL {proposal.action} on {proposal.machine_id} "
                f"[{proposal.status}]: {shorten(proposal.reason, 120)}"
            )
        check = state.verification
        if check is not None and check != self.verification:
            self.verification = check
            self.write(f"CHECK: {check.outcome} ({shorten(check.prediction, 120)})")
            self.write(calls_line(state))

    def _recheck(self, state: InvestigationState) -> None:
        """What the critic follow-up did, printed once when it first appears."""
        # Variables:
        #   record: The follow-up's record; compared with the last one printed.
        #   why: The trigger (objection or agreement), or "skipped".
        #   call: The tool it used and the evidence it got, when it made a call.
        #   got: That evidence's id, or "no evidence" when the call gave nothing.
        record = state.recheck
        if record is None or record == self.recheck:
            return
        self.recheck = record
        if record.outcome == "skipped":
            self.write(f"FOLLOW-UP skipped: {record.reason or 'no reason recorded'}")
            return
        why = record.trigger or "no trigger"
        call = ""
        if record.tool is not None:
            got = record.evidence_id or "no evidence"
            call = f", {record.tool} -> {got}"
        self.write(f"FOLLOW-UP ({why}): {record.outcome.replace('_', ' ')}{call}")
        if record.reason:
            self.write(f"  why: {shorten(record.reason, 120)}")
        if record.question:
            self.write(f"  question: {shorten(record.question, 120)}")
        if record.leading_before is not None:
            self.write(
                f"  leader before {belief(record.leading_before, record.confidence_before)}"
                f", after {belief(record.leading_after, record.confidence_after)}"
            )

    def _critique(self, state: InvestigationState) -> None:
        """The critic's verdict, printed once when it first appears."""
        # Variables:
        #   record: What the critic stage produced; compared with the last one
        #     printed so the lines appear once.
        #   r: The critic's reply; None when there was no usable one.
        #   kinds: The kinds of objection the critic raised, in order, so the line
        #     shows how it objected without printing every sentence.
        #   mode: ", blind" for a blind critique; anchored ones keep the plain
        #     heading, so either treatment is plain from the first line.
        record = state.critique
        if record is None or record == self.critique:
            return
        self.critique = record
        r = record.result
        mode = ", blind" if record.blind else ""
        if r is None:
            self.write(f"CRITIC ({record.outcome}{mode}): no critique")
            self.write(f"  tried for {record.seconds:.1f} s")
            return
        kinds = ", ".join(o.kind for o in r.objections) or "none"
        self.write(
            f"CRITIC ({record.outcome}{mode}): favoured {r.favoured}, {r.verdict}, "
            f"check: {shorten(r.discriminating_check, 120)}"
        )
        if record.blind and record.shown_order:
            self.write(f"  {shown_order_line(record)}")
        self.write(f"  why: {shorten(r.why, 120)}")
        if record.verdict_mismatch:
            self.write(f"  verdict does not match the pick: {record.verdict_mismatch}")
        self.write(
            f"  confidence {r.favoured_confidence:.2f}, supports action: "
            f"{'yes' if r.supports_action else 'no'}, objections: {kinds}; "
            f"{record.answered_by or 'unknown model'} in {record.seconds:.1f} s"
        )

    def _beliefs(self, state: InvestigationState) -> None:
        """The leading hypotheses, printed only when they changed."""
        # Variables:
        #   leading: The most confident hypotheses, at most TOP_BELIEFS.
        #   beliefs: Their id, claim and confidence; printed only if they differ from
        #     last time.
        leading = sorted(state.hypotheses, key=lambda h: -h.confidence)[:TOP_BELIEFS]
        beliefs = tuple((h.id, h.claim, round(h.confidence, 2)) for h in leading)
        if beliefs and beliefs != self.beliefs:
            self.beliefs = beliefs
            self.write("  beliefs:")
            for hypothesis_id, claim, confidence in beliefs:
                self.write(
                    f"    {hypothesis_id} {confidence:.2f}  {shorten(claim, 80)}"
                )

    def _pruned(self, state: InvestigationState) -> None:
        """What tree-of-thought dropped, printed once when it first appears.

        Contradicted candidates were ruled out by evidence; deferred ones were
        only set aside (rated lower, not disproved), so they get their own heading.
        """
        # Variables:
        #   new: Pruned candidates not printed yet.
        #   heading: The heading for one status.
        #   group: The new candidates with that status, in the order pruned.
        new = state.pruned_candidates[self.pruned_shown :]
        if not new:
            return
        self.pruned_shown = len(state.pruned_candidates)
        for status, heading in PRUNED_HEADINGS.items():
            group = [p for p in new if p.status == status]
            if not group:
                continue
            self.write(heading)
            for p in group:
                self.write(f"    {p.id}  {shorten(p.claim, 60)}  ({p.reason})")


PRUNED_HEADINGS = {
    "contradicted": "  ruled out by tree-of-thought (contradicted by evidence):",
    "deferred": "  set aside by tree-of-thought (deferred, not disproved):",
}


def belief(hypothesis_id: str | None, confidence: float | None) -> str:
    """A hypothesis id with its confidence, or "none"."""
    if hypothesis_id is None:
        return "none"
    return hypothesis_id if confidence is None else f"{hypothesis_id} {confidence:.2f}"


def shown_order_line(record) -> str:
    """Which label stood for which hypothesis in a blind critique.

    The agent's leader is the first of `shown_hypotheses` (the anchored order),
    so its position in the shuffle shows whether the critic picked by place.
    """
    # Variables:
    #   record: A blind CritiqueRecord with its shown order.
    #   labels: Each shown label with the hypothesis it stood for.
    #   leader: The agent's leading hypothesis when the critic was asked.
    labels = [f"X{n}={h}" for n, h in enumerate(record.shown_order, start=1)]
    line = "shown as " + ", ".join(labels)
    leader = record.shown_hypotheses[0] if record.shown_hypotheses else None
    if leader in record.shown_order:
        line += (
            f"; the agent's leader {leader} was X{record.shown_order.index(leader) + 1}"
        )
    return line


def assessment_lines(conclusion) -> list[str]:
    """Whether the agent called its diagnosis supported or unresolved, and what is open.

    Explains why a plausible diagnosis can still end in escalation. Older
    conclusions without an assessment print nothing.
    """
    # Variables:
    #   conclusion: The agent's AgentConclusion.
    #   lines: The assessment, then the open questions and the next check if any.
    if conclusion.assessment is None:
        return []
    lines = [f"  assessment: {conclusion.assessment}"]
    if conclusion.unresolved_questions:
        lines.append(
            "  open: " + shorten("; ".join(conclusion.unresolved_questions), 160)
        )
    if conclusion.next_check:
        lines.append(f"  next check: {shorten(conclusion.next_check, 120)}")
    return lines


def advice_line(advice: InvestigateAdvice) -> str:
    """One TRIAGE_INVESTIGATE record: the compiled read and what the model did."""
    # Variables:
    #   chose: The compiled read, or why there was none.
    #   model: What the model asked for, when it was asked.
    if advice.root is not None:
        chose = (
            f"{advice.tool} {advice.root} t={advice.from_tick}-{advice.to_tick} "
            f"for {advice.question_id}"
        )
    else:
        chose = f"none ({advice.reason})"
    model = (
        ""
        if advice.outcome == "compiled"
        else f"; model {advice.model_tool or '-'} {advice.model_root or ''}".rstrip()
    )
    return (
        f"INVESTIGATE {advice.mode} {advice.phase} ({advice.source}): "
        f"{advice.candidates} candidate(s); compiled {chose}{model}; {advice.outcome}"
    )


def packet_lines(packet: EvidencePacket) -> list[str]:
    """The triage evidence packet in a few lines: calls, coverage, what is missing."""
    # Variables:
    #   calls: Each call as tool:role:outcome, with "+q" when its answer qualified.
    #   missing: Each missing item as where:reason, at most MAX_PACKET_MISSING.
    #   roster: Whether the expected-machine roster was read, and what it lacked.
    calls = ", ".join(
        f"{c.tool}:{c.role}:{c.outcome}{'+q' if c.qualified else ''}"
        for c in packet.calls
    )
    missing = [
        f"{i.physical_root or i.machine_id or '?'}:{i.missing_reason}"
        for i in packet.items
        if i.status == "missing"
    ]
    shown = missing[:MAX_PACKET_MISSING]
    more = len(missing) - len(shown)
    roster = (
        f"roster {len(packet.roster)} machine(s)"
        + (
            f", absent from screening: {', '.join(packet.absent_from_screening)}"
            if packet.absent_from_screening
            else ""
        )
        if packet.roster_verified
        else "roster not verified"
    )
    return [
        f"PACKET t={packet.trigger_tick} cutoff, as of t={packet.observation_tick}; "
        f"{len(packet.qualified_roots)} qualified sensor root(s); {roster}",
        f"  calls: {calls}",
        "  missing (unknown, not normal): "
        + (", ".join(shown) if shown else "none")
        + (f" (+{more} more)" if more > 0 else ""),
    ]


def calls_line(state: InvestigationState) -> str:
    """The three separate call allowances, used against their limits.

    Research, the critic's one check, and the checks after an action are
    budgeted apart (`InvestigationState.research_tool_calls`), so one running
    out does not spend the others.
    """
    # Variables:
    #   budgets: The run's limits.
    budgets = state.budgets
    return (
        f"  calls: research {state.research_tool_calls}/{budgets.max_tool_calls}, "
        f"critic check {state.critic_tool_calls_used}/{budgets.critic_tool_calls}, "
        f"after the action {state.followup_tool_calls_used}/{budgets.followup_tool_calls}"
    )


def late_thinking_words(settings) -> str:
    """The late model's thinking in words: off, on, or on with a token budget."""
    if not settings.late_model_thinking:
        return "off"
    budget = settings.late_model_reasoning_budget
    return "on" if budget is None else f"on, budget {budget} tokens"


def run_header(
    settings,
    *,
    manual: str | None,
    tree_of_thought: bool = False,
    hazards=False,
    stage_context: bool | None = None,
    triage: bool = False,
) -> list[str]:
    """What this run is set to, printed once before the first case.

    Names the critic treatment (off, anchored or blind, and the follow-up),
    the manual (how it is searched and, for semantic search, the embedding
    model), the manual step, tree-of-thought, hazards and, when set, the
    decide step's reasoning effort and the late-run model. Model names only:
    no key or other secret is read here.
    """
    # Variables:
    #   settings: The project settings (CRITIC, CRITIC_BLIND, ... EMBEDDING_MODEL).
    #   manual: semantic, keyword, or None for no manual.
    #   tree_of_thought: Whether the hypothesize step branches and prunes.
    #   hazards: False, True / "standard", or "blackout".
    #   stage_context: Whether the run uses the stage views; None leaves the line
    #     out, so a caller that does not know prints the usual header.
    #   triage: Whether this run triages; if so, a line names the effective
    #     triage profile (`triage_profile_line`).
    #   deterministic: Whether TRIAGE_RUN_MODE=deterministic, so the triage
    #     model line says it answers the conclusion only.
    #   critic: The critic treatment in words.
    #   book: The manual setting in words.
    #   calls: DECIDE_CALLS; a third line names it only above 1, so the usual
    #     header is unchanged.
    #   effort: DECIDE_REASONING_EFFORT, or None when it is not set; a third
    #     line names it only when set, so the usual header is unchanged.
    #   triage: TRIAGE_MODEL, or None when it is not set; a line names it and
    #     its thinking only when set, so the usual header is unchanged.
    #   late: LATE_MODEL, or None when it is not set; a line names it, its
    #     threshold and its thinking only when set, so the usual header is
    #     unchanged.
    #   settings.late_conclude: Adds the conclusion route to the header only
    #     when it is enabled alongside LATE_MODEL.
    if not settings.critic:
        critic = "critic off"
    else:
        critic = (
            f"critic {'blind' if settings.critic_blind else 'anchored'}, "
            f"follow-up {'on' if settings.critic_followup else 'off'}"
        )
    if manual is None:
        book = "no manual"
    elif manual == "semantic":
        book = f"manual by meaning ({settings.embedding_model})"
    else:
        book = f"manual by {manual}"
    if hazards is True:
        hazards = "standard"
    lines = [
        f"RUN: {critic}; {book}, manual step {'on' if settings.manual_step else 'off'}",
        f"RUN: tree-of-thought {'on' if tree_of_thought else 'off'}; "
        f"hazards {hazards or 'off'}",
    ]
    if stage_context is not None:
        lines.append(f"RUN: stage views {'on' if stage_context else 'off'}")
    calls = getattr(settings, "decide_calls", 1)
    if calls > 1:
        lines.append(f"RUN: up to {calls} tool calls per decide answer")
    effort = getattr(settings, "decide_reasoning_effort", None)
    if effort is not None:
        lines.append(f"RUN: decide reasoning effort {effort} (NVIDIA models only)")
    if triage:
        profile = triage_profile_line(settings)
        if profile is not None:
            lines.append(profile)
    deterministic = getattr(settings, "triage_run_mode", "custom") == "deterministic"
    model = getattr(settings, "triage_model", None)
    if model is not None:
        role = "triage conclusion only" if deterministic else "every triage question"
        lines.append(
            f"RUN: triage model {model} ({role}; thinking "
            f"{'on' if settings.triage_model_thinking else 'off'})"
        )
    late = getattr(settings, "late_model", None)
    if late is not None:
        lines.append(
            f"RUN: late-run model {late} (decide with under "
            f"{settings.late_model_seconds:g} s left; thinking "
            f"{late_thinking_words(settings)})"
        )
        if settings.late_conclude:
            lines.append(
                f"RUN: late conclude model {late} (under "
                f"{settings.late_model_seconds:g} s left; thinking "
                f"{late_thinking_words(settings)})"
            )
    return lines


def truth_lines(score: Score) -> list[str]:
    """The evaluator's side, for after the run: what was really wrong and how it went."""
    # Variables:
    #   score: The scored run, which holds the hidden truth.
    #   causes: The true faults in words.
    #   asked: Everything the agent asked for.

    def target(machine_id, batch_id) -> str:
        # Variables:
        #   machine_id: The machine a fault was on, if it was on one.
        #   batch_id: The batch a fault was in, if it was a batch.
        return f"batch {batch_id}" if batch_id is not None else str(machine_id)

    if score.causes:
        causes = "; ".join(
            f"{c.fault} on {target(c.machine_id, c.batch_id)}" for c in score.causes
        )
    else:
        causes = f"{score.true_fault} on {target(score.true_machine_id, score.true_batch_id)}"
    asked = ", ".join(score.recommended_actions) or "nothing"
    return [
        "--- after the run: the truth (the agent never saw this) ---",
        f"true cause: {causes}",
        f"asked for: {asked} "
        f"({'right' if score.recommendation_correct else 'not the needed fix'})",
        f"resolved: {'yes' if score.resolved else 'no'}; "
        f"tool calls: {score.tool_calls}; stop: {score.termination_reason}",
        "root cause not judged here: label it with `python -m capstone.experiment "
        "label` to score it",
    ]


def watch_episode(
    seed: int,
    policy: ReasoningPolicy,
    *,
    write: Write = print_progress,
    **options,
) -> EpisodeResult:
    """Run one episode with the view attached; print the truth only at the end.

    Other options go to `run_episode` (fault, kind, approver, memory, ...).
    """
    # Variables:
    #   seed: Decides the whole factory.
    #   policy: The decision-maker.
    #   write: Where lines go.
    #   options: Passed on to the episode, such as fault, kind or approver.
    #   result: The finished episode; its truth is printed only now, after the run.
    result = run_episode(seed, policy, watch=ProgressView(write), **options)
    for line in truth_lines(result.score):
        write(line)
    return result


APPROVERS: dict[str, Approver] = {
    "console": ask_on_console,
    "all": approve_all,
    "none": reject_all,
}


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()  # a conclusion with "→" must not stop the run
    parser = argparse.ArgumentParser(prog="python -m capstone.progress")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--fault", choices=FAULTS, help="default: the seed's own")
    parser.add_argument("--kind", choices=SCENARIO_KINDS, default=STANDARD)
    parser.add_argument(
        "--approve",
        choices=list(APPROVERS),
        default="console",
        help="console: ask at the prompt (default); all / none: decide for you",
    )
    parser.add_argument("--memory", action="store_true", help="recall, learn nothing")
    parser.add_argument("--manual", choices=["keyword", "semantic"])
    parser.add_argument("--hazards", action="store_true", help="unreliable tools")
    args = parser.parse_args(argv)

    from capstone.experiment import model_policy_factory, open_manual, open_memory
    from capstone.settings import get_settings

    for line in run_header(get_settings(), manual=args.manual, hazards=args.hazards):
        print_progress(line)
    memory = open_memory() if args.memory else None
    manual = open_manual(args.manual) if args.manual else None
    policy = model_policy_factory(
        with_recall=memory is not None, with_manual=manual is not None
    )()
    watch_episode(
        args.seed,
        policy,
        fault=args.fault,
        kind=args.kind,
        approver=APPROVERS[args.approve],
        memory=memory,
        hazards=args.hazards,
        manual=manual,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
