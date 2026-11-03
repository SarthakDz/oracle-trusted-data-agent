"""Every accuracy gold is verified by running it, as the design requires."""

import json
from pathlib import Path

import pytest

from evals.scoring import results_match
from tda.db import end_user_connection, service_connection
from tda.personas import PERSONAS

pytestmark = pytest.mark.integration

DATASET = Path(__file__).resolve().parents[2] / "evals" / "datasets" / "accuracy.jsonl"
CASES = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def _rows_as_persona() -> dict[str, list[tuple]]:
    rows = {}
    for persona in PERSONAS:
        with end_user_connection(persona) as conn:
            cur = conn.cursor()
            for case in (c for c in CASES if c["persona"] == persona):
                rows[case["id"]] = cur.execute(case["gold_sql"]).fetchall()
    return rows


def test_every_accuracy_gold_runs_as_persona():
    # An aggregate over no visible rows still returns one row of NULLs, so NULLs fail too.
    rows = _rows_as_persona()
    bad = [cid for cid, r in rows.items() if not r or None in r[0]]
    assert not bad


def test_every_accuracy_gold_is_in_scope():
    # The same query as HR (who sees everything) must return the same rows. If it doesn't,
    # the gold is right only because DDS filtered it: the question leaves the persona's scope.
    rows = _rows_as_persona()
    with service_connection() as conn:
        cur = conn.cursor()
        bad = [c["id"] for c in CASES if not results_match(cur.execute(c["gold_sql"]).fetchall(), rows[c["id"]])]
    assert not bad
