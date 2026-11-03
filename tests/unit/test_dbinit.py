from tda.dbinit import render_sql


def test_render_sql_splits_on_slash_lines():
    text = "create table t (x number)\n/\nbegin\n  null;\nend;\n/\n-- trailing comment\n"
    assert render_sql(text) == ["create table t (x number)", "begin\n  null;\nend;"]


def test_render_sql_substitutes_params():
    text = 'create user hr identified by "&ORACLE_PWD"\n/\n'
    assert render_sql(text, {"ORACLE_PWD": "Secret1x"}) == ['create user hr identified by "Secret1x"']


def test_render_sql_skips_comment_only_chunks():
    assert render_sql("-- only a comment\n/\n\n/\n") == []


def test_schema_sql_uses_the_default_tablespace():
    # Free's default tablespace is USERS, Autonomous AI Database's is DATA: dbinit asks the database.
    from tda.dbinit import DB_DIR

    for name in ("01_schema.sql", "06_agent_memory.sql"):
        sql = render_sql((DB_DIR / name).read_text(), {"APP_PWD": "p", "TABLESPACE": "DATA"})[0]
        assert 'identified by "p" default tablespace DATA quota unlimited on DATA' in sql and "users" not in sql
