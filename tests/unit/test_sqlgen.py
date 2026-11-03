import types

import litellm

from evals.sqlgen import extract_sql, generate_sql, is_select


def _fake_completion(sent: dict):
    def completion(**kwargs):
        sent.update(kwargs)
        message = types.SimpleNamespace(content="```sql\nselect 1 from dual;\n```")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    return completion


def test_generate_sql_forwards_think_flag(monkeypatch):
    sent: dict = {}
    monkeypatch.setattr(litellm, "completion", _fake_completion(sent))
    assert generate_sql("m:1b", "q", "schema", think=False) == "select 1 from dual"
    assert sent["think"] is False
    assert sent["model"] == "ollama_chat/m:1b"


def test_generate_sql_omits_think_by_default(monkeypatch):
    sent: dict = {}
    monkeypatch.setattr(litellm, "completion", _fake_completion(sent))
    generate_sql("m:1b", "q", "schema")
    assert "think" not in sent


def test_is_select_accepts_queries_only():
    assert is_select("select 1 from dual")
    assert is_select("  WITH t AS (select 1 x from dual) select x from t")
    assert not is_select("delete from hr.employees")
    assert not is_select("update hr.employees set salary = 0")
    assert not is_select("begin null; end;")


def test_extract_sql_from_fence_with_semicolon():
    text = "Here you go:\n```sql\nSELECT * FROM hr.employees;\n```\nDone."
    assert extract_sql(text) == "SELECT * FROM hr.employees"


def test_extract_sql_plain_text_passes_through():
    assert extract_sql("  select 1 from dual  ") == "select 1 from dual"


def test_extract_sql_unlabelled_fence():
    assert extract_sql("```\nselect 2 from dual;\n```") == "select 2 from dual"


def test_extract_sql_drops_thinking():
    # Thinking models put reasoning in <think> blocks before the answer.
    text = "<think>The ```sql guess``` is wrong</think>\nselect 3 from dual;"
    assert extract_sql(text) == "select 3 from dual"
