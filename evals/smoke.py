"""Day 2 smoke eval: 10 persona-scoped questions through the whole agent.

The expected rows come from gold SQL run as the persona under Deep Data Security, so a
correct answer is one the persona is allowed to see. Scored by results_match, never by
an LLM judge.

    python -m evals.smoke [CONFIG]
"""

import json
import statistics
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from evals.scoring import results_match
from tda import tracing
from tda.agent.graph import ask
from tda.db import end_user_connection
from tda.llm import LLMError, chat

HERE = Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "day2_smoke.jsonl"
RESULTS = HERE.parent / "results"
SHOWN_ROWS = 5  # rows kept per case in the JSONL log, for debugging misses


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def expected_rows(cases: list[dict]) -> dict[str, list[tuple]]:
    expected = {}
    for persona in sorted({c["persona"] for c in cases}):
        with end_user_connection(persona) as conn:
            cur = conn.cursor()
            for case in (c for c in cases if c["persona"] == persona):
                expected[case["id"]] = cur.execute(case["gold_sql"]).fetchall()
    return expected


def score(state: dict, expected: Sequence[Sequence[object]]) -> bool:
    """Correct only if the run ended without an error and its rows match the gold rows."""
    return state.get("error") is None and "rows" in state and results_match(state["rows"], expected)


def run(config: str = "A") -> list[dict]:
    cases = load_cases()
    expected = expected_rows(cases)
    # Untimed warm-up: the first call loads the model into VRAM, which would otherwise
    # land on the first case's latency.
    try:
        chat("Reply with OK.", think=False)
    except LLMError:
        pass  # a dead model shows up again, case by case, below
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            state = ask(case["question"], case["persona"], config, approver=lambda preview: "reject")  # smoke never writes
        except Exception as e:  # one crashed run costs one case, not the whole eval
            state = {"error": f"{type(e).__name__}: {e}", "answer": ""}
        result = {
            "id": case["id"],
            "persona": case["persona"],
            "question": case["question"],
            "correct": score(state, expected[case["id"]]),
            "attempts": state.get("attempts", 0),
            "latency_s": round(time.perf_counter() - started, 1),
            "sql": state.get("sql"),
            "rows": list(state.get("rows") or [])[:SHOWN_ROWS],
            "expected": expected[case["id"]][:SHOWN_ROWS],
            "error": state.get("error"),
            "answer": state.get("answer", ""),
        }
        results.append(result)
        print(f"{case['id']} {'ok  ' if result['correct'] else 'MISS'} {result['latency_s']:6.1f}s  {case['question']}", flush=True)
    return results


def _cell(text: str, width: int = 120) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|")
    return text if len(text) <= width else text[: width - 1] + "…"


def write_report(
    results: list[dict], path: Path, config: str, latency: str = "Latency excludes one untimed warm-up call (model load)."
) -> None:
    n, correct = len(results), sum(r["correct"] for r in results)
    latencies = [r["latency_s"] for r in results]
    lines = [
        f"# Smoke eval — {date.today().isoformat()} — config {config}",
        "",
        f"**{correct}/{n} correct ({correct / n:.0%})**. Median latency {statistics.median(latencies):.1f} s.",
        "Gold SQL runs as each persona under Deep Data Security; scored by `results_match`.",
        latency,
        "",
        "| Case | Persona | Correct | Attempts | Latency (s) | Answer |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['id']} | {r['persona']} | {'yes' if r['correct'] else '**no**'} | {r['attempts']} "
            f"| {r['latency_s']:.1f} | {_cell(r['answer'])} |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    config = sys.argv[1] if len(sys.argv) > 1 else "A"
    tracing.setup_tracing()
    try:
        results = run(config)
    finally:
        tracing.shutdown_tracing()  # flush the run's spans before the process exits
    RESULTS.mkdir(exist_ok=True)
    stamp = date.today().isoformat()
    with (RESULTS / f"smoke-{stamp}.jsonl").open("w") as log:
        for r in results:
            log.write(json.dumps(r, default=str) + "\n")
    write_report(results, RESULTS / f"smoke-{stamp}.md", config)
    print(f"{sum(r['correct'] for r in results)}/{len(results)} correct; report in results/smoke-{stamp}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
