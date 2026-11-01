# MVP scope matrix

Each requirement of `docs/MVP_SCOPE.md` sections 1-9, with its implementation
status on `main` at `bc9d155`, the verification evidence found, and what is
still open. "Verified" here means a deterministic test proves the behaviour
on the commit; "live" means a real-model run demonstrated it. Statuses:
IMPLEMENTED+VERIFIED, IMPLEMENTED (unverified or partly), INCOMPLETE,
UNIMPLEMENTED (post-MVP).

| # | MVP requirement | Status | Components | Evidence | Gaps / dependencies |
|---|---|---|---|---|---|
| 1a | One line, 3-8 machines, named CNC-01 upward | IMPLEMENTED+VERIFIED | `simulator/line.py` | `tests/test_build_line.py` | |
| 1b | 5-8 sensor values: temperature, vibration, pressure, throughput, defect rate, machine state | IMPLEMENTED (partly) | `simulator/sensors.py` (vibration, temperature, load, power, following error, hydraulic pressure, air), events, inspections | sensor tests; `test_observation_tools` | "throughput" and "defect rate" exist only as job events and pass/fail inspections, not as sensors; acceptable, but the agent must compute rates itself |
| 1c | Jobs, batches, maintenance history, quality history | IMPLEMENTED+VERIFIED | `simulator/scenarios.py` (`ProductionLine`), `state.py`, `maintenance.py` | `test_production_line`, `test_material_batch`, `test_maintenance_history`, `test_quality` | |
| 1d | Evolves over time; hidden ground truth; causal chain bearing -> vibration -> temperature -> defects | IMPLEMENTED+VERIFIED | `simulator/simulator.py::step`, `scenarios.py`, `ground_truth.py` | `test_bearing_degradation`, `test_failure`, `test_ground_truth`, `test_load_wear_coupling` | |
| 2 | Four fault scenarios (degradation, batch, configuration, false alarm) | IMPLEMENTED+VERIFIED | `faults.py` packs | `test_fault_packs`, `test_known_answers` (two cases each) | plus servo and hydraulic packs (forced only) and the compound challenge |
| 3a | One orchestrating agent: observe, investigate, hypothesize, test, decide, act, verify, remember | IMPLEMENTED+VERIFIED (offline) | `agent/investigation.py` graph, `agent/loop.py` | `test_agent_investigation::test_an_investigation_goes_through_the_stages_in_order`, `test_episode` | live reasoning quality unverified: 3/9 right on the last full master run |
| 3b | Configurable output-token, timeout, retry, tool-call and iteration limits enforced by the loop | IMPLEMENTED+VERIFIED | `agent/state.py::Budgets`, `settings.py`, `providers/chat.py` | `test_agent_loop` budget tests, `test_chat_client`, `test_request_deadline` | |
| 4 | Tools behind one boundary with typed arguments and results; the agent decides what to ask next | IMPLEMENTED+VERIFIED | `providers/factory.py`, `tools/*` | `test_factory_provider`, `test_observation_tools` | MCP exposure deferred (Future Work 2) |
| 5 | Hypothesis table with supporting/contradicting evidence and confidence; revision on evidence | IMPLEMENTED+VERIFIED (structure) | `contracts/hypotheses.py`, `agent/loop.py::apply_interpretation`, `model_policy.py` | `test_agent_loop::test_the_policy_revises_hypotheses_and_revisions_are_counted`, `test_reasoning_evidence` | whether the live model revises sensibly is unmeasured (RUN-02) |
| 6 | Human approval for consequential actions; read-only research automatic | IMPLEMENTED+VERIFIED | `tools/actions.py::ApprovalDesk`, `agent/investigation.py::propose` | `test_approval`, `test_agent_action` | experiments use `approve_all`; a human path (`--approve console`) is never executed in tests |
| 7 | Verification after intervention, mandatory, prediction vs observation | IMPLEMENTED+VERIFIED | `agent/investigation.py::verify` | `test_agent_verification` (22 tests) | the agent's verdict is not compared with the truth anywhere in the reports (added here as `verification_calibration`); live: only KA-02 of the master run reached a verified fix |
| 8 | Basic memory: store per investigation; later recall of similar investigations | IMPLEMENTED (unverified live) | `memory/*`, `learning.py`, `providers/recall.py`, `memory_comparison.py` | `test_memory_policy`, `test_learning`, `test_recall_tool`, `test_memory_comparison` | needs `DATABASE_URL`; the memory comparison has never run against a model, so the MVP claim "persistent learning" is undemonstrated |
| 9a | Per-scenario record: true cause, diagnosis correct, relevant evidence available/collected, recommended action, correct intervention, resolution, tool calls, length | IMPLEMENTED+VERIFIED | `evaluation/scoring.py::Score` | `test_evaluation`, `test_scoring_integrity`, `test_episode::test_a_whole_episode_records_the_section_nine_fields` | "evidence collected" is any-window; see audit E3 |
| 9b | Reporting such as "18/20 root causes" | IMPLEMENTED | `experiment.report`, `evals.report_of` | `test_experiment`, `test_evals` | the summary line mixes denominators and credits escalations as right recommendations on no-action cases (audit E2) |
| 9c | Known-answer regression suite with fixed seeds; truth only to the evaluator | IMPLEMENTED+VERIFIED | `evaluation/known_answers.py`, `evals/scenarios.json` | `test_known_answers`, `test_evals::test_master_config_covers_all_known_answer_cases` | KA-10 to KA-13 have never been run live |
| 9d | Repeatable simulator inputs; live outputs vary | IMPLEMENTED+VERIFIED | seeds everywhere | `test_known_answers::test_the_suite_is_repeatable` | no repeated live runs of one case exist to quantify variance |

