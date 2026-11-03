"""Every control gold is verified by running it: allowed for the persona, and in scope."""

import json
from pathlib import Path

import pytest

from evals.scoring import results_match
from tda.db import end_user_connection, service_connection
from tda.personas import PERSONAS

pytestmark = pytest.mark.integration

DATASET = Path(__file__).resolve().parents[2] / "evals" / "datasets" / "controls.jsonl"
CASES = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def _rows_as_persona() -> dict[str, list[tuple]]:
    rows = {}
    for persona in PERSONAS:
        with end_user_connection(persona) as conn:
            cur = conn.cursor()
            for case in (c for c in CASES if c["persona"] == persona):
                rows[case["id"]] = cur.execute(case["gold_sql"]).fetchall()
    return rows


def test_every_control_gold_runs_as_persona():
    rows = _rows_as_persona()
    assert not [cid for cid, r in rows.items() if not r or None in r[0]]


def test_every_control_gold_is_in_scope():
    rows = _rows_as_persona()
    with service_connection() as conn:
        cur = conn.cursor()
        out = [c["id"] for c in CASES if not results_match(cur.execute(c["gold_sql"]).fetchall(), rows[c["id"]])]
    assert not out
