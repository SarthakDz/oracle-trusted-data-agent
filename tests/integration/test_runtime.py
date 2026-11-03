import pytest

from tda import cli, llm
from tda.agent import runtime
from tda.agent.nodes import ROW_CAP, SQLExecutionError
from tda.agent.runtime import run_sql
from tda.db import service_connection
from tda.seed import generate

pytestmark = pytest.mark.integration

DS = generate(42)


def test_run_sql_returns_columns_and_rows():
    columns, rows, truncated = run_sql("select count(*) as n from hr.departments", "employee", "A")
    assert (columns, rows, truncated) == (["N"], [(8,)], False)


def test_run_sql_rolls_back():
    # Day 2 never commits anything the agent runs.
    run_sql("update hr.employees set phone = 'x' where email = 'arao'", "employee", "A")
    with service_connection() as conn:
        phone = conn.cursor().execute("select phone from hr.employees where email = 'arao'").fetchone()[0]
    assert phone == next(e.phone for e in DS.employees if e.email == "arao")


def test_run_sql_row_cap():
    _, rows, truncated = run_sql("select expense_id from hr.expenses", "finance_analyst", "A")
    assert len(rows) == ROW_CAP and truncated is True


def test_run_sql_error_message():
    with pytest.raises(SQLExecutionError, match="ORA-00904"):
        run_sql("select bogus from hr.departments", "employee", "A")


def test_cli_end_to_end_with_scripted_llm(monkeypatch, capsys):
    replies = iter(["read", "select count(*) from hr.departments", "There are 8 departments."])
    monkeypatch.setattr(llm, "chat", lambda prompt, think, model=None: next(replies))
    monkeypatch.setattr(runtime, "search_schema", lambda question: "Tables:\nhr.departments(dept_id, code, name)")
    assert cli.main(["--persona", "employee", "How many departments?"]) == 0
    out = capsys.readouterr().out
    assert "There are 8 departments." in out and "select count(*) from hr.departments" in out


def test_config_c_runs_as_the_persona():
    # Same query, two configs: B reads through HR, C through the employee's DDS session.
    _, rows_b, _ = run_sql("select email from hr.employees", "employee", "B")
    _, rows_c, _ = run_sql("select email from hr.employees", "employee", "C")
    assert len(rows_b) == len(DS.employees) and rows_c == [("arao",)]


def test_config_c_resolves_unqualified_table_names():
    assert run_sql("select count(*) from employees", "manager", "C")[1] == [(28,)]


def _write(update_sql: str, persona: str, config: str, decision: str):
    """The whole write path against Oracle: real run_sql and run_write, a stub model that proposes `update_sql`."""
    from tda.agent.graph import ask
    from tda.agent.state import Deps

    def chat(prompt, think):
        return "write" if "Reply with exactly one word" in prompt else update_sql

    deps = Deps(chat=chat, search=lambda q: "ctx", run_sql=runtime.run_sql, run_write=runtime.run_write)
    return ask("change something", persona, config, deps=deps, approver=lambda preview: decision)


def _employee(email: str, column: str):
    with service_connection() as conn:
        return conn.cursor().execute(f"select {column} from hr.employees where email = :e", e=email).fetchone()[0]


def _restore(email: str, column: str):
    seed = next(getattr(e, column) for e in DS.employees if e.email == email)
    with service_connection() as conn:
        conn.cursor().execute(f"update hr.employees set {column} = :v where email = :e", v=seed, e=email)
        conn.commit()


def test_employee_changes_own_phone_in_c():
    try:
        state = _write("update hr.employees set phone = '+91 9876500001' where email = 'arao'", "employee", "C", "approve")
        assert state["changed"] == 1 and _employee("arao", "phone") == "+91 9876500001"  # committed: another session sees it
    finally:
        _restore("arao", "phone")


def test_config_c_own_salary_changes_nothing():
    # DDS lets vmehta read their own row (the preview shows it) but update only their phone, so the UPDATE changes 0 rows.
    try:
        state = _write("update hr.employees set salary = salary * 1.05 where email = 'vmehta'", "manager", "C", "approve")
        assert state["answer"].startswith("No change made") and "changed" not in state
        assert _employee("vmehta", "salary") == next(e.salary for e in DS.employees if e.email == "vmehta")
    finally:
        _restore("vmehta", "salary")


def test_rejected_write_changes_nothing():
    state = _write("update hr.employees set phone = '+91 9876500001' where email = 'arao'", "employee", "C", "reject")
    assert state["answer"].startswith("No change made") and _employee("arao", "phone") == next(e.phone for e in DS.employees if e.email == "arao")


def test_config_c_rolls_back():
    run_sql("update hr.employees set phone = 'x' where email = 'arao'", "employee", "C")
    with service_connection() as conn:
        phone = conn.cursor().execute("select phone from hr.employees where email = 'arao'").fetchone()[0]
    assert phone == next(e.phone for e in DS.employees if e.email == "arao")
