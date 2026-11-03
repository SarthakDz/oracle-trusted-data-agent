"""Day 7 live smoke: the Day 2 smoke questions through the public API over HTTPS.

The gold rows come from the database the deployment uses, through the settings in the
environment and .env (for the laptop demo, the local database). The answers come from
POST /ask in config C, with TLS verified. The demo token is read from TDA_DEMO_TOKEN,
never from the command line.

    python -m evals.live_smoke --url https://203.0.113.7
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import date

from evals.scoring import results_match
from evals.smoke import RESULTS, SHOWN_ROWS, expected_rows, load_cases, write_report
from tda.api import SHOWN_ROWS as API_ROWS


def ask_live(base_url: str, token: str, persona: str, question: str, timeout_s: float = 900) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/ask",
        data=json.dumps({"persona": persona, "question": question}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.load(response)


def run_live(base_url: str, token: str) -> list[dict]:
    cases = load_cases()
    expected = expected_rows(cases)
    if too_long := [c["id"] for c in cases if len(expected[c["id"]]) > API_ROWS]:
        raise ValueError(f"the API returns {API_ROWS} rows; these cases expect more: {too_long}")
    results = []
    for case in cases:
        started = time.perf_counter()
        try:
            reply, error = ask_live(base_url, token, case["persona"], case["question"]), None
        except OSError as e:  # HTTP errors, refused connections and timeouts: one case, not the run
            reply, error = {}, f"{type(e).__name__}: {e}"
        rows = [tuple(r) for r in reply.get("rows") or []]
        results.append({
            "id": case["id"],
            "persona": case["persona"],
            "question": case["question"],
            "correct": error is None and reply.get("pending") is None and results_match(rows, expected[case["id"]]),
            "attempts": 1,
            "latency_s": round(time.perf_counter() - started, 1),
            "sql": reply.get("sql"),
            "rows": rows[:SHOWN_ROWS],
            "expected": expected[case["id"]][:SHOWN_ROWS],
            "error": error,
            "answer": reply.get("answer") or "",
        })
        print(f"{case['id']} {'ok  ' if results[-1]['correct'] else 'MISS'} {results[-1]['latency_s']:6.1f}s  {case['question']}", flush=True)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the live API.")
    parser.add_argument("--url", required=True, help="the public base URL, e.g. https://203.0.113.7")
    args = parser.parse_args(argv)
    token = os.environ.get("TDA_DEMO_TOKEN")
    if not token:
        print("set TDA_DEMO_TOKEN (the laptop demo: export TDA_DEMO_TOKEN=$(grep ^TDA_DEMO_TOKEN= .env | cut -d= -f2-))", file=sys.stderr)
        return 2
    results = run_live(args.url, token)
    stamp = date.today().isoformat()
    with (RESULTS / f"cloud-smoke-{stamp}.jsonl").open("w") as log:
        for r in results:
            log.write(json.dumps(r, default=str) + "\n")
    write_report(
        results, RESULTS / f"cloud-smoke-{stamp}.md", "C (live)",
        "Latency is the full HTTPS round trip through the public URL, with no warm-up call "
        "(the first case includes any model load).",
    )
    print(f"{sum(r['correct'] for r in results)}/{len(results)} correct; report in results/cloud-smoke-{stamp}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
