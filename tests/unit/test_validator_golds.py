"""The validator must not cost accuracy on honest queries: every gold and every query the agent has run passes."""

import json
from pathlib import Path

from tda.guards import validate_sql

ROOT = Path(__file__).resolve().parents[2]


def _jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / "evals" / "datasets" / name).read_text().splitlines() if line.strip()]


def test_validator_accepts_every_gold():
    golds = [c["gold_sql"] for name in ("accuracy.jsonl", "controls.jsonl", "day2_smoke.jsonl") for c in _jsonl(name)]
    assert not [(sql, why) for sql in golds if (why := validate_sql(sql))]


def test_validator_accepts_every_query_the_agent_ran():
    runs = [json.loads(p.read_text()) for p in ROOT.glob("results/**/[ABC]-*.json")]
    queries = {c["sql"] for r in runs for c in r["cases"] if c["sql"] and c["error"] is None}
    assert queries
    assert not [(sql, why) for sql in sorted(queries) if (why := validate_sql(sql))]
