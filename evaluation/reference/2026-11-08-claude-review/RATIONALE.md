# Why each answer

Reviewer: Claude (Claude Code), at the developer's request; the developer has not checked these. One row per answer in `answers.json`. Evidence ids (E1, E2, ...) and hypothesis ids refer to the blinded packet of the same review id. Source lines for the FN, TS and TL items are from commit `ffd8349`.

## Agent investigations (RUN)

### RUN `230bb91f581d295e` (vibration alarm on CNC-02; escalated, committed at 0.92)

| Question | Answer | Why |
|---|---|---|
| RUN-01 | 3 | E3, E7, E16, E17 show the symptom; the wait and re-read (E7, E16) separate it from a transient and the peer reads (E5, E11 to E14) from a line-wide cause. Not 4: load, temperature, settings and maintenance were never read, so operating causes the retrieved manual names (speed change, heavier load, sensor disturbance) were not separated, and the "bearing or axis-drive wear" part rests on the stated assumption that wear need not raise power. |
| RUN-02 | 4 | Three distinct hypotheses (transient H1, CNC-02 equipment H2, line-wide H3); readings aimed at each; decision confidences rose 0.55 to 0.95 as each peer read came back normal and the re-reads stayed high; a no-change hypothesis (transient) was held and tested. Weakness noted but outside this rubric: no setting, load or sensor hypothesis was ever listed. |
| RUN-03 | ineffective | The critic named a real gap (no temperature or load data to rule out operating changes) but its discriminating check was a redundant CNC-02 vibration trend (E17). The gap was never followed up and the conclusion does not reflect it. Its second objection (CNC-08's drop) has no substance: CNC-08 went idle after job 7 finished (E10). |
| RUN-04 | unnecessary | E2 (sections 1.2, 2.1, 2.4) is cited by no hypothesis, decision or conclusion. The investigation reads the same without it, and the conclusion goes against its "do not diagnose a bearing by vibration alone". |
| RUN-05 | not_applicable | Recommendation escalate, proposal null, verification empty. |
| RUN-06 | inappropriate | It named a cause ("developing equipment problem ... bearing or axis-drive wear") at 0.92 while operating-condition rivals were untested and its own unresolved list says bearing vs servo drive is open. Escalate was not the agent's choice: the final check lowered the policy's intervene because the investigation was unresolved (recommendation_lowered). |
| RUN-07 | reasoning | The earliest failure is at decision 18: the agent declared "nothing further is needed" with only vibration and power read, and read persistence plus normal peers as confirming equipment wear. No tool error or budget limit stopped those reads. |
| RUN-08 | 2 | The CNC-02-specific, non-transient elevation is shown. But "sustained vibration above the 4.50 mm/s alarm setpoint" overstates readings whose means are 4.35 to 4.42 (only peaks cross 4.50), "developing" is not shown (flat 26-tick trend, no pre-alarm history), and the conclusion lists open questions (bearing vs drive, E17 unverified). Confidence 0.92 is not proportionate. |
| RUN-11 | used | The follow-up was made where the critic pointed (E17). H2 stayed at 0.95 and E17 (bucket means 4.375, 4.39, 4.407) is consistent with it. The conclusion cites E17, and its 4.633 maximum and 4.38 to 4.41 means match E17's buckets. |
| RUN-12 | false | E14 shows CNC-08 at mean 1.32 and minimum 0.0, not "roughly 1.7-2.6 mm/s". E3, E7, E16 and E17 show means below 4.50, not "sustained vibration above the 4.50 mm/s alarm setpoint". |

### RUN `c552284a9d4329d3` (vibration alarm on CNC-05; escalated, H2 sensor bias or H3 normal band)

| Question | Answer | Why |
|---|---|---|
| RUN-01 | 3 | Thorough observable base: CNC-05 load, temperature, power, following error (E6 to E9, E17), events (E10), settings (E14), all peers (E5, E11 to E13), a re-read after waiting (E16). Not 4: the one history read meant to separate a long-standing band from a recent rise (E18, ticks 800 to 816) shows a climb from 3.61 to about 4.2 after job 9 started at 802, and it was read as the opposite. The slow-onset mechanical alternative (C2) was set aside on flat power alone. |
| RUN-02 | 3 | Distinct hypotheses (transient, sensor bias, normal band, plus pruned mechanical C2 and local disturbance C5), discriminating reads, and confidences that mostly track the evidence. Not 4: the test-phase read E18 was left "uninterpreted" and never moved any confidence although it bears on H3 vs a rising fault. The final ranking (H1 0.72 highest) also does not match the conclusion, which names H2 or H3. |
| RUN-03 | ineffective | The critic's check asked for ticks 840 to 900 at tick 840, so E19 holds one sample and can say nothing about a trend. It did not raise the untested slow-onset alternative or the E18 rise. Its H3 objection (CNC-03 lower at a higher speed) does not bear on a machine-specific band. |
| RUN-04 | useful | E2 is not cited by id, but the plan visibly follows it: temperature, load and factory air temperature over the same window (section 1.2), settings, events and nearby stations (2.1), instrument issues as a cause (H2), and the next check "independent reference measurement ... or maintenance inspection" (2.1, physical inspection when telemetry cannot separate mechanical vibration from sensor movement). The reasoning is consistent with that content. Borderline: the rubric's "useful" names citation, and no hypothesis cites E2 by id. |
| RUN-05 | not_applicable | Escalate, no proposal. |
| RUN-06 | appropriate | It declined to choose between H2 and H3, which the evidence (no independent measurement) cannot separate, and escalated at 0.75. |
| RUN-07 | reasoning | Readings in hand were misread: E18 was taken to show the ~4.04 mm/s level predates job 9 when 15 of its 17 samples are from job 9 and the two pre-job samples (3.61, 3.76) are lower. Flat power was taken to exclude any mechanical fault. The later timeout came after the agent had already stopped investigating (decision 19). |
| RUN-08 | 2 | The narrowing to H2 or H3 is mostly supported. But "the elevated vibration predates job 9 ... so it is not job-specific" is not supported, and the conclusion's own open question asks exactly that. "Isolated threshold crossings at ticks 826 and 828" omits E16's further crossings at 836, 837 and 839. Two listed open questions (power at 816 to 830 and 830 to 840) were already answered by E8 and E17. |
| RUN-11 | used | The follow-up was made where the critic pointed. Its single sample (4.425 at tick 840) is consistent with the stable band and H1 stayed at 0.72, a sensible non-response to an uninformative reading. The check's flaw is the critic's (RUN-03), not the investigator's. Borderline with no_feedback. |
| RUN-12 | false | E18 (with E10's job 9 start at tick 802) does not show that the elevation "predates job 9" at a 4.04 mean; that mean is mostly job 9 data. The other cited figures check out (load mean 68.96, temperature mean 147.19, following error mean 4.96, peer means 1.00, 2.06, 1.05, 1.80, power about 12.45 at both alarm ticks). |

### RUN `26b1f92dbf2b1844` (3 of 4 jobs failed inspection; escalated unresolved at 0.4)

| Question | Answer | Why |
|---|---|---|
| RUN-01 | 2 | The symptom and routes are shown (E9, E10, E12 to E14), and E19 and E18 discriminate CNC-05's following error and CNC-02's baseline. But the conclusion dismisses a CNC-04 fault on clean vibration (E15), which the retrieved manual (section 2.14) says a worn feed-axis drive leaves unchanged. Following error was read on CNC-05 only, though every job passes all five stations, so a drive fault elsewhere was never examined. |
| RUN-02 | 2 | Distinct hypotheses (CNC-04, material or inspection, multiple causes, CNC-05, CNC-02 baseline) with some discriminating reads. But H1 was dropped to 0.05 on non-discriminating vibration, H2 rose to 0.7 with no positive evidence (only the absence of vibration anomalies), and the test phase made no readings at all (hypothesize "invalid_decision", test "an answer before the time ran out"). A literal reading of the test-phase criterion would give 1. |
| RUN-03 | unknown | The critique outcome is invalid_reply. |
| RUN-04 | misleading | H2 ("material or inspection variation; CNCs not implicated") cites E2, but E2 does not support "CNCs not implicated". Section 2.9 says to judge a batch against other batches (only batch 1 exists here) and to "also consider machine or inspection causes". Section 2.14 says normal vibration is the drive-fault signature. The retrieval had the needed guidance and was cited for the opposite. |
| RUN-05 | not_applicable | Escalate, no proposal. |
| RUN-06 | appropriate | With one batch and every job routed through every station, the evidence leaves several causes open. It declined (committed false, 0.4) and escalated. |
| RUN-07 | reasoning | At decision 21 the agent stopped ("No further checks are needed") after reading clean vibration as excluding machine faults and following error on one station only. The hypothesize and test failures and the timeout came after that choice. The critic's invalid reply removed a safeguard but was not the earliest cause. |
| RUN-08 | 2 | "Unresolved" is supported, as are the CNC-02 baseline (E18) and the CNC-05 following-error comparison (E19). But "a CNC-04 fault (H1) is contradicted by clean CNC-04 vibration (E15)" does not follow, and "all occur immediately after CNC-05 processing" is equally true of the passing job 3. |
| RUN-11 | no_feedback | The critic gave an invalid reply and the recheck was skipped ("the critic gave no usable answer"). |
| RUN-12 | true | Every cited item contains what is attributed: failures right after CNC-05 (E10, E12, E13), CNC-02 means of about 1.8 to 2.4 from tick 60 (E18), comparable recent vibration (E7, E11, E15 to E17), and the job-window following-error means and maxima (E19, approximate but present). The faulty step is the inference drawn from E15, not its content. |

## Tool, functions, tests and the batch comparison

### TL `1260f9b4e44f1ac3` (tool `get_maintenance_history`)

| Question | Answer | Why |
|---|---|---|
| TL-01 | true | It reads only past service records (machine, date, kind, note) and this run's `maintenance` events. `run_tool` rebuilds every row through `MaintenanceObservation` (`extra="forbid"`), an unknown machine is refused with a message naming only the caller's own id, other exceptions become "Tool execution failed.", and the tool changes nothing. The "finished" notes describe a removed part in words ("old bearing ..."), which is the designed technician finding the manual (section 2.14) calls direct evidence, not a raw hidden value. |
| TL-02 | true | The description matches the behaviour: one machine or all, oldest first (past records are sorted by date, then this run's events in tick order), past rows with a date and tick null, run rows with their tick, "what a technician did and wrote, not a cause". The shared 300-row cap is not mentioned, but this tool cannot plausibly reach it (one to four past records per machine). |
| TL-03 | 0 | A direct projection of stored records. The only filter is an exact machine match after the machine is checked to exist, with no window, unit or ordering step that could drop or distort rows. The stale-record hazard does return a wrong row with nothing marking it, but it is a designed degradation pinned by `test_hazards.py`, and this question asks for undesigned ones. Counting the designed hazard would give 3. |

### FN `012cf733fced8b7d` (`capstone.ingestion.channel_map:main`)

| Question | Answer | Why |
|---|---|---|
| FN-01 | false | The stated contract (docstring and `outcome` in the variable block) names results 0 and 1 only. The function also returns 2 when `--probe` does not match the map, and exits through `parser.error` when the output or map is inside the checkout without `--allow-inside-repo`. A calling script needs to know both. Borderline: the CLI help texts mention both refusals. |
| FN-02 | partly | Asserted: build and check happy paths, the probe-mismatch return 2, and the inside-repo refusal for `build`. Not reached: the non-clean result 1 (unmapped or mismatched lines), the inside-repo refusal for `check --update-reported`, and `check` without `--probe`. Statement coverage of 0.935 agrees. |
| FN-03 | insufficient | Direct passing tests exist, but the contract's own stated non-clean outcome (return 1 with "unmapped" or "mismatch" lines) is never exercised. |

### FN `014845a67471fce4` (`capstone.evaluation.auto_label:main`)

| Question | Answer | Why |
|---|---|---|
| FN-01 | false | No docstring and no variable block, so the rubric's rule applies: false, contract unspecified. Only the argparse description says what it does. |
| FN-02 | uncovered | The function has no raise or except of its own. Its one test asserts the happy path only (one undetermined conclusion, `--hand` given, full agreement). The no-`--hand` branch, the disagreement lines and the review flag are never asserted. |
| FN-03 | insufficient | No contract, one happy-path test with a fake client, and the comparison and reporting branches untested. |

### TS `000105d208db21de` (`tests/test_state.py::test_bearing_health_outside_unit_interval_is_rejected_on_assignment`)

| Question | Answer | Why |
|---|---|---|
| TS-01 | true | For `bad` in (-0.01, 1.01) (parametrize line, not in the packet), it asserts that the assignment raises `ValidationError` and that the value stays 1.0. That is the claim. The packet flags `exercises_no_project_function` because the bound lives in the declarative `MachineCondition` model (`Field(ge=0.0, le=1.0)`, `validate_assignment=True`), not in a function coverage can see. The TS-01 missing-evidence rule ("no exercised project function: unknown") would leave this unanswered; I answered on the code. |
| TS-02 | true | Removing the bound, turning off assignment validation, or loosening `le` past 1.01 makes the assignment succeed, so `pytest.raises` fails. |
| TS-03 | 3 | A specific exception type plus a check that the state was not changed: the whole relevant outcome. |

### TS `000a7e2d5a39a74a` (`tests/test_failure.py::test_same_seed_fails_at_the_same_tick`)

| Question | Answer | Why |
|---|---|---|
| TS-01 | true | `stops` (module helper, not shown in the packet, which lists `helpers_used: []`) returns every `status` event from a 1,200-tick bearing-degradation run. Equal lists for seed 42 twice establish the same failure tick. The `[0]` index in the second assertion guarantees the lists are not empty, and the different first tick for seeds 42 and 7 shows the seed matters. |
| TS-02 | true | Unseeded randomness or global state in degradation or sensors would change the stop ticks between the two seed-42 runs. A failure tick that ignored the seed would break the inequality. |
| TS-03 | 3 | Compares the full list of status events (whole outcome) and a specific field across seeds. |

### BT `124952c4943081f1` (master-tot13-anchored vs master-tot13-blind)

| Question | Answer | Why |
|---|---|---|
| BT-01 | valid | Same commit (`e59208d`), same `cases_sha256` (13 cases, all 13 paired by scenario and seed), same label sources, and identical saved settings except `CRITIC_BLIND` (false vs true), which is the treatment. Nothing suggests a resumed mixed-configuration run. Outages fell on different cases in each arm, which is a sample problem for BT-02, not a configuration difference. |
| BT-02 | insufficient_sample | One run per case at sampling temperature 1.0, only 11 matched judged cases (one pending review on each side), and outages removed different cases from each side (4 in A, 3 in B). Right on matched cases is 3 vs 3 in any case. The code's sample rule gives the same answer. |
