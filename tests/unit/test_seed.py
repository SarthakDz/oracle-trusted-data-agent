from decimal import Decimal

from tda.personas import PERSONAS
from tda.seed import N_DEPARTMENTS, N_EMPLOYEES, N_EXPENSES, POISON_TEXTS, generate


def _by_email(ds):
    return {e.email: e for e in ds.employees}


def test_deterministic():
    assert generate(42) == generate(42)
    assert generate(42) != generate(7)


def test_counts():
    ds = generate(42)
    assert (len(ds.employees), len(ds.departments), len(ds.expenses)) == (200, 8, 2000)
    assert (N_EMPLOYEES, N_DEPARTMENTS, N_EXPENSES) == (200, 8, 2000)


def test_sensitive_values_unique():
    # The string-match leak detector relies on these values never colliding.
    emps = generate(42).employees
    salaries = [e.salary for e in emps]
    assert len(set(salaries)) == len(salaries)
    assert all(400_000 <= s <= 6_000_000 and s % 100 != 0 for s in salaries)
    assert len({e.ssn for e in emps}) == len(emps)
    assert len({e.phone for e in emps}) == len(emps)


def test_personas_placed():
    ds = generate(42)
    emps = _by_email(ds)
    dept_code = {d.dept_id: d.code for d in ds.departments}
    p = {key: emps[persona.username] for key, persona in PERSONAS.items()}
    ceo = ds.employees[0]
    assert ceo.employee_id == 1 and ceo.manager_email is None
    assert dept_code[p["manager"].dept_id] == "ENG"
    assert p["manager"].manager_email == ceo.email
    assert dept_code[p["employee"].dept_id] == "ENG"
    assert p["employee"].manager_email == "vmehta"
    assert dept_code[p["finance_analyst"].dept_id] == "FIN"
    assert dept_code[p["hr_admin"].dept_id] == "HR"


def test_org_structure():
    ds = generate(42)
    ceo = ds.employees[0]
    managers = [e for e in ds.employees if e.manager_email == ceo.email]
    assert len(managers) == 8
    assert len({m.dept_id for m in managers}) == 8
    manager_of_dept = {m.dept_id: m.email for m in managers}
    for e in ds.employees[1:]:
        if e not in managers:
            assert e.manager_email == manager_of_dept[e.dept_id]


def test_poison_rows():
    ds = generate(42)
    assert len(POISON_TEXTS) == 5
    assert sum(e.notes in POISON_TEXTS for e in ds.employees) == 5
    assert sum(x.description in POISON_TEXTS for x in ds.expenses) == 5


def test_expense_manager_matches_employee():
    ds = generate(42)
    by_id = {e.employee_id: e for e in ds.employees}
    for x in ds.expenses:
        emp = by_id[x.employee_id]
        assert x.employee_email == emp.email
        assert x.manager_email == emp.manager_email
        assert isinstance(x.amount, Decimal) and x.amount > 0
