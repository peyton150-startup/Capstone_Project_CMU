# What happens after an investigation ends: keep the record, maybe keep a lesson.
# Responsibility: join the finished loop to the audit log and the memory gate.
"""The step after `run_investigation`, kept outside the agent on purpose.

    state = run_investigation(state, deps)   # the agent's job ends here
    learn_from(state, policy, memory, log)   # trusted code, afterwards

This module imports both `capstone.agent` and `capstone.memory`; the agent
imports neither, so nothing inside the loop holds the audit log or the
memory store and nothing there can write to them or skip the gate.

In order:

1. The audit record is written first, for every investigation, so the
   history never depends on the memory step that follows.
2. The model is asked for its one advice sentence only for a verified fix
   that was carried out. A failed fix needs no model (code writes that
   sentence), and nothing else can become a memory: not even a check that
   found the symptom gone after the agent chose to do nothing, which the
   gate refuses (`no_action_taken`). A model that declines or fails gives
   no lesson.
3. The candidate is built from the shared record and sent through the
   gate to the store. A store failure is raised to the caller; the audit
   record is already on disk.
"""

from uuid import UUID

from capstone.agent.completion import AuditLog, audit_record, complete
from capstone.agent.policy import ReasoningPolicy
from capstone.agent.state import InvestigationState
from capstone.contracts import Contract
from capstone.memory.contracts import PromotionDecision
from capstone.memory.reflection import build_candidate
from capstone.memory.service import MemoryService


class LearningOutcome(Contract):
    """What became of one finished investigation after it ended."""

    investigation_id: UUID
    lesson_requested: bool
    lesson: str | None = None
    decision: PromotionDecision | None = None  # None: nothing went to the gate


def learn_from(
    state: InvestigationState,
    policy: ReasoningPolicy,
    memory: MemoryService,
    log: AuditLog,
) -> LearningOutcome:
    """Audit the investigation, then offer what it showed to the memory gate."""
    # Variables:
    #   state: The finished investigation.
    #   policy: The decision-maker, asked for one advice sentence at most.
    #   memory: The memory service whose gate decides what is kept.
    #   log: Where the audit record is written first, whatever the gate does.
    #   record: The shared record of the investigation; refuses one that has not
    #     finished.
    #   check: The after-the-fix check, if one was made.
    #   requested: True only for a verified fix that was carried out; only then is the
    #     model asked for a sentence.
    #   lesson: The advice sentence, or None if none was asked for or the model failed.
    #   written: The policy's reply before it is reduced to text.
    #   candidate: What goes to the gate, or None if there is no outcome or no sentence.
    record = complete(state)  # refuses an unfinished investigation
    log.append(audit_record(state))
    check = record.verification
    # Ask only when the sentence can reach memory: a fix that was carried out
    # and verified. A verified no-action watch is refused by the gate.
    requested = (
        check is not None
        and check.status == "verified"
        and record.proposed_action is not None
    )
    lesson = None
    if requested:
        try:
            written = policy.write_lesson(state)
        except Exception:  # a failed model call costs the lesson, not the run
            written = None
        lesson = written.text if written is not None else None
    candidate = build_candidate(record, tuple(state.provenance), lesson)
    return LearningOutcome(
        investigation_id=record.investigation_id,
        lesson_requested=requested,
        lesson=lesson,
        decision=memory.promote(candidate) if candidate is not None else None,
    )
