# Independent reference review

The developer reviews a blinded sample **before** SNAP answers it. Use a new
`full_evaluation` dry-run folder with no `*.answers.json` files:

```sh
cd evaluation
uv run python -m evaltools.reference_review export \
  --requests full-eval/<new-cohort>/requests \
  --out reference/<new-cohort>-review
```

Open only `reference/<new-cohort>-review/blinded/*.json`. Each file has an opaque
`review_id`, the same judge-visible state SNAP will receive, and question
criteria. Do not open `private_mapping.json`, truth-side packets, existing SNAP
answers or paired-arm scores while deciding. The default sample is eight RUN,
eight function, eight test, five tool and two batch items; full-trace RUN items
come first. Adjust `--run`, `--function`, `--test`, `--tool` and `--batch` to
enlarge it, then freeze the exported folder. Check the sample includes both
sound and deliberately broken evidence; a hash sample alone does not ensure
that diversity.

Write `answers.json` as `{ "review_id": { "RUN-01": 3, "RUN-12": true } }`.
Scores are integer rubric levels, choices are the exact named options, and
`noul` answers are true or false. Skipping a question means leaving its key
out, not giving it zero. Import the reviewed answers:

```sh
uv run python -m evaltools.reference_review import \
  --review-dir reference/<new-cohort>-review \
  --answers reference/<new-cohort>-answers.json \
  --out reference/<new-cohort>-reference.json
```

The import validates the answers and maps opaque IDs to private evaluator IDs.
Freeze and hash the answers before sending SNAP requests. Pass the imported
file to `full_evaluation --reference` for per-item agreement and disagreement.
The separate `compare_evaluators` command reports agreement by question;
neither agreement nor two models' consensus establishes correctness without
this independent review. Keep the private mapping and imported reference away
from judge request bodies.
