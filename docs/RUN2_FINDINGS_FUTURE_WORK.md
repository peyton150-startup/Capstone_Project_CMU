# Future work: findings from the run-2 tree-of-thought master runs

**Status (rechecked 2026-11-05 at `main` `d4bbbd6`):** Historical run-2 findings. **Item 3 implemented; items 1 and 5 not built; item 4 partly addressed; item 6 partly complete.** Original problem 2 (blind critic) was implemented and compared live, without a demonstrated accuracy gain. This document preserves run-specific reasoning failures; [`MVP_SCOPE.md`](MVP_SCOPE.md) is the active roadmap. Nothing here authorizes a runtime change.
**Source:** the run-2 master runs `master-tot-critic-off-run-2` and
`master-tot-critic-on-run-2` (2026-10-31), reviewed against `main`.
**Related:** [ToT and critic evaluation](TOT_CRITIC_EVALUATION_FUTURE_WORK.md),
[Multi-agent survey](MULTI_AGENT_SURVEY_FUTURE_WORK.md).

The three appended episodes had no 429/422 errors or unanswered questions;
the two older episodes retained their earlier failures. Critic-on also had one
invalid reply in an appended episode. Availability improved, but these are
mixed-configuration continuations. What remains is how the agent reasons and finishes. Six problems were
found. Problem 2 (critic anchoring) was subsequently implemented as opt-in
`CRITIC_BLIND` and [compared in archived live runs](benchmarks/2026-11-01-tot13-pairs/README.md). The other five are below. Each item
needs its own pull request and the teach-first gate (AGENTS.md §1), and should
be measured with matched cases before it becomes a default.

**Implementation cross-check:** PR #150 added a separate one-call critic diagnostic allowance, confidence-independent trigger, structured read-only checks and explicit unresolved completion records. It addressed the mechanical follow-up failures in item 3, not the accuracy problem. Four later 13-case runs recorded **29 follow-ups with newly gathered observations**; extra data has not been shown to correct diagnoses. The observed-route view partly addresses item 4, but identical serial job routes do not discriminate causes. Items 1 and 5 remain unbuilt. Blind-critic mode is built and evaluated with inconclusive outcomes. See [implementation details](INVESTIGATION_REASONING.md) and [paired results](benchmarks/2026-11-01-tot13-pairs/README.md).

## 1. Confidently dismissing real faults as a transient — ❌ DETERMINISTIC RULE NOT BUILT

**Seen:** both agents called the challenge (KA-09) a harmless transient at 90%
confidence, missing the bearing wear and wrong setting on CNC-07.

**Why, in the code:** the challenge's first alarm is the harmless spike on
CNC-03 (pinned in `tests/test_known_answers.py`). The real faults are on
CNC-07, which the agent never examined. "The alarm cleared" is true of the
decoy, and nothing makes the agent look further. Rejects stay above normal
after the spike, because of CNC-07, and that already contradicts "transient".

