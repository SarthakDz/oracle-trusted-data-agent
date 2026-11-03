import json
from collections import Counter
from pathlib import Path

from tda.personas import PERSONAS

DATASET = Path(__file__).resolve().parents[2] / "evals" / "datasets" / "accuracy.jsonl"
PER_PERSONA = {"simple": 8, "join": 7, "aggregate": 8, "time": 7}


def test_accuracy_dataset_shape():
    cases = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    assert len(cases) == 120
    assert len({c["id"] for c in cases}) == 120
    # The same question for two personas is two cases ("what is my own salary?"); within a persona it is a duplicate.
    assert len({(c["persona"], c["question"]) for c in cases}) == 120
    assert {c["persona"] for c in cases} == set(PERSONAS)
    for persona in PERSONAS:
        assert Counter(c["category"] for c in cases if c["persona"] == persona) == PER_PERSONA, persona
