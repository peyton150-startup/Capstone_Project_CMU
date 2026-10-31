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
