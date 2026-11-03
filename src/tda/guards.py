"""App-level guards for configs B and C: SQL validators for reads and writes, the write rule
DDS can't express (a raise of at most 10%), an SSN output filter and a grounding check.

All of them are deterministic code. Config A runs without them; config C adds Deep Data
Security underneath them.
"""

import re
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

import sqlglot
from sqlglot import exp

from tda.personas import PERSONAS

HR_TABLES = frozenset({"employees", "expenses", "departments"})
PRIMARY_KEYS = {"employees": "employee_id", "expenses": "expense_id", "departments": "dept_id"}
# The columns each data role may change, mirroring the update(...) parts of db/04_data_grants.sql.
WRITABLE: dict[str, frozenset[tuple[str, str]]] = {
    "employee_role": frozenset({("employees", "phone")}),
    "manager_role": frozenset({("employees", "salary"), ("expenses", "status")}),
}
MAX_RAISE = Decimal("1.10")

_SSN = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
SSN_MASK = "***-**-****"
_SEPARATOR = re.compile(r"(?<=\d),(?=\d)")  # 1,234,567 and Indian 12,34,567 alike
_NUMBER = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?!\d)")
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)](?=\s)")  # "4. ..." numbers a list item, it claims nothing


def validate_sql(sql: str) -> str | None:
    """None when the query may run, else a one-line reason the repair prompt can act on.

    Tables are allow-listed (the three HR tables, CTE names, DUAL), so the data dictionary,
    SYS, V$ views and other schemas are out without naming them. Unqualified HR table names
    pass: the HR account and config C's end-user session (current_schema = HR) both resolve them.
    """
    tree = _select(sql)
    return tree if isinstance(tree, str) else _objects_reason(tree)


def select_only(sql: str) -> str | None:
    """validate_sql without the table checks: the public API's floor for config A, which has no validator."""
    tree = _select(sql)
    return tree if isinstance(tree, str) else None


def _select(sql: str) -> exp.Expression | str:
    """The single parsed SELECT, or a validator reason."""
    tree = _statement(sql)
    if isinstance(tree, str):
        return tree
    if not isinstance(tree, (exp.Select, exp.SetOperation, exp.Subquery)):
        return "validator: only SELECT queries are allowed"
    if any(s.args.get("locks") for s in tree.find_all(exp.Select)):
        return "validator: SELECT ... FOR UPDATE is not allowed"
    return tree


# Write rejections about how the SQL is written; the model may fix these. Every other rejection
# says what it would change is not allowed, and a repair could only change the request.
REPAIRABLE = (
    "validator: the query could not be parsed",
    "validator: send exactly one SQL statement",
    "validator: an UPDATE needs a WHERE clause",
)


def validate_write(sql: str, persona: str) -> str | None:
    """None when the write may run, else a one-line reason: one UPDATE of a column the persona's data roles may change, with a WHERE clause.

    Which rows the persona may change is not checked here: in config C the database enforces it.
    """
    tree = _statement(sql)
    if isinstance(tree, str):
        return tree
    if not isinstance(tree, exp.Update):
        return "validator: a change must be one UPDATE statement (no INSERT, DELETE, MERGE or DDL)"
    if reason := _objects_reason(tree):
        return reason
    table = tree.this.name.lower()
    allowed = set().union(*(WRITABLE.get(role, frozenset()) for role in PERSONAS[persona].data_roles))
    for assignment in tree.expressions:
        column = assignment.this.name.lower()
        if (table, column) not in allowed:
            return f"validator: this user may not change {table}.{column}"
    if not tree.args.get("where"):
        return "validator: an UPDATE needs a WHERE clause"
    return None


