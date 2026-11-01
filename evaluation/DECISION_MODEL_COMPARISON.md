# Decision model comparison: SubQ Snap 1.1 and TypeSafe Jev 1.14

Design for running two independent decision models over the same evidence
with semantically identical questions, normalizing their answers into one
schema, measuring where they agree, and deciding whether keeping both is
worth it. Proposed and scaffolded; no request has been sent. Version 1.0.0,
2026-11-01, pairs with rubric 1.0.0 and `SNAP_QUESTIONS.json` 1.0.0.

## 1. What is known about the two services, and how well

Neither documentation site resolved from the session that wrote this
(`docs.subq.ai`, `docs.typesafe.ai`). Every row below is second-hand, from
the quickstart text as quoted by search results, two open-source clients
(devbux/subq-snap-mcp, opentalon PR #394), secondary write-ups of the Jev
1.14 release, and this repository's own TypeSafe client
(`capstone/providers/typesafe.py`), which already sends noul and choice
questions to `POST https://api.typesafe.ai/v1/systemone` and reads
`answers.<name>.noul` / `.choice` with `confidence` and `probabilities`.

| | Snap 1.1 | Jev 1.14 |
|---|---|---|
| model id | `subq-snap-1.1` (preview) | `jev-1.14.0`; whether `jev-latest` points at it is disputed, so the id is pinned |
| endpoint | `POST https://api.subq.ai/v1/systemone` | `POST https://api.typesafe.ai/v1/systemone` |
| request | `{model, state, questions: {name: {type, instructions, criteria}}}` | same shape |
| question types | noul, choice (2-255), score (2-10 ordered levels) | noul, choice (up to 255), score (2-10 levels) |
| questions per request | 1-16 | not found in the sources read; 16 assumed for parity (the auto-labeller already sends up to 12) |
| context | 384K tokens | 64K per request by default, 32K for the state plus the longest question; an opt-in header raises it (not used here); gateway listings say 32K |
| input price | $0.040 per million | $0.042 per million, output free |
| answer | `answers.<name>.{noul | choice, confidence, probabilities | score, confidence, probabilities}`, `model`, `usage.input_tokens` | same, verified for noul and choice by the repository's client |
| to confirm before the first live request | the key for score levels (`criteria` vs `levels`); the score answer field name | the same two; the questions-per-request limit; whether 1.14 is reachable under `jev-1.14.0` with the project's key |

`evaltools/decision_models.py::PROVIDERS` holds these facts with
`facts_verified: false`; flip it only after a live check.

## 2. Requirements and how each is met

1. **Same questions, criteria, scales and missing-evidence rules.**
   One file, `SNAP_QUESTIONS.json`; `DecisionQuestion.to_request` produces
   one body per question used for both providers; a test asserts the two
   providers' question bodies are equal.
2. **Deterministic Python checks for root-cause accuracy, tests, tools,
   simulator state changes, latency, deadline compliance.** Unchanged:
   `evaltools.run_packet` (`evaluator_only`, `facts`), the inventories, the
   junit outcomes. Neither model is asked anything code already answers.
3. **Models judge evidence sufficiency, hypothesis quality, critic
   effectiveness, retrieval contribution, verification quality.** RUN-01
   to RUN-12, FN-*, TS-*, TL-*, BT-* as before.
4. **Common answer schema.** `decision_models.normalize` returns the
   provider-neutral record described in `DECISION_ANSWER_SCHEMA.json`:
   provider, model requested and reported, question id and name, type,
   `value` (probability of yes, chosen option, or weighted level),
   `confidence`, `probabilities`, latency, input tokens, cost.
5. **Agreement, disagreement, confidence, latency, tokens, cost.**
   `evaltools.compare_evaluators` writes `agreement.json` and
   `agreement.md`: agreement rate overall, by family and by question;
   every disagreement with both values; per-provider request count, median
   latency, total tokens and cost (counted once per request) and mean
   confidence per question kind (a noul's distance from one half is never
   averaged with a choice's or a score's service confidence).
6. **Disagreements go to a person; agreement is not correctness.** The
   report lists `disagreements_for_review` and carries the caveat in its
   output; the reference set is the only source of correctness.
7. **Reference set.** Rubric section 8: successful investigations (KA-02),
   incorrect diagnoses (KA-03 to KA-06), a misleading success (to be
   found: a right label with RUN-08 below 2), insufficient-evidence cases
   (the escalations), one deliberately broken packet. `--reference` to the
   comparison gives each provider's agreement with the reviewer's answers.
8. **Jev's smaller context.** `decision_models.fit_state` trims a packet's
   judge view to a fixed budget by one deterministic sequence (evidence
   content to 600 characters, decision rationale, pruned candidates,
   evidence to 200 characters, decisions, search records; hypotheses,
   conclusion, critique, verification and facts are never cut). In a
   matched comparison both providers get the state fitted to Jev's share
   (28,000 tokens, under its 32K state limit with room for the questions),
   so both see the same bytes; the report compares a pair only when the
   two `state_digest`s are equal. A Snap-only run may use
   `--full-context`; its answers are then not comparable and the report
   says so by leaving the pair unmatched.
9. **Versions recorded.** Every request and answer file carries
   `rubric_version`, `commit_sha`, `provider`, `model_requested`,
   `model_reported` (from the reply), `state_digest`,
   `state_budget_tokens`, `state_trimmed` and the question ids.
10. **Retain both or one?** Section 5.

## 3. Evidence-extraction strategy in detail

The judge view of a run (`snap_view`) for the nine saved master packets is
between 2,000 and 3,500 tokens because those runs kept no trace. A traced
run with twenty evidence items of up to 1,500 characters, forty decisions
and five hypotheses is about 12,000 to 20,000 tokens, which fits Jev's
share without trimming. Trimming begins only on long runs (the compound
challenge at 26 tool calls, or any run near the 300-row answer cap).

Why trim rather than split: a question like RUN-02 (hypothesis reasoning)
needs the hypotheses and the test-phase decisions together; sending half
the trace to one request and half to another would give each model a
different partial view and the comparison would measure the split. The
trimming order removes the least question-relevant text first and never
touches what the questions are about. The `state_trimmed` tag records
exactly what was removed from each request, so a disagreement on a trimmed
packet can be re-run with the full state on Snap alone to see whether the
trimming caused it.

## 4. The comparison procedure

1. Build packets for a traced batch (`evaltools.run_packet` with `--audit`).
2. `snap_request --provider both runs --packets ...` writes the request
   pairs; read a few by hand; confirm the question shape for each service
   against its documentation (section 1).
3. `--send` with both keys in the environment; answers are normalized as
   they arrive.
4. Fill `reference/<batch>.json` with the reviewer's own answers for the
   reference items before reading any model answer.
5. `compare_evaluators --answers ... --reference ... --out ...`.
6. Review every disagreement against the trace and, for RUN questions
   only, against `evaluator_only`; record the verdict beside the pair.

## 5. Deciding whether both models are worth keeping

Decide per question family, after one traced batch of 13 cases and the
reference set, on these figures from `agreement.json`:

| Outcome on the reference set | Decision |
|---|---|
| Both at or above 0.8 agreement with the reviewer, and their disagreements are mostly on items the reviewer also found hard | keep both: the disagreements are the review queue, and that queue is cheaper than reviewing everything |
| One at or above 0.8, the other clearly below | keep the better one; use the other only as a tie-breaker on flagged items, or drop it |
| Both below 0.8 | neither is ready for that family; sharpen the question or the evidence, keep deterministic checks only |
| Both high and nearly always in agreement (above 0.95) | one suffices for that family; the second adds cost and complexity without a review signal |

Operational factors to weigh beside the figures: Jev's context trimming
(does `state_trimmed` appear on the runs that matter?), latency per request,
cost per batch (expected well under a dollar per batch for both at the
listed prices), and the fact that the repository already depends on
TypeSafe for labels, so keeping Jev adds no new vendor while keeping Snap
does.

## 6. Does a second model materially improve detection of misleading successes?

It can, under two conditions, and otherwise it is overhead.

Where it helps: a misleading success is a run the deterministic scorer
calls right and a judge calls poorly supported (RUN-08 low, RUN-12 false).
A single judge that is too generous never raises the flag, and nothing in
the deterministic layer can tell. Two independent judges make a generous
one visible: a run one model scores 4 and the other 1 is exactly the kind
of case the reviewer should read, and the reference set then shows which
model was right. The value is the disagreement queue and the per-model
reference agreement, not the agreement rate.

Where it does not help: if both models share the same blind spot (both
praise fluent conclusions that cite the right-looking ids), agreement is
high and false, and the second model adds cost without a signal. The
deliberately broken packet in the reference set exists to detect this. If
both fail it, the second model is not improving detection; the fix is in
the evidence packet (for example, adding the cited items' contents next to
the conclusion so the judge cannot avoid reading them), not in a third
model.

So the recommendation stands as proposed: run Jev as a second evaluator on
the first traced batch, with the reference set filled first; keep both only
where their disagreements prove to be the useful review queue; otherwise
keep the one that agrees with the reviewer and drop the other. The
deterministic layer remains the arbiter of correctness either way.

## 7. What was built for this

- `evaltools/decision_models.py`: provider table, `fit_state`, `normalize`,
  `compare`, `reference_match`.
- `evaltools/snap_request.py`: `--provider snap|jev|both`, matched state
  budget, `--full-context` for a single provider, answers normalized on
  `--send`.
- `evaltools/compare_evaluators.py`: the agreement report.
- `DECISION_ANSWER_SCHEMA.json`: the provider-neutral answer schema.
- Tests in `tests/test_evaluation_tools.py`: identical state and questions
  for both providers; deterministic fitting that never cuts the conclusion;
  one schema and the stated agreement rules; the report pairs only
  identical states and flags disagreements.

Not done: no live request; no reference answers yet; the two services'
score shapes unconfirmed.
