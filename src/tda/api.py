"""HTTP API: ask the agent, and approve or reject a write it proposed.

    POST /ask      {"persona", "question", "config": "C"} -> answer, or a pending write preview
    POST /approve  {"thread_id", "decision": "approve" | "reject"} -> the outcome
    GET  /health   (?deep=true also queries the database)

Both POSTs need `Authorization: Bearer <TDA_DEMO_TOKEN>`. One shared token, and the caller picks
the persona: a demo of four users over synthetic data, not real authentication (the production
path is identity propagation, see the design doc). The default config is C, the safest, and
the only one where an approved write can commit, and only with TDA_DEMO_WRITES=1 (otherwise,
and in A and B, approve answers "No change made").

    uvicorn tda.api:app --host 0.0.0.0 --port 8000
"""

import logging
import secrets
import threading
import uuid
from dataclasses import replace
from functools import lru_cache
from typing import Literal

import oracledb
from fastapi import Depends, FastAPI, Header, HTTPException
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from tda.agent.graph import build_graph
from tda.agent.nodes import SQLExecutionError
from tda.agent.state import Deps
from tda.config import get_settings
from tda.db import service_connection
from tda.guards import select_only

SHOWN_ROWS = 20

app = FastAPI(title="Trusted Data Agent", description="Independent demo project; not affiliated with Oracle.")
# shortcut: pending approvals are lost on restart; move to a database checkpointer before real users.
_saver = InMemorySaver()
_threads: dict[str, str] = {}  # thread_id -> config, so /approve resumes the graph that paused
# Threads paused for approval. /approve claims one under the lock, so a double click applies once;
# a claimed approval that then fails needs a new /ask.
_waiting: set[str] = set()
_claim = threading.Lock()


class AskBody(BaseModel):
    persona: Literal["employee", "manager", "finance_analyst", "hr_admin"]
    question: str
    config: Literal["A", "B", "C"] = "C"


class ApproveBody(BaseModel):
    thread_id: str
    decision: Literal["approve", "reject"]


@lru_cache(maxsize=1)
def get_deps() -> Deps:
    from tda.agent.runtime import default_deps  # imported here: it needs Oracle and Ollama

    return default_deps()


def require_token(authorization: str | None = Header(None)) -> None:
    token = get_settings().demo_token
    if not token:
        raise HTTPException(503, "the API is not configured: set TDA_DEMO_TOKEN")
    if authorization is None or not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "a valid demo token is required")


_graphs: dict[tuple[str, int], tuple[Deps, object]] = {}


def _graph(config: str, deps: Deps):
    """One compiled graph per (config, deps); the entry keeps deps alive, so its id can't be reused."""
    key = (config, id(deps))
    if key not in _graphs:
        run = deps
        if config != "C":  # in A and B an approved UPDATE would run as the shared HR account
            run = replace(deps, run_write=_no_writes("writes commit only in config C"))
        elif not get_settings().demo_writes:
            run = replace(deps, run_write=_no_writes("writes are disabled in this demo"))
        if config == "A":  # no validator in A, and HR owns the tables: DDL would commit for every visitor after
            run = replace(run, run_sql=_select_only(run.run_sql))
        _graphs[key] = (deps, build_graph(run, config, _saver))
    return _graphs[key][1]


def _select_only(run_sql):
    """A run_sql that refuses anything but one SELECT before it reaches the database."""

    def run(sql: str, persona: str, config: str):
        if reason := select_only(sql):
            raise SQLExecutionError(reason)
        return run_sql(sql, persona, config)

    return run


def _no_writes(reason: str):
    """A run_write that refuses; apply turns the error into "No change made: <reason>."."""

    def run_write(*_):
        raise SQLExecutionError(reason)

    return run_write


def _reply(thread_id: str, state: dict) -> dict:
    pending = state["__interrupt__"][0].value if "__interrupt__" in state else None
    return {
        "thread_id": thread_id,
        "answer": None if pending else state.get("answer"),
        "sql": state.get("write_sql") or state.get("sql"),
        "rows": [list(r) for r in (state.get("rows") or [])[:SHOWN_ROWS]],
        "pending": pending and {**pending, "rows": [list(r) for r in pending["rows"][:SHOWN_ROWS]]},
    }


@app.get("/health")
def health(deep: bool = False) -> dict:
    """deep=true also queries the database: an Always Free database stops after 7 idle days."""
    if not deep:
        return {"status": "ok"}
    try:
        with service_connection() as conn:
            conn.cursor().execute("select 1 from dual").fetchone()
    except oracledb.Error as e:
        # No token on this endpoint: the cause goes to the log, never to the caller (it names hosts).
        logging.getLogger(__name__).warning("deep health: %s", str(e).splitlines()[0])
        raise HTTPException(503, {"status": "error", "database": "unreachable"}) from e
    return {"status": "ok", "database": "ok"}


@app.post("/ask", dependencies=[Depends(require_token)])
def ask(body: AskBody, deps: Deps = Depends(get_deps)) -> dict:
    thread_id = str(uuid.uuid4())
    start = {"persona": body.persona, "config": body.config, "question": body.question, "attempts": 0, "error": None}
    state = _graph(body.config, deps).invoke(start, {"configurable": {"thread_id": thread_id}})
    _threads[thread_id] = body.config
    reply = _reply(thread_id, state)
    if reply["pending"]:
        _waiting.add(thread_id)
    return reply


@app.post("/approve", dependencies=[Depends(require_token)])
def approve(body: ApproveBody, deps: Deps = Depends(get_deps)) -> dict:
    with _claim:
        if body.thread_id not in _threads:
            raise HTTPException(404, "unknown thread")
        if body.thread_id not in _waiting:
            raise HTTPException(409, "nothing is waiting for approval in this thread")
        _waiting.discard(body.thread_id)
    graph, run = _graph(_threads[body.thread_id], deps), {"configurable": {"thread_id": body.thread_id}}
    return _reply(body.thread_id, graph.invoke(Command(resume=body.decision), run))
