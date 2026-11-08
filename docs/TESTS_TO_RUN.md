# Tests still to run

Live runs that need a real model. Codex runs these (AGENTS.md §12), one live run
at a time, and records each result in `docs/benchmarks/` and `docs/PROGRESS.md`.
Claude Code builds the code and checks it offline only.

Tick a line and add the result note's path when it has been run.

## 1. Stage views off vs on (`STAGE_CONTEXT`)

Added in PR #209. Off is today's behaviour: every question sees the shared
`render(state)`. On gives `judge_verification` evidence sorted by when its data
was taken (before the work, after it, spanning it), same-signal before/after
numbers and the gaps, and gives `write_lesson` the conclusion, calls made and
the factual brief instead of raw evidence.

- [ ] **A/B with identical cases, models, budgets and approver.** Only the flag
  differs, so the flag, not `.env`, decides each run and each header says which:

  ```
  uv run python -m capstone.experiment run --name stage-off --known --stage-context off --out docs/benchmarks/<date>-stage-off.jsonl
  uv run python -m capstone.experiment run --name stage-on  --known --stage-context on  --out docs/benchmarks/<date>-stage-on.jsonl
  ```

  Each run prints `RUN: stage views on|off` first and `stage views: N on` /
  `N off` in its report, and exits 1 if any record disagrees with the flag.
  Run the known-answer cases first, then the seeded grid (`--seeds`, `--faults`)
  and `--hazards` once, since verification under a stale or missing reading is
  where the new view matters most.
- [ ] **Judge on accuracy first, size second.** Compare, off vs on:
  - verification outcome against the truth, and especially false `resolved`
    verdicts (a repair judged fixed when it was not);
  - premature conclusions and false diagnoses (these must not rise);
  - input tokens, output tokens and characters sent per job
    (`input_tokens_by_job` and the others on each record's `model_calls`);
  - seconds per run and tool calls per run.

  A smaller prompt that judges worse is a regression, not a saving.
- [ ] **Repeat enough times to tell noise from effect.** One pass per setting
  is a first look. Use the same seeds more than once, or more seeds, before
  keeping or dropping the views.
- [ ] **Failure modes of the new view.** Check by hand, on a few runs, that:
  - a trend fetched after the work but covering earlier ticks is shown as a
    baseline, not a result;
  - a signal measured before the work and never after it appears under
    "Verification gaps", and the model does not read silence as success;
  - a memory or manual answer is never offered as a result;
  - nothing about the verdict is stated in the view itself.

## 2. Do real prompts reach the evidence cap?

Needs the token logging from PR #209 and any ordinary live run.

- [ ] **Read the size distributions** (input tokens and characters sent, by
  job) from a few real runs, and count how often the evidence section shows a
  piece as "not shown here". The 8,000 and 12,000 character figures are
  limits, not measured sizes.
- [ ] **Decide from it.** If the cap rarely cuts evidence, drop evidence
  relevance scoring and the slimmer views for good. If it often cuts, scoring
  by what separates the competing hypotheses becomes worth testing.

## 3. Optional, only if section 1 shows a gain

- [ ] **Conditional guidance.** Move a few rules out of the shared `COMMON`
  instructions into context-sensitive guidance (for example, a missing
  reading is not evidence of normal operation, shown only when readings are
  missing) and compare against the same cases. Not a procedure library for
  particular faults: that would tune the agent to the simulated faults.
- [ ] **A slimmer `plan` view.** Only if section 2 shows `plan` prompts are
  large. At plan time there is little evidence to remove, so expect little.

## Not planned until something changes

- Tool discovery or filtering: thirteen research tools do not justify it, and a
  tool that is not shown is refused as an invalid choice. Revisit when the
  tool list grows a lot (MTConnect, audio, vision tools).
- Fault-specific diagnostic procedure catalogs.
