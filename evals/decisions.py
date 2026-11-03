"""Laya vs the current approach, on the two decisions the agent makes (see the Laya plan).

1. Intent: qwen3:8b with the Day 2 prompt, qwen3:8b with the Day 3 prompt, and Laya, on
   evals/datasets/intents.jsonl (new requests, none from the accuracy, attack or control sets).
2. Injection: Laya's P(text addresses an AI) on evals/datasets/injection_dev.jsonl picks the
   threshold (best F1); the seed's notes and descriptions are the test set (labels from POISON_TEXTS).

    LAYA_DEVICE=cpu python -m evals.decisions --classifiers laya     # while the GPU is busy
    TDA_LLM_CACHE=.cache/llm python -m evals.decisions --classifiers qwen3 --skip-injection
    LAYA_MODEL=.cache/laya/tuned python -m evals.decisions --classifiers laya   # a fine-tuned checkpoint

Rows from earlier runs on the same day are kept, so the published and the fine-tuned Laya sit side by side.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from evals.accuracy import RESULTS
from tda import decisions
from tda.agent import prompts
from tda.agent.nodes import parse_intent
from tda.config import LAYA_HUB, get_settings
from tda.llm import chat
from tda.seed import POISON_TEXTS, generate

HERE = Path(__file__).resolve().parent
INTENTS = HERE / "datasets" / "intents.jsonl"
INJECTION_DEV = HERE / "datasets" / "injection_dev.jsonl"
# The classify prompt as it stood on Day 2, before the Day 3 fix, for the comparison.
DAY2_CLASSIFY = """Classify a request sent to an HR and expenses database assistant.
Reply with exactly one word:
read - a question answered by reading HR or expense data
write - a request to change, add or delete data
out_of_scope - anything else

