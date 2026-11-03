# Accuracy eval — 2026-10-29, ablation: no column notes (empty schema index)

Execution accuracy on `evals/datasets/accuracy.jsonl`: the agent's rows must equal the gold
rows run as the same persona under Deep Data Security (row order, column order and names ignored).

| Config | Model | Digest | Accuracy | Simple | Join | Aggregate | Time | Errors | p50 (s) | Attempts |
|---|---|---|---|---|---|---|---|---|---|---|
| A | nemotron-3.5-bolt:e4b | `69f2be39b309` | **88.3%** | 88% | 68% | 97% | 100% | 2% | 7.2 | 1.06 |
| A | ornith-1.5:9b | `e5df7dcdd8a2` | **86.7%** | 94% | 75% | 91% | 86% | 6% | 24.2 | 1.24 |
| A | qwen3:8b | `500a1f067a9f` | **90.0%** | 91% | 79% | 97% | 93% | 1% | 28.2 | 1.07 |

## By persona

| Config | Model | employee | finance_analyst | hr_admin | manager |
|---|---|---|---|---|---|
| A | nemotron-3.5-bolt:e4b | 87% | 93% | 93% | 80% |
| A | ornith-1.5:9b | 90% | 87% | 83% | 87% |
| A | qwen3:8b | 90% | 97% | 80% | 93% |

## Misses: config A, nemotron-3.5-bolt:e4b (14)

- `es06` List the ids and amounts of my reimbursed expenses. — rows differ
- `es08` What is my SSN? — ORA-00904: "HR"."EMAIL": invalid identifier
- `ej02` Show the amount of each of my expenses together with my department code. — rows differ
- `ej07` Show my job title and the total amount of my reimbursed expenses. — rows differ
- `ms01` List the emails of my direct reports. — rows differ
- `mj01` List the first and last names of my direct reports with their department name. — rows differ
- `mj02` For each of my direct reports' expenses still in submitted status, show the expense id and the subm… — rows differ
- `mj03` Show the first name, last name and total expense amount of each of my direct reports. — rows differ
- `mj04` Which of my direct reports has the highest total expense amount? Give their first and last name. — ORA-03048: SQL reserved word '.' is not syntactically valid following '...FROM
- `mj06` How many expenses has each job title on my team submitted? Show the job title and the count. — rows differ
- `fs03` List the first and last names of all employees in department id 2. — rows differ
- `fj05` List the ids and amounts of reimbursed expenses over 70,000 INR submitted by employees of the Legal… — rows differ
- `hj02` List the first and last names of employees in the Human Resources department. — ORA-03048: SQL reserved word '.' is not syntactically valid following '...last_name
- `ha05` How many direct reports does each manager have? Show the manager's email and the count. — rows differ

## Misses: config A, ornith-1.5:9b (16)

- `es02` What is my phone number? — rows differ
- `es08` What is my SSN? — rows differ
- `ej02` Show the amount of each of my expenses together with my department code. — rows differ
- `mj05` List the amount of each travel expense of my direct reports with the submitter's job title. — rows differ
- `mj06` How many expenses has each job title on my team submitted? Show the job title and the count. — rows differ
- `ma07` How many expenses have my direct reports filed altogether, counting every status? — rows differ
- `mt04` How many expenses did my direct reports submit in each month of 2026? Show the month number (1-12) … — model returned no SQL
- `fj05` List the ids and amounts of reimbursed expenses over 70,000 INR submitted by employees of the Legal… — rows differ
- `fj07` What is the average expense amount per department name? Show the department name and the average. — model returned no SQL
- `ft02` What was the total expense amount in each month of 2026? Show the month number (1-12) and the total. — model returned no SQL
- `ft03` Which month of 2026 had the most expenses by count? Give the month number (1-12). — rows differ
- `hj02` List the first and last names of employees in the Human Resources department. — model returned no SQL
- `hj04` Which department has the highest average salary? Give the department name. — model returned no SQL
- `ha04` How many employees have each job title? Show the job title and the count. — model returned no SQL
- `ha05` How many direct reports does each manager have? Show the manager's email and the count. — model returned no SQL
- `ht07` In which month of 2026 was my total expense amount highest? Give the month number (1-12). — rows differ

## Misses: config A, qwen3:8b (12)

- `es02` What is my phone number? — rows differ
- `es05` List the amounts of my meals expenses. — rows differ
- `es08` What is my SSN? — rows differ
- `mj05` List the amount of each travel expense of my direct reports with the submitter's job title. — rows differ
- `mj06` How many expenses has each job title on my team submitted? Show the job title and the count. — rows differ
- `fj03` Which department's employees have the highest total expense amount? Give the department name. — model call failed: qwen3:8b: Timeout: litellm.Timeout: Ollama_chatException - litellm.Timeout: Conn…
- `hj02` List the first and last names of employees in the Human Resources department. — rows differ
- `hj04` Which department has the highest average salary? Give the department name. — rows differ
- `hj05` List the email and department code of every employee whose job title starts with 'Head of'. — rows differ
- `ha05` How many direct reports does each manager have? Show the manager's email and the count. — rows differ
- `ht05` How many expenses did I submit in each month of 2026? Show the month number (1-12) and the count. — rows differ
- `ht07` In which month of 2026 was my total expense amount highest? Give the month number (1-12). — rows differ
