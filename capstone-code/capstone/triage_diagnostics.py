"""Per-case triage diagnostics built from a finished experiment record.

Two views for finding where a triage went wrong, both from data the record
already holds (no new collection):

- `timing_lines`: where the time went, with the deterministic reads per stage
  kept apart from the conclusion model's wait and its attempts, so slow Python
  is never confused with a slow provider.
- `failure_summary`: one JSON-safe object for a triage that did not finish
  with sufficient evidence: the seed and scenario to rerun, the effective
  profile and its config fingerprint, the source cutoff, and the stop and
  requirement reason codes. Codes and identifiers only: no evidence text, no
  model prose and no hidden simulator truth.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from capstone.agent.triage_trace import requirement_reason_code
from capstone.progress import read_chains, read_ok

if TYPE_CHECKING:
    from capstone.experiment import ExperimentRecord

SUFFICIENT = "evidence_sufficient"


def timing_lines(record: ExperimentRecord) -> list[str]:
    """One TIMING line: deterministic reads by stage, then the conclusion model."""
    # Variables:
    #   triage: The record's triage part; None when the run did not triage.
    #   reads: Per stage, how many reads completed and their summed time.
    #   conclude: The triage's conclusion questions, each with its attempts.
    #   attempts: Every request made for those questions, retries and the
    #     fallback model included.
    triage = record.triage
    if triage is None:
        return []
    reads: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    for event in triage.diagnostic_trace or ():
        if event.event == "tool.completed":
            reads[event.phase][0] += 1
            reads[event.phase][1] += event.duration_ms or 0.0
    parts = [
        f"{phase} reads {int(n)} ({ms:.0f} ms)"
        for phase, (n, ms) in sorted(reads.items())
    ] or ["no deterministic reads"]
    if triage.conclude_model_seconds is not None:
        details = () if record.model_calls is None else record.model_calls.details
        conclude = [
            call
            for call in details or ()
            if call.job == "conclude" and call.mode in (None, "triage")
        ]
        attempts = [a for call in conclude for a in call.attempts]
        tried = ", ".join(
            f"{a.model} {a.outcome}"
            + ("" if a.seconds is None else f" {a.seconds:.1f} s")
            for a in attempts
        )
        parts.append(
            f"conclude model {triage.conclude_model_seconds:.2f} s "
            f"({len(conclude)} question(s), {len(attempts)} attempt(s)"
            + (f": {tried}" if tried else "")
            + ")"
        )
    if triage.conclude_check_seconds is not None:
        parts.append(f"conclude checks {triage.conclude_check_seconds:.3f} s")
    return ["TIMING: " + "; ".join(parts)]


def failure_summary(record: ExperimentRecord, name: str) -> dict | None:
    """A replayable summary of a triage that did not finish sufficient, else None.

    Enough to rerun the same case (`name`, seed, scenario, run key, profile)
    and to see which rule stopped it, without opening the audit log.
    """
    # Variables:
    #   triage: The record's triage part; None when the run did not triage.
    #   events: The triage's typed trace events.
    #   started: The triage.started events, which carry the config fingerprint.
    #   stops: Every stop the controller recorded, phase and reason code.
    #   unresolved: Each requirement not satisfied, with its stable reason code.
    triage = record.triage
    if triage is None or triage.termination_reason == SUFFICIENT:
        return None
    events = list(triage.diagnostic_trace or ())
    started = [e for e in events if e.event == "triage.started"]
    cutoffs = {e.source_cutoff_tick for e in events if e.source_cutoff_tick is not None}
    stops = [
        {"phase": e.phase, "reason": e.reason_code}
        for e in events
        if e.event == "triage.stopped"
    ]
    unresolved = {
        rid: requirement_reason_code(result.status, result.reason)
        for rid, result in sorted((triage.requirement_results or {}).items())
        if result.status != "satisfied"
    }
    failed_reads = [
        {
            "phase": chain["phase"],
            "tool": chain["tool"],
            "request_hash": chain["request_hash"],
            "attempt": chain["attempt"],
            "reason": chain["failure"] or chain["validation"],
        }
        for chain in read_chains(events)
        if not read_ok(chain)
    ]
    return {
        "name": name,
        "run_key": record.run_key,
        "scenario_id": record.scenario_id,
        "seed": record.seed,
        "triage_run_mode": triage.triage_run_mode,
        "config_fingerprint": (started[0].config_fingerprint if started else None),
        "source_cutoff_tick": max(cutoffs) if cutoffs else None,
        "termination_reason": triage.termination_reason,
        "stops": stops,
        "completion_converted": any(
            e.event == "triage.completion_converted" for e in events
        ),
        "unresolved_requirements": unresolved,
        "failed_reads": failed_reads,
    }
