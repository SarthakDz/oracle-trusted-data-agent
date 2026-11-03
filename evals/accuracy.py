"""Day 3 accuracy eval: 120 persona-scoped questions through the whole agent.

Expected rows come from gold SQL run as each persona under Deep Data Security, and the
agent's rows are scored with results_match: execution accuracy, no LLM judge. Run it
through `make accuracy`, which turns on the response cache, so a re-run reproduces a run.

    python -m evals.accuracy --config A --model qwen3:8b
"""

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from evals.smoke import expected_rows, score
from tda import tracing
from tda.agent.graph import ask
from tda.agent.runtime import default_deps
from tda.config import get_settings
from tda.guards import ungrounded_numbers
from tda.llm import LLMError, chat, model_digest

HERE = Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "accuracy.jsonl"
RESULTS = HERE.parent / "results"
SHOWN_ROWS = 5  # rows kept per case, for reading misses


def load_cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def result_path(day: str, config: str, model: str) -> Path:
    return RESULTS / day / f"{config}-{model.replace(':', '_').replace('/', '_')}.json"


def ungrounded(state: dict, question: str) -> list[str]:
    """Numbers in the final answer that the rows don't explain; measured the same way in every config."""
    if state.get("error") is not None or "rows" not in state:
        return []
    return ungrounded_numbers(state.get("answer", ""), state["rows"], question)


def run(config: str = "A", model: str | None = None) -> dict:
    model = model or get_settings().agent_model
    digest = model_digest(model)  # before anything else: a missing model must not cost an hour
    cases = load_cases()
    expected = expected_rows(cases)
    try:
        chat("Reply with OK.", think=False, model=model)  # untimed warm-up: loads the model into VRAM
    except LLMError:
        pass  # a dead model shows up again, case by case, below
    deps = default_deps(model)
    results = []
    for n, case in enumerate(cases, 1):
        started = time.perf_counter()
        try:
            # A read eval never writes: a proposed change is rejected, so the gold rows cannot drift.
            state = ask(case["question"], case["persona"], config, deps=deps, approver=lambda preview: "reject")
        except Exception as e:  # one crashed run costs one case, not the whole eval
            state = {"error": f"{type(e).__name__}: {e}", "answer": ""}
        result = {
            "id": case["id"],
            "persona": case["persona"],
            "category": case["category"],
            "question": case["question"],
            "correct": score(state, expected[case["id"]]),
            "attempts": state.get("attempts", 0),
            "latency_s": round(time.perf_counter() - started, 1),
            "sql": state.get("sql"),
            "rows": list(state.get("rows") or [])[:SHOWN_ROWS],
            "expected": expected[case["id"]][:SHOWN_ROWS],
            "error": state.get("error"),
            "answer": state.get("answer", ""),
            "ungrounded": ungrounded(state, case["question"]),
            "schema_context": state.get("schema_context"),
        }
        results.append(result)
        print(f"[{n:3}/{len(cases)}] {case['id']} {'ok  ' if result['correct'] else 'MISS'} {result['latency_s']:6.1f}s", flush=True)
    return {"config": config, "model": model, "digest": digest, "date": date.today().isoformat(), "cases": results}


def summarize(cases: list[dict]) -> dict:
    def accuracy(subset: list[dict]) -> float:
        return sum(c["correct"] for c in subset) / len(subset)

    def by(key: str) -> dict[str, float]:
        return {v: accuracy([c for c in cases if c[key] == v]) for v in sorted({c[key] for c in cases})}

    return {
        "accuracy": accuracy(cases),
        "by_category": by("category"),
        "by_persona": by("persona"),
        "error_rate": sum(c["error"] is not None for c in cases) / len(cases),
        "p50_latency_s": statistics.median(c["latency_s"] for c in cases),
        "mean_attempts": statistics.mean(c["attempts"] for c in cases),
        "grounding_failure_rate": grounding_failure_rate(cases),
    }


def grounding_failure_rate(cases: list[dict]) -> float:
    # Result files from before Day 5 have no "ungrounded" field: they count as unmeasured, not as clean.
    measured = [c for c in cases if "ungrounded" in c]
    return sum(bool(c["ungrounded"]) for c in measured) / len(measured) if measured else float("nan")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the accuracy eval.")
    parser.add_argument("--config", default="A")
    parser.add_argument("--model", default=None, help="Ollama model tag (default: Settings.agent_model)")
    args = parser.parse_args(argv)
    tracing.setup_tracing()
    try:
        result = run(args.config, args.model)
    finally:
        tracing.shutdown_tracing()  # flush the run's spans before the process exits
    path = result_path(result["date"], result["config"], result["model"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, default=str, indent=1) + "\n")
    s = summarize(result["cases"])
    print(f"{result['model']} config {result['config']}: {s['accuracy']:.1%} correct, p50 {s['p50_latency_s']:.1f}s -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
