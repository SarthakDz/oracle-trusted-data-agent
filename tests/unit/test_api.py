"""The HTTP API with a scripted model and a fake database (no Oracle, no Ollama)."""

import pytest
from fastapi.testclient import TestClient

from tda import api
from tda.config import get_settings
from tests.unit.test_agent_graph import OWN_PHONE, PHONE_PREVIEW, FakeDB, FakeWriter, ScriptedModel, _deps

TOKEN = {"Authorization": "Bearer demo-secret"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORACLE_PWD", "x")
    monkeypatch.setenv("TDA_APP_PASSWORD", "a")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "y")
    monkeypatch.setenv("TDA_DEMO_TOKEN", "demo-secret")
    monkeypatch.setenv("TDA_DEMO_WRITES", "0")  # pinned, so a TDA_DEMO_WRITES=1 in .env can't reach the tests
    get_settings.cache_clear()

    def use(model, db=None, writer=None):
        deps = _deps(model, db or FakeDB(), writer=writer)
        api.app.dependency_overrides[api.get_deps] = lambda: deps
        return deps

    yield TestClient(api.app), use
    api.app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_health_needs_no_token(client):
    http, _ = client
    assert http.get("/health").json() == {"status": "ok"}


def test_token_required(client, monkeypatch):
    http, use = client
    use(ScriptedModel())
    body = {"persona": "employee", "question": "How many departments?"}
    assert http.post("/ask", json=body).status_code == 401
    assert http.post("/ask", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    monkeypatch.setenv("TDA_DEMO_TOKEN", "")  # not delenv: settings would fall back to a token in .env
    get_settings.cache_clear()
    assert http.post("/ask", json=body, headers=TOKEN).status_code == 503  # no token configured: closed, not open


def test_ask_read(client):
    http, use = client
    use(ScriptedModel())
    reply = http.post("/ask", json={"persona": "employee", "question": "How many departments?"}, headers=TOKEN).json()
    assert reply["answer"] == "There are 8." and reply["rows"] == [[8]] and reply["pending"] is None
    assert reply["sql"] == "select count(*) from hr.departments" and reply["thread_id"]


def test_public_config_a_runs_only_selects(client):
    # A has no validator and HR owns the tables: DDL from the model would commit for every visitor after.
    http, use = client
    db = FakeDB()
    use(ScriptedModel(sqls=("truncate table hr.expenses",)), db)
    http.post("/ask", json={"persona": "employee", "question": "Empty the expenses.", "config": "A"}, headers=TOKEN)
    assert db.calls == []
    use(ScriptedModel(), db)  # a SELECT still runs, unvalidated, as A was measured
    http.post("/ask", json={"persona": "employee", "question": "How many departments?", "config": "A"}, headers=TOKEN)
    assert [sql for sql, _, _ in db.calls] == ["select count(*) from hr.departments"]


def test_bad_persona_or_config_422(client):
    http, use = client
    use(ScriptedModel())
    assert http.post("/ask", json={"persona": "ceo", "question": "q"}, headers=TOKEN).status_code == 422
    assert http.post("/ask", json={"persona": "employee", "question": "q", "config": "D"}, headers=TOKEN).status_code == 422


def test_write_then_approve(client, monkeypatch):
    http, use = client
    monkeypatch.setenv("TDA_DEMO_WRITES", "1")
    writer = FakeWriter()
    use(ScriptedModel(intent="write", writes=(OWN_PHONE,)), FakeDB(PHONE_PREVIEW), writer)
    asked = http.post("/ask", json={"persona": "employee", "question": "Change my phone"}, headers=TOKEN).json()
    assert asked["pending"]["sql"] == OWN_PHONE and asked["pending"]["columns"] == ["ID", "OLD_PHONE", "NEW_PHONE"]
    assert writer.calls == []
    done = http.post("/approve", json={"thread_id": asked["thread_id"], "decision": "approve"}, headers=TOKEN).json()
    assert done["answer"].startswith("Done") and done["pending"] is None
    assert writer.calls == [(OWN_PHONE, "employee", "C", 1)]  # the API defaults to config C


def test_reject_changes_nothing(client):
    http, use = client
    writer = FakeWriter()
    use(ScriptedModel(intent="write", writes=(OWN_PHONE,)), FakeDB(PHONE_PREVIEW), writer)
    asked = http.post("/ask", json={"persona": "employee", "question": "Change my phone"}, headers=TOKEN).json()
    done = http.post("/approve", json={"thread_id": asked["thread_id"], "decision": "reject"}, headers=TOKEN).json()
    assert done["answer"].startswith("No change made") and writer.calls == []


def test_approve_unknown_thread_404(client):
    http, use = client
    use(ScriptedModel())
    assert http.post("/approve", json={"thread_id": "nope", "decision": "approve"}, headers=TOKEN).status_code == 404


def test_approve_twice_409(client, monkeypatch):
    http, use = client
    monkeypatch.setenv("TDA_DEMO_WRITES", "1")
    writer = FakeWriter()
    use(ScriptedModel(intent="write", writes=(OWN_PHONE,)), FakeDB(PHONE_PREVIEW), writer)
    asked = http.post("/ask", json={"persona": "employee", "question": "Change my phone"}, headers=TOKEN).json()
    approve = {"thread_id": asked["thread_id"], "decision": "approve"}
    assert http.post("/approve", json=approve, headers=TOKEN).status_code == 200
    assert http.post("/approve", json=approve, headers=TOKEN).status_code == 409  # nothing pending any more
    assert len(writer.calls) == 1


def test_overlapping_approvals_apply_once(client, monkeypatch):
    # A double click: the second /approve arrives while the first is still inside apply.
    import threading
    import time

    class SlowWriter(FakeWriter):
        def __call__(self, *args):
            time.sleep(0.3)
            return super().__call__(*args)

    http, use = client
    monkeypatch.setenv("TDA_DEMO_WRITES", "1")
    writer = SlowWriter()
    use(ScriptedModel(intent="write", writes=(OWN_PHONE,)), FakeDB(PHONE_PREVIEW), writer)
    asked = http.post("/ask", json={"persona": "employee", "question": "Change my phone"}, headers=TOKEN).json()
    approve = {"thread_id": asked["thread_id"], "decision": "approve"}
    codes = []
    calls = [threading.Thread(target=lambda: codes.append(http.post("/approve", json=approve, headers=TOKEN).status_code)) for _ in range(2)]
    for t in calls:
        t.start()
    for t in calls:
        t.join()
    assert sorted(codes) == [200, 409]
    assert len(writer.calls) == 1


def test_api_commits_writes_only_in_config_c(client):
    # In A and B an approved UPDATE would run as the shared HR account: the public demo must not allow it.
    http, use = client
    writer = FakeWriter()
    use(ScriptedModel(intent="write", writes=(OWN_PHONE,)), FakeDB(PHONE_PREVIEW), writer)
    for config in ("A", "B"):
        asked = http.post("/ask", json={"persona": "employee", "question": "Change my phone", "config": config}, headers=TOKEN).json()
        done = http.post("/approve", json={"thread_id": asked["thread_id"], "decision": "approve"}, headers=TOKEN).json()
        assert done["answer"].startswith("No change made")
    assert writer.calls == []


def test_public_demo_commits_no_writes_by_default(client):
    # One visitor holding the shared token must not change the demo data for everyone after.
    http, use = client
    writer = FakeWriter()
    use(ScriptedModel(intent="write", writes=(OWN_PHONE,)), FakeDB(PHONE_PREVIEW), writer)
    asked = http.post("/ask", json={"persona": "employee", "question": "Change my phone"}, headers=TOKEN).json()
    assert asked["pending"]["sql"] == OWN_PHONE  # the preview still shows
    done = http.post("/approve", json={"thread_id": asked["thread_id"], "decision": "approve"}, headers=TOKEN).json()
    assert done["answer"] == "No change made: writes are disabled in this demo." and writer.calls == []


def test_deep_health_reports_the_database(client, monkeypatch):
    # An Always Free database stops after 7 idle days; the public check says so without the error's details.
    import oracledb

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return self

        def execute(self, sql):
            assert sql == "select 1 from dual"
            return self

        def fetchone(self):
            return (1,)

    http, _ = client
    assert http.get("/health").json() == {"status": "ok"}  # no database call
    monkeypatch.setattr(api, "service_connection", lambda: Conn())
    assert http.get("/health?deep=true").json() == {"status": "ok", "database": "ok"}

    def down():
        raise oracledb.DatabaseError("DPY-6005: cannot connect to database (host adb.example.oraclecloud.com)")

    monkeypatch.setattr(api, "service_connection", down)
    r = http.get("/health?deep=true")
    assert r.status_code == 503 and r.json() == {"detail": {"status": "error", "database": "unreachable"}}
