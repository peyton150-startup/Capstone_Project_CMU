# Gemma 4 E4B on Cloud Run: feasibility check

Checked 2026-10-26. **Research only: no service deployed, no inference run,
and no zero-cost project run demonstrated.**

## What was verified

Google documents both vLLM and Ollama deployments of Gemma 4 E4B on Cloud
Run. The model identifiers are `google/gemma-4-E4B-it` (vLLM) and
`gemma4:e4b` (Ollama). These are the requested model, not Gemma 3n E4B.

- [Google deployment guide](https://docs.cloud.google.com/run/docs/run-gemma-on-cloud-run)
- [Google Ollama guide](https://docs.cloud.google.com/run/docs/tutorials/gpu-gemma-with-ollama)
- [Ollama model listing](https://ollama.com/library/gemma4)

The official vLLM example allocates one RTX PRO 6000 GPU, 20 vCPUs and
80 GiB RAM. It is a working reference configuration, not a free offer.
Do not deploy that example under the assumption that open weights imply
free hosted inference.

## Can project runs be free?

[Cloud Run pricing](https://cloud.google.com/run/pricing) lists no free GPU
allowance. The nonredundant RTX PRO 6000 costs $0.00036522/second, about
$1.31/hour for the GPU alone. CPU and memory add cost. Trial or education
credits could cover a bill; that is different from an ongoing free tier.

A CPU-only, request-billed service is the candidate to test first. Its
monthly free allowance is 180,000 vCPU-seconds, 360,000 GiB-seconds and two
million requests, shared across projects on the billing account. At
4 vCPUs and 16 GiB, unused allowances would cover at most 22,500 billable
seconds (6.25 hours), limited by RAM. This arithmetic is not a throughput
measurement or a guarantee that the model fits and meets the agent's
request deadlines. Model downloads, startup and other billable activity
also consume resources. Storage, image builds and network charges need
separate accounting. Scale-to-zero does not cap the monthly bill.

## Project access in this session

The user supplied project ID `capstone-project-512814`. The Windows host
initially had no installed CLI or saved Google Cloud login. Downloaded
Google's portable SDK 590.0.1 into the ignored project-local directory
`.chroma/cloud-run-tools/`, verified its SHA256 against Google's archive
listing, and confirmed `gcloud version` succeeds. Windows tar rejected
several links under the bundled gsutil documentation/test files; the
`gcloud` version and account-list commands still returned successfully.
The SDK is a local operational tool, not a project dependency or PR file.
No account was authenticated; started Google's browser login flow.
Project access, billing, remaining free allowance and credits still need
to be verified. No cloud resource has been provisioned.
## Next executable checks once project access is available

1. Finish Google Cloud CLI authentication with the user, and
   select the supplied project explicitly. Confirm billing, credits and
   existing consumption before provisioning anything.
2. Try a private CPU-only Ollama service with request billing, minimum zero
   instances, maximum one, concurrency one, and a bounded context. Start
   with 4 vCPUs / 16 GiB as an unmeasured candidate. Include the model-file
   download in peak RAM estimates: Cloud Run's writable filesystem uses
   instance memory. If it cannot fit, stop and recalculate before resizing.
3. Pull only `gemma4:e4b`. Measure cold startup and one short JSON reply,
   then one realistic project prompt. Stop on startup failures, memory
   exhaustion, or latency beyond the project's allowed request time.
4. Keep the endpoint authenticated. Cloud Run requires a Google identity
   token; an existing provider's API key does not authorize that endpoint.
   A local authenticated Cloud Run proxy can support the initial probe.
5. If probes work, connect through the project's existing `ChatClient`
   (`providers/chat.py`), which already accepts an explicit URL and model.
   `client_for` and `Settings` currently have no Cloud Run provider or
   endpoint setting: setting `DEFAULT_MODEL` alone cannot connect it.
   Any persistent provider/auth integration is a separate feature with
   the repository's teaching gate and offline tests; do not repurpose
   another provider's URL or overwrite its key.
6. Run one episode at a time with isolated result files and a throwaway
   memory store. Record cold/warm time, JSON validity, model timeouts,
   billed resource usage and diagnosis labels. Never describe a synthetic
   transport test as live inference. Keep the simulator independent of
   the hosted model and keep hidden truth outside prompts.
7. Delete the test service after measurement, verify deletion, and inspect
   billing once usage has posted. Remove only test-owned storage or build
   artifacts. Claim a free run only after actual billing confirms it.

The hosting, model and quantization may be affordable yet unsuitable for
long investigations. A successful short reply is only the first probe.
No default model, provider, dependency or `.env` was changed here.
