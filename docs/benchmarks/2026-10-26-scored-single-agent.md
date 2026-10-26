# Scored single-agent run, 2026-10-26

The "before" picture for the multi-agent work: the current single agent on the
nine known-answer cases, hand-labelled, beside the rule baseline. Live models,
real calls.

## Setup

- Code: `main` at `e65bd8f` (everything merged on 2026-10-26: three-day bearing
  profile opt-in, power, fault packs, servo and hydraulic packs, fallback chain).
  Seeds still draw from the original four faults; servo and hydraulics only
  appear when forced, and no case forced them.
- Command: `experiment run --name single-known-1 --known --out
  results-single-1.jsonl` (results and log kept locally: they hold the truth).
- Models: NVIDIA Nemotron 3.5 Super 120B for every job; fallback chain for this
  run only (through the environment, `.env` untouched): Cloudflare Llama 3.3
  70B, then Cohere Command A (output capped at 8,192), then Requesty Nemotron 3
  Ultra 550B. Limits from the `.env`: 120 s per request, 240 s per question.
- Probes first: all four models answered in 1-2 s.
- Ran 16:32-18:21, one case at a time.
- Labels: `2026-10-26-labels-single-1.jsonl`, by the developer. Three were
  first labelled with the true fault; relabelled the same evening, at the
  developer's decision, by the conclusion's words (the file is append-only, so
  both versions are kept; the latest wins): KA-03 servo drive wear on CNC-06,
  KA-05 and KA-06 no cause named.
- Rule baseline on the same code: `2026-10-26-baseline-known.txt`.

## Results

| Case | The agent's conclusion | Labelled cause | Recommendation (confidence) | Evidence | Miss |
|---|---|---|---|---|---|
| KA-01 bearing | bearing wear on CNC-02 | right | escalate (0.80) | 2/3 | - |
| KA-02 bearing | bearing wear on CNC-05 | right | escalate (0.85) | 2/3 | - |
| KA-03 batch | a CNC-06 axis (servo) fault, heading for a drive replacement | **wrong** | escalate (0.60) | 3/3 | reasoning |
| KA-04 batch | material batch 2, no machine common to the failures | right | no action (0.85) | 2/3 | - |
| KA-05 setting | "pending", cause not isolated | **none named** | escalate (0.50) | 3/3 | reasoning |
| KA-06 setting | "failure rate rose at job 14, a new regime" | **none named** | escalate (0.97) | 1/3 | evidence |
| KA-07 false alarm | transient spike on CNC-01 | right | no action (0.90) | 2/2 | - |
| KA-08 false alarm | transient spike on CNC-03 | right | no action (0.97) | 2/2 | - |
| KA-09 challenge | the decoy spike on CNC-03 | not labelled (several causes) | no action (0.90) | 1/5 | - |

| Measure (one-fault cases) | Agent | Rule baseline |
|---|---|---|
| Root causes right | **5/8** | 8/8 |
| Right machine or batch | 5/8 | 7/8 |
| Right recommendation | 4/8 | 7/8 |
| Fixes asked for | **0** | 3 |
| Unnecessary interventions | 0 | 0 |
| Relevant evidence collected | 77% | 44% |

The baseline was also right on KA-09 (bad batch); the agent named only the
decoy and missed both real causes on CNC-07, as on 2026-10-21.

## What it shows

1. **The agent never asked for a fix.** Its four right recommendations are the
   four cases where the right answer is to do nothing. Both bearing cases had
   the right machine and cause but escalated at 0.80 and 0.85, below the 0.9
   `min_action_confidence` that `check_conclusion` enforces and the prompt
   never states. KA-06 escalated at 0.97 with no cause named. This is the
   MAX-HIGH priority for 2026-10-27 (`docs/MVP_SCOPE.md`).
2. **It gathers more evidence than the rules and reasons worse.** Two of its
   three misses (KA-03, KA-05) came with every relevant piece of evidence in
   hand. Reasoning, more than research, is the first target for a second
   agent (a critic or independent analyst), after the fix above.
3. **The new servo evidence can mislead.** On KA-03 the agent read the
   batch-2 rejects as an odd/even job pattern and blamed the last machine's
   servo drive, the risk named in the servo walkthrough (PR #82).
4. **Calibration is off.** KA-06: confidence 0.97 in a conclusion that names
   no cause.
5. **The fallback chain worked.** 220 model questions: 213 answered, 5
   unanswered, 2 invalid. 139 failed attempts (76 timeouts, 51 HTTP 500, 12
   HTTP 429). NVIDIA was unreliable all evening; Cloudflare answered many
   questions, and when Cloudflare's quota ran out (HTTP 429, KA-07 and KA-08)
   Cohere answered. No case ended "model unavailable". 727 s per episode on
   average.

## Limits

- One run per case: answers vary between runs of the same case (seen on
  2026-10-21: KA-02 was fixed then, escalated now).
- KA-09 has no label (it needs one per cause).
- The agent's own recommendation before `check_conclusion` is not recorded,
  so "chose escalate" cannot yet be told apart from "overruled"; that is
  change 1 of the MAX-HIGH item.
