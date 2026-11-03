import pytest

from evals.smoke import load_cases
from tda.db import end_user_connection
from tda.personas import PERSONAS

pytestmark = pytest.mark.integration


def test_every_smoke_gold_runs_as_persona():
    # The design's eval rule: the expected answer is what the persona may see, so gold SQL
    # runs as that persona under Deep Data Security, never as the HR owner.
    cases = load_cases()
    assert len(cases) == 10
    assert len({c["id"] for c in cases}) == 10
    assert {c["persona"] for c in cases} == set(PERSONAS)
    for persona in PERSONAS:
        with end_user_connection(persona) as conn:
            cur = conn.cursor()
            for case in (c for c in cases if c["persona"] == persona):
                rows = cur.execute(case["gold_sql"]).fetchall()
                # An aggregate over no visible rows still returns one row of NULLs.
                assert rows and None not in rows[0], case["id"]
