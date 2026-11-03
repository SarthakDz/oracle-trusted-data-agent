import json
from collections import Counter
from pathlib import Path

from tda.personas import PERSONAS

DATASETS = Path(__file__).resolve().parents[2] / "evals" / "datasets"
CATEGORIES = ("direct", "roleplay", "indirect", "sql_trick", "aggregation")


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / name).read_text().splitlines() if line.strip()]


def test_attacks_shape():
    cases = _load("attacks.jsonl")
    assert len(cases) == 80
    assert len({c["id"] for c in cases}) == 80
    assert len({(c["persona"], c["question"]) for c in cases}) == 80
    assert Counter((c["persona"], c["category"]) for c in cases) == {(p, c): 4 for p in PERSONAS for c in CATEGORIES}
    for c in cases:
        assert set(c) == {"id", "persona", "category", "question"}
        assert c["id"][:2] == c["persona"][0] + {"roleplay": "r", "aggregation": "g"}.get(c["category"], c["category"][0])


def test_controls_shape():
    cases = _load("controls.jsonl")
    assert len(cases) == 30
    assert len({c["id"] for c in cases}) == 30
    assert {c["persona"] for c in cases} == set(PERSONAS)
    for c in cases:
        assert set(c) == {"id", "persona", "question", "gold_sql"}
        assert c["id"][:2] == "c" + c["persona"][0]
