import json
from collections import Counter
from pathlib import Path

from evals.laya_data import injection_rows, intent_rows
from tda.seed import POISON_TEXTS, generate

DATA = Path(__file__).resolve().parents[2] / "evals" / "datasets"


def _texts(name, field):
    return {json.loads(line)[field].strip().lower() for line in (DATA / name).read_text().splitlines() if line.strip()}


def test_intent_training_rows_are_balanced_and_never_test_requests():
    rows = intent_rows()
    assert Counter(r["expected"]["intent"] for r in rows) == {"read": 500, "write": 500, "out_of_scope": 500}
    train = {r["state"].strip().lower() for r in rows}
    for name in ("intents.jsonl", "accuracy.jsonl", "attacks.jsonl", "controls.jsonl"):
        field = "request" if name == "intents.jsonl" else "question"
        assert not train & _texts(name, field), name


def test_injection_training_rows_never_hold_dev_or_seed_texts():
    rows = injection_rows()
    assert Counter(r["expected"]["injected"] for r in rows) == {True: 300, False: 300}
    ds = generate(42)
    held_out = _texts("injection_dev.jsonl", "text") | {t.lower() for t in POISON_TEXTS}
    held_out |= {e.notes.lower() for e in ds.employees} | {x.description.lower() for x in ds.expenses}
    assert not {r["state"].strip().lower() for r in rows} & held_out


def test_generation_is_deterministic():
    assert intent_rows(per_label=20) == intent_rows(per_label=20)
