"""One real end-to-end question: Oracle + Ollama (qwen3:8b with thinking for SQL) + the vector index."""

import pytest

from tda.agent.graph import ask
from tda.db import service_connection
from tda.schema_index import build_index

pytestmark = [pytest.mark.integration, pytest.mark.llm]


@pytest.fixture(scope="module", autouse=True)
def indexed():
    with service_connection() as conn:
        build_index(conn)


def test_ask_real_model_counts_departments():
    state = ask("How many departments are there?", "employee")
    assert state["rows"] == [(8,)], state.get("sql")
    assert "8" in state["answer"]