def preview_sql(sql: str) -> str | None:
    """The dry run of an UPDATE: a SELECT of the rows it would change, with each changed column's old and new value."""
    tree = _statement(sql)
    if not isinstance(tree, exp.Update) or tree.this.name.lower() not in PRIMARY_KEYS:
        return None
    columns = [exp.column(PRIMARY_KEYS[tree.this.name.lower()]).as_("id")]
    for assignment in tree.expressions:
        name = assignment.this.name
        columns += [exp.column(name).as_(f"old_{name}"), assignment.expression.copy().as_(f"new_{name}")]
    select = exp.select(*columns).from_(tree.this.copy())
    if where := tree.args.get("where"):
        select = select.where(where.this.copy())
    return select.sql("oracle")


def raise_limit(old: int) -> int:
    """The highest salary a 10% raise allows, rounded as Oracle stores NUMBER(10)."""
    return int((Decimal(old) * MAX_RAISE).quantize(Decimal(1), ROUND_HALF_UP))


def rule_violations(columns: list[str], rows: Sequence[Sequence[object]]) -> list[str]:
    """Preview rows that break the app's write rule: a salary raised by more than 10%."""
    names = [c.lower() for c in columns]  # Oracle returns the preview's aliases in upper case
    if "old_salary" not in names or "new_salary" not in names:
        return []
    old, new = names.index("old_salary"), names.index("new_salary")
    out = []
    for row in rows:
        if row[old] is None or row[new] is None:
            continue
        stored = Decimal(str(row[new])).quantize(Decimal(1), ROUND_HALF_UP)
        if stored > raise_limit(row[old]):
            out.append(f"a raise above 10% (row {row[0]}: {row[old]} to {stored}, at most {raise_limit(row[old])})")
    return out


def _statement(sql: str) -> exp.Expression | str:
    """The single parsed statement, or a validator reason."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="oracle") if s is not None]
    except sqlglot.errors.SqlglotError as e:
        return f"validator: the query could not be parsed ({str(e).splitlines()[0][:120]})"
    if len(statements) != 1:
        return "validator: send exactly one SQL statement"
    return statements[0]


def _objects_reason(tree: exp.Expression) -> str | None:
    # A package call (DBMS_XMLGEN.GETXML, UTL_HTTP.REQUEST) can run SQL the table check never sees.
    if any(isinstance(d.expression, exp.Func) for d in tree.find_all(exp.Dot)):
        return "validator: package function calls are not allowed"
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), table.db.lower()
        if schema == "hr" and name in HR_TABLES:
            continue
        if not schema and (name in HR_TABLES or name in ctes or name == "dual"):
            continue
        return f"validator: table {table.sql('oracle')} is not allowed; use only hr.employees, hr.expenses and hr.departments"
    return None


def mask_ssns(text: str) -> str:
    return _SSN.sub(SSN_MASK, text)


def mask_rows(rows: Sequence[Sequence[object]]) -> list[tuple]:
    return [tuple(mask_ssns(v) if isinstance(v, str) else v for v in row) for row in rows]


def _numbers(text: str) -> list[str]:
    return _NUMBER.findall(_SEPARATOR.sub("", text))


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def ungrounded_numbers(answer: str, rows: Sequence[Sequence[object]], question: str) -> list[str]:
    """Numbers in the answer that no row value, question number or the row count explains.

    A row number explains an answer number when it rounds to it at the answer's precision
    (half up or half even), so "INR 12,34,567.89" is grounded by an average of 1234567.8912.
    List numbering at the start of a line is not checked.
    """
    allowed = {Decimal(len(rows))} | {Decimal(n) for n in _numbers(question)}
    for row in rows:
        for cell in row:
            if isinstance(cell, (int, float, Decimal)) and not isinstance(cell, bool):
                if (d := _decimal(cell)) is not None:
                    allowed.add(d)
            elif cell is not None:
                allowed.update(Decimal(n) for n in _numbers(str(cell)))
    out = []
    for n in _numbers(_LIST_MARKER.sub("", answer)):
        places = len(n.split(".")[1]) if "." in n else 0
        value, step = Decimal(n), Decimal(1).scaleb(-places)
        if not any(a.quantize(step, r) == value for a in allowed if a.is_finite() for r in (ROUND_HALF_UP, ROUND_HALF_EVEN)):
            out.append(n)
    return out
