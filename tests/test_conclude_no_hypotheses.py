"""The conclusion is told when no hypothesis was formed (2026-11-14).

In the 2026-11-14 afternoon triage runs, KA-12 r1 ended research before the
hypothesize question, and the conclusion named a hypothesis id anyway; the
check refused the whole answer ("the conclusion names a hypothesis that was
never formed"). The conclusion prompt now says, only in that case, to leave
hypothesis_id empty. The check itself is unchanged.
"""

import pytest

from capstone.agent.investigation import check_conclusion
from capstone.agent.model_policy import NO_HYPOTHESES_NOTE
from tests.test_model_policy import policy, state_with_evidence

ANSWER = {
    "conclusion": {
        "diagnosis": "uncertain",
        "confidence": 0.5,
        "recommendation": "escalate",
        "assessment": "unresolved",
    }
}


def conclusion_prompt(state):
    p = policy(conclude=[ANSWER])
    p.conclude(state)
    return p.clients["conclude"].asked[0][1]


def test_without_hypotheses_the_conclusion_is_told_to_name_none():
    state = state_with_evidence()
    state.hypotheses = []
    assert NO_HYPOTHESES_NOTE.strip() in conclusion_prompt(state)


def test_with_a_hypothesis_the_prompt_is_unchanged():
    state = state_with_evidence()
    assert state.hypotheses
    assert "NO HYPOTHESES WERE FORMED" not in conclusion_prompt(state)


def test_a_made_up_hypothesis_is_still_refused():
    state = state_with_evidence()
    state.hypotheses = []
    p = policy(
        conclude=[
            {**ANSWER, "conclusion": {**ANSWER["conclusion"], "hypothesis_id": "H1"}}
        ]
    )
    conclusion, action = p.conclude(state)
    with pytest.raises(ValueError, match="never formed"):
        check_conclusion(state, None, conclusion, action)
