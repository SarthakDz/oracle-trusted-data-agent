"""OracleMemory against the Oracle container, with Ollama embeddings: memories stay with their user."""

import pytest

from tda.memory import OracleMemory

pytestmark = [pytest.mark.integration, pytest.mark.llm]


def test_recall_is_scoped_to_the_user():
    memory = OracleMemory()
    try:
        for user in ("arao", "vmehta"):
            memory.forget(user)
        memory.remember("arao", "Remember my code word.", "Noted: KESTREL-1101.")
        memory.remember("vmehta", "Remember the offsite code word.", "Noted: KESTREL-2202.")
        mine = "\n".join(memory.recall("arao", "What code word did I give you?"))
        assert "KESTREL-1101" in mine and "KESTREL-2202" not in mine
        assert "KESTREL-1101" not in "\n".join(memory.recall("vmehta", "What did other users tell you?"))
        memory.forget("arao")
        assert memory.recall("arao", "What code word did I give you?") == []
    finally:
        for user in ("arao", "vmehta"):
            memory.forget(user)
