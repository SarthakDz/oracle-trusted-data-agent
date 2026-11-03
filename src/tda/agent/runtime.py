"""The agent's real dependencies: Oracle for SQL and schema search, Ollama for the model.

Configs A and B run every query as the shared HR service account; config C runs it as
the persona's Deep Data Security end user, so the database filters rows, columns and cells.
A read (run_sql) is never committed. A write (run_write) runs only after a person approved
its preview, and commits only if it changed exactly the previewed number of rows.
DDL can't be rolled back in Oracle; if an attack ever drops something, `make db-init` rebuilds it.
"""

import oracledb

from tda import llm
from tda.agent.nodes import ROW_CAP, SQLExecutionError
from tda.agent.state import Deps
from tda.config import get_settings
from tda.db import end_user_connection, service_connection
from tda.schema_index import schema_context

CALL_TIMEOUT_MS = 10_000


def _connect(persona: str, config: str) -> oracledb.Connection:
    if config in ("A", "B"):
        return service_connection()
    if config == "C":
        conn = end_user_connection(persona)
        # An end user owns no schema: without this, the unqualified names the HR account resolves fail with ORA-00942.
        conn.cursor().execute("alter session set current_schema = hr")
        return conn
    raise ValueError(f"unknown config {config}")


def run_sql(sql: str, persona: str, config: str) -> tuple[list[str], list[tuple], bool]:
    with _connect(persona, config) as conn:
        conn.call_timeout = CALL_TIMEOUT_MS
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                if cur.description is None:  # not a query: nothing to fetch
                    return [], [], False
                columns = [d[0] for d in cur.description]
                rows = cur.fetchmany(ROW_CAP + 1)
        except oracledb.Error as e:
            raise SQLExecutionError(str(e).splitlines()[0]) from e
        finally:
            conn.rollback()
    return columns, rows[:ROW_CAP], len(rows) > ROW_CAP


def run_write(sql: str, persona: str, config: str, expected_rows: int | None) -> int:
    """Run an approved write; commit only when it changed `expected_rows` rows (None: no preview to compare)."""
    with _connect(persona, config) as conn:
        conn.call_timeout = CALL_TIMEOUT_MS
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                changed = cur.rowcount
        except oracledb.Error as e:
            conn.rollback()
            raise SQLExecutionError(str(e).splitlines()[0]) from e
        if expected_rows is not None and changed != expected_rows:
            conn.rollback()
            raise SQLExecutionError(f"expected {expected_rows} rows, the statement changed {changed}")
        conn.commit()
    return changed


def search_schema(question: str) -> str:
    with service_connection() as conn:
        return schema_context(conn, question)


def default_deps(model: str | None = None) -> Deps:
    """model=None uses Settings.agent_model; evals pass a model to compare candidates."""
    return Deps(
        chat=lambda prompt, think: llm.chat(prompt, think=think, model=model),
        search=lambda question: search_schema(question),
        run_sql=run_sql,
        intent=_laya_intent if get_settings().classifier == "laya" else None,
        run_write=run_write,
        memory=_memory() if get_settings().memory else None,
    )


def _memory():
    from tda.memory import OracleMemory  # imported here: the library loads only when memory is on

    return OracleMemory()


def _laya_intent(question: str) -> str:
    from tda import decisions  # imported here: torch and the checkpoint load only when chosen

    return decisions.intent(question)[0]
