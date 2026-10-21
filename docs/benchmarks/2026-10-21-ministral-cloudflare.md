# Fallback candidates benchmarked, 2026-10-21

Live, real models, the developer's keys. The question was whether Mistral's
Ministral 14B or Cloudflare's Llama 3.3 70B is a better fallback than Cohere
command-a-03-2025 (the fallback since 2026-10-20). Same command and limits as the
2026-10-20 benchmark, so the rows compare directly:

    MODEL_REQUEST_SECONDS=45 MODEL_QUESTION_SECONDS=90 python -m capstone.benchmark <model> --seeds 0

Every job given the one model alone, no fallback, 3 retries, the 1,200 s budget,
each fault on seed 0 (four episodes per model). Raw calls:
`2026-10-21-ministral-cloudflare-calls.jsonl`. Cohere's row is from
`2026-10-20.md`.

| Model | Valid answers | Invalid replies | Failed requests | Median s | Slowest-5% s | Right action | Median episode s |
|---|---|---|---|---|---|---|---|
| cloudflare/@cf/meta/llama-3.3-70b-instruct-fp8-fast | **100/100** | **0** | **0** | 2.8 | **5.7** | 2/4 | **77.5** |
| cohere/command-a-03-2025 (2026-10-20) | 94/98 | 4 | 6 (HTTP 429 5, unreachable 1) | 2.9 | 11.2 | 2/4 | 89.8 |
| mistral/ministral-14b-2512 | 118/121 | 3 | 0 | 2.4 | 8.2 | 0/4 | 126.2 |

"Right action" 2/4 is what a model gets by never changing anything (the false alarm
and the bad batch need no change). No model here fixed the bearing or the setting.
Ministral asked for changes the bad batch and the false alarm did not need, which is
the worse mistake for a model that sometimes writes part of an investigation.

**Decision (the developer's rule, 2026-10-21: switch if a candidate does better than
Cohere):** Cloudflare Llama 3.3 70B matches Cohere on actions and beats it on every
reliability column, so it becomes the recommended `FALLBACK_MODEL`. The developer set
it in their `.env` the same day. Cloudflare needs `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` (the 32-character ID at the start of the account's
`*.r2.cloudflarestorage.com` address). This run fit in Workers AI's free daily
allowance.

Ministral 14B stays a candidate for a narrow small-agent job (reliable, fast), not the
fallback. Mistral's key reaches ministral-3b/8b/14b and open-mistral-nemo; Small and
Medium were rate-limited and Large is not in the key's tier.

## The default model with 120 s waits

The developer raised `MODEL_REQUEST_SECONDS` to 120 and `MODEL_QUESTION_SECONDS` to 240
to test whether nemotron 120b, given time, would answer every question itself. Three
known cases that escalated in `results-5` (seed 6 bearing, seed 7 batch, seed 9
setting), `--timeout-seconds 2400`, Cohere as fallback:

| Case | Stop | NVIDIA timeouts | Fallback answers | `conclude` | Outcome |
|---|---|---|---|---|---|
| bearing (seed 6) | evidence sufficient | 0 | 0 | NVIDIA | "brief, self-clearing spikes", no action (wrong) |
| batch (seed 7) | diagnosis supported | 0 | 0 | invalid reply | undetermined |
| setting (seed 9) | iteration limit, 1,240 s | 0 | 0 | invalid reply | undetermined; 9 of 43 replies invalid |

The waits worked: no timeouts, and the fallback was never needed (versus 88 timeouts
in nine cases at 45 s). But two of three conclusions were invalid replies, so the run
cannot show whether NVIDIA would commit to a fix. The record does not keep why a reply
was refused (cut off at the 8,192 output tokens, or the wrong shape); recording that is
the next step.
