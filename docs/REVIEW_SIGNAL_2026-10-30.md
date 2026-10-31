# Review signal: ToT code review and four machining videos (2026-10-30)

**Status:** PLANNED / FUTURE WORK ONLY, except where an item is marked ✅ IMPLEMENTED. *Audit 2026-10-31 against `main` at `af3b7bf`.* Item 1 is built, item 2 is partly built, items 3 to 7 are not built.
**Gate:** Same as [TOT_CRITIC_EVALUATION_FUTURE_WORK.md](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#scheduling-gate-protect-the-runs-in-progress): finish and score the current baseline runs first.

This page keeps only the **verified signal** from four outside reviews (one code review, three video reviews) and one extra video. Each claim was checked against `main` or against frames of the uploaded file. Claims that were already done, overstated or unsupported are listed at the end so they are not re-proposed.

## Sources checked

| Source | What it actually is | Verified how | Usable? |
|---|---|---|---|
| ToT code review (CMU Module 4.1) | Review of `agent/tree_of_thought.py` | Read against `main` | Yes |
| Video A: *Prevent a Spindle Crash on Your Haas Mill!* (5:04) | Haas NGC control, zero tool-length-offset macro | Frames at ~4:00 | Yes |
| Video B: *Haas VF3 spindle failure* (12:16) | Shop vlog on one VF-3 spindle failure; bearing shown | Frames across the file | Limited. The review written for it described a different video (a 3:55 Haas service video with Bijur pump and sight-glass checks). None of those scenes are in this file. |
| Video C: Swiss-type lathe install vlog (9:07) | Tornos-style sliding-headstock lathe, bar feeder, delivery and setup | Frames across the file | Low. Different machine class from the Haas VF mill reference. |

Frames were sampled; audio was not transcribed. Narration-only claims are therefore unverified.

## Signal, in priority order

## Code vs. model: the rule used here

Anything that can be checked exactly from data (thresholds, required fields, citation validity, time budgets, configuration limits, which model answers which job) is **code**. Anything that needs judgment over messy evidence (proposing causes, rating them, choosing the next check, writing the diagnosis) is the **model**. The model never decides whether a safety rule applies, and code never invents a cause.

| Item | Code | Model |
|---|---|---|
| 1. P0 | Neutral score for unproven `impossible`; ranking; hypothesis confidence | Unchanged: still gives verdict and confidence |
| 2. Runtime | Job routing, timeouts, new `value` job | None |
| 3. Safety rules | Detect and block | None |
| 4. Offsets / pockets | Simulator state, read tool, block | Explain and connect to other evidence |
| 5. Technician check | Record request, return `unverified`, no evidence id | Choose which check |
| 6. P5 | Whether to run the pass (ambiguity, time left), pruning | Re-rate kept candidates with new evidence |
| 7. Machine profiles | Versioned profile data | Uses the profile through retrieval |

### 1. P0 confidence bug (already logged) — ✅ IMPLEMENTED (PR #136)

**✅ IMPLEMENTED.** `unproven_confidence()`, `prune()` and `Thought.unresolved` in `agent/tree_of_thought.py`; tests in `tests/test_tree_of_thought.py`. Nothing left to do.

See [P0](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#p0--unproven-impossible-ratings-must-not-become-confident-hypotheses). An `impossible` rating with no cited contradiction keeps its raw confidence, so a 0.95 can become H1 and pass `min_diagnosis_confidence` and `min_action_confidence` (both 0.9). Small, deterministic fix; no extra model calls. **Highest priority after the baseline.**

### 2. Runtime: model routing and per-call timeouts — 🟡 PARTLY IMPLEMENTED

**✅ IMPLEMENTED:** `DECIDE_MODEL` and `MODEL_QUESTION_SECONDS` (configuration only). **❌ NOT BUILT:** the `value` job: `TreeOfThoughtPolicy.hypothesize()` still sends the rating question to the `hypothesize` client, and `JOBS` has no `value`.

**Evidence:** `docs/benchmarks/2026-10-27-master-resumed.records.jsonl` (KA-06-setting) made 22 sequential model questions; single answers took about 4 s to 113 s on the primary model; 5 attempts timed out; the case ended `timeout` at about 881 s wall time. The fallback model answered narrow jobs in about 4 to 5 s.

**Experiment:** Send narrow jobs to the faster model and tighten per-call timeouts so failover happens sooner.

- `decide`: configuration only. Set `DECIDE_MODEL` (job table in `providers/chat.py`, `JOBS` / `_JOB_SETTING`).
- Per-call timeout: configuration only. `MODEL_QUESTION_SECONDS` (`settings.model_question_seconds`, default 90 s, passed as `FallbackClient(max_seconds=...)` in `clients_for_jobs()`).
- ToT `value`: **needs a code change.** Both ToT questions go to the `hypothesize` client by design, so `HYPOTHESIZE_MODEL` would move `generate` too. Touch points: add `"value"` to `JOBS` and `_JOB_SETTING` (`providers/chat.py`); add `value_model = _optional("VALUE_MODEL")` to `Settings` and to the blank-is-missing validator list (`settings.py`); give `value` an entry in the per-job system-prompt table in `agent/model_policy.py` or confirm `_ask(..., system=VALUE)` never reads it; change the rating call in `TreeOfThoughtPolicy.hypothesize()` to `self._ask("value", ...)` and update its docstring (it currently says both questions use `hypothesize`); give `tests/test_tree_of_thought.py` a `value` fake client. With `VALUE_MODEL` unset it falls back to `DEFAULT_MODEL`, so default behavior is unchanged. Leave `generate` on `hypothesize`, since it needs the stronger model. Measure p50/p95 wall time, `timeout` terminations and accuracy against the frozen baseline. This is the lever for speed, not more agents (see [Not planned: a third agent](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#not-planned-a-third-agent-for-speed)).

### 3. Deterministic safety rules stay out of the model — ❌ NOT BUILT

`why_not_acted()` still checks only: an action is named, evidence is cited, confidence reaches the bar. (Only `propose_action()` refuses `repair_hydraulics` on a machine without hydraulics.)

**Evidence (Video A, ~4:00):** the control shows program `O09601 (M6 - ZERO OFFSET CHECK)`: `M16` tool change, `G04 P2` dwell, then `IF [#[#3026 + 2000] LT [1.]] THEN #[#3026 + 2000] = 99.` That is, after a tool change, if the active tool's length offset is under 1, set it to 99. The value 99 is the presenter's example, not a safe default.

**Principle:** A rule that code can check exactly (missing offset, tool not in pocket, setting out of range) is checked in code before or alongside model reasoning, never left for the LLM to notice. Same reasoning as P0.

**Where it belongs:** the action/approval step: `why_not_acted()` in `agent/investigation.py`, as a condition checked alongside "no evidence cited" and the `min_action_confidence` bar, as a hard block on recommending a run with unsafe or unknown configuration. It is a crash-**prevention** check, separate from the post-anomaly investigator and from ToT.

### 4. Tool offset and pocket state in the simulator — ❌ NOT BUILT

**Gap:** The simulator has no tool-length offset, tool table or pocket model. Existing configuration coverage is `wrong_setting` (spindle speed 18 to 20% off standard, `reset_setting`) read through `get_settings`, which today returns only `machine_id` and `speed_rpm`.

**Future scenarios (one per fault pack, evaluator-only truth):** zero or missing offset; offset assigned to the wrong tool; empty or mismatched pocket; configuration unavailable.

**Who does what:**

- **Code:** the simulator state and a read-only tool that returns the tool table; the item 3 rule that detects the unsafe or unknown configuration and blocks the action; an unknown value is returned as unknown, never filled in.
- **Model:** explain the finding in the diagnosis, connect it to other evidence (e.g. inspection rejects after a tool change), and choose what to check next. It never decides whether the block applies.

**Haas reference fields (Video A screen):** spindle speed, spindle power (kW), surface speed, chip load, spindle load %, X/Y/Z axis load %, active tool, offset, pocket, max load, next tool, Safe Run (F3). Visible on the NGC control; the video does not show which are exposed to an external Python interface. Fold into the [Haas VF retrofit](MVP_SCOPE.md#high-priority-future-work--retrofit-the-simulator-around-real-haas-vf-series-machines-2026-10-29) profile.

Haas Safe Run limits damage once a collision starts; it does not prevent one. Do not model it as prevention.

### 5. A "request technician check" tool — ❌ NOT BUILT

**Gap:** `sim-cnc-001.md` §2.2 and §2.3 already say a technician may verify bearing play, noise and lubrication state, but no tool lets the agent ask for that. Today the agent can only use sensor tools, so a physical check is either skipped or guessed.

**Experiment:** Add a read-only tool that records a requested physical check (oil level, sight glass, bearing play, tool seated) and returns `unverified` in the simulator unless the scenario supplies an answer. **Who does what:**

- **Model:** decide which physical check to ask for and when.
- **Code:** record the request and return `unverified` with **no evidence id**. The existing rules then do the enforcement: hypotheses citing ungathered evidence are refused (`agent/loop.py`, "a hypothesis cites evidence that was not gathered"), conclusions too (`agent/investigation.py`, "the conclusion cites evidence that was not gathered"), ToT `prune()` drops such candidates, and the critic's objections may cite only gathered ids. So an unverified physical condition cannot be cited as evidence. Add a test for that. Free-text wording in the diagnosis is not checked by code, so the evaluator still scores it.

Score whether the agent requests the right check (evaluator side) and whether a conclusion ever states an unverified physical condition as fact.

### 6. P5 second depth, gated by ambiguity (already logged) — ❌ NOT BUILT

See [P5](TOT_CRITIC_EVALUATION_FUTURE_WORK.md#p5--bounded-second-depth-through-observation-not-more-model-reasoning) and P3. Do after items 1 and 2 so the extra model call has room in the time budget. **Code** decides whether the pass runs (observable ambiguity from P3, time left before `followup_seconds`) and prunes the result; the **model** only re-rates the kept candidates.

### 7. Low priority: machine class and material feed — ❌ NOT BUILT (note only)

**Evidence (Video C):** a sliding-headstock lathe fed from a bar feeder, a different machine class from the Haas VF mill reference.

**Note only:** Keep machine-specific knowledge in versioned machine profiles rather than hard-coding mill assumptions into the agent. Bar-feed or material-supply stoppages are a possible later fault family next to `bad_material_batch`. No action before the Haas VF profile exists.

## Already done or noise (do not re-propose)

- **"Add configuration faults."** `wrong_setting` and `get_settings` exist. Only offsets and pockets are new (item 4).
- **"Test missing or unavailable data."** Covered by `false_alarm`, `SensorDropout` and `SensorDrift`.
- **"Add symptom-driven lubrication, overheating, vibration and stuck-tool procedures to RAG."** `sim-cnc-001.md` already has §2.1 Vibration, §2.2 Bearing, §2.3 Lubrication, §2.4 Alignment/Imbalance, §2.5 Temperature, §2.10 Tool Wear, each with causes and checks. What is missing is real Haas sources, which belongs to the retrofit.
- **The Video B review's timestamped table** (Bijur pump, sight-glass tubing, oil quantity, spindle balance, stuck tooling). Not shown in the uploaded file; treat as unverified.
- **"Expand from a mechanical investigator into machine health plus configuration."** Overstated; fault packs already include settings, material batches and false alarms.
- **A third agent to save time.** Rejected; adds sequential model calls. See item 2.
- **Full breadth-five, depth-three BFS from the course lab.** Not planned; P5 caps at depth two.
