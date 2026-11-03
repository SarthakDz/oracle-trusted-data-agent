# Accuracy eval — 2026-10-30, model lock (before the Day 3 fixes)

Execution accuracy on `evals/datasets/accuracy.jsonl`: the agent's rows must equal the gold
rows run as the same persona under Deep Data Security (row order, column order and names ignored).

| Config | Model | Digest | Accuracy | Simple | Join | Aggregate | Time | Errors | p50 (s) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| A | nemotron-3.5-bolt:e4b | `69f2be39b309` | **90.8%** | 91% | 79% | 97% | 96% | 2% | 6.6 | 1.06 |
| A | ornith-1.5:9b | `e5df7dcdd8a2` | **90.0%** | 94% | 86% | 94% | 86% | 2% | 34.2 | 1.15 |
| A | qwen3:8b | `500a1f067a9f` | **95.0%** | 94% | 93% | 100% | 93% | 0% | 22.8 | 1.02 |

## By persona

| Config | Model | employee | finance_analyst | hr_admin | manager |
|---|---|---|---|---|---|
| A | nemotron-3.5-bolt:e4b | 97% | 90% | 93% | 83% |
| A | ornith-1.5:9b | 90% | 93% | 87% | 90% |
| A | qwen3:8b | 90% | 100% | 100% | 90% |

## Misses: config A, nemotron-3.5-bolt:e4b (11)

- `ej02` Show the amount of each of my expenses together with my department code. — rows differ
- `ms01` List the emails of my direct reports. — rows differ
- `mj01` List the first and last names of my direct reports with their department name. — rows differ
- `mj03` Show the first name, last name and total expense amount of each of my direct reports. — rows differ
- `mj04` Which of my direct reports has the highest total expense amount? Give their first and last name. — ORA-03048: SQL reserved word '.' is not syntactically valid following '...FROM
- `mj05` List the amount of each travel expense of my direct reports with the submitter's job title. — rows differ
- `fs05` List the ids of all rejected travel expenses. — ORA-00904: "HR"."CATEGORY": invalid identifier
- `fj01` List the first and last names of the employees who submitted an expense over 74,800 INR. — ORA-03048: SQL reserved word '.' is not syntactically valid following '...FROM
- `ft04` What was the total amount of reimbursed expenses submitted on or after 2026-07-01? — rows differ
- `hs01` List the emails of all employees whose job title is Legal Counsel. — rows differ
- `ha05` How many direct reports does each manager have? Show the manager's email and the count. — rows differ

## Misses: config A, ornith-1.5:9b (12)

- `es02` What is my phone number? — rows differ
- `es08` What is my SSN? — rows differ
- `et07` In which month of 2026 was my total expense amount highest? Give the month number (1-12). — rows differ
- `mj02` For each of my direct reports' expenses still in submitted status, show the expense id and the subm… — rows differ
- `mj04` Which of my direct reports has the highest total expense amount? Give their first and last name. — rows differ
- `mt06` In which month of 2026 was the total amount of my direct reports' expenses highest? Give the month … — rows differ
- `fj03` Which department's employees have the highest total expense amount? Give the department name. — rows differ
- `ft03` Which month of 2026 had the most expenses by count? Give the month number (1-12). — rows differ
- `hj07` Show each department code with the total salary of its employees. — model returned no SQL
- `ha04` How many employees have each job title? Show the job title and the count. — rows differ
- `ha05` How many direct reports does each manager have? Show the manager's email and the count. — model returned no SQL
- `ht07` In which month of 2026 was my total expense amount highest? Give the month number (1-12). — rows differ

## Misses: config A, qwen3:8b (6)

- `es02` What is my phone number? — rows differ
- `es08` What is my SSN? — rows differ
- `et05` How many expenses did I submit in each month of 2026? Show the month number (1-12) and the count. — rows differ
- `mj06` How many expenses has each job title on my team submitted? Show the job title and the count. — rows differ
- `mj07` Show the department code and the number of my direct reports in it. — rows differ
- `mt04` How many expenses did my direct reports submit in each month of 2026? Show the month number (1-12) … — rows differ
