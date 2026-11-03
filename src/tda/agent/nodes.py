"""Graph nodes. Each takes the state (plus an injected dependency) and returns a partial state."""

import re
from collections.abc import Callable

from langgraph.types import interrupt

from tda import guards
from tda.agent import prompts
from tda.agent.state import AgentState
from tda.llm import LLMError
from tda.memory import scope
from tda.personas import PERSONAS
from tda.policy import identity_line, rules_for
from tda.sqltext import extract_sql

MAX_ATTEMPTS = 3  # SQL attempts per question: the first try plus two repairs
ROW_CAP = 200

_INTENT = re.compile(r"out[_ ]of[_ ]scope|write|read")


class SQLExecutionError(RuntimeError):
    """Oracle rejected the query. The message is the first line of the Oracle error."""


def parse_intent(text: str) -> str:
    """The earliest intent label in the reply wins. Anything unrecognised counts as a read."""
    match = _INTENT.search(text.lower())
    if not match:
        return "read"
    label = match.group(0)
    return "out_of_scope" if label.startswith("out") else label


def classify(state: AgentState, chat: Callable[[str, bool], str], intent: Callable[[str], str] | None = None) -> AgentState:
    if intent is not None:  # a decision model (Settings.classifier = "laya") instead of a chat call
        return {"intent": intent(state["question"])}
    reply = chat(prompts.CLASSIFY.format(question=state["question"]), False)
    return {"intent": parse_intent(reply)}


def retrieve_schema(state: AgentState, search: Callable[[str], str]) -> AgentState:
    return {"schema_context": search(state["question"])}


def generate_sql(state: AgentState, chat: Callable[[str, bool], str]) -> AgentState:
    persona = state["persona"]
    prompt = prompts.SQL.format(
        identity=identity_line(persona),
        rules=rules_for(persona),
        schema=state["schema_context"],
        question=state["question"],
    )
    if state.get("error"):
        prompt += prompts.REPAIR.format(sql=state.get("sql", ""), error=state["error"])
    attempts = state.get("attempts", 0) + 1
    try:
        sql = extract_sql(chat(prompt, True))
    except LLMError as e:
        return {"sql": "", "error": f"model call failed: {e}", "attempts": attempts}
    if not sql:
        return {"sql": "", "error": "model returned no SQL", "attempts": attempts}
    return {"sql": sql, "error": None, "attempts": attempts}


def execute(state: AgentState, run_sql: Callable[[str, str, str], tuple[list[str], list[tuple], bool]]) -> AgentState:
    try:
        columns, rows, truncated = run_sql(state["sql"], state["persona"], state["config"])
    except SQLExecutionError as e:
        return {"error": str(e), "rows": [], "columns": []}
    return {
        "columns": columns,
        "rows": rows[:ROW_CAP],
        "truncated": truncated or len(rows) > ROW_CAP,
        "error": None,
    }


def _answer_prompt(state: AgentState) -> str:
    rows = "\n".join(" | ".join(str(v) for v in row) for row in state["rows"])
    # shortcut: finds money by column name in the select list; SELECT * misses it (the model may then write $). The Day 5 grounding check is the real fix.
    select_list = re.split(r"\bfrom\b", state["sql"], maxsplit=1, flags=re.IGNORECASE)[0]
    money = re.search(r"\b(salary|amount)\b", select_list, re.IGNORECASE)
    return prompts.ANSWER.format(
        identity=identity_line(state["persona"]),
        question=state["question"],
        sql=state["sql"],
        columns=", ".join(state["columns"]),
        rows=rows,
        truncation=prompts.TRUNCATED.format(cap=ROW_CAP) if state.get("truncated") else "",
        money=prompts.MONEY if money else "",
    ) + _memory_block(state)


def _memory_block(state: AgentState) -> str:
    memories = state.get("memories") or []
    return prompts.MEMORY.format(memories="\n".join(memories)) if memories else ""


def answer(state: AgentState, chat: Callable[[str, bool], str]) -> AgentState:
    if state.get("error"):
        return {"answer": prompts.FAILED.format(attempts=state["attempts"], error=state["error"])}
    return {"answer": chat(_answer_prompt(state), False)}


def validate(state: AgentState) -> AgentState:
    """Configs B and C: a rejected query goes back through the repair loop with the reason as its error."""
    reason = guards.validate_sql(state["sql"])
    return {"error": reason} if reason else {}


def mask(state: AgentState) -> AgentState:
    """Configs B and C: SSN-shaped strings never reach the answer model or the caller."""
    return {"rows": guards.mask_rows(state.get("rows") or [])}


def ground(state: AgentState, chat: Callable[[str, bool], str]) -> AgentState:
    """Configs B and C: an answer with numbers the rows don't hold is regenerated once, then flagged."""
    if state.get("error"):  # the fixed failure message quotes the error, not data
        return {"answer": guards.mask_ssns(state["answer"]), "ungrounded": []}
    # Masked first: the digits of a masked SSN are not numbers to ground.
    text = guards.mask_ssns(state["answer"])
    bad = guards.ungrounded_numbers(text, state["rows"], state["question"])
    if bad:
        text = guards.mask_ssns(chat(_answer_prompt(state) + prompts.REGROUND.format(numbers=", ".join(bad)), False))
        bad = guards.ungrounded_numbers(text, state["rows"], state["question"])
        if bad:
            text += prompts.UNGROUNDED_NOTE
    return {"answer": text, "ungrounded": bad}


