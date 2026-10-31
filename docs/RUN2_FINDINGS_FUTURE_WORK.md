# Future work: findings from the run-2 tree-of-thought master runs

**Status:** NOT BUILT. Recorded 2026-10-31 for the developer to revisit later;
nothing here is approved for a runtime change.
**Source:** the run-2 master runs `master-tot-critic-off-run-2` and
`master-tot-critic-on-run-2` (2026-10-31), reviewed against `main`.
**Related:** [ToT and critic evaluation](TOT_CRITIC_EVALUATION_FUTURE_WORK.md),
[Multi-agent survey](MULTI_AGENT_SURVEY_FUTURE_WORK.md).

The runs had no 429/422 errors and no unanswered questions, so availability
improved. What remains is how the agent reasons and finishes. Six problems were
found. Problem 2 (the critic reinforcing the agent's mistake) is being built
separately as the blind-critic change. The other five are below. Each item
needs its own pull request and the teach-first gate (AGENTS.md §1), and should
be measured with matched cases before it becomes a default.

## 1. Confidently dismissing real faults as a transient

**Seen:** both agents called the challenge (KA-09) a harmless transient at 90%
confidence, missing the bearing wear and wrong setting on CNC-07.

**Why, in the code:** the challenge's first alarm is the harmless spike on
CNC-03 (pinned in `tests/test_known_answers.py`). The real faults are on
CNC-07, which the agent never examined. "The alarm cleared" is true of the
decoy, and nothing makes the agent look further. Rejects stay above normal
after the spike, because of CNC-07, and that already contradicts "transient".

**Idea:** a deterministic stop rule like R4e (`agent/loop.py`,
`diagnosis_supported`): a "no action" conclusion is blocked, or marked
unsupported, while the reject rate since the alarm is still above the line's
normal rate. Code computes the rate from observed inspections, never from truth.

**Open questions:** what counts as "above normal" with random rejects (manual
§2.9); whether the rule should block or only lower confidence; the effect on
the true false-alarm cases KA-07 and KA-08, which must still conclude "no action".

## 3. The critic follow-up never gathers evidence

**Seen:** one case had used up its tool budget, another stopped by itself, and
another skipped the check because confidence had already reached the bar.

**Why, in the code:** `recheck_trigger` (`agent/investigation.py`) skips the
follow-up when `remaining_tool_calls == 0`, and on an agreement when the leader
is already at `min_action_confidence`. The investigate stage can spend every
tool call before the critic runs. So high confidence prevents the one check
that could disprove it.

**Idea:** keep one tool call back for the follow-up (like `followup_seconds`
keeps time back), and still run the follow-up at the bar when the conclusion
would be "no action" or when the critic listed missing evidence.

**Open questions:** whether one reserved call should come out of the research
budget or be extra; the effect on wall time.

## 4. The setting case left unresolved; job routes cannot separate machines

**Seen:** critic-off ended "Pending: I need to compare…" after 23 answered
questions; critic-on proposed a broad common cause.

**Why, in the code:** the line is serial (`ProductionLine` in
`simulator/scenarios.py`): every job passes through every machine.
`get_job_history` returns one job's events across all machines. Comparing the
routes of passing and failing jobs can therefore never single out a machine.
Only comparing machines with each other works (heat, vibration, power, job
times), as manual §2.7 says. This is a likely explanation; the records have not
yet been checked to confirm the agent was comparing routes.

**Idea:** first confirm from the records what the agent compared. If it was
routes, add one sentence to the manual (or the tool description) saying every
job takes the same route, so a job's route cannot point to a machine.

## 5. A `no_objection` verdict that lists serious objections is not flagged

**Seen:** in the challenge the critic returned `no_objection` while listing
missing evidence, alternatives and overconfidence.

**Why, in the code:** `verdict_mismatch` (`agent/critic.py`) flags
`no_objection` only when the critic favours a hypothesis other than the leader.
It does not flag `no_objection` alongside a serious objection (`SERIOUS_OBJECTIONS`:
a contradiction or a better alternative).

**Idea:** also flag `no_objection` with any serious objection, and consider
letting `recheck_trigger` treat it as an objection. This is a few
deterministic lines. The mismatch is recorded, never corrected, so the
prompt's effect stays measurable.

## 6. The experiment cannot yet show an improvement

**Seen:** each run has only one confirmed correct case. Critic-on's 25% leaves
out one uncertain label, while critic-off's 20% counts all five. Earlier
overlap, identical seeds and settings changed during resumed runs limit the
comparison further.

**Idea:** before more master runs, fix the weaknesses above, then run all 13
known cases (KA-01 to KA-13; KA-10 to KA-13 added 2026-10-31 are four where
"no action" is always wrong) with one frozen configuration, no resume across
code or settings changes, and every label decided before comparing. More runs
alone would mostly repeat the same failures. Live runs are Codex's job
(AGENTS.md §12).
