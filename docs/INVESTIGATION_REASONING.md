# Evidence use and investigation completion

This change implements the six requested improvements using the current models,
sampling, tools and investigation graph. It also adopts evidence-driven question
selection, evidence-grounded critic correction, and mechanical verification from
the pasted proposal. Adaptive ToT, memory changes and a blind-critic experiment
are deferred so they can be evaluated separately. No performance improvement is
claimed before live evaluation.

## What the investigator and critic see

`agent/evidence_brief.py` derives a factual brief from collected results with
observable provenance. Manual guidance and memories cannot create coverage or
numeric facts. The brief is at most 8,000 characters, with separate space for
machine coverage, job routes, inspections and measurements. Missing material is
explicitly unknown. The original evidence section and its IDs remain available.

- Coverage lists observed operating states and sensors checked, not a diagnosis
  of which machines are healthy. A past measurement is not proof of present health.
- Measurement arithmetic uses complete returned samples, not their truncated
  prompt representation. It groups by machine, sensor and unit, orders by data
  tick, and reports count, extrema, mean and delta. Retrieval tick is separate.
- Repeated exact measurements are flagged; overlapping views must not be treated
  as independent corroboration. This warning does not establish statistical
  independence of distinct measurements or automatically prove causal support.
- Routes show observed job events ordered by tick. A single event never implies
  a complete route; missing machine visits stay unknown. Inspections retain job,
  batch, result and tick. Speed settings never expose or infer hidden standard speed.
- Summaries do not label a sensor abnormal using hidden thresholds or simulator
  truth. The agent must compare the observations and manual guidance itself.

## Comparing explanations and choosing checks

`Hypothesis` retains its existing supporting/contradicting evidence and gains
expected observations, assumptions, unexplained evidence IDs and a distinguishing
check. These fields are beliefs, not facts. The existing interpretation boundary
checks that unexplained evidence IDs actually exist. ToT candidates carry the
same comparison material into retained hypotheses; search depth is unchanged.

Questions can name rival hypothesis IDs, estimated calls (1–3), and whether their
signal is direct, indirect or unknown. The rendered question list ranks by the
number of distinct current hypotheses distinguished, then signal reliability,
then estimated call cost. Unknown IDs do not boost rank. These annotations are
model estimates. The rubric is not expected information gain or a calibrated
probability, and the model still chooses the actual next permitted tool call.

Prompts explicitly distinguish a recovered alarm from the absence of faults
elsewhere, allow simultaneous unrelated causes, and avoid treating a passing
part as disproving any cause that increases reject probability.

## Mechanical verification

`NumericClaim` identifies an evidence ID, machine, sensor, metric, value, unit and
optional data window. The verifier computes the corresponding arithmetic from
observations or uses an observed summary for its exact window. It rejects
demonstrably different numeric values (absolute rounding tolerance 0.001, relative
tolerance 0.000001), incorrect known units, unknown evidence references and
reversed windows. It does not convert units.

Absent/ambiguous samples, unknown units and non-observable sources produce
`unverified`, not `false`. A model must provide structured numeric claims for this
check; arbitrary arithmetic embedded only in prose is not extracted or certified.
Semantic support for a causal claim remains outside deterministic verification.
Incorrect numeric claims are refused before a revised hypothesis is applied;
unverified final numeric claims prevent a supported completion assessment.

## Finishing honestly

Model-backed conclusions request `assessment` (`supported` or `unresolved`),
unresolved questions, a next check, and a separate action rationale. A model
answer omitting its assessment is treated as unresolved and escalated, preserving
its diagnosis. Legacy saved records and scripted policies can still omit the
fields; they are not silently relabelled.

For an assessed answer, the controller cannot accept supported completion with
unresolved diagnostic questions, explicit unexplained/conflicting evidence for
the selected hypothesis, unverified numeric claims, or no cited observable
evidence. It records unresolved status, escalates and retains the diagnostic
text. These checks cannot prove a causal explanation merely because its IDs are
valid. A budget stop is not evidence of correctness.

Diagnosis and action are separate: a cause can be supported even if none of the
available repairs addresses it. The model should preserve that cause and explain
why human escalation is needed. The existing intervention confidence threshold
still applies to permission to propose a repair; it is not a target confidence
the model must invent for its diagnosis. Human approval and post-action
verification remain mandatory.

Experiment JSONL records retain assessment, unresolved questions, next check,
action rationale and the critic diagnostic-call count. The original diagnosis,
recommendation and recommendation-lowering audit fields remain present.

## Making the critic check usable

With critic follow-up enabled, there is a separate allowance of at most one
diagnostic call (`Budgets.critic_tool_calls`, default 1, allowed 0–1). It uses the
existing separate 90-second recheck window. It cannot consume post-action
verification calls, and research cannot consume it. This permits **one additional
read** compared with earlier runs; compare total calls and runtime as well as
accuracy when evaluating the change. Critic-off runs make no extra call.

Self-reported confidence reaching the action threshold no longer skips a useful
critic check. The critic is asked for a structured `check_request`, executed by
the controller through the ordinary observation/evidence path. Only listed
read-only research tools are allowed; `wait`, actions and invented tools are
refused. Arguments remain subject to the existing factory provider validation.

An exact check already observed at the current tick reuses its evidence, without
another call. A legacy unstructured check can still be translated by the policy.
If that policy stops, it can cite existing observable evidence answering the
check; the record marks semantic adequacy as unverified. A stop with no such
evidence leaves the question unresolved. There is no repeated critic cycle.

## How to evaluate

Offline tests cover factual summaries, provenance, windows/units/arithmetic,
routes, section budgets, question ordering, completion escalation, preserved
diagnoses, reserved critic calls, read-only enforcement and evidence reuse.
Existing scripted repairs must still run in both step modes and ToT.

For live evaluation after review and merge, use fresh matched cases and fixed
models/sampling. Measure correct diagnoses, confidently wrong diagnoses,
unresolved endings, critic checks executed/reused/refused, corrections versus
regressions, total calls and runtime. Keep the existing mixed-configuration
run-2 files as historical evidence; do not append this treatment to them and
describe it as the same baseline. Ground truth belongs only to evaluation.
