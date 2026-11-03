"""Wire the nodes into a LangGraph graph.

Config A, reads:
classify -> retrieve_schema -> generate_sql -> execute -> answer
              (out of scope -> refuse)   (error -> generate_sql, at most MAX_ATTEMPTS)

Configs B and C add three guards on the same path:
generate_sql -> validate_sql -> execute -> mask_rows -> answer -> ground
                (rejected -> generate_sql, inside the same MAX_ATTEMPTS)
C also runs every query as the persona's DDS end user (runtime.py).

Writes (Day 6), after retrieve_schema:
A:    generate_write -> dry_run -> approve -> apply
B, C: generate_write -> validate_write -> dry_run -> check_rules -> approve -> apply
(validate_write repairs a badly written statement; a forbidden change ends with "No change made")
dry_run previews the rows an UPDATE would change (no rows: "No change made", nobody is asked); approve pauses the graph (interrupt)
until a person answers "approve" or "reject"; apply commits only the previewed row count.

With memory on (Deps.memory, off by default), load_memory runs before classify and
save_memory before the end, both scoped to the signed-in user.
"""

import uuid
from collections.abc import Callable

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from tda.agent import nodes
from tda.agent.state import AgentState, Deps

CONFIGS_AVAILABLE = ("A", "B", "C")
GUARDED = ("B", "C")


def build_graph(deps: Deps, config: str = "A", checkpointer=None):
    guarded = config in GUARDED
    graph = StateGraph(AgentState)
    graph.add_node("classify", lambda s: nodes.classify(s, deps.chat, deps.intent))
    graph.add_node("retrieve_schema", lambda s: nodes.retrieve_schema(s, deps.search))
    graph.add_node("generate_sql", lambda s: nodes.generate_sql(s, deps.chat))
    graph.add_node("execute", lambda s: nodes.execute(s, deps.run_sql))
    graph.add_node("answer", lambda s: nodes.answer(s, deps.chat))
    graph.add_node("refuse", lambda s: nodes.refuse(s, deps.chat))
    graph.add_node("generate_write", lambda s: nodes.generate_write(s, deps.chat))
    graph.add_node("dry_run", lambda s: nodes.dry_run(s, deps.run_sql, mask=guarded))
    graph.add_node("approve", nodes.approve)
    graph.add_node("apply", lambda s: nodes.apply(s, deps.run_write))

    end = END
    if deps.memory is None:
        graph.add_edge(START, "classify")
    else:
        graph.add_node("load_memory", lambda s: nodes.load_memory(s, deps.memory))
        graph.add_node("save_memory", lambda s: nodes.save_memory(s, deps.memory))
        graph.add_edge(START, "load_memory")
        graph.add_edge("load_memory", "classify")
        graph.add_edge("save_memory", END)
        end = "save_memory"
    graph.add_conditional_edges(
        "classify", nodes.route_after_classify, {"read": "retrieve_schema", "write": "retrieve_schema", "refuse": "refuse"}
    )
    graph.add_conditional_edges("retrieve_schema", nodes.route_after_schema, {"read": "generate_sql", "write": "generate_write"})
    run = "validate_sql" if guarded else "execute"
    graph.add_conditional_edges(
        "generate_sql", nodes.route_after_generate, {"execute": run, "retry": "generate_sql", "answer": "answer"}
    )
    graph.add_conditional_edges(
        "execute", nodes.route_after_execute, {"retry": "generate_sql", "answer": "mask_rows" if guarded else "answer"}
    )
    preview = "validate_write" if guarded else "dry_run"
    graph.add_conditional_edges(
        "generate_write", nodes.route_after_generate, {"execute": preview, "retry": "generate_write", "answer": "answer"}
    )
    graph.add_conditional_edges(
        "dry_run", nodes.route_after_dry_run, {"ok": "check_rules" if guarded else "approve", "nothing": end, "retry": "generate_write", "answer": "answer"}
    )
    graph.add_edge("approve", "apply")
    graph.add_edge("apply", end)
    graph.add_edge("refuse", end)
    if not guarded:
        graph.add_edge("answer", end)
        return graph.compile(checkpointer=checkpointer)

    graph.add_node("validate_sql", nodes.validate)
    graph.add_node("mask_rows", nodes.mask)
    graph.add_node("ground", lambda s: nodes.ground(s, deps.chat))
    graph.add_node("validate_write", nodes.validate_write)
    graph.add_node("check_rules", nodes.check_rules)
    # A rejected query routes exactly like a failed generation: repair, or report after the last attempt.
    graph.add_conditional_edges(
        "validate_sql", nodes.route_after_generate, {"execute": "execute", "retry": "generate_sql", "answer": "answer"}
    )
    graph.add_conditional_edges(
        "validate_write", nodes.route_after_validate_write, {"execute": "dry_run", "retry": "generate_write", "answer": "answer", "blocked": end}
    )
    graph.add_conditional_edges("check_rules", nodes.route_after_rules, {"ok": "approve", "blocked": end})
    graph.add_edge("mask_rows", "answer")
    graph.add_edge("answer", "ground")
    graph.add_edge("ground", end)
    return graph.compile(checkpointer=checkpointer)


def ask(
    question: str,
    persona: str,
    config: str = "A",
    deps: Deps | None = None,
    approver: Callable[[dict], str] | None = None,
) -> AgentState:
    """Run one request. A proposed write goes to approver(preview) -> "approve" | "reject"; with no
    approver the state comes back with `pending` (the preview) and `thread_id`, still waiting."""
    if config not in CONFIGS_AVAILABLE:
        raise ValueError(f"unknown config {config}; expected one of {CONFIGS_AVAILABLE}")
    if deps is None:
        from tda.agent.runtime import default_deps  # imported here: it needs Oracle and Ollama

        deps = default_deps()
    graph = build_graph(deps, config, InMemorySaver())
    thread_id = str(uuid.uuid4())
    run = {"configurable": {"thread_id": thread_id}}
    start: AgentState = {"persona": persona, "config": config, "question": question, "attempts": 0, "error": None}
    state = graph.invoke(start, run)
    while "__interrupt__" in state:
        payload = state.pop("__interrupt__")[0].value
        if approver is None:
            return {**state, "pending": payload, "thread_id": thread_id}
        state = graph.invoke(Command(resume=approver(payload)), run)
    return state
