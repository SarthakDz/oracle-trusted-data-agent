"""The write eval's scoring rules and restore, against Oracle and DDS."""

import oracledb
import pytest

from evals import writes
from tda.db import end_user_connection, service_connection
from tda.personas import PERSONAS

pytestmark = pytest.mark.integration


def _sample(before: dict) -> list[tuple[str, int, str]]:
    """Cells to probe: own rows, a report's row and expenses, someone else's row and expense."""
    emp = before["employees"]
    by_email = {r["email"]: pk for pk, r in emp.items()}
    other_expense = next(pk for pk, r in before["expenses"].items() if r["manager_email"] not in ("vmehta", None))
    cells = [("employees", by_email[p.username], c) for p in PERSONAS.values() for c in ("phone", "salary")]
    cells += [("employees", by_email["mjain"], c) for c in ("phone", "salary", "ssn")]  # a report of vmehta
    cells += [("employees", by_email["dagarwal"], "salary"), ("expenses", 49, "status"), ("expenses", other_expense, "status")]
    return cells


def test_rules_match_dds():
    # DDS can't express the 10% rule, so each probe rewrites a cell with its own value (a 0% change).
    with service_connection() as hr:
        before = writes.snapshot(hr)
    mismatches = []
    for persona in PERSONAS:
        with end_user_connection(persona) as conn:
            for table, pk, column in _sample(before):
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"update hr.{table} set {column} = {column} where {writes.PRIMARY_KEYS[table]} = :pk", pk=pk)
                        granted = cur.rowcount == 1  # a row outside the grant: 0 rows, no error
                except oracledb.DatabaseError:  # no update grant on the table at all: ORA-41900
                    granted = False
                conn.rollback()
                value = before[table][pk][column]
                rule = writes.allowed_change(persona, {"table": table, "id": pk, "column": column, "old": value, "new": value}, before)
                if granted != rule:
                    mismatches.append((persona, table, pk, column, granted, rule))
    assert mismatches == []


def test_restore_undoes_update_delete_insert():
    with service_connection() as conn:
        before = writes.snapshot(conn)
        cur = conn.cursor()
        cur.execute("update hr.employees set phone = '+91 9000000099' where email = 'arao'")
        cur.execute("delete from hr.expenses where expense_id = 49")
        cur.execute("insert into hr.departments (dept_id, code, name) values (99, 'TMP', 'Temporary')")
        conn.commit()
        after = writes.snapshot(conn)
        assert len(writes.diff(before, after)) == 3
        writes.restore(conn, before, after)
        assert writes.snapshot(conn) == before


def test_runner_refuses_a_drifted_database(monkeypatch):
    monkeypatch.setattr(writes, "model_digest", lambda model: "sha256:test")
    monkeypatch.setattr(writes, "ask", lambda *a, **k: pytest.fail("ran a case on a drifted database"))
    with service_connection() as conn:
        before = writes.snapshot(conn)
        conn.cursor().execute("update hr.employees set phone = '+91 9000000098' where email = 'arao'")
        conn.commit()
        try:
            with pytest.raises(RuntimeError, match="make db-init"):
                writes.run("A", "fake:1b")
        finally:
            writes.restore(conn, before, writes.snapshot(conn))
