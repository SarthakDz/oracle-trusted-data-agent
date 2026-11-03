from dataclasses import fields

from tda.schema_docs import schema_docs
from tda.seed import Department, Employee, Expense

TABLES = {"departments": Department, "employees": Employee, "expenses": Expense}


def _doc(table, column):
    return next(d for d in schema_docs() if d.table == table and d.column == column)


def test_every_column_has_a_doc():
    docs = {(d.table, d.column) for d in schema_docs()}
    for table, cls in TABLES.items():
        assert (table, None) in docs
        for f in fields(cls):
            assert (table, f.name) in docs


def test_status_doc_lists_allowed_values():
    # The bake-off's a3 miss: models guessed 'APPROVED' because the prompt never said what is stored.
    text = _doc("expenses", "status").text
    for value in ("submitted", "approved", "rejected", "reimbursed"):
        assert f"'{value}'" in text


def test_category_and_department_values_listed():
    assert "'travel'" in _doc("expenses", "category").text
    assert "'ENG'" in _doc("departments", "code").text


def test_sensitive_columns_flagged():
    for column in ("salary", "ssn", "phone", "notes"):
        assert "sensitive" in _doc("employees", column).text.lower()


def test_table_doc_lists_every_column():
    text = _doc("employees", None).text
    for f in fields(Employee):
        assert f.name in text
