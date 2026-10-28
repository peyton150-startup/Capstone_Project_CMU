# Critic, review only: the first multi-agent role

Date: 2026-10-28. Status: design agreed in conversation with the developer;
not built. Next: the teaching gate (AGENTS.md section 1.2), then one PR.

## Why

The single-agent master baseline (EV1, 2026-10-28) got 3 of 9 known-answer
cases right. The misses are mostly reasoning, not research:

- On 2026-10-26, KA-03 and KA-05 were wrong with every relevant piece of
  evidence in hand (`docs/benchmarks/2026-10-26-scored-single-agent.md`).
- On KA-03 the agent drifted from the bad batch to a servo drive: a
  confusion between the leading explanation and its runner-up.
- In the baseline, no intervention was lowered by the action bar; KA-01
  escalated at 0.85 by its own choice. Lowering the bar would not help.

A second model that challenges the leading explanation is the role the
future-work plan names first for reasoning misses (`docs/MVP_SCOPE.md`,
Future Work 3). A second model can also make results worse (the paper behind
R4c), so this role first only **reports**; it earns the power to change the
run by meeting a bar set in advance.

## Goals

1. A critic stage that runs on every investigation that reaches it, judges
   the two leading explanations against the evidence, and records its
   verdict.
2. Measurements that decide, later, whether the critic may send the agent
   back for one more round of testing (option 2).
3. The plumbing later roles reuse: a role's own job, model setting, typed
   reply, graph stage, time window and agent tag.

## Non-goals

- The critic does not change the conclusion, the confidence, the
  recommendation, the proposal or anything the agent does next. Not in this
  build.
- No tools for the critic. It judges only what the agent gathered.
- No memory: the critic's verdict is never written to memory.
- No change to the action bar, the follow-up reserve or research time.

## Anti-goals (a failure even if it runs)

- The critic sees hidden truth, the scenario config, a run key or a score.
- The critic's verdict counts as evidence, or as proof a fix worked.
- The critic's time is taken from research, the conclusion, the proposal,
  the work or the check.
- A critic reply that does not fit its type is quietly accepted or repaired.

## Decided with the developer

- **Where:** a new stage in the investigation graph
  (`agent/investigation.py`, `build_graph`), after `test` and before
  `conclude`: the place where it will later be allowed to act, so what is
  measured is what may later be given power. Investigations that skip
  `test` (nothing to explain, or no hypotheses) go straight to `conclude` as
  now, and the critic does not run.
- **What it sees:** the evidence and the **two leading hypotheses** by
  confidence (the only one, if there is one), built by code in the style of
  `render(state)`. Not the scenario, not the truth.
- **What it returns:** a typed contract, `CritiqueResult`, with:
  - `favoured`: the id of the hypothesis the evidence supports better (or
    `none` if it supports neither);
  - `why`: one or two sentences;
  - `discriminating_check`: one check that would tell the two apart;
  - `objections`: a list, each a kind (`contradiction`, `unsupported_claim`,
    `missing_evidence`, `alternative`, `overconfidence`) and a sentence,
    citing evidence ids where it can;
  - `verdict`: `object` or `no_objection`.
  Evidence ids it cites must exist; an invalid reply is refused and its
  reason recorded, as for the seven policy questions (`_ask`, `_refuse`).
- **Its own time window:** `CRITIC_SECONDS`, default **30**, on top of the
  investigation's own time. The investigation's deadline is moved back by
  the time the critic actually used, so research and the follow-up reserve
  keep exactly what they have now. 30 is a starting point to benchmark, not a
  decision.
- **Its own model:** `CRITIC_MODEL`, with the same fallback chain
  (`FallbackClient`). Both settings live in `.env` for now and join the
  frontend's settings list if a frontend is built
  (`docs/MVP_SCOPE.md`, frontend settings note).
- **Records:** the `CritiqueResult` (or why there is none: no answer in the
  window, invalid reply) is kept on the investigation state and in the
  experiment record. The critic's model questions are tagged
  `agent="critic"`, so the EV1 report counts them apart (`steps_by_agent`).

- **A critic outage never ends the run.** Today a `ModelError` that no
  fallback answers stops the whole investigation (`stop_without_a_model`).
  For the critic it must not: no answer in its window is recorded as
  "no critique" and the run goes on to `conclude` as if the critic were
  absent.
- **Works with every mode:** both `STEP_QUESTIONS` settings and
  `--tree-of-thought`; the critic reads only the state after `test`.
- **Shown live:** as a graph stage it is shown by the progress view after it
  finishes (`staged` calls `notify`).

## Calls made in the builder check (the coding assistant's, to confirm)

- **Off by default.** A setting `CRITIC` (`on`/`off`, default `off`) switches
  the stage on, so existing runs, the rule baseline and scripted test
  policies behave exactly as now, and a run without the critic stays
  comparable with the EV1 baseline.
- **The EV1 report gains the critic's verdict and pick per case**
  (`EvalCase`), so the comparison below can be read from one report.
- **The critic's prompt uses the same evidence section** as the other
  questions (`evidence_section`, same size limit), so it is never shown
  evidence the agent was not.

## How "tried and true" is decided (before the runs)

Run the EV1 cases several times with the critic in review only, label the
conclusions as usual, then compare:

1. **Objects on wrong answers:** on cases labelled wrong, the critic says
   `object` in most of them (proposed: about 2 in 3 or more).
2. **Rarely objects on right answers:** on cases labelled right, `object` in
   about 1 in 4 or fewer.
3. **Its pick beats the agent's:** `favoured` matches the labelled cause more
   often than the agent's leading hypothesis does.
4. **It answers in its window:** it answers in nearly every case; the window
   is then set from the measured times (the slowest 5%, rounded up, as
   `suggested_limits` does).

The numbers in 1 and 2 are proposals the developer has not yet confirmed.
They hold over several runs, not one.

Measure 3 needs one more label per case: hypotheses are free text, so the
critic's favoured hypothesis must be read as a cause the same way a
conclusion is. Open: whether that is done by hand, or by the Jev
auto-labeller (`evaluation/auto_label.py`, `propose`) with flagged cases
reviewed by hand.

## Constraints

- AGENTS.md: determinism of the simulator unchanged; hidden truth never
  crosses the tool boundary; no Anthropic or OpenAI model or SDK; only the
  in-scope providers; every change through a PR; the teaching gate before
  building.
- `docs/MVP_SCOPE.md` Future Work 3: our own orchestration (no CrewAI);
  typed handoffs; a role's output is a belief, never evidence; no role
  approves or executes; one role at a time.
- Tests need no key: the critic's client is faked like the other jobs.

## Left to the builder

- Exact names of the state and record fields, and whether the critic is a
  method on `ModelPolicy` or its own small class using `_ask`.
- How the paused deadline is implemented (for example, adding the critic's
  spent seconds to the deadline), as long as research and the follow-up
  reserve keep their time and tests prove it.
- The prompt wording, within the rules above.
- The `CRITIC_MODEL` default when unset: the main model is the safe choice;
  the plan's long-term pick is Mistral.

## Later, not now (option 2)

Once the bar above is met: the same stage may add one open question from
`discriminating_check` and allow one extra `test` round. That round needs its
own time too, or it squeezes the follow-up reserve; decide it then.
