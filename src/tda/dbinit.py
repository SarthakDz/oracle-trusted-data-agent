"""Create (or re-create) the HR schema, seed data and DDS objects. Safe to run repeatedly."""

import re
import time
from collections.abc import Mapping
from dataclasses import astuple, fields
from pathlib import Path

import oracledb

from tda.config import get_settings
from tda.db import service_connection, sys_connection
from tda.seed import Dataset, Department, Employee, Expense, generate

DB_DIR = Path(__file__).resolve().parents[2] / "db"
_PARAM = re.compile(r"&([A-Z_]+)")
_SEPARATOR = re.compile(r"^/\s*$", re.MULTILINE)


def render_sql(text: str, params: Mapping[str, str] | None = None) -> list[str]:
    """Split a SQL file into statements and substitute &NAME parameters.

    Statements are separated by a line holding only "/", the same rule for SQL and
    PL/SQL, so a PL/SQL block can keep its semicolons and plain SQL needs none.
    """
    params = params or {}
    statements = []
    for chunk in _SEPARATOR.split(text):
        body = chunk.strip()
        if all(not line.strip() or line.strip().startswith("--") for line in body.splitlines()):
            continue
        statements.append(_PARAM.sub(lambda m: params[m.group(1)], body))
    return statements


def run_sql_file(conn: oracledb.Connection, path: Path, params: Mapping[str, str] | None = None) -> None:
    with conn.cursor() as cur:
        for statement in render_sql(path.read_text(), params):
            cur.execute(statement)


def wait_ready(timeout_s: int = 900) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with sys_connection() as conn:
                conn.cursor().execute("select 1 from dual")
            return
        except oracledb.Error:
            if time.monotonic() >= deadline:
                raise
            time.sleep(5)


def _insert(cur: oracledb.Cursor, table: str, rows) -> None:
    # Column names are the dataclass field names, so the seed and the schema cannot drift silently.
    cls = {"departments": Department, "employees": Employee, "expenses": Expense}[table]
    names = [f.name for f in fields(cls)]
    binds = ", ".join(f":{i + 1}" for i in range(len(names)))
    cur.executemany(f"insert into hr.{table} ({', '.join(names)}) values ({binds})", [astuple(r) for r in rows])


def load_dataset(conn: oracledb.Connection, ds: Dataset) -> None:
    with conn.cursor() as cur:
        _insert(cur, "departments", ds.departments)
        _insert(cur, "employees", ds.employees)
        _insert(cur, "expenses", ds.expenses)
    conn.commit()


def default_tablespace(conn: oracledb.Connection) -> str:
    """USERS on Free, DATA on Autonomous AI Database."""
    with conn.cursor() as cur:
        sql = "select property_value from database_properties where property_name = 'DEFAULT_PERMANENT_TABLESPACE'"
        return cur.execute(sql).fetchone()[0]


def main() -> None:
    s = get_settings()
    wait_ready()
    with sys_connection() as conn:
        run_sql_file(conn, DB_DIR / "00_reset.sql")
        schema = {"APP_PWD": s.app_password, "TABLESPACE": default_tablespace(conn)}
        run_sql_file(conn, DB_DIR / "01_schema.sql", schema)
    with service_connection() as conn:
        load_dataset(conn, generate(42))
    with sys_connection() as conn:
        run_sql_file(conn, DB_DIR / "03_end_users.sql", {"END_USER_PASSWORD": s.end_user_password})
        run_sql_file(conn, DB_DIR / "04_data_grants.sql")
        run_sql_file(conn, DB_DIR / "05_schema_docs.sql")
        run_sql_file(conn, DB_DIR / "06_agent_memory.sql", schema)
    print("db-init: schema, seed data, Deep Data Security grants and the memory schema loaded (run `make index` next)")


if __name__ == "__main__":
    main()
