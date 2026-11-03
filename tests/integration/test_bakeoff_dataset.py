import pytest

import evals.bakeoff as bakeoff
from evals.bakeoff import load_cases
from tda.db import service_connection

pytestmark = pytest.mark.integration


def test_evaluate_survives_model_errors(monkeypatch, tmp_path):
    # One failing model call must cost one case, not the whole multi-hour run.
    def crash(*args, **kwargs):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(bakeoff, "generate_sql", crash)
    log_path = tmp_path / "log.jsonl"
    with service_connection() as conn, log_path.open("w") as log:
        row = bakeoff.evaluate("fake:1b", False, load_cases()[:2], conn, log)
    assert (row.accuracy, row.valid_sql_rate) == (0, 0)
    assert log_path.read_text().count("model crashed") == 2


def test_every_gold_sql_runs_and_returns_rows():
    cases = load_cases()
    assert len(cases) == 20
    assert sorted({c["category"] for c in cases}) == ["aggregate", "join", "simple", "time"]
    with service_connection() as conn:
        cur = conn.cursor()
        for case in cases:
            assert cur.execute(case["gold_sql"]).fetchall(), case["id"]
