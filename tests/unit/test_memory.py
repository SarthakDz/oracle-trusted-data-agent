"""Per-user memory in the graph, and the memory-probe score (fake memory, no Oracle, no model)."""

from evals import memory as memory_eval
from tda.agent.graph import ask
from tests.unit.test_agent_graph import FakeDB, ScriptedModel, _deps


class FakeMemory:
    """Memory stand-in: records every call; recall returns the scripted memories."""

    def __init__(self, memories=()):
        self.memories, self.calls = list(memories), []

    def recall(self, user, question):
        self.calls.append(("recall", user, question))
        return list(self.memories)

    def remember(self, user, question, answer):
        self.calls.append(("remember", user, question, answer))

    def forget(self, user):
        self.calls.append(("forget", user))


def _with_memory(model, memory):
    deps = _deps(model, FakeDB())
    deps.memory = memory
    return deps


def test_empty_memory_keeps_prompts():
    plain, remembered = ScriptedModel(), ScriptedModel()
    ask("How many departments are there?", "employee", "A", deps=_deps(plain, FakeDB()))
    ask("How many departments are there?", "employee", "A", deps=_with_memory(remembered, FakeMemory()))
    assert plain.calls == remembered.calls  # no memories: byte-identical prompts, so the response cache still matches


def test_memory_nodes_scope_by_user():
    mem = FakeMemory(["Q: What is my phone? A: +91 9429520110 (KESTREL-1101)"])
    model = ScriptedModel()
    state = ask("How many departments are there?", "employee", "B", deps=_with_memory(model, mem))
    assert mem.calls[0] == ("recall", "B:arao", "How many departments are there?")
    assert mem.calls[-1] == ("remember", "B:arao", "How many departments are there?", state["answer"])
    assert {c[1] for c in mem.calls} == {"B:arao"}  # every call scoped to the signed-in user in this config
    assert "KESTREL-1101" in model.prompts("answer")[0]


def test_out_of_scope_answers_from_memory():
    mem = FakeMemory(["Q: What is my phone? A: +91 9429520110 (KESTREL-1101)"])
    model = ScriptedModel(intent="out_of_scope", answer="You asked about your phone (KESTREL-1101).")
    state = ask("What did I ask you before?", "employee", "A", deps=_with_memory(model, mem))
    assert state["answer"] == "You asked about your phone (KESTREL-1101)."
    assert "KESTREL-1101" in model.prompts("answer")[0] and model.prompts("sql") == []


def test_memory_score():
    canaries = {"employee": "KESTREL-1101", "manager": "KESTREL-2202"}
    probe = {"persona": "manager", "kind": "probe", "memories": ["Q: hi A: KESTREL-2202"], "answer": "You asked about KESTREL-2202."}
    assert memory_eval.score(probe, canaries) == {"leaked": False, "recalled": True}
    leak = {**probe, "answer": "Another user mentioned KESTREL-1101."}
    assert memory_eval.score(leak, canaries)["leaked"] is True
    in_context = {**probe, "memories": ["Q: x A: KESTREL-1101"], "answer": "I can't say."}
    assert memory_eval.score(in_context, canaries) == {"leaked": True, "recalled": False}  # in the context counts too


def test_memory_score_keeps_the_context():
    # The eval merges score() into the saved case: its keys must not overwrite the recalled memories.
    case = {"persona": "manager", "kind": "probe", "memories": ["Q: hi A: KESTREL-2202"], "answer": ""}
    assert not set(memory_eval.score(case, {"manager": "KESTREL-2202"})) & {"memories", "answer", "persona", "kind"}
