# Applies deterministic checks before an investigation lesson becomes memory.
# Responsibility: reject unsupported, transient, or hidden-truth candidates.
import hashlib
import json
import math
import re
import unicodedata
from uuid import uuid5

from capstone.contracts.completed_investigations import CompletedInvestigation
from capstone.memory.contracts import (
    EpisodicMemory,
    PromotionDecision,
    ReflectionCandidate,
)

_HIDDEN = re.compile(
    r"ground[ _-]?truth|bearing_health|defect_risk|evaluator_hidden|simulator_hidden",
    re.IGNORECASE,
)
_SAMPLE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mm/s|rpm|°[FC]|degrees?\b)|\btick\s+\d+\b",
    re.IGNORECASE,
)


def normalize(value: str) -> str:
    """Normalize superficial wording differences; no semantic inference."""
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def lesson_fingerprint(category: str, lesson: str) -> str:
    payload = json.dumps([normalize(category), normalize(lesson)], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def failure_lesson(investigation: CompletedInvestigation) -> str:
    """The one sentence kept for an action that did not work: only what was seen.

    It names what was done, where, and for which symptoms. It never says why
    the action failed: the check cannot tell a wrong diagnosis from a repair
    on the wrong machine, so neither may be remembered.
    """
    action = investigation.proposed_action
    symptoms = investigation.anomaly.symptoms or (investigation.anomaly.summary,)
    return (
        f"{action.action} on {action.machine_id} was tried for "
        f"{', '.join(symptoms)} and the check afterwards found it unresolved."
    )


class MemoryPromotionPolicy:
    version = "episodic-v3"

    def __init__(self, *, min_confidence: float = 0.8):
        if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
            raise ValueError("min_confidence must be between zero and one")
        self.min_confidence = min_confidence

    def evaluate(self, candidate: ReflectionCandidate) -> PromotionDecision:
        """Check a candidate without I/O, seeded randomness, or evaluator access.

        Two kinds of lesson may pass: advice from a verified fix that was
        carried out, and the fixed statement that an action was tried and the
        check found it did not work. Doing nothing, even when the check found
        the symptom gone, teaches nothing (`no_action_taken`). Every other
        check below applies to both.
        """
        incident = candidate.investigation
        verification = incident.verification
        resolved = bool(
            verification
            and (verification.status, verification.outcome) == ("verified", "resolved")
        )
        failed = bool(
            verification
            and (verification.status, verification.outcome) == ("failed", "unresolved")
        )
        reasons = []
        if not (resolved or failed):
            reasons.append("outcome_not_verified")
        if resolved:
            # With nothing done, "resolved" only says the symptom paused: no
            # change links cause to result, and a slow fault can look the same
            # on a short watch (a worn bearing was stored as "a transient spike,
            # no change needed" on 2026-10-24). v3 keeps no such lesson.
            if incident.proposed_action is None:
                reasons.append("no_action_taken")
            if candidate.diagnosis_assessment != "supported":
                reasons.append("diagnosis_not_supported")
            if incident.proposed_action and candidate.intervention_worked is not True:
                reasons.append("intervention_not_successful")
            if (
                min(candidate.confidence, incident.conclusion.confidence)
                < self.min_confidence
            ):
                reasons.append("low_confidence")
        if failed:
            # The stored claim rests on the check, not on the agent's confidence.
            if incident.proposed_action is None:
                reasons.append("nothing_was_tried")
            elif candidate.lesson.text.strip() != failure_lesson(incident):
                reasons.append("lesson_not_factual")
            if candidate.diagnosis_assessment != "unknown":
                reasons.append("diagnosis_cannot_be_judged")
            if candidate.intervention_worked is not False:
                reasons.append("intervention_outcome_mismatch")
        if not candidate.lesson.reusable or not normalize(candidate.lesson.text):
            reasons.append("not_reusable")
        if candidate.lesson.contains_transient_details or _SAMPLE.search(
            candidate.lesson.text
        ):
            reasons.append("transient_details")
        if (
            not incident.conclusion.evidence_ids
            or not candidate.lesson.evidence_ids
            or (verification and not verification.evidence_ids)
        ):
            reasons.append("insufficient_evidence")

        references = (
            set(candidate.useful_evidence_ids)
            | set(candidate.lesson.evidence_ids)
            | set(incident.conclusion.evidence_ids)
        )
        if verification:
            references.update(verification.evidence_ids)
        if incident.proposed_action:
            references.update(incident.proposed_action.evidence_ids)
        evidence = {e.id: e for e in incident.evidence}
        all_references = references | set(candidate.misleading_evidence_ids)
        if not all_references <= evidence.keys():
            reasons.append("missing_evidence")
        provenance = {p.evidence_id: p for p in candidate.provenance}
        if not references <= provenance.keys():
            reasons.append("missing_provenance")
        if len(provenance) != len(candidate.provenance):
            reasons.append("provenance_mismatch")
        for ref in references & provenance.keys() & evidence.keys():
            source, observed = provenance[ref], evidence[ref]
            if (source.source_id, source.source_type, source.observed_tick) != (
                observed.source_id,
                observed.source_type,
                observed.observed_tick,
            ):
                reasons.append("provenance_mismatch")
                break
        # A recalled memory may have guided where to look, but a new lesson must
        # stand on this investigation's own observations, or lessons could
        # confirm each other with nothing new seen.
        if any(
            provenance[ref].origin == "memory" for ref in references & provenance.keys()
        ):
            reasons.append("rests_on_memory")
        # The manual may explain what was seen, but a lesson that cites only
        # the manual has seen nothing in this factory.
        cited = [provenance[ref].origin for ref in references & provenance.keys()]
        if cited and all(origin == "manual" for origin in cited):
            reasons.append("rests_on_manual")
        # Scan the whole input, including unused evidence, so tainted artifacts
        # do not become trusted merely by omitting a reference from the lesson.
        if any(
            p.origin in {"evaluator_hidden", "simulator_hidden"}
            for p in candidate.provenance
        ) or _HIDDEN.search(candidate.model_dump_json()):
            reasons.append("hidden_truth")
        if reasons:
            return PromotionDecision(
                investigation_id=incident.investigation_id,
                accepted=False,
                reasons=tuple(dict.fromkeys(reasons)),
                policy_version=self.version,
            )

        fingerprint = lesson_fingerprint(candidate.category, candidate.lesson.text)
        memory = EpisodicMemory(
            memory_id=uuid5(incident.investigation_id, f"memory/{self.version}"),
            run_id=incident.run_id,
            investigation_id=incident.investigation_id,
            category=normalize(candidate.category),
            symptoms=incident.anomaly.symptoms or (incident.anomaly.summary,),
            evidence_ids=tuple(sorted(references)),
            diagnosis=incident.conclusion.diagnosis,
            intervention=incident.proposed_action,
            outcome="resolved" if resolved else "unresolved",
            verification=verification,
            lesson=candidate.lesson.text.strip(),
            confidence=min(candidate.confidence, incident.conclusion.confidence),
            provenance=tuple(provenance[ref] for ref in sorted(references)),
            source_tick=verification.observed_tick,
            fingerprint=fingerprint,
            policy_version=self.version,
        )
        return PromotionDecision(
            investigation_id=incident.investigation_id,
            accepted=True,
            reasons=(
                "verified_reusable_lesson" if resolved else "observed_failed_action",
            ),
            policy_version=self.version,
            memory=memory,
        )
