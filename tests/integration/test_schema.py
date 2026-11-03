import pytest

from tda import dbinit
from tda.db import service_connection
from tda.seed import POISON_TEXTS, generate

pytestmark = pytest.mark.integration


def _counts() -> tuple[int, int, int]:
    with service_connection() as conn:
        cur = conn.cursor()
        return tuple(
            cur.execute(f"select count(*) from hr.{table}").fetchone()[0]
            for table in ("departments", "employees", "expenses")
        )


def test_counts_match_seed():
    ds = generate(42)
    assert _counts() == (len(ds.departments), len(ds.employees), len(ds.expenses))


def test_values_round_trip():
    ds = generate(42)
    with service_connection() as conn:
        cur = conn.cursor()
        assert cur.execute("select sum(salary) from hr.employees").fetchone()[0] == sum(e.salary for e in ds.employees)
        assert cur.execute("select sum(amount) from hr.expenses").fetchone()[0] == pytest.approx(
            float(sum(x.amount for x in ds.expenses))
        )
        poisoned = cur.execute(
            "select count(*) from hr.employees where notes in (:1, :2, :3, :4, :5)", list(POISON_TEXTS)
        ).fetchone()[0]
        assert poisoned == 5


def test_db_init_idempotent():
    dbinit.main()
    test_counts_match_seed()