**Recheck:** the current investigator prompt encourages looking beyond the alarmed machine, and `MVP_SCOPE.md` proposes a bounded line-wide incident packet. Neither is the deterministic post-alarm reject-rate guard proposed here, nor has a corrective gain for KA-09 been demonstrated. Test this within the [line-wide evaluation](MVP_SCOPE.md#fw-line-scope) before making it a default.

**Idea:** a deterministic stop rule like R4e (`agent/loop.py`,
`diagnosis_supported`): a "no action" conclusion is blocked, or marked
unsupported, while the reject rate since the alarm is still above the line's
normal rate. Code computes the rate from observed inspections, never from truth.

**Open questions:** what counts as "above normal" with random rejects (manual
§2.9); whether the rule should block or only lower confidence; the effect on
the true false-alarm cases KA-07 and KA-08, which must still conclude "no action".

## 3. The critic follow-up never gathers evidence — ✅ MECHANISM FIXED (PR #150)

**Seen:** one case had used up its tool budget, another stopped by itself, and
another skipped the check because confidence had already reached the bar.

**Historical cause (no longer current):** the earlier `recheck_trigger()` skipped follow-up when research calls were exhausted or the leader had reached the confidence bar. PR #150 reserves a distinct `critic_tool_calls` allowance (at most one), and confidence alone no longer skips the check. Tests in `tests/test_agent_investigation.py` verify both conditions.

**Implemented:** the follow-up has one additional bounded diagnostic call and its own time window; an agreed or objected check can run regardless of the action-confidence bar. A structured read-only request can be executed directly, and the controller may reuse an already observed exact check. This is **not** a second critic review round.

**Remaining evaluation:** the diagnostic call is extra to the research allowance. Measure whether these extra observations improve decisions compared with the old baseline; the 52-episode archive demonstrates collection, not diagnosis improvement. No further code work is needed merely to enable a follow-up.

## 4. The setting case left unresolved; job routes cannot separate machines — 🟡 PARTLY ADDRESSED

**Seen:** critic-off ended "Pending: I need to compare…" after 23 answered
questions; critic-on proposed a broad common cause.

**Why, in the code:** the line is serial (`ProductionLine` in
`simulator/scenarios.py`): every job passes through every machine.
`get_job_history` returns one job's events across all machines. Comparing the
routes of passing and failing jobs can therefore never single out a machine.
Only comparing machines with each other works (heat, vibration, power, job
times), as manual §2.7 says. This is a likely explanation; the records have not
yet been checked to confirm the agent was comparing routes.

**Current state:** `agent/evidence_brief.py` already lists observed job visits in time order, without treating missing visits as complete routes. The specific manual/tool reminder that all jobs traverse the same serial line (so identical routes cannot isolate a cause) is **not built**. The original trace-level claim that mistaken route comparison caused the failure remains unverified.

**Next gate:** inspect saved setting-case decisions before changing the manual. If this error occurred, add one general clarification and test it within the existing [line-wide context](MVP_SCOPE.md#fw-line-context), rather than creating a second workflow.

## 5. A `no_objection` verdict that lists serious objections is not flagged — ❌ NOT BUILT; ORIGINAL RULE NEEDS REVISION

**Seen:** in the challenge the critic returned `no_objection` while listing
missing evidence, alternatives and overconfidence.

**Why, in the code:** `verdict_mismatch` (`agent/critic.py`) flags
`no_objection` only when the critic favours a hypothesis other than the leader.
It does not flag `no_objection` alongside a serious objection (`SERIOUS_OBJECTIONS`:
a contradiction or a better alternative).

**Current state:** `agent/critic.py:verdict_mismatch()` detects a different preferred hypothesis with `no_objection`, and `object` while preferring the leader without serious objections; it does **not** detect `no_objection` solely because an `alternative` or `contradiction` was listed. `recheck_trigger()` already treats preference for another *current* hypothesis as an objection.

**Do not implement the blanket rule as written.** In the two archived 13-case **blind** runs, **all 19 `no_objection` reviews** contained an `alternative` or `contradiction` objection. Often the model merely said another cause was *not fully ruled out* while still favouring the leader. Flagging all 19 as mismatches would conflate uncertainty with contradiction. First define an objection that genuinely defeats the leader, retrospectively hand-label a sample, and evaluate false-positive mismatch flags. Keep the raw reply unchanged and recorded.

## 6. The experiment cannot yet show an improvement — 🟡 NEW RUNS ARCHIVED, GAIN UNPROVEN

**Seen:** each run has only one confirmed correct case. Critic-on's 25% leaves
out one uncertain label, while critic-off's 20% counts all five. Earlier
overlap, identical seeds and settings changed during resumed runs limit the
comparison further.

**Completed since the original note:** the two anchored/blind pairs covered all 13 known-answer cases (52 episodes), with within-pair configurations pinned; the archive also records overlapping runs, service failures, manual-index maintenance and four held-out labels. On mutually judged cases both critic modes had the same confirmed-correct count in each pair, so an improvement remains unproven. A later five-case audited blind run was not a matched second arm.

**Still worth doing:** review held-out labels, investigate unresolved conclusions and repeat clean, non-overlapping matched cohorts only after addressing material failure modes. Distinguish diagnosis quality, tool reliability and post-action verification; keep simulator truth evaluator-only. Live-run authority remains in `AGENTS.md` §12.
