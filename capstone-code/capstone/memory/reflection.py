# Builds the reflection candidate the memory gate checks.
# Responsibility: fill every fact from the finished record; the model adds one sentence.
"""From a finished investigation to a `ReflectionCandidate`.

Code fills every field that states a fact, from the shared record and the
provenance labels written when the evidence arrived:

    category              the symptom that started the investigation, because
                          a later agent looks memories up before it knows the cause
    intervention_worked   from the check: resolved -> True, failed -> False
    diagnosis_assessment  resolved -> supported; anything else -> unknown.
                          A fix that did not work does not prove the diagnosis wrong.
    evidence              what the conclusion and the check cite
    confidence            the conclusion's

The model writes only the advice sentence for a fix that worked. For an
action that did not work, code writes the sentence too (`failure_lesson`):
what was tried, where, and for which symptoms, never why it failed.
Nothing the model says can change the facts beside it. This builder decides nothing: the gate still accepts or
refuses the candidate. Where no outcome was observed (no check, or one that
could not decide) there is nothing to learn from, and no candidate is made.
"""

from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.contracts.provenance import ProvenanceReference
from capstone.memory.contracts import ReflectionCandidate, ReusableLesson
from capstone.memory.policy import failure_lesson

# Check status in the shared record -> did the action work.
WORKED = {"verified": True, "failed": False}


def build_candidate(
    investigation: CompletedInvestigation,
    provenance: tuple[ProvenanceReference, ...],
    lesson: str | None,
) -> ReflectionCandidate | None:
    """The candidate for the gate, or None if there is no outcome or no sentence."""
    check = investigation.verification
    if check is None or check.status not in WORKED:
        return None
    if check.status == "failed" and investigation.proposed_action:
        # What did not work is stated by code; the model may not explain it.
        text = failure_lesson(investigation)
    else:
        text = (lesson or "").strip()
    if not text:
        return None
    cited = tuple(
        dict.fromkeys((*investigation.conclusion.evidence_ids, *check.evidence_ids))
    )
    anomaly = investigation.anomaly
    return ReflectionCandidate(
        investigation=investigation,
        category=(anomaly.symptoms or (anomaly.summary,))[0][:128],
        useful_evidence_ids=cited,
        diagnosis_assessment="supported" if check.status == "verified" else "unknown",
        intervention_worked=WORKED[check.status]
        if investigation.proposed_action
        else None,
        # The two flags are the writer's own claims; the gate checks the text itself.
        lesson=ReusableLesson(
            text=text,
            evidence_ids=cited,
            reusable=True,
            contains_transient_details=False,
        ),
        confidence=investigation.conclusion.confidence,
        provenance=provenance,
    )
