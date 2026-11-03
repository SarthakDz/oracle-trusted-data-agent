import re

from tda.config import Settings
from tda.personas import PERSONAS


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("ORACLE_PWD", "x")
    monkeypatch.setenv("TDA_APP_PASSWORD", "a")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "y")
    s = Settings(_env_file=None)
    assert s.oracle_dsn == "localhost:1521/FREEPDB1"
    assert s.oracle_pwd == "x"
    assert s.end_user_password == "y"
    assert s.ollama_base == "http://localhost:11434"


def test_settings_agent_defaults(monkeypatch):
    monkeypatch.setenv("ORACLE_PWD", "x")
    monkeypatch.setenv("TDA_APP_PASSWORD", "a")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "y")
    monkeypatch.delenv("TDA_TRACING", raising=False)
    s = Settings(_env_file=None)
    assert (s.agent_model, s.embed_model) == ("qwen3:8b", "nomic-embed-text")
    assert s.llm_timeout_s == 300.0
    assert (s.llm_num_ctx, s.llm_max_tokens) == (8192, 7000)
    assert s.phoenix_endpoint == "http://localhost:6006/v1/traces"
    assert s.tracing is False


def test_memory_off_by_default(monkeypatch):
    # Off for every eval but the memory probe, so read and write cases stay independent of each other.
    monkeypatch.setenv("ORACLE_PWD", "x")
    monkeypatch.setenv("TDA_APP_PASSWORD", "a")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "y")
    monkeypatch.delenv("TDA_MEMORY", raising=False)
    assert Settings(_env_file=None).memory is False
    monkeypatch.setenv("TDA_MEMORY", "1")
    assert Settings(_env_file=None).memory is True


def test_settings_cache_off_by_default(monkeypatch):
    monkeypatch.setenv("ORACLE_PWD", "x")
    monkeypatch.setenv("TDA_APP_PASSWORD", "a")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "y")
    monkeypatch.delenv("TDA_LLM_CACHE", raising=False)
    assert Settings(_env_file=None).llm_cache_dir is None


def test_personas():
    assert set(PERSONAS) == {"employee", "manager", "finance_analyst", "hr_admin"}
    usernames = [p.username for p in PERSONAS.values()]
    assert len(set(usernames)) == 4
    assert all(re.fullmatch(r"[a-z0-9]+", u) for u in usernames)
    assert all(p.key == key for key, p in PERSONAS.items())
    # Every persona is also an employee, so each one can read their own row.
    assert all("employee_role" in p.data_roles for p in PERSONAS.values())


def test_settings_load_without_admin_password(monkeypatch):
    # The app container on the VM gets the app and end-user passwords, never the admin one.
    monkeypatch.delenv("ORACLE_PWD", raising=False)
    monkeypatch.setenv("TDA_APP_PASSWORD", "app-pw")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "y")
    s = Settings(_env_file=None)
    assert s.oracle_pwd is None and s.app_password == "app-pw" and s.oracle_admin_user == "sys"
