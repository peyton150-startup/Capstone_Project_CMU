# Machine manual RAG: design note

The developer's design for giving the agent searchable equipment knowledge,
written on 2026-10-22 and built in the same PR as the `search_manual` tool.
This note is developer documentation: it is **not** indexed for the agent.

## What and why

Factories keep a maintenance manual for each machine model. The agent now has
one too: `capstone-code/capstone/manual/sim-cnc-001.md` (SIM-CNC-001, revision
1.1), written about the machine type and never from a run. It lists far more
causes than the simulator produces, so retrieving a section never gives the
answer: the agent must still gather the factory's own evidence.

Decisions made by the developer on 2026-10-22:

- **Option B:** the manual gives no station speeds or job times (the settings
  tool shows only current speeds, on purpose), so a wrong setting must be found
  from its effects; §2.7 describes that method.
- Stored as Markdown in the repository, not a PDF, so every edit is a reviewed
  diff; only the numbered sections (§1.1 to §2.13) are indexed.
- No system-prompt line: the tool's description and the evidence label carry
  the guidance, so runs without the manual are unchanged.
- A leak check refuses any section naming a fault's internal name, a seed, a
  case ID or "ground truth".
- Measure with and without the manual on tuning seeds first; keep the held-out
  seeds for final numbers.

## How it works

1. `capstone.manual.sections`: `load_manual()` splits the Markdown at "## §"
   headings into `ManualSection` (number, title, text, revision) and runs
   `check_no_leaks`.
2. `capstone.manual.index`: `ChromaManualIndex` searches by meaning in its own
   Chroma collection (`MANUAL_COLLECTION`, default `cnc_machine_manual_v1`),
   never the memory collection; `KeywordManualSearch` ranks by shared words and
   needs no service. Build once: `python -m capstone.manual.index --rebuild`.
3. `capstone.providers.manual`: `ManualProvider` answers `search_manual(text,
   limit)` with sections (number, title, text, document), source "manual", at
   most 3 searches, repeats refused; every other tool passes through.
4. The loop labels manual evidence `origin="manual"`; every prompt marks it
   "FROM THE MANUAL: general guidance for this machine model, not a look at the
   factory now". It cannot verify a fix (only observable evidence counts), and
   the memory gate refuses a lesson that cites only the manual
   (`rests_on_manual`).
5. Experiments: the manual is offered by default, searched by meaning
   (since 2026-10-29); `--manual keyword` searches by shared words and
   `--no-manual` runs without it, in `capstone.experiment run` and
   `capstone.evals` alike; each record keeps `manual_searches` (query, outcome,
   sections) and the report adds a "manual:" line.

## Keeping the index in step with the manual (2026-10-29)

**Rule (developer, 2026-10-29): when the manual changes, the index must be
rebuilt before the next run.** It is now automatic. Each indexed section
carries a fingerprint of its title, text and revision (`section_digest`).
Before every semantic run, `open_manual` calls `ready_manual_index`, which
rebuilds the index first and prints why if:
- it is empty (a new machine),
- any section's fingerprint differs, or a section was added or removed (the
  manual was edited), or
- it was built by another embedding model (`EMBEDDING_MODEL` changed).

Otherwise the built index is reused: the manual's vectors do not change
between runs, so nothing is embedded again except each search's own words.
`python -m capstone.manual.index --rebuild` still rebuilds by hand. An index
built before fingerprints were kept is rebuilt once, on its next run.

## Evaluating it

Run the same tuning cases with and without `--manual`, same model, prompts,
seeds and budgets, and compare root-cause accuracy, unnecessary interventions,
evidence collected, model and tool calls, and time. Then check retrieval:
whether the agent searched, which sections it was given, and whether it chased
a distractor section (lubrication, alignment, coolant, tool wear, ambient air).
