"""Deep Data Security: each persona sees and changes exactly its slice.

Every expected set is derived from generate(42), never hard-coded, so the data
and these tests cannot drift apart.
"""

import pytest

from tda.db import end_user_connection, service_connection
from tda.personas import PERSONAS
from tda.seed import generate

pytestmark = pytest.mark.integration

DS = generate(42)
BY_EMAIL = {e.email: e for e in DS.employees}
BY_ID = {e.employee_id: e for e in DS.employees}
EMPLOYEE = PERSONAS["employee"].username
MANAGER = PERSONAS["manager"].username
FINANCE = PERSONAS["finance_analyst"].username
HR_ADMIN = PERSONAS["hr_admin"].username


def test_employee_sees_only_self():
    with end_user_connection("employee") as conn:
        cur = conn.cursor()
        assert cur.execute("select email from hr.employees").fetchall() == [(EMPLOYEE,)]
        seen = sorted(r[0] for r in cur.execute("select expense_id from hr.expenses"))
    assert seen == sorted(x.expense_id for x in DS.expenses if x.employee_email == EMPLOYEE)


def test_employee_write_scope():
    with end_user_connection("employee") as conn:
        cur = conn.cursor()
        cur.execute("update hr.employees set salary = salary + 1")
        assert cur.rowcount == 0
        cur.execute("update hr.employees set phone = '+91 9000000000'")
        assert cur.rowcount == 1
        conn.rollback()


def test_manager_ssn_visibility():
    # The manager holds employee_role and manager_role: the grants union, so their
    # own SSN is visible (employee_self) and their reports' SSNs are not.
    reports = {e.email for e in DS.employees if e.manager_email == MANAGER}
    with end_user_connection("manager") as conn:
        rows = dict(conn.cursor().execute("select email, ssn from hr.employees").fetchall())
    assert set(rows) == reports | {MANAGER}
    assert rows[MANAGER] == BY_EMAIL[MANAGER].ssn
    assert all(rows[r] is None for r in reports)


def test_manager_salary_update_scope():
    n_reports = sum(e.manager_email == MANAGER for e in DS.employees)
    with end_user_connection("manager") as conn:
        cur = conn.cursor()
        cur.execute("update hr.employees set salary = salary + 1")
        assert cur.rowcount == n_reports  # not their own row: employee_self allows update(phone) only
        conn.rollback()


def test_finance_sees_all_expenses_limited_directory():
    with end_user_connection("finance_analyst") as conn:
        cur = conn.cursor()
        assert cur.execute("select count(*) from hr.expenses").fetchone()[0] == len(DS.expenses)
        rows = cur.execute("select employee_id, salary, ssn, phone from hr.employees").fetchall()
    assert len(rows) == len(DS.employees)
    for employee_id, salary, ssn, phone in rows:
        e = BY_ID[employee_id]
        expected = (e.salary, e.ssn, e.phone) if e.email == FINANCE else (None, None, None)
        assert (salary, ssn, phone) == expected


def test_hr_admin_sees_all_no_ssn():
    with end_user_connection("hr_admin") as conn:
        rows = conn.cursor().execute("select email, salary, ssn from hr.employees").fetchall()
    assert len(rows) == len(DS.employees)
    for email, salary, ssn in rows:
        assert salary == BY_EMAIL[email].salary
        assert ssn == (BY_EMAIL[email].ssn if email == HR_ADMIN else None)


def test_service_account_sees_everything():
    # The config A/B baseline: one privileged account, no database-side filtering.
    with service_connection() as conn:
        rows = conn.cursor().execute("select email, ssn from hr.employees").fetchall()
    assert len(rows) == len(DS.employees)
    assert all(ssn == BY_EMAIL[email].ssn for email, ssn in rows)
