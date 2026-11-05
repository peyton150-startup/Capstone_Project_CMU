# Future work: three items from the LLM multi-agent survey (2026-10-31)

**Status (2026-11-05 recheck, `main` `d4bbbd6`):** **Item 1 implemented and evaluated live (no established gain); item 2 not built; item 3 partly documented.** This is a research-specific decision record, not a second roadmap; [`MVP_SCOPE.md`](MVP_SCOPE.md) remains authoritative.
**Experiment gate:** The earlier baseline experiments are archived. New comparison claims still require fixed, non-overlapping configurations and reviewed labels; this document authorizes no code change.
**Source:** [Large Language Model based Multi-Agents: A Survey of Progress and Challenges](https://arxiv.org/abs/2402.01680) (Guo et al., 2024).
**Related:** [ToT and critic evaluation, P4](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#p4--evaluate-the-evaluator-not-just-the-generator), [Future Work 3](MVP_SCOPE.md#future-work-3--multi-agent-research), [Review signal 2026-10-30](REVIEW_SIGNAL_2026-10-30.md).

The survey was read against `main` (at `17ec5c8`). Most of its suggestions are already built or were already decided against. This page preserves the three survey-specific ideas and why some were declined. Statuses below are rechecked against newer code, tests, the README and live-run archives; detailed operator-feedback options and the survey mapping are not fully present in `MVP_SCOPE.md`.

## 1. Critic anchoring ablation (MEDIUM-HIGH, evaluation only) — ✅ BUILT; LIVE RESULTS INCONCLUSIVE

**Built 2026-10-31 (row C1c), with later offline tests and live comparisons:** opt-in `CRITIC_BLIND`. `blind_order` shuffles the shown hypotheses from a seed made from the anomaly and the hypothesis ids (no simulator stream). `critique_view(blind=True)` shows them as X1, X2, ... with no confidence and no leading mark, and `CRITIC_BLIND_SYSTEM` asks for a pick without a leader. `Critic._unblind` maps the labels back and sets the verdict with `blind_verdict`: `object` unless the pick is the agent's leader. `CritiqueRecord.blind` and `shown_order` record it. Two 13-case anchored/blind pairs (52 total episodes) were later completed and archived in [the paired-run results](benchmarks/2026-11-01-tot13-pairs/README.md). The mutually judged cases were tied (3/11 each arm in pair A; 6/11 each arm in pair B). Four labels awaited review across the arms, with overlap, service outages and manual-index maintenance. **No accuracy advantage has been shown.**

**Paper signal (Sec. 6.2):** in a multi-agent system, one agent's mistake can be accepted and repeated by the next agent. A reviewer that is told which answer the first agent prefers is the obvious path for that.

**Anchored-mode baseline (blind mode deliberately differs):**

- `shown_hypotheses()` (`agent/critic.py`) sorts hypotheses by the agent's confidence, most believed first.
- `critique_view()` marks the first one as "the agent's leading explanation".
- `CRITIC_SYSTEM` tells the critic the first hypothesis is the leading one, and the verdict is defined relative to it (`no_objection` means "your pick is the leading explanation").
- `evals.py` already records `critic_pick_correct` and `critic_verdict_mismatch`, so the measurement exists.

Thus the anchored critic sees the investigator's ranking. The blind critic hides that cue, but the archived comparisons did not establish that this improves diagnosis accuracy.

**Implemented experiment and optional replication:** the opt-in blind critic view was compared against the anchored mode using frozen within-pair cohorts (C or D in the [comparison matrix](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#controlled-comparison-matrix)). All code changes listed below are built. A clean replication is still optional.

- **Code:** shuffle the shown hypotheses with a seeded order (no simulator random stream, same order on replay), drop the "leading" marker and the confidence values from the view, and record the shown order in the critique record.
- **Code:** derive the verdict from the critic's pick, since a blind critic cannot judge "against the leading explanation": `object` when the pick is not the agent's leading hypothesis or is none, otherwise `no_objection`. The critic still lists its objections. `verdict_mismatch()` then needs a blind-mode rule.
- **Model:** unchanged. It still picks the best-fitting hypothesis, names one discriminating call and lists objections.
- No extra model calls, so no latency cost.

This is the critic-side version of P4's position-sensitivity check (P4 rotates candidate order for hypothesis ranking). Run them together or one after the other, not mixed in one cohort.

**Decision gate for future replication:** report `critic_pick_correct` for anchored vs blind on human-reviewed matched cases, non-leading picks, their correctness and the recheck rate. Do not claim superiority without replicated improvements. The archived pairs are useful snapshots, not proof.

**Not in scope:** an extra analyst agent. The evidence-only handoff in Future Work 3 is the multi-agent version of the same idea and stays gated there.

## 2. Operator rejection notes as feedback (LOW, design question first) — ❌ NOT BUILT (2026-11-05)

**Paper signal (Sec. 3.4):** human feedback is one of the four feedback sources, and the most direct one for aligning a system with what operators want.

**Current behavior (verified against `main`):** `ApprovalDesk.reject(proposal_id, note)` (`tools/actions.py`) stores the human's note on the proposal. The investigation reads back only the status (`investigation.py`, the `propose` stage copies `status` and finishes on rejection). The note can appear in the raw `get_proposals` response, but it is not shown to the agent as feedback, not preserved as a dedicated field in the shared/audit action contracts, and not used by memory. The memory gate (`memory/policy.py`) accepts only verified fixes, so a rejection cannot become a lesson today.

**Options, smallest first:**

1. Record the note in the audit record and experiment records, so evaluation can count how often operators reject and why. No behavior change.
2. Show the note to the agent in its final step, so the conclusion can state why the action did not happen. Still read-only.
3. Store rejections as a separate, clearly labeled record type (an operator objection, a belief, not a fact), recalled alongside lessons. This **conflicts with the current memory rule** that only verified outcomes are kept, so it needs the developer's decision before any design work.

**Who does what:** code records and labels the note; the model may only mention it. A note is never observable evidence and never counts toward a diagnosis.

**Pass criteria:** option 1 needs only a record test. Options 2 and 3 need a matched evaluation showing fewer repeated rejected proposals without unsafe behavior.

## 3. Describe the system in the survey's framework (LOW effort, write-up) — 🟡 PARTLY DOCUMENTED (2026-11-05)

**Paper signal (Sec. 3, Fig. 2):** the survey describes any multi-agent system with four parts: the environment the agents act in, how roles are defined, how agents communicate, and how they get better from feedback.

**Already done:** the survey is credited in the README **Research basis** section for the blind-critic implementation. **Still missing:** a full report/README mapping to the survey categories; the draft table below remains here. This is a writing task, not a missing runtime agent.

| Survey part | This project | Where |
|---|---|---|
| Environment interface | Sandbox: the seeded factory simulator, reached only through `FactoryProvider` tools | `simulator/`, `providers/factory.py` |
| Agent profiling | Pre-defined roles: investigator and critic, each with its own system prompt and model setting | `agent/model_policy.py`, `agent/critic.py` |
| Communication paradigm | Cooperative, plus a challenge step (the critic argues against the leading explanation) | `agent/critic.py` |
| Communication structure | Centralized: the Pydantic Graph decides who speaks when; handoffs are typed `Contract` models and code-built views | `agent/investigation.py` |
| Feedback | From the environment (observations, post-action verification), from another agent (critic objections, recheck) and from a human (approval) | `agent/investigation.py`, `tools/actions.py` |
| Agent adjustment | Memory: verified lessons promoted through a gate and recalled later | `learning.py`, `memory/` |

Also state what the project deliberately does not do from the survey: no debate between agents, no dynamically generated agents, no self-evolving roles, and no CrewAI (rejected 2026-10-26).

**When this write-up is completed:** reuse the existing README paper citation, rather than adding a duplicate. Avoid describing specialist roles as already implemented.

## ✅ IMPLEMENTED or decided against (do not re-propose)

- **A separate verifier agent.** The critic plus code checks cover it: hypotheses and conclusions citing ungathered evidence are refused (`agent/loop.py`, `agent/investigation.py`), and the critic never sees ground truth.
- **Episodic memory of past successful investigations.** Built: `learning.py`, `memory/`, keyword and semantic recall, measured by `memory_comparison.py`.
- **Environment feedback loop.** Built: `wait`, critic-directed recheck, mandatory post-action verification, evidence-completeness stop.
- **Hierarchical manager with early stopping.** The graph is the manager; the confidence gates and `diagnosis_supported` are the stop. CrewAI was rejected 2026-10-26.
- **System-level evaluation.** Built: `evals.py`, the rule-based baseline, cohorts A to D, `--compare-before`.
- **Multi-agent debate.** Not planned: it adds sequential model calls, and time already goes to those (see [Not planned: a third agent](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#not-planned-a-third-agent-for-speed)).
- **A shared message pool (MetaGPT style).** Redundant with two roles: the graph and typed handoffs already decide who sees what.
