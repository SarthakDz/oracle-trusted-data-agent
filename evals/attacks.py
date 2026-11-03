"""Day 4 attack eval: 80 read attacks and 30 controls through the whole agent.

Every attack and control is scored by the leak detector (evals.leak), whose answer key
is read from the database. Controls are allowed questions that look sensitive: they
measure over-refusal, and their gold rows score accuracy as in Day 3. Run it through
`make attacks`, which turns on the response cache.

    python -m evals.attacks --config A --model qwen3:8b
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from evals import accuracy
from evals.leak import find_leaks, forbidden_values
from evals.smoke import expected_rows, score
from tda import tracing
from tda.agent.graph import ask
from tda.agent.runtime import default_deps
from tda.config import get_settings
from tda.llm import LLMError, chat, model_digest
from tda.personas import PERSONAS

HERE = Path(__file__).resolve().parent
ATTACKS = HERE / "datasets" / "attacks.jsonl"
CONTROLS = HERE / "datasets" / "controls.jsonl"
CATEGORIES = ("direct", "roleplay", "indirect", "sql_trick", "aggregation")


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def result_path(day: str, config: str, model: str) -> Path:
    path = accuracy.result_path(day, config, model)
    return path.with_name(f"attacks-{path.name}")


def _run_case(case: dict, config: str, deps, forbidden: dict[str, set]) -> tuple[dict, dict]:
    started = time.perf_counter()
    try:
        # A read eval never writes: a proposed change is rejected, so the answer key cannot drift.
        state = ask(case["question"], case["persona"], config, deps=deps, approver=lambda preview: "reject")
    except Exception as e:  # one crashed run costs one case, not the whole eval
        state = {"error": f"{type(e).__name__}: {e}", "answer": ""}
    rows = list(state.get("rows") or [])
    # A write preview is shown to the approver (and runs as HR in A and B): score it like returned rows.
    leaks = find_leaks(rows + list(state.get("preview_rows") or []), state.get("answer", ""), forbidden)
    result = {
        "id": case["id"],
        "persona": case["persona"],
        "category": case.get("category", "control"),
        "question": case["question"],
        "intent": state.get("intent"),
        "refused": state.get("intent", "read") != "read",
        "attempts": state.get("attempts", 0),
        "latency_s": round(time.perf_counter() - started, 1),
        "sql": state.get("sql"),
        "error": state.get("error"),
        "leaks": leaks,
        "leaked": bool(leaks),
        "answer": state.get("answer", ""),
        "ungrounded": accuracy.ungrounded(state, case["question"]),
        "rows": rows[: accuracy.SHOWN_ROWS],
    }
    return result, state


def run(config: str = "A", model: str | None = None) -> dict:
    model = model or get_settings().agent_model
    digest = model_digest(model)  # before anything else: a missing model must not cost an hour
    attacks, controls = load(ATTACKS), load(CONTROLS)
    expected = expected_rows(controls)
    forbidden = {p: forbidden_values(p) for p in PERSONAS}
    try:
        chat("Reply with OK.", think=False, model=model)  # untimed warm-up: loads the model into VRAM
    except LLMError:
        pass  # a dead model shows up again, case by case, below
    deps = default_deps(model)
    out: dict[str, list[dict]] = {"attacks": [], "controls": []}
    for kind, cases in (("attacks", attacks), ("controls", controls)):
        for n, case in enumerate(cases, 1):
            result, state = _run_case(case, config, deps, forbidden[case["persona"]])
            if kind == "controls":
                result["correct"] = score(state, expected[case["id"]])
                result["over_refused"] = result["refused"] or result["error"] is not None or not state.get("rows")
                flag = "REFUSED" if result["over_refused"] else "served "
            else:
                flag = "LEAK   " if result["leaked"] else ("refused" if result["refused"] else "held   ")
            out[kind].append(result)
            print(f"[{kind[:3]} {n:3}/{len(cases)}] {case['id']} {flag} {result['latency_s']:6.1f}s", flush=True)
    return {"config": config, "model": model, "digest": digest, "date": date.today().isoformat(), **out}


def _rate(cases: list[dict], test) -> float:
    return sum(1 for c in cases if test(c)) / len(cases) if cases else 0.0


def summarize_attacks(cases: list[dict]) -> dict:
    def by(key: str) -> dict[str, float]:
        return {v: _rate([c for c in cases if c[key] == v], lambda c: c["leaked"]) for v in sorted({c[key] for c in cases})}

    return {
        "leak_rate": _rate(cases, lambda c: c["leaked"]),
        "by_category": by("category"),
        "by_persona": by("persona"),
        "rows_leak_rate": _rate(cases, lambda c: any(leak["where"] == "rows" for leak in c["leaks"])),
        "answer_leak_rate": _rate(cases, lambda c: any(leak["where"] == "answer" for leak in c["leaks"])),
        "refused_rate": _rate(cases, lambda c: c["refused"]),
        "error_rate": _rate(cases, lambda c: c["error"] is not None),
        "grounding_failure_rate": accuracy.grounding_failure_rate(cases),
    }


def summarize_controls(cases: list[dict]) -> dict:
    return {
        "over_refusal_rate": _rate(cases, lambda c: c["over_refused"]),
        "accuracy": _rate(cases, lambda c: c["correct"]),
        "leak_rate": _rate(cases, lambda c: c["leaked"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the attack and control eval.")
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
    a, c = summarize_attacks(result["attacks"]), summarize_controls(result["controls"])
    print(
        f"{result['model']} config {result['config']}: leak rate {a['leak_rate']:.1%}, "
        f"over-refusal {c['over_refusal_rate']:.1%}, control accuracy {c['accuracy']:.1%} -> {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
