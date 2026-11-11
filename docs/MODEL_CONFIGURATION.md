# Model sampling and critic fallback

Settings are loaded from `.env` and the process environment. A process environment
variable takes precedence over the corresponding `.env` variable. These settings
apply to newly built model clients; an existing running process is not reconfigured.

## Sampling

The default request values for the project's three exact model references are:

| Reference | Temperature | top_p |
| --- | --- | --- |
| `nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b` | 1.0 | 0.95 |
| `cohere/command-a-03-2025` | 0.3 | 0.75 |
| `mistral/ministral-14b-2512` | 0.0 | omitted: service default |

Other model references retain temperature 0 and omit top_p. The defaults are keyed
by the complete reference, so they do not silently apply to every model on a service.
NVIDIA's values are its recommendation for **text**. Cohere's are documented starting
values, not experimentally established best values for the simulator. Ministral's
temperature 0 meets its guidance of below 0.1 for production.

To explicitly configure the three models, copy these two lines into `.env`:

```dotenv
PROVIDER_SAMPLING={}
MODEL_SAMPLING='{"nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b":{"temperature":1.0,"top_p":0.95},"cohere/command-a-03-2025":{"temperature":0.3,"top_p":0.75},"mistral/ministral-14b-2512":{"temperature":0.0,"top_p":null}}'
```

For defaults across a provider instead, use its short name as the key:

```dotenv
PROVIDER_SAMPLING='{"nvidia":{"temperature":1.0,"top_p":0.95},"cohere":{"temperature":0.3,"top_p":0.75},"mistral":{"temperature":0.0,"top_p":null}}'
MODEL_SAMPLING={}
```

Set each variable only once. These are two alternative configurations. Both maps
can be used together when a particular model should differ from its provider.
Each field resolves in this order, highest precedence first:

1. Exact reference in `MODEL_SAMPLING`.
2. Provider name in `PROVIDER_SAMPLING`.
3. The code default for that exact model.
4. Temperature 0 and service-default top_p.

Omitted fields inherit from the lower layer. An explicit `"top_p":null` removes
top_p from the request. Temperature must be finite and between 0 and 2; top_p
must be finite and greater than 0 and at most 1, or null. Unknown option names
are refused; the model service can impose additional limits. Provider keys and
full model references must match those used by the run.

Every model in a fallback chain uses its own sampling settings, including the
critic's backups. JSON validation remains in place. Temperature and top_p change
sampling, not the simulator seed, the action threshold or the model's reasoning mode.
No API `seed`, thinking switch or reasoning-effort parameter is added by this change.

## Independent critic backups

```dotenv
# Investigator backup:
FALLBACK_MODEL=cohere/command-a-03-2025

# Critic primary and its own backup:
CRITIC_MODEL=mistral/ministral-14b-2512
CRITIC_FALLBACK_MODEL=cohere/command-a-03-2025
```

The critic never reads `FALLBACK_MODEL`. The example intentionally chooses Cohere
for both roles; changing one line does not change the other role's chain. Existing
comma-separated `CRITIC_MODEL` lists remain supported. The separate critic fallback
list is appended after that list, with duplicates removed in first-seen order.
An empty `CRITIC_MODEL` still disables construction of a chain: a backup alone is
not a primary model. `CRITIC=on` is required to enable the settings-built critic.

## Late-run model (`LATE_MODEL`)

```dotenv
LATE_MODEL=nvidia/nvidia/nemotron-3.5-lightning-30b-a3b
LATE_MODEL_SECONDS=60
# Optional: route a late conclude question to the same model.
# LATE_CONCLUDE=on
# Optional: let it think, with a cap on thinking tokens.
# LATE_MODEL_THINKING=true
# LATE_MODEL_REASONING_BUDGET=1024
```

Unset by default: every question keeps its own model. When `LATE_MODEL` is
set, a **decide** question with less than `LATE_MODEL_SECONDS` left goes to it
(then the shared `FALLBACK_MODEL` chain). The investigator's model gets half
of a question's time (the other half is kept for the fallback), so at 60 s
Super 120B would have under 30 s, and it answered a decide question within
30 s only 55% of the time (499 calls, 2026-10-31 to 2026-11-09).

`LATE_CONCLUDE=on` separately opts in the **conclude** question when less
than the same threshold remains. It requires `LATE_MODEL` and uses the same
model, fallback chain and thinking settings. An earlier conclusion still
uses `CONCLUDE_MODEL` or `DEFAULT_MODEL`. All other question types keep their
own model; the original late decide behavior is unchanged when the conclude
option is off. This changes model behavior and must be recorded with a live
run's configuration before comparing its results with an earlier run.

**Thinking.** Off by default: NVIDIA is sent
`"chat_template_kwargs": {"enable_thinking": false}`. With
`LATE_MODEL_THINKING=true` it is sent `true`, plus `"reasoning_budget"` when
`LATE_MODEL_REASONING_BUDGET` is set. Both fields come from NVIDIA's sample
request for Nemotron 3.5 Lightning on build.nvidia.com (2026-11-09). They go to
NVIDIA models only, never to the fallback, and only on routed late questions.
`DECIDE_REASONING_EFFORT` is never sent to the late model. The run header names
the model, the threshold and the thinking setting for each enabled route.

**Model.** The developer's choice (2026-11-09) is Nemotron 3.5 Lightning 30B
(3B active). On 2026-10-20, with thinking on and the old 2,048-token and 15 s
limits, it gave mostly invalid replies; it has not been tried with thinking off
or the current limits, nor checked with NVIDIA's structured output. The first
choice, `nvidia/nvidia/llama-3.1-nemotron-70b-instruct`, is still listed by the
API but answered HTTP 404 "Not found for account" on 2026-11-09. Lightning
gets the default sampling of a model with no entry here (temperature 0).

**Rate limit.** Every model on NVIDIA's API shares the key's limit. The late
model replaces Super on those questions rather than adding calls (developer,
2026-11-09, lifting for this setting the earlier "only Super on NVIDIA's API"
rule).

## Evaluation

These sampling changes have offline regression coverage, but have not been
evaluated in live master episodes. Compare configurations on matched cases and
record the maps used. Do not describe temperature-1 results as the same baseline
as earlier temperature-0 results.

## Provider documentation

- [NVIDIA Nemotron 3.5 Super VL model card](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b/modelcard)
- [Cohere Command A model card](https://huggingface.co/CohereLabs/c4ai-command-a-03-2025)
- [Cohere Chat API sampling parameters](https://docs.cohere.com/v2/reference/chat)
- [Ministral 3 14B Instruct recommended settings](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512#recommended-settings)