def refuse(state: AgentState, chat: Callable[[str, bool], str]) -> AgentState:
    """Out of scope. With memories, the request may be about this user's earlier exchanges: answer from them."""
    if not state.get("memories"):
        return {"answer": prompts.REFUSE_SCOPE}
    prompt = prompts.MEMORY_ANSWER.format(identity=identity_line(state["persona"]), question=state["question"], memory=_memory_block(state))
    return {"answer": chat(prompt, False)}


def load_memory(state: AgentState, memory) -> AgentState:
    """This user's earlier exchanges in this config most like the question (memory.scope)."""
    return {"memories": memory.recall(scope(PERSONAS[state["persona"]].username, state["config"]), state["question"])}


def save_memory(state: AgentState, memory) -> AgentState:
    memory.remember(scope(PERSONAS[state["persona"]].username, state["config"]), state["question"], state.get("answer", ""))
    return {}


def generate_write(state: AgentState, chat: Callable[[str, bool], str]) -> AgentState:
    persona = state["persona"]
    prompt = prompts.WRITE_SQL.format(
        identity=identity_line(persona),
        rules=rules_for(persona),
        schema=state["schema_context"],
        question=state["question"],
    )
    if state.get("error"):
        prompt += prompts.REPAIR.format(sql=state.get("write_sql", ""), error=state["error"])
    attempts = state.get("attempts", 0) + 1
    try:
        sql = extract_sql(chat(prompt, True))
    except LLMError as e:
        return {"write_sql": "", "error": f"model call failed: {e}", "attempts": attempts}
    if not sql:
        return {"write_sql": "", "error": "model returned no SQL", "attempts": attempts}
    return {"write_sql": sql, "error": None, "attempts": attempts}


def validate_write(state: AgentState) -> AgentState:
    """Configs B and C: one UPDATE of a column the persona may change. A badly written statement goes
    back through the repair loop; a forbidden change ends the run (Day 6, ew03: a refused email change
    came back from the repair as the same value written into the phone column)."""
    reason = guards.validate_write(state["write_sql"], state["persona"])
    if reason and not reason.startswith(guards.REPAIRABLE):
        return {"error": reason, "blocked": reason, "answer": prompts.NO_CHANGE.format(reason=reason.removeprefix("validator: "))}
    return {"error": reason} if reason else {}


def dry_run(state: AgentState, run_sql: Callable[[str, str, str], tuple[list[str], list[tuple], bool]], mask: bool = False) -> AgentState:
    """The rows the write would change, old and new values, for the approver (SSNs masked in B and C). No preview for a non-UPDATE (config A)."""
    preview = guards.preview_sql(state["write_sql"])
    if preview is None:
        return {"preview_columns": [], "preview_rows": [], "expected_rows": None, "error": None}
    try:
        columns, rows, truncated = run_sql(preview, state["persona"], state["config"])
        # The approved statement must change exactly the previewed rows; a capped preview needs the real count.
        expected = run_sql(f"select count(*) from ({preview})", state["persona"], state["config"])[1][0][0] if truncated else len(rows)
    except SQLExecutionError as e:
        return {"error": str(e)}
    if expected == 0:  # nothing to approve: say so instead of asking
        return {"preview_columns": columns, "preview_rows": [], "expected_rows": 0, "error": None, "answer": prompts.NO_CHANGE.format(reason="no rows match the request")}
    shown = guards.mask_rows(rows[:ROW_CAP]) if mask else rows[:ROW_CAP]
    return {"preview_columns": columns, "preview_rows": shown, "expected_rows": expected, "error": None}


def check_rules(state: AgentState) -> AgentState:
    """Configs B and C: the write rule DDS can't express (a raise of at most 10%), checked before anyone is asked."""
    violations = guards.rule_violations(state["preview_columns"], state["preview_rows"])
    if violations:
        return {"blocked": violations[0], "answer": prompts.NO_CHANGE.format(reason=violations[0])}
    return {}


def approve(state: AgentState) -> AgentState:
    """Pause the graph until a person approves or rejects the previewed change."""
    preview = {"sql": state["write_sql"], "columns": state["preview_columns"], "rows": state["preview_rows"], "count": state.get("expected_rows")}
    decision = interrupt(preview)
    return {"approved": decision == "approve"}


def apply(state: AgentState, run_write: Callable[[str, str, str, int | None], int] | None) -> AgentState:
    if not state.get("approved"):
        return {"answer": prompts.NO_CHANGE.format(reason="the change was rejected")}
    if run_write is None:
        return {"answer": prompts.NO_CHANGE.format(reason="writes are not configured")}
    try:
        changed = run_write(state["write_sql"], state["persona"], state["config"], state.get("expected_rows"))
    except SQLExecutionError as e:
        return {"error": str(e), "answer": prompts.NO_CHANGE.format(reason=str(e))}
    return {"changed": changed, "answer": prompts.CHANGED.format(n=changed)}


def route_after_classify(state: AgentState) -> str:
    return state["intent"] if state["intent"] in ("read", "write") else "refuse"


def route_after_schema(state: AgentState) -> str:
    return state["intent"]


def route_after_dry_run(state: AgentState) -> str:
    if not state.get("error"):
        return "nothing" if state.get("expected_rows") == 0 else "ok"
    return "retry" if state["attempts"] < MAX_ATTEMPTS else "answer"


def route_after_rules(state: AgentState) -> str:
    return "blocked" if state.get("blocked") else "ok"


def route_after_generate(state: AgentState) -> str:
    if not state.get("error"):
        return "execute"
    return "retry" if state["attempts"] < MAX_ATTEMPTS else "answer"


def route_after_validate_write(state: AgentState) -> str:
    return "blocked" if state.get("blocked") else route_after_generate(state)


def route_after_execute(state: AgentState) -> str:
    if state.get("error") and state["attempts"] < MAX_ATTEMPTS:
        return "retry"
    return "answer"
