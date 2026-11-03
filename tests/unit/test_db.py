"""Connection settings: who connects as what (no database needed)."""

import oracledb
import pytest

from tda import db
from tda.config import Settings


@pytest.fixture
def settings(monkeypatch):
    for name in ("ORACLE_PWD", "ORACLE_ADMIN_USER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TDA_APP_PASSWORD", "app-pw")
    monkeypatch.setenv("TDA_END_USER_PASSWORD", "end-pw")
    calls = []
    monkeypatch.setattr(db.oracledb, "connect", lambda **kwargs: calls.append(kwargs))

    def use(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(db, "get_settings", lambda: Settings(_env_file=None))
        return calls

    return use


def test_sys_connection_needs_the_admin_password(settings):
    # The cloud app runs without it: only dbinit and the admin tests may ask for it.
    settings()
    with pytest.raises(RuntimeError, match="ORACLE_PWD"):
        db.sys_connection()


def test_admin_connection_mode(settings):
    calls = settings(ORACLE_PWD="admin-pw")
    db.sys_connection()
    assert calls[-1]["user"] == "sys" and calls[-1]["mode"] == oracledb.AUTH_MODE_SYSDBA
    settings(ORACLE_ADMIN_USER="admin")  # Autonomous AI Database: ADMIN, never SYSDBA
    db.sys_connection()
    assert calls[-1]["user"] == "admin" and "mode" not in calls[-1]
    assert calls[-1]["password"] == "admin-pw"


def test_service_connection_uses_the_app_password(settings):
    calls = settings(ORACLE_PWD="admin-pw")
    db.service_connection()
    assert calls[-1]["user"] == "hr" and calls[-1]["password"] == "app-pw"
