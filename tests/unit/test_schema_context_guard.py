import pytest

from tda import schema_index


def test_schema_context_fails_loudly_when_index_empty(monkeypatch):
    # db-init recreates HR.SCHEMA_DOCS empty; the Day 3 first runs then went without any
    # column notes, silently. An empty index must stop the agent instead.
    monkeypatch.setattr(schema_index, "search", lambda conn, question, k=8: [])
    with pytest.raises(RuntimeError, match="make index"):
        schema_index.schema_context(None, "how many expenses?")
