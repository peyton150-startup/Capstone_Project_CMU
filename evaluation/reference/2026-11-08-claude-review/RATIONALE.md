# Why each answer

Reviewer: Claude (Claude Code), at the developer's request; the developer has
not checked these. Rubric 1.1.0. One row per answer in `answers.json`.
Evidence ids (E1, E2, ...) and hypothesis ids refer to the blinded packet of the
same review id. Source lines for the FN, TS and TL items are from this PR.
Rows marked **changed** or **new** differ from the first round under rubric
1.0.0 (`answers.rubric-1.0.0.json`).

## Agent investigations (RUN)

### RUN `230bb91f581d295e` (vibration alarm on CNC-02; named a cause at 0.92, the final check lowered intervene to escalate)

| Question | Answer | Why |
|---|---|---|
| RUN-01 | 3 | E3, E7, E16 and E17 show the symptom. The wait and re-read (E7, E16) separate it from a transient, and the peer reads (E5, E11 to E14) separate it from a line-wide cause. Not 4: load, temperature, settings and maintenance were never read, so the operating and instrument causes the retrieved manual names were not separated. The "bearing or axis-drive wear" part also rests on the stated assumption that wear need not raise power. |
| RUN-02 | 3 (**changed**, was 4) | There are three distinct hypotheses: transient H1, CNC-02 equipment H2 and line-wide H3. The re-reads and peer reads tell them apart, and the confidences rose from 0.55 to 0.95 as those readings came back. Not 4: the set missed two kinds of cause the retrieved manual names for this symptom (section 1.2: operating changes and instrument issues). |
| RUN-03 | ineffective | The critic named a real gap: no temperature or load data to rule out operating changes. But its check was a CNC-02 vibration trend (E17) that repeats readings already in hand, so the gap was never tested. Its second objection (CNC-08's drop) has no substance: CNC-08 went idle after job 7 finished (E10). |
| RUN-04 | ignored (**changed**, was unnecessary) | E2 is cited nowhere. The conclusion ("most consistent with bearing or axis-drive wear", from vibration with stable power) goes against section 2.1's caution "Do not diagnose a bearing by vibration alone". |
| RUN-05 | not_applicable | Recommendation escalate, proposal null, verification empty. |
| RUN-06 | inappropriate | It named one cause ("developing equipment problem ... bearing or axis-drive wear") while operating and instrument rivals were untested. That counts as committed: the escalate came from the final check lowering the policy's intervene, not from the agent. |
| RUN-07 | evidence_gathering (**changed**, was reasoning) | At decision 18 the agent stopped ("nothing further is needed"). It had not made the temperature, load, settings or maintenance reads the retrieved manual recommends for this symptom (sections 1.2 and 2.1), and no tool error or budget limit forced the stop. The readings it did have were read correctly. |
| RUN-08 | 2 | The CNC-02-specific, non-transient elevation is shown. Two claims stated as settled are not supported. "Sustained vibration above the 4.50 mm/s alarm setpoint" overstates readings whose means are 4.35 to 4.42, since only peaks cross 4.50. "Developing" is not shown: the trend over 26 ticks is flat and no pre-alarm history was read. |
| RUN-09 | true (**new**) | Confidence is 0.92, while operating and instrument causes, which the retrieved manual names for this symptom, were never separated by a reading. |
| RUN-11 | used | The follow-up was made where the critic pointed (E17, a window already in the past). H2 stayed at 0.95, and E17's bucket means (4.375, 4.39, 4.407) are consistent with it. The conclusion cites E17, and its figures match. |
| RUN-12 | false | E14 shows CNC-08 at a mean of 1.32 and a minimum of 0.0, not "roughly 1.7-2.6 mm/s". E3, E7, E16 and E17 show means below 4.50, not "sustained vibration above the 4.50 mm/s alarm setpoint". |

### RUN `c552284a9d4329d3` (vibration alarm on CNC-05; escalated between sensor bias and a normal band)

| Question | Answer | Why |
|---|---|---|
| RUN-01 | 3 | The observable base is thorough: CNC-05 load, temperature, power and following error (E6 to E9, E17), events (E10), settings (E14), all peers (E5, E11 to E13) and a re-read after waiting (E16). Not 4: the local-disturbance rival (C5) was never separated. The one history read (E18, ticks 800 to 816) shows a climb from 3.61 to about 4.2 after job 9 started at 802, which leaves a job-linked or slowly rising cause open; the conclusion read it the other way. |
| RUN-02 | 4 (**changed**, was 3) | The distinct hypotheses cover every kind of cause in section 1.2: transient H1, instrument H2, operating band H3, equipment C2, plus local disturbance C5. Readings tell them apart: peers, load, temperature, power, following error, settings, events and a re-read. The confidences follow those readings. The drop from 0.9 to 0.72 came when the set was rebuilt with more rivals, not from a reading. E18 does not contradict the leader: its rise comes at the job 9 start and the band then holds. Its misreading in the conclusion is scored under RUN-08 and RUN-12. |
| RUN-03 | ineffective | The critic's check asked for ticks 840 to 900 at tick 840, a window that ends after the current tick, so E19 holds one sample. It did not raise the E18 rise or the untested local disturbance. |
| RUN-04 | useful | E2 shaped the plan: temperature, load and factory air temperature over the same window (section 1.2, with factory air set aside for a stated reason), settings, events and nearby stations (2.1), instrument issues as a cause (H2), and the next check, "independent reference measurement ... or maintenance inspection" (2.1). Nothing it recommends for telling sensor bias from a normal band was skipped. |
| RUN-05 | not_applicable | Escalate, no proposal. |
| RUN-06 | appropriate | It kept H2 and H3 open, which the evidence cannot separate without an independent measurement, and escalated. |
| RUN-07 | reasoning | Readings in hand were misread. At decision 19 flat power was taken to rule out any mechanical fault ("effectively ruled out"). In the conclusion E18 was taken to show the ~4.04 mm/s level predates job 9, although 15 of its 17 samples are from job 9 and the two earlier samples (3.61, 3.76) are lower. The first of these comes before the time limit cut the test phase, so tooling is not the earliest cause. |
| RUN-08 | 2 | The narrowing to H2 or H3 is mostly supported. But "the elevated vibration predates job 9 ... so it is not job-specific" is stated as settled without support, and the conclusion's own open question asks exactly that. "Isolated threshold crossings at ticks 826 and 828" also omits E16's further crossings at 836, 837 and 839. |
| RUN-09 | false (**new**) | Confidence is 0.75, below the 0.8 line. |
| RUN-11 | no_feedback (**changed**, was used) | The critic's only check (ticks 840 to 900, given at tick 840) could not be carried out when it was given. |
| RUN-12 | false | E18, with E10's job 9 start at tick 802, does not show that the elevation "predates job 9" at a 4.04 mean: that is a time window that does not match, and the mean is mostly job 9 data. The other cited figures check out: load mean 68.96, temperature mean 147.19, following error mean 4.96, peer means 1.00, 2.06, 1.05 and 1.80, and power about 12.45 at both alarm ticks. |

### RUN `26b1f92dbf2b1844` (3 of 4 jobs failed inspection; escalated unresolved at 0.4)

| Question | Answer | Why |
|---|---|---|
| RUN-01 | 3 (**changed**, was 2) | E19 (CNC-05 following error over the job windows) and E18 (CNC-02's history) are discriminating readings: they separate the conclusion from H4 and from a new CNC-02 fault. A feed-axis drive fault on CNC-01 to CNC-04 is left unseparated. E15's clean vibration cannot separate it, because section 2.14 says a worn drive leaves vibration unchanged, and following error was read on CNC-05 only. |
| RUN-02 | 2 | The hypotheses are distinct: CNC-04, material or inspection, multiple causes, CNC-05 and the CNC-02 baseline. But confidences moved on readings that cannot tell the hypotheses apart. H1 fell to 0.05 on E15, and H2 rose to 0.7 on normal vibration everywhere, and neither reading separates a drive fault from material or inspection causes (section 2.14). |
| RUN-03 | unknown | The critique outcome is invalid_reply. |
| RUN-04 | misleading | H2 ("material or inspection variation; CNCs not implicated") cites E2, but E2 does not support "CNCs not implicated". Section 2.9 says to judge a batch against other batches (only batch 1 exists here) and to "also consider machine or inspection causes". Section 2.14 says normal vibration is the drive-fault signature. |
| RUN-05 | not_applicable | Escalate, no proposal. |
| RUN-06 | appropriate | There is one batch and every job is routed through every station, so the evidence leaves several causes open. It declined (committed false, 0.4) and escalated. |
| RUN-07 | reasoning | The earliest failure is at decision 18: clean vibration on CNC-04 (E15) was read as arguing against a CNC-04 fault, which it cannot do for a drive fault. The stop at decision 21 without following error on the other stations came after that misreading. |
| RUN-08 | 2 | "Unresolved" is supported, and so are the CNC-02 baseline (E18) and the CNC-05 following-error comparison (E19). But "a CNC-04 fault (H1) is contradicted by clean CNC-04 vibration (E15)" is stated as settled without support. |
| RUN-11 | no_feedback | The critic gave an invalid reply and the recheck was skipped ("the critic gave no usable answer"). |
| RUN-12 | true | Every cited item contains what is attributed to it: failures right after CNC-05 (E10, E12, E13), CNC-02 means of about 1.8 to 2.4 from tick 60 (E18), comparable recent vibration (E7, E11, E15 to E17), and the job-window following-error means and maxima (E19, to the precision stated). The faulty step is the inference drawn from E15, which RUN-08 scores. |

## Tool, functions, tests and the batch comparison

### TL `1260f9b4e44f1ac3` (tool `get_maintenance_history`)

| Question | Answer | Why |
|---|---|---|
| TL-01 | true | It reads only past service records (machine, date, kind, note) and this run's `maintenance` events. `run_tool` rebuilds every row through `MaintenanceObservation` (`extra="forbid"`). An unknown machine is refused with a message that names only the caller's own id, other exceptions become "Tool execution failed.", and the tool changes nothing. The "finished" notes describe a removed part in words, which is the designed technician finding (section 2.14), not hidden state. |
| TL-02 | true | The description matches the behaviour: one machine or all, oldest first (past records sorted by date, then this run's events in tick order), past rows with a date and tick null, run rows with their tick, "what a technician did and wrote, not a cause". The shared 300-row cap is not mentioned, but a normal call cannot reach it (one to four past records per machine). |
| TL-03 | 0 | It is a direct projection of stored records. The only filter is an exact machine match, made after the machine is checked to exist. There is no window, unit or ordering step that could drop rows. The stale-record hazard is designed and does not count. |

### FN `012cf733fced8b7d` (`capstone.ingestion.channel_map:main`)

| Question | Answer | Why |
|---|---|---|
| FN-01 | false | The contract (docstring, the `outcome` variable, and the argparse help) names results 0 and 1 only. The function also returns 2 when `--probe` does not match the map, and exits through `parser.error` when the output or map is inside the checkout. The help texts mention the refusals but not these exit codes. |
| FN-02 | partly | Asserted: the build and check happy paths, the probe-mismatch return 2, and the inside-repo refusal for `build`. Not reached: the non-clean result 1 (unmapped or mismatched lines), the inside-repo refusal for `check --update-reported`, and `check` without `--probe`. |
| FN-03 | insufficient | The direct tests pass, but an outcome the contract states (return 1 with "unmapped" or "mismatch" lines) is never exercised. |

### FN `014845a67471fce4` (`capstone.evaluation.auto_label:main`)

| Question | Answer | Why |
|---|---|---|
| FN-01 | false | There is no docstring and no variable block, so the stated rule applies: false, contract unspecified. |
| FN-02 | uncovered | The one test asserts the happy path only: one undetermined conclusion, `--hand` given, full agreement. The branch without `--hand`, the disagreement lines and the review flag are never asserted. |
| FN-03 | insufficient | There is no contract and one happy-path test with a fake client, and the comparison and reporting branches are untested. |

### TS `000105d208db21de` (`tests/test_state.py::test_bearing_health_outside_unit_interval_is_rejected_on_assignment`)

| Question | Answer | Why |
|---|---|---|
| TS-01 | true | For `bad` in (-0.01, 1.01), now shown under `decorators`, the test asserts that the assignment raises `ValidationError` and that the value stays 1.0. That is the claim. No project function is listed as exercised, because the bound is declared on the `MachineCondition` model, which the 1.1.0 rule counts as project code. |
| TS-02 | true | Removing the bound, turning off assignment validation, or loosening `le` past 1.01 makes the assignment succeed, so `pytest.raises` fails. |
| TS-03 | 3 | It asserts a specific exception type and that the state was not changed: the whole relevant outcome. |

### TS `000a7e2d5a39a74a` (`tests/test_failure.py::test_same_seed_fails_at_the_same_tick`)

| Question | Answer | Why |
|---|---|---|
| TS-01 | true | `module_helpers` now shows `degrading` (a 1,200-tick bearing-degradation run) and `stops` (every `status` event). Equal lists for seed 42 twice establish the same failure tick. The `[0]` index guarantees the lists are not empty, and the different first tick for seed 7 shows the seed matters. |
| TS-02 | true | Unseeded randomness in degradation or sensors would change the stop ticks between the two seed-42 runs. A failure tick that ignored the seed would break the inequality. |
| TS-03 | 3 | It compares the full list of status events, the whole outcome, and a specific field across seeds. |

### BT `124952c4943081f1` (master-tot13-anchored vs master-tot13-blind)

| Question | Answer | Why |
|---|---|---|
| BT-01 | valid | Both batches share the commit (`e59208d`), the case hash (13 cases, all paired by scenario and seed), the label sources, and identical saved settings except `CRITIC_BLIND`, which is the treatment. Which model answered and the outages are outcomes, not configuration. |
| BT-02 | insufficient_sample | There is one run per case, with 11 matched judged cases (below 13), and outages fell on different cases in each batch. `sample_rule_in_code.rule` agrees. Right on matched cases is 3 vs 3 in any case. |