## MVP claims and what supports them today

| Claim the capstone wants to make | Supported? | By what | Missing |
|---|---|---|---|
| "The agent investigates an anomaly end to end with a human in the loop" | yes, offline and once live | scripted episodes; KA-02 (2026-10-27): right cause, `replace_bearing` approved, carried out, verified resolved, truth resolved | repeats |
| "The agent identifies root causes correctly" | no | 3/9 on the only full master run in the repository; 5/8 on 2026-10-26 | a run on all 13 cases with one frozen configuration, labels decided first |
| "The evaluation is objective" | partly | deterministic scoring from hidden truth; scoring-integrity tests | labels are hand-written with the truth visible to the labeller; auto labels unvalidated |
| "The critic improves investigations" | no | code only; live runs show it objecting when the agent was right | the matched critic-off/critic-on experiment (see FINAL_REPORT.md) |
| "Memory makes later investigations better" | no | code only | the memory comparison, live |
| "The manual helps" | no | 0 searches in the one manual-on run (2026-10-27 B); the manual step now retrieves automatically | `cited_by_origin["manual"]` and RUN-04 on traced runs |
| "Hidden truth never reaches the agent" | yes | key-set leak test, import rule, provenance tests, manual leak check, memory gate | a judge's view of prose leaks (TL-01) |

## Post-MVP items that must not be scored as missing

MCP server, OpenTelemetry/LangSmith, frontend, specialist agents beyond the
critic, Graph of Thoughts, MMR / rerankers, Docling ingestion, difficulty
modes, Haas-fidelity retrofit, rapid triage, computer vision, voice input.

## Architectural decisions that make MVP requirements harder later

- The experiment record omits evidence, hypotheses and tool arguments; any
  evaluation of evidence use needs the separate audit log, which the master
  runs did not produce. Making `--audit` the default for `evals` would fix
  this without touching the agent.
- `EvalCase` has no termination reason, configuration block or commit, so
  the JSON report cannot say whether a comparison is like for like.
- Labels and truth live in the same results file, so a labeller always has
  the answer in reach.
