# Full-project evaluation

Commit pinned `0ca0b1689ea8ff0fc66cc7ed09f686a133a9652c`, checked out `0ca0b1689ea8ff0fc66cc7ed09f686a133a9652c`; uncommitted tracked changes: False. Rubric 1.0.0, packet schema 1.3.0, normalize 1.1.0. There is no single blended score.

## Scope

Files by class: {'excluded': 4, 'inventoried': 81, 'no_functions': 23, 'test_support': 2, 'tests': 91}. Unexplained: none. Stale: none.

## Correctness (deterministic)

| Namespace | Run | Correct / judged (evals) | Pending review | Reasoned correct / judged | Abstained | Confident wrong | False interventions |
|---|---|---|---|---|---|---|---|
| audited-tot13-blind | master-audited-20261102-tot13-blind | 3/5 | 0 | 3/5 | 1/5 | 0/5 | 0/5 |
| tot13-20261031-184429-543214a2 | master-tot13-anchored | 3/12 | 1 | 3/8 | 3/8 | 2/8 | 0/9 |
| tot13-20261031-184429-543214a2 | master-tot13-blind | 3/12 | 1 | 3/9 | 5/9 | 1/9 | 0/10 |
| tot13-20261031-210256-3910997b | master-tot13-anchored | 6/13 | 0 | 6/9 | 2/9 | 1/9 | 0/9 |
| tot13-20261031-210256-3910997b | master-tot13-blind | 6/11 | 2 | 6/11 | 3/11 | 1/11 | 0/13 |

Functions by verification status (773): {'INSUFFICIENT EVIDENCE': 296, 'NOT APPLICABLE': 24, 'NOT TESTED': 36, 'PARTIALLY VERIFIED': 372, 'VERIFIED': 45}.

## Comparisons (BT-02 sample rule, in code)

- `BT::tot13-20261031-184429-543214a2::master-tot13-anchored__vs__master-tot13-blind`: 13 cases paired by scenario and seed (0 only in A, 0 only in B, 0 ambiguous, 0 case numbers naming different cases); 11 judged in both; right on those A 3, B 3; rule: **insufficient_sample**.
- `BT::tot13-20261031-210256-3910997b::master-tot13-anchored__vs__master-tot13-blind`: 13 cases paired by scenario and seed (0 only in A, 0 only in B, 0 ambiguous, 0 case numbers naming different cases); 11 judged in both; right on those A 6, B 6; rule: **insufficient_sample**.

## Evidence

5/57 episodes have a full trace; 52 are record-only (their trace questions are unknown, not failed).

## Reliability

Episodes where no model answered: 11/57. Ends: {'diagnosis_supported': 1, 'evidence_sufficient': 14, 'max_tool_calls': 3, 'model_unavailable': 11, 'no_useful_action': 8, 'timeout': 20}.

## Judging and missingness

7504 ledger rows by status: {'answered': 6564, 'not_applicable': 214, 'unknown': 726}.

| Family | Statuses |
|---|---|
| BT | {'answered': 4} |
| FN | {'answered': 1849, 'not_applicable': 72, 'unknown': 398} |
| RUN | {'answered': 214, 'not_applicable': 142, 'unknown': 328} |
| TL | {'answered': 51} |
| TS | {'answered': 4446} |

Requests planned: 2296; estimated input cost $0.4301.

- snap: key `SUBQ_API_KEY` set; live contract verified.

## Live send budget

New requests sent: 2276; cumulative settled or reserved charge: $0.310979; stop: complete.
