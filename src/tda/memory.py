"""Per-user memory: earlier exchanges, recalled by similarity and always scoped to one user.

OracleMemory keeps them in Oracle through `oracleagentmemory` (schema TDA_MEMORY, created by
`make db-init`), embedded with the same Ollama model as the schema index. The agent passes
scope(username, config) as the user id on every call, so one user's memories never reach
another user's context, and config A's unguarded answers never reach a config B or C prompt. The library can also scope memory rows with Deep Data
Security policies (`core.deepsec`); that is the production path, not built here.
"""

from typing import Protocol

from tda.config import get_settings

MEMORY_USER = "tda_memory"


def scope(username: str, config: str) -> str:
    """The memory user id: one user in one config, so an unguarded config A answer never reaches a config C prompt."""
    return f"{config}:{username}"


class Memory(Protocol):
    def recall(self, user: str, question: str) -> list[str]: ...

    def remember(self, user: str, question: str, answer: str) -> None: ...

    def forget(self, user: str) -> None: ...


class OracleMemory:
    def __init__(self, max_results: int = 3):
        import oracledb  # imported here: memory is off by default
        from oracleagentmemory.core import OracleAgentMemory
        from oracleagentmemory.core.embedders import Embedder

        s = get_settings()
        self.max_results = max_results
        # shortcut: one connection shared by every request; use a pool before running more than one API worker.
        self._conn = oracledb.connect(user=MEMORY_USER, password=s.app_password, dsn=s.oracle_dsn)
        self._memory = OracleAgentMemory(
            connection=self._conn,
            embedder=Embedder(model=f"ollama/{s.embed_model}", api_base=s.ollama_base),
            schema_policy="create_if_necessary",
        )

    def recall(self, user: str, question: str) -> list[str]:
        hits = self._memory.search(question, user_id=user, exact_user_match=True, max_results=self.max_results)
        return [h.content for h in hits]

    def remember(self, user: str, question: str, answer: str) -> None:
        self._memory.add_memory(f"Q: {question}\nA: {answer}", user_id=user)

    def forget(self, user: str) -> None:
        # add_memory with a user_id creates no user profile, so delete_user would find nothing: delete the records.
        while records := self._memory.list_memories(user_id=user):  # listing is capped, so repeat until empty
            for record in records:
                self._memory.delete_memory(record.id)
