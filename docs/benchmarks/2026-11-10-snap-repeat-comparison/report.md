# Full-project evaluation

Commit pinned `0b089d83065eaa0eea8cb0928d895e75ba6994a7`, checked out `0b089d83065eaa0eea8cb0928d895e75ba6994a7`; uncommitted tracked changes: False. Rubric 1.1.1, packet schema 1.4.0, normalize 1.1.0. There is no single blended score.

## Scope

Files by class: {'excluded': 5, 'inventoried': 100, 'no_functions': 23, 'test_support': 2, 'tests': 123}. Unexplained: none. Stale: none.

## Correctness (deterministic)

| Namespace | Run | Correct / judged (evals) | Pending review | Reasoned correct / judged | Abstained | Confident wrong | False interventions |
|---|---|---|---|---|---|---|---|
| audited-tot13-blind | master-audited-20261102-tot13-blind | 3/5 | 0 | 3/5 | 1/5 | 0/5 | 0/5 |
| pair-01 | baseline | 0/0 | 0 | 0/0 | 0/0 | 0/0 | 0/9 |
| pair-01 | treatment | 0/0 | 0 | 0/0 | 0/0 | 0/0 | 0/12 |
| tot13-20261031-184429-543214a2 | master-tot13-anchored | 3/12 | 1 | 3/8 | 3/8 | 2/8 | 0/9 |
| tot13-20261031-184429-543214a2 | master-tot13-blind | 3/12 | 1 | 3/9 | 5/9 | 1/9 | 0/10 |
| tot13-20261031-210256-3910997b | master-tot13-anchored | 6/13 | 0 | 6/9 | 2/9 | 1/9 | 0/9 |
| tot13-20261031-210256-3910997b | master-tot13-blind | 6/11 | 2 | 6/11 | 3/11 | 1/11 | 0/13 |

Functions by verification status (976): {'INSUFFICIENT EVIDENCE': 408, 'NOT APPLICABLE': 25, 'NOT TESTED': 14, 'PARTIALLY VERIFIED': 484, 'VERIFIED': 45}.

## Comparisons (BT-02 sample rule, in code)

- `BT::pair-01::baseline__vs__treatment`: 10 cases paired by scenario and seed (0 only in A, 3 only in B, 0 ambiguous, 0 case numbers naming different cases); 0 judged in both; right on those A 0, B 0; rule: **insufficient_sample**.
- `BT::tot13-20261031-184429-543214a2::master-tot13-anchored__vs__master-tot13-blind`: 13 cases paired by scenario and seed (0 only in A, 0 only in B, 0 ambiguous, 0 case numbers naming different cases); 11 judged in both; right on those A 3, B 3; rule: **insufficient_sample**.
- `BT::tot13-20261031-210256-3910997b::master-tot13-anchored__vs__master-tot13-blind`: 13 cases paired by scenario and seed (0 only in A, 0 only in B, 0 ambiguous, 0 case numbers naming different cases); 11 judged in both; right on those A 6, B 6; rule: **insufficient_sample**.

## Evidence

28/80 episodes have a full trace; 52 are record-only (their trace questions are unknown, not failed).

## Reliability

Episodes where no model answered: 13/80. Ends: {'diagnosis_supported': 1, 'evidence_sufficient': 23, 'max_tool_calls': 3, 'model_unavailable': 13, 'no_useful_action': 14, 'timeout': 26}.

## Judging and missingness

9726 ledger rows by status: {'answered': 8126, 'not_applicable': 258, 'unknown': 1342}.

| Family | Statuses |
|---|---|
| BT | {'answered': 6} |
| FN | {'answered': 1853, 'not_applicable': 75, 'unknown': 1000} |
| RUN | {'answered': 449, 'not_applicable': 183, 'unknown': 328} |
| TL | {'answered': 40, 'unknown': 14} |
| TS | {'answered': 5778} |

Per-item findings: 3003 in `report.json`; independent reference items: 10; judge/reference disagreements: 17.
Evidence-grounded decisions: 3/5 eligible; misleading successes: 0/5 eligible. Missing trace or answers remain unknown.

Requests planned: 2965; estimated input cost $0.4026.

- snap: key `SUBQ_API_KEY` set; live contract verified.

## Live send budget

New requests sent: 2965; cumulative settled or reserved charge: $0.287996; stop: complete.
