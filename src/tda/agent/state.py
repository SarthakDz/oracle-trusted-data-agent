"""The agent's state and the dependencies its nodes call."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from tda.memory import Memory


class AgentState(TypedDict, total=False):
    persona: str
    config: str
    question: str
    intent: str
    schema_context: str
    sql: str
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    error: str | None
    attempts: int
    answer: str
    ungrounded: list[str]  # configs B and C: answer numbers the rows do not explain
    # The write path: the UPDATE, its dry-run preview, the approval and the outcome.
    write_sql: str
    preview_columns: list[str]
    preview_rows: list[tuple]
    expected_rows: int | None  # rows the approved statement must change; None when there is no preview (config A)
    blocked: str  # configs B and C: the app write rule the preview breaks
    approved: bool
    changed: int
    pending: dict  # set by ask() when the run waits for an approval: {"sql", "columns", "rows"}
    thread_id: str
    memories: list[str]  # this user's earlier exchanges, when memory is on


@dataclass
class Deps:
    """Everything the nodes reach outside the graph, injected so tests can use fakes."""

    chat: Callable[[str, bool], str]  # (prompt, think) -> reply text
    search: Callable[[str], str]  # question -> schema context
    run_sql: Callable[[str, str, str], tuple[list[str], list[tuple], bool]]  # (sql, persona, config) -> (columns, rows, truncated)
    intent: Callable[[str], str] | None = None  # question -> intent label; None = ask the chat model
    # (sql, persona, config, expected_rows) -> rows changed, committed only when the count matches; None = no writes
    run_write: Callable[[str, str, str, int | None], int] | None = None
    memory: Memory | None = None  # per-user memory (tda.memory); None = off