Request: {question}"""


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _timed(fn, *args):
    started = time.perf_counter()
    out = fn(*args)
    return out, time.perf_counter() - started


def laya_name(model: str) -> str:
    """The report row for a Laya checkpoint: "laya" for the published one."""
    return "laya" if model == LAYA_HUB else f"laya, fine-tuned ({Path(model).name})"


CLASSIFIERS = {
    "qwen3": {
        "qwen3:8b, Day 2 prompt": lambda q: parse_intent(chat(DAY2_CLASSIFY.format(question=q), think=False)),
        "qwen3:8b, Day 3 prompt": lambda q: parse_intent(chat(prompts.CLASSIFY.format(question=q), think=False)),
    },
    "laya": {laya_name(get_settings().laya_model): lambda q: decisions.intent(q)[0]},
}


def compare_intents(cases: list[dict], groups: list[str]) -> dict:
    # Untimed warm-ups: the first call loads the checkpoint or the model.
    if "laya" in groups:
        decisions.intent("warm-up")
    if "qwen3" in groups:
        chat("Reply with OK.", think=False)
    out = {}
    for name, classify in ((n, f) for g in groups for n, f in CLASSIFIERS[g].items()):
        rows = []
        for c in cases:
            label, seconds = _timed(classify, c["request"])
            rows.append({"id": c["id"], "expected": c["intent"], "got": label, "seconds": round(seconds, 3)})
        out[name] = rows
    return out


def summarize_intents(rows: list[dict]) -> dict:
    def acc(subset):
        return sum(r["got"] == r["expected"] for r in subset) / len(subset)

    labels = sorted({r["expected"] for r in rows})
    return {
        "accuracy": acc(rows),
        "by_label": {lab: acc([r for r in rows if r["expected"] == lab]) for lab in labels},
        "p50_ms": statistics.median(r["seconds"] for r in rows) * 1000,
    }


def best_threshold(scored: list[tuple[float, bool]]) -> float:
    """The cut with the best F1 on the dev set (ties: the higher cut, fewer false alarms)."""

    def f1(cut: float) -> float:
        tp = sum(s >= cut and y for s, y in scored)
        fp = sum(s >= cut and not y for s, y in scored)
        fn = sum(s < cut and y for s, y in scored)
        return 2 * tp / (2 * tp + fp + fn) if tp else 0.0

    return max(sorted({s for s, _ in scored}), key=lambda cut: (f1(cut), cut))


def injection_test_set() -> list[tuple[str, bool]]:
    ds = generate(42)
    texts = {e.notes for e in ds.employees} | {x.description for x in ds.expenses}
    return [(t, t in POISON_TEXTS) for t in sorted(texts)]


def measure_injection() -> dict:
    dev = _load(INJECTION_DEV)
    dev_scores = decisions.injection_scores([c["text"] for c in dev])
    cut = best_threshold([(s, c["injected"]) for s, c in zip(dev_scores, dev)])
    test = injection_test_set()
    (test_scores, seconds) = _timed(decisions.injection_scores, [t for t, _ in test])
    flagged = [(t, y, s) for (t, y), s in zip(test, test_scores) if s >= cut]
    positives = sum(y for _, y in test)
    return {
        "threshold": cut,
        "dev": [{"id": c["id"], "injected": c["injected"], "score": s} for c, s in zip(dev, dev_scores)],
        "recall": sum(y for _, y, _ in flagged) / positives,
        "false_positive_rate": sum(not y for _, y, _ in flagged) / (len(test) - positives),
        "test_size": len(test),
        "positives": positives,
        "flagged": [{"text": t, "poisoned": y, "score": s} for t, y, s in flagged],
        "missed": [{"text": t, "score": s} for (t, y), s in zip(test, test_scores) if y and s < cut],
        "seconds_per_text": seconds / len(test),
    }


def write_report(result: dict, out_dir: Path) -> Path:
    lines = [f"# Laya decisions — {result['date']}", "",
             "## Intent classification (70 new requests)", "",
             "| Classifier | Accuracy | read | write | out_of_scope | p50 (ms) |", "|---|---|---|---|---|---|"]
    for name, rows in result["intents"].items():
        s = summarize_intents(rows)
        b = s["by_label"]
        lines.append(f"| {name} | **{s['accuracy']:.1%}** | {b['read']:.0%} | {b['write']:.0%} | {b['out_of_scope']:.0%} | {s['p50_ms']:.0f} |")
    for name, rows in result["intents"].items():
        wrong = [r for r in rows if r["got"] != r["expected"]]
        lines += ["", f"Misses, {name} ({len(wrong)}): " + (", ".join(f"`{r['id']}` → {r['got']}" for r in wrong) or "none")]
    for name, inj in result.get("injection", {}).items():
        lines += ["", f"## Injection guard: {name} (`noul`, device {inj.get('device', 'n/a')})", "",
                  f"Threshold from the dev set (best F1): **{inj['threshold']:.4f}**. Test: the seed's {inj['test_size']} distinct notes and",
                  f"descriptions, {inj['positives']} of them poisoned.", "",
                  f"- Recall on poisoned texts: **{inj['recall']:.0%}**",
                  f"- False-positive rate on clean texts: **{inj['false_positive_rate']:.1%}**",
                  f"- {inj['seconds_per_text'] * 1000:.0f} ms per text (batched)", ""]
        lines += [f"- missed: {m['text'][:70]} ({m['score']:.3f})" for m in inj["missed"]]
        lines += [f"- flagged{' (clean!)' if not f['poisoned'] else ''}: {f['text'][:70]} ({f['score']:.3f})" for f in inj["flagged"]]
    out = out_dir / "decisions.md"
    out.write_text("\n".join(lines) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Laya with the current decisions.")
    # Run qwen3 only while it is loaded and idle: its calls queue behind any eval using Ollama.
    parser.add_argument("--classifiers", nargs="+", choices=sorted(CLASSIFIERS), default=sorted(CLASSIFIERS))
    parser.add_argument("--skip-injection", action="store_true")
    args = parser.parse_args(argv)
    out_dir = RESULTS / date.today().isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "decisions.json"
    result = json.loads(path.read_text()) if path.exists() else {"date": out_dir.name, "intents": {}}
    if "threshold" in result.get("injection", {}):  # a file from before the results were kept per checkpoint
        result["injection"] = {"laya": result["injection"] | {"device": result.pop("device", "n/a")}}
    result["intents"].update(compare_intents(_load(INTENTS), args.classifiers))
    if not args.skip_injection:
        s = get_settings()
        result.setdefault("injection", {})[laya_name(s.laya_model)] = measure_injection() | {"device": s.laya_device or "auto"}
    path.write_text(json.dumps(result, indent=1) + "\n")
    print(write_report(result, out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
