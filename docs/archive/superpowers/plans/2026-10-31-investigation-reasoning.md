# Investigation reasoning implementation plan

**Goal:** Implement the six approved improvements to evidence presentation,
hypothesis comparison, routes/time, completion, critic checking and independent
diagnosis/action decisions, without changing models or revealing simulator truth.

**Architecture:** Derive a bounded factual brief from observable tool results.
Extend existing typed beliefs with optional comparison and completion fields for
backward compatibility. Keep decisions and enforcement in the existing policy
and investigation controller. No new provider, agent framework or live run.

**Stack:** Python, Pydantic, existing Pydantic Graph, pytest. The approved scope
is the six-item proposal in the chat; this records implementation choices.

## Increments

- [x] Add failing evidence-brief tests; implement machine coverage and bounded
  arithmetic summaries from collected observations. Unknown remains unknown.
- [x] Add failing comparison tests; extend hypotheses with expected observations,
  assumptions, unexplained evidence and distinguishing checks. Render them and
  validate cited evidence IDs through the existing boundary.
- [x] Add failing route/time tests; show ordered observed job events and explicit
  data windows, preserving gaps, origin and duplicate-measurement warnings.
- [x] Add failing completion tests; require model-backed final assessments to
  distinguish supported and unresolved findings, with unresolved questions and
  next checks. Refuse unsupported claims of completion without inventing causes.
- [x] Add failing critic tests; reserve one diagnostic call independently of
  research/post-action calls, remove confidence-only skipping, and make accepted
  checks read-only. A stop must identify evidence already answering the check.
- [x] Add failing action/diagnosis tests; retain the diagnosis when no supported
  repair is available and make uncertain diagnoses escalate. Do not turn the
  intervention threshold into a diagnosis confidence target.

## Verification and review

For each increment: observe red tests, implement, run touched tests. After green,
make a separate variable-comment pass, then rerun touched tests and Ruff. Add any
new test file to `.github/test_groups.py`; run its grouping check and the full
offline suite because controller/contracts are shared. Open a PR and **do not
merge**, per the developer's latest instruction. Record built ungated,
understood: no; do not claim live accuracy improvements.

## Pasted proposals

Keep evidence-driven testing and feedback grounded in observable evidence.
Keep deterministic verification only for mechanical facts (IDs, arithmetic,
windows, provenance); semantic uncertainty is not a deterministic falsehood.
Defer adaptive ToT, memory changes and blind-critic experimentation so their
effects can be measured separately. Do not use unverified performance claims or
papers as justification for implemented behavior.
