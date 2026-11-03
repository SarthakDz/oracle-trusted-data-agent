"""Connections to Oracle AI Database 26ai Free (python-oracledb thin mode)."""

import oracledb

from tda.config import get_settings
from tda.personas import PERSONAS


def sys_connection() -> oracledb.Connection:
    """The admin account: SYS as SYSDBA on Free, ADMIN on Autonomous AI Database (no SYSDBA there)."""
    s = get_settings()
    if s.oracle_pwd is None:
        raise RuntimeError("ORACLE_PWD is not set: only dbinit and the admin tests need the admin password")
    mode = {"mode": oracledb.AUTH_MODE_SYSDBA} if s.oracle_admin_user.lower() == "sys" else {}
    return oracledb.connect(user=s.oracle_admin_user, password=s.oracle_pwd, dsn=s.oracle_dsn, **mode)


def service_connection() -> oracledb.Connection:
    """The shared service account (schema owner HR): the baseline for configs A and B."""
    s = get_settings()
    return oracledb.connect(user="hr", password=s.app_password, dsn=s.oracle_dsn)


def end_user_connection(persona_key: str) -> oracledb.Connection:
    """A DDS local end user session, so Deep Data Security filters every query (config C)."""
    s = get_settings()
    return oracledb.connect(user=PERSONAS[persona_key].username, password=s.end_user_password, dsn=s.oracle_dsn)
