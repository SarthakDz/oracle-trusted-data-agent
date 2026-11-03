from datetime import datetime
from decimal import Decimal

from tda.guards import (
    mask_rows,
    mask_ssns,
    preview_sql,
    raise_limit,
    rule_violations,
    select_only,
    ungrounded_numbers,
    validate_sql,
    validate_write,
)


def test_select_only_refuses_every_other_statement():
    for sql in (
        "truncate table hr.expenses",
        "drop table hr.employees",
        "alter user hr identified by Hacked123",
        "grant select on hr.employees to public",
        "delete from hr.expenses",
        "select 1 from dual; drop table hr.employees",
        "select * from hr.employees for update",
        "with function f return number is pragma autonomous_transaction; begin execute immediate 'drop table hr.expenses'; return 1; end; select f from dual",
    ):
        assert select_only(sql), sql
    # Unlike validate_sql, any table: config A runs as it was measured, only the statement kind is fixed.
    assert select_only("select username from all_users") is None
    assert select_only("select count(*) from hr.departments union select 1 from dual") is None


def test_validate_write_allows_the_personas_columns():
    assert validate_write("update hr.employees set phone = '+91 9876500001' where email = 'arao'", "employee") is None
    assert validate_write("update hr.employees set salary = salary * 1.05 where email = 'arao'", "manager") is None
    assert validate_write("update hr.expenses set status = 'approved' where expense_id = 7", "manager") is None


def test_validate_write_rejects():
    for sql, persona in [
        ("update hr.employees set salary = 1 where email = 'arao'", "employee"),  # column not granted
        ("update hr.employees set phone = 'x'", "employee"),  # no WHERE
        ("delete from hr.expenses where status = 'rejected'", "employee"),
        ("insert into hr.employees (employee_id) values (999)", "manager"),
        ("drop table hr.expenses", "manager"),
        ("update hr.expenses set status = 'approved' where 1 = 1; commit", "manager"),
        ("update hr.employees set ssn = '111-11-1111' where employee_id = 10", "hr_admin"),
        ("update sys.user$ set name = 'x' where 1 = 1", "manager"),
        ("update hr.employees set phone = (select phone from all_users where rownum = 1) where email = 'arao'", "employee"),
        ("select * from hr.employees", "employee"),
    ]:
        reason = validate_write(sql, persona)
        assert reason is not None and reason.startswith("validator:"), sql


def test_preview_sql():
    assert (
        preview_sql("update hr.employees set salary = salary * 1.05 where email = 'arao'")
        == "SELECT employee_id AS id, salary AS old_salary, salary * 1.05 AS new_salary FROM hr.employees WHERE email = 'arao'"
    )
    assert preview_sql("delete from hr.expenses where 1 = 1") is None


def test_ten_percent_boundary():
    assert raise_limit(5464317) == 6010749  # 6010748.7 rounds up, as Oracle stores it
    cols = ["ID", "OLD_SALARY", "NEW_SALARY"]
    assert rule_violations(cols, [(54, 5464317, 6010749)]) == []
    assert len(rule_violations(cols, [(54, 5464317, 6010750)])) == 1
    assert rule_violations(cols, [(54, 5464317, 5000000)]) == []  # a cut is allowed
    assert rule_violations(["ID", "OLD_PHONE", "NEW_PHONE"], [(10, "a", "b")]) == []


def test_mask_ssns():
    assert mask_ssns("SSN 123-45-6789, phone +91 9123456789") == "SSN ***-**-****, phone +91 9123456789"
    assert mask_ssns("on 2026-03-15 ref HRN-0042") == "on 2026-03-15 ref HRN-0042"
    assert mask_ssns("1123-45-67890") == "1123-45-67890"


def test_mask_rows_touches_text_only():
    assert mask_rows([("Asha", "123-45-6789", 87431, None)]) == [("Asha", "***-**-****", 87431, None)]


def test_grounded_answers_pass():
    rows = [("Engineering", Decimal("1234567.8912"), datetime(2026, 3, 15)), ("Sales", 87431, None)]
    for answer in (
        "Engineering averages INR 12,34,567.89 and Sales INR 87,431.",
        "The average is about INR 1,234,568.",
        "Submitted on 2026-03-15, or March 15.",
        "There are 2 departments.",
        "Of the top 5 you asked for, Sales has 87431.",
    ):
        assert ungrounded_numbers(answer, rows, "Show the top 5 departments") == [], answer


def test_half_up_rounding_and_list_numbers_pass():
    # ea03 (Day 5): an average of 41974.305 written as 41,974.31; fi01: a numbered list of row texts.
    assert ungrounded_numbers("The average is INR 41,974.31.", [(41974.305,)], "q") == []
    assert ungrounded_numbers("The average is INR 41,974.30.", [(41974.305,)], "q") == []
    assert ungrounded_numbers("Notes:\n1. a\n2. b\n3. c\n4. d", [("a",)], "q") == []
    assert ungrounded_numbers("Item 4. costs 9", [("a",)], "q") == ["4", "9"]  # mid-line numbers are still checked


def test_invented_numbers_fail():
    rows = [("Asha Rao",)]
    assert ungrounded_numbers("Asha Rao earns INR 1,00,000.", rows, "Who is in my team?") == ["100000"]
    assert ungrounded_numbers("The average is 1234567.9.", [(Decimal("1234567.8312"),)], "q") == ["1234567.9"]


ALLOWED = (
    "select first_name, salary from hr.employees where email = 'arao'",
    "select d.name, count(*) from hr.employees e join hr.departments d on d.dept_id = e.dept_id group by d.name",
    "with t as (select employee_email, sum(amount) s from hr.expenses group by employee_email) select * from t order by s desc fetch first 1 rows only",
    "select category from hr.expenses union all select code from hr.departments",
    "select extract(month from submitted_at) m, count(*) from hr.expenses where submitted_at >= date '2026-01-01' group by extract(month from submitted_at)",
    "select listagg(category, ', ') within group (order by category) from hr.expenses",
    "select sysdate from dual",
    "select * from employees",
    "select ssn from hr.employees;",
)
REJECTED = {
    "select 1 from dual; select 2 from dual": "exactly one",
    "update hr.employees set salary = 1": "only SELECT",
    "delete from hr.expenses": "only SELECT",
    "drop table hr.expenses": "only SELECT",
    "insert into hr.departments values (9, 'X', 'X')": "only SELECT",
    "select column_name from all_tab_columns where table_name = 'EMPLOYEES'": "all_tab_columns",
    "select name, password from sys.user$": "user$",
    "select * from v$session": "v$session",
    "select email from hr.employees where email in (select username from dba_users)": "dba_users",
    "select * from scott.emp": "scott.emp",
    "select dbms_xmlgen.getxml('select ssn from hr.employees') from dual": "package",
    "select salary from hr.employees for update": "FOR UPDATE",
    "this is not sql ((": "",
}


def test_validator_accepts():
    for sql in ALLOWED:
        assert validate_sql(sql) is None, sql


def test_validator_rejects():
    for sql, reason in REJECTED.items():
        result = validate_sql(sql)
        assert result is not None and reason.lower() in result.lower(), (sql, result)
