"""Pick the local model for Day 2: execution accuracy and latency on 20 questions.

Runs as the HR service account (unscoped accuracy only). Model SQL is executed only
if it is a query, and every case is rolled back, so a bad answer cannot change data.
"""

import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import oracledb

from evals.scoring import results_match
from evals.sqlgen import generate_sql, is_select
from tda.db import service_connection
from tda.dbinit import DB_DIR, render_sql

HERE = Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "bakeoff.jsonl"
MODELS = HERE / "bakeoff_models.txt"
RESULTS = HERE.parent / "results"


@dataclass
class BakeoffRow:
    model: str
    thinking: bool
    accuracy: float
    valid_sql_rate: float
    p50_s: float
    p95_s: float


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def load_models() -> list[str]:
    lines = (line.strip() for line in MODELS.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def schema_text() -> str:
    # The CREATE TABLE statements from db/01_schema.sql, comments included, so the prompt
    # always describes the schema that is actually loaded.
    statements = render_sql((DB_DIR / "01_schema.sql").read_text(), {"APP_PWD": "unused", "TABLESPACE": "users"})
    return "\n\n".join(s for s in statements if "create table" in s.lower())


def evaluate(model: str, thinking: bool, cases: list[dict], conn: oracledb.Connection, log) -> BakeoffRow:
    schema = schema_text()
    # Warm-up call, not timed: the first call loads the model into VRAM (9–36 s measured),
    # which would otherwise dominate the latency numbers.
    try:
        generate_sql(model, cases[0]["question"], schema, think=thinking)
    except Exception:
        pass  # a failed warm-up shows up again, case by case, below
    cur = conn.cursor()
    correct = valid = 0
    latencies = []
    for case in cases:
        expected = cur.execute(case["gold_sql"]).fetchall()
        started = time.perf_counter()
        ok = error = None
        try:
            sql = generate_sql(model, case["question"], schema, think=thinking)
        except Exception as e:  # one failed model call costs one case, not the whole run
            sql, error = "", f"model call failed: {type(e).__name__}: {e}"
        latencies.append(time.perf_counter() - started)
        if error is None and not is_select(sql):
            error = "not a query"
        if error is None:
            try:
                ok = results_match(cur.execute(sql).fetchall(), expected)
                valid += 1
                correct += ok
            except oracledb.Error as e:
                error = str(e).splitlines()[0]
            finally:
                conn.rollback()
        log.write(
            json.dumps({"model": model, "thinking": thinking, "id": case["id"], "sql": sql, "correct": ok, "error": error})
            + "\n"
        )
    n = len(cases)
    p95 = statistics.quantiles(latencies, n=20)[18] if n > 1 else latencies[0]
    return BakeoffRow(model, thinking, correct / n, valid / n, statistics.median(latencies), p95)


def write_report(rows: list[BakeoffRow], path: Path) -> None:
    lines = [
        f"# Model bake-off — {date.today().isoformat()}",
        "",
        f"{len(load_cases())} questions from `evals/datasets/bakeoff.jsonl`, run as HR, temperature 0,",
        "RTX 4060 Laptop (8 GB), Ollama default 4,096-token context. Latency excludes one untimed",
        "warm-up call per model and mode (model load).",
        "",
        "| Model | Thinking | Exec accuracy | Valid SQL | p50 latency (s) | p95 latency (s) |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: (-r.accuracy, r.p50_s)):
        lines.append(
            f"| {r.model} | {'on' if r.thinking else 'off'} | {r.accuracy:.0%} | {r.valid_sql_rate:.0%} "
            f"| {r.p50_s:.1f} | {r.p95_s:.1f} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    models = sys.argv[1:] or load_models()
    cases = load_cases()
    RESULTS.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    rows = []
    with service_connection() as conn, (RESULTS / f"bakeoff-{stamp}.jsonl").open("w") as log:
        conn.call_timeout = 10_000  # ms; a runaway query counts as a failure, not a hang
        for model in models:
            for thinking in (True, False):
                rows.append(evaluate(model, thinking, cases, conn, log))
                r = rows[-1]
                print(f"{model} thinking={'on' if thinking else 'off'}: {r.accuracy:.0%} accurate, p50 {r.p50_s:.1f}s", flush=True)
    write_report(rows, RESULTS / f"bakeoff-{stamp}.md")


if __name__ == "__main__":
    main()
