# Project evaluation context

Stable knowledge an evaluator needs before judging anything in this
repository. Every claim below was checked against the code on `main` at
`bc9d155` (2026-11-01), not taken from the design documents. When the
architecture changes, add a dated entry under "Change log" and bump
`context_version`; never edit an older entry, so that a historical judgment
can still be read against the context it was made in.

- context_version: 1.0.0
- rubric_version it pairs with: 1.0.0 (`EVALUATION_RUBRIC.md`)
- inventory_version: 1.0.0 (`inventory/*.json`)
- packet_schema_version: 1.0.0 (`RUN_EVIDENCE_SCHEMA.json`)

## 1. What the system is for

An agent investigates an anomaly on a simulated CNC production line, forms
and tests hypotheses through read-only tools, recommends a bounded action,
asks a human for approval, carries the approved work out, and looks again
to see whether its prediction came true. The simulator keeps hidden ground
truth; only the evaluator reads it, after the run.

## 2. The execution path of a master run (verified)

```
python -m capstone.evals --config evals/scenarios.json --name <run> --out <report>.json
  capstone.evals.main                         reads the evaluator-only config
  -> capstone.evals.run_cases                 (manual opened here, if offered)
  -> capstone.experiment.run_experiment       one fresh policy per case
     -> capstone.episode.run_episode
        settings = get_settings()             .env + environment
        critic from settings if CRITIC=on     (critic_client, own model chain)
        sim  = build_world(seed, kind, fault) simulator/generator.build_scenario
                                              or simulator/challenge.build_challenge
        desk = ApprovalDesk(sim)              the human's side, never given out
        look, act = ObservationTools, ActionTools
        anomaly = agent.monitor.detect_anomaly(look, act)   symptom, never cause
        provider = SimulatorFactoryProvider(look, act)
                   [UnreliableProvider]       with --hazards / case hazards
                   [RecallingProvider]        with --memory
                   [ManualProvider]           with the manual (default on)
        state = InvestigationState(...)       agent working memory
        deps  = InvestigationDeps(...)        budgets, critic, hooks
        agent.investigation.run_investigation(state, deps)
           pydantic_graph: observe -> manual -> plan -> investigate
             -> hypothesize -> test -> critique -> recheck -> conclude
             -> propose -> execute -> verify   (critique is on every path
             into conclude; propose/execute/verify are a fixed procedure)
        learning.learn_from(...)              only with --memory and --audit;
                                              otherwise --audit writes the
                                              AuditRecord alone
        score = evaluation.scoring.evaluate(sim, None, desk.proposals(), ...)
                                              reads sim.ground_truth() and
                                              hidden state; diagnosis unjudged
     -> experiment.record_of -> ExperimentRecord (JSONL, holds the Score)
  -> evals.report_of(records, labels)         labels by hand (LabelBook) or
                                              --auto-label (TypeSafe Jev);
                                              correct = Score.fully_right
  -> EvalReport JSON, optional comparison with --compare-before
```

Files: `capstone-code/capstone/evals.py`, `experiment.py`, `episode.py`,
`agent/investigation.py`, `agent/loop.py`, `agent/model_policy.py`,
`agent/critic.py`, `evaluation/scoring.py`, `evaluation/labels.py`,
`evaluation/auto_label.py`.

`python -m capstone.experiment run` is the same path with a text report
instead of the JSON one; `python -m capstone.benchmark` runs single-model
episodes; `python -m capstone.baseline` runs the rule-based yardstick
through the same tools and `evaluate`.

## 3. Boundaries that keep truth, observation and belief apart

| Boundary | Where | Enforced by |
|---|---|---|
| Hidden truth never crosses the tools | `tools/observation.py`, `providers/factory.py` (`run_tool` rebuilds every answer from an output contract) | `tests/test_observation_tools.py::test_nothing_hidden_leaks_through_any_tool_over_a_full_run` pins the exact key set of every tool's answer |
| The agent cannot approve its own proposal | `tools/actions.py` (`ApprovalDesk` is never handed to the agent; `PROCEDURE_TOOLS` are not offered to a policy) | `tests/test_approval.py`, `tests/test_factory_provider.py::test_the_provider_offers_no_way_to_approve_or_reject` |
| The agent package imports no truth-side or memory code | `capstone/agent/*` | `tests/test_agent_artifacts.py::test_the_agent_package_does_not_import_truth_side_code` (import-graph rule) |
| Provenance is written by the loop, not the model | `agent/loop.py::gather` sets `origin` from the provider's `source` | `tests/test_agent_provenance.py` |
| Manual and memory are guidance, not observation | `providers/manual.py`, `providers/recall.py`; `diagnosis_supported` and `verify` count only `observable` evidence | `tests/test_agent_loop.py::test_only_factory_answers_count_as_support_for_the_automatic_stop`, `tests/test_agent_verification.py` |
| The manual carries no answer key | `manual/sections.py::check_no_leaks` | `tests/test_manual.py` |
| Memory cannot store hidden truth or a lesson resting on memory alone | `memory/policy.py` | `tests/test_memory_policy.py` |
| Scoring reads truth only after the run and changes nothing | `evaluation/scoring.py` | `tests/test_scoring_integrity.py` |
| Results files hold the truth and are evaluator-side | `ExperimentRecord.score`; `evals/scenarios.json` names the fault | documented; `tests/test_evals.py::test_full_episode_report_keeps_truth_out_of_policy_and_scores_only_labels` |

