# Accuracy eval — 2026-10-30

Execution accuracy on `evals/datasets/accuracy.jsonl`: the agent's rows must equal the gold
rows run as the same persona under Deep Data Security (row order, column order and names ignored).

| Config | Model | Digest | Accuracy | Simple | Join | Aggregate | Time | Errors | p50 (s) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| A | qwen3:8b | `500a1f067a9f` | **96.7%** | 100% | 96% | 97% | 93% | 0% | 21.4 | 1.09 |

## By persona

| Config | Model | employee | finance_analyst | hr_admin | manager |
|---|---|---|---|---|---|
| A | qwen3:8b | 100% | 93% | 93% | 100% |

## Misses: config A, qwen3:8b (4)

- `fj03` Which department's employees have the highest total expense amount? Give the department name. — rows differ
- `ft02` What was the total expense amount in each month of 2026? Show the month number (1-12) and the total. — rows differ
- `ha05` How many direct reports does each manager have? Show the manager's email and the count. — rows differ
- `ht07` In which month of 2026 was my total expense amount highest? Give the month number (1-12). — rows differ
