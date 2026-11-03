-- The schema that holds per-user agent memory (oracleagentmemory creates its tables in it on first use).
-- Runs as the admin user (SYS in FREEPDB1, ADMIN on Autonomous AI Database). The library installs a PL/SQL package and a text index, so it needs
-- the developer role and Oracle Text (CTXAPP); create table/sequence/view/procedure alone fail with ORA-01031.
create user tda_memory identified by "&APP_PWD" default tablespace &TABLESPACE quota unlimited on &TABLESPACE
/
grant db_developer_role, ctxapp to tda_memory
/