## 4. Components, as implemented

| Component | Module(s) | Status (code) | Notes for an evaluator |
|---|---|---|---|
| Simulator: clock, rng, state, sensors, events, scenarios, consequences | `simulator/*` | implemented, deterministic per seed | 6 fault packs in `faults.py`; 4 drawn by seed, servo and hydraulic only when forced |
| Compound challenge | `simulator/challenge.py` | implemented | two true faults on one machine, three distractors |
| Observation and action tools | `tools/observation.py`, `tools/actions.py` | implemented | 11 research tools, `wait`, 3 procedure tools |
| Provider boundary | `providers/factory.py` | implemented | argument models, output contracts, `MAX_ROWS=300`, safe errors |
| Hazards (tool unreliability) | `providers/hazards.py` | implemented, opt-in | standard schedule or blackout |
| Monitoring | `agent/monitor.py` | implemented | names a symptom; routine check after 4000 ticks |
| Inner loop | `agent/loop.py` | implemented | budgets, repeat check, provenance, supported-diagnosis gate |
| Stages (graph) | `agent/investigation.py` | implemented | fixed procedure after the conclusion; `check_conclusion` lowers unjustified interventions |
| Model-backed policy | `agent/model_policy.py` | implemented | 7 jobs, one client chain each; `STEP_QUESTIONS` 1 (default) or 2 |
| Tree-of-thought hypothesize | `agent/tree_of_thought.py` | implemented, opt-in | depth one, code prunes |
| Evidence brief and numeric claims | `agent/evidence_brief.py`, `contracts/hypotheses.py` | implemented (PR #150) | arithmetic checked, causes never |
| Critic | `agent/critic.py` | implemented, opt-in (`CRITIC`), review only; `CRITIC_FOLLOWUP` adds one reading; `CRITIC_BLIND` | its verdict never gates the conclusion |
| Manual RAG | `manual/sections.py`, `manual/index.py`, `providers/manual.py` | implemented; manual offered by default; `MANUAL_STEP` default on | keyword or Chroma semantic index; rev 1.3, 17 sections |
| Episodic memory | `memory/*`, `learning.py`, `providers/recall.py` | implemented; needs `DATABASE_URL`, opt-in `--memory` | gate `episodic-v3`; never run live in a comparison |
| Model clients | `providers/chat.py` | implemented | providers in scope only; fallback chains; whole-request deadline |
| Scoring | `evaluation/scoring.py` | implemented | root cause from labels only; action, resolution, evidence share from truth |
| Labels | `evaluation/labels.py`, `evaluation/auto_label.py` | implemented | hand labels authoritative; Jev proposals unvalidated against hand labels |
| Known-answer suite | `evaluation/known_answers.py`, `evals/scenarios.json` | implemented | 13 cases, pinned by tests |
| Degraded matrix | `evals/degraded.json`, `evals.py` abstention card | implemented, not run live | |
| Harness and reports | `experiment.py`, `evals.py` | implemented | records keep no evidence or hypotheses (see audit R1) |
| Baseline | `baseline.py` | implemented | 9/9 on known cases (2026-10-26) |
| Benchmark | `benchmark.py` | implemented | single-model episodes |
| Progress view | `progress.py` | implemented | display only |
| MCP, OpenTelemetry, frontend, multi-agent specialists beyond the critic, GoT, MMR, reranking | none | not implemented (Future Work) | do not evaluate |

## 5. Configuration that changes behaviour

Settings (`settings.py`, read from `.env`): `DEFAULT_MODEL`
(`nvidia/nvidia/nemotron-3.5-super-vl-120b-a12b`), per-job models,
`FALLBACK_MODEL` chain, `STEP_QUESTIONS` (1), `STATE_ACTION_BAR` (true),
`MIN_ACTION_CONFIDENCE` (0.9), `CRITIC` (off), `CRITIC_MODEL`,
`CRITIC_FALLBACK_MODEL`, `CRITIC_SECONDS` (40), `CRITIC_FOLLOWUP` (off),
`CRITIC_FOLLOWUP_SECONDS` (90), `CRITIC_BLIND` (off), `MANUAL_STEP` (on),
`MODEL_REQUEST_SECONDS` (45), `MODEL_QUESTION_SECONDS` (90), `MODEL_RETRIES`
(3), `MODEL_MAX_OUTPUT_TOKENS` (16384), `EMBEDDING_MODEL`, sampling maps.

Budgets (`agent/state.py::Budgets`): 24 iterations, 20 research calls,
1200 s in all with 400 s kept for the follow-up, 14 follow-up calls, 1
critic diagnostic call, 3 unproductive steps.

Command options: `--manual [semantic|keyword] | --no-manual`, `--memory`,
`--audit`, `--hazards [standard|blackout]`, `--tree-of-thought`,
`--timeout-seconds`, `--approve all|none|console`, `--known | --seeds |
--challenge | --held-out`.

The record keeps `step_questions`, `state_action_bar`, whether a critic ran
(and blind), whether the follow-up ran, whether the manual or memory was
offered, and which models answered. It does not keep the commit SHA, the
`.env` values, the budgets or the manual revision: those must be recorded
beside a run by whoever runs it (`EVALUATION_README.md`).

## 6. Evidence a run produces

| Artifact | Produced by | Holds | Truth? |
|---|---|---|---|
| `ExperimentRecord` JSONL | `experiment.append_records` | conclusion, recommendation, scores, tool names, agent steps, model-call summary, critique and recheck records, manual/recall searches | yes (`score`) |
| `AuditRecord` JSONL | `--audit` (`agent/completion.AuditLog`) | evidence with content, hypotheses, every decision with arguments, provenance, conclusion, proposal, verification, pruned candidates | no |
| `EvalReport` JSON | `evals.report_of` | per-case correctness from labels, tool calls, runtime, critic fields, abstention card | yes (`expected_faults`) |
| Labels JSONL | hand or `--auto-label` | the cause a conclusion names | no, but written with the truth available |
| Live progress text | `progress.py` | observable steps | no |

Only the audit log holds what a judge of investigation quality needs. The
master runs saved in `docs/benchmarks/` were made without `--audit`.

## 7. Experiments on record (in the repository)

| Run | Date | Where | Configuration | Outcome |
|---|---|---|---|---|
| scored single agent, 9 known cases | 2026-10-26 | `docs/benchmarks/2026-10-26-scored-single-agent.md`, labels `2026-10-26-labels-single-1.jsonl` (results file local only) | `main` e65bd8f, NVIDIA 120B with a fallback chain, no manual, bar 0.9, two questions per step | 5/8 one-fault cases right by hand label; 0 fixes asked for |
| master-single-2026-10-27 | 2026-10-27/28 | `2026-10-27-master-resumed.json`, `.records.jsonl`, `2026-10-27-master-labels.jsonl` | defaults of the day (two questions per step, bar stated, no manual, no critic); resumed at KA-04; commit not recorded | 3/9 right; 5 timeouts; labels drafted by the coding assistant and decided by the developer |
| rule baseline | 2026-10-26 | `2026-10-26-baseline-known.txt` | code only | 9/9 on known cases |
| provider benchmarks | 2026-10-20/21 | `2026-10-20.md`, `2026-10-21-*.md` | single models | timing and reliability |
| bar-0.80 runs A/B, 2026-10-30 critic runs, run-2 ToT critic-off/on (2026-10-31) | | notes in `docs/PROGRESS.md` and `docs/RUN2_FINDINGS_FUTURE_WORK.md`; files local only | mixed, resumed configurations | one confirmed correct case per run-2 arm |

## 8. Constraints an evaluator must respect

- Live runs are Codex's job (AGENTS.md section 12); this framework prepares
  and scores, it does not launch.
- Model providers in scope: NVIDIA, Groq, Mistral, Gemini, Cohere,
  Cloudflare, the routers, TypeSafe Jev for typed judgments. SubQ Snap and
  TypeSafe Jev are used here only as evaluators of evidence, outside the
  `capstone` package, with their keys in the environment of the person
  running `evaltools.snap_request --send`.
- Held-out seeds 1000-1009 (`experiment.HELD_OUT_SEEDS`) are for reported
  numbers; nothing may be tuned on them.
- A real model does not answer identically twice; one run per case is a
  snapshot, not a measurement.

## Change log

- 1.0.0 (2026-11-01): first version, written from `main` at `bc9d155`.
