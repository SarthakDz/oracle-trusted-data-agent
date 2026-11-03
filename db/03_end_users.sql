-- Deep Data Security identities. Runs as the admin user (SYS in FREEPDB1, ADMIN on Autonomous AI Database).
-- Local end users own no schema; usernames match src/tda/personas.py and HR.EMPLOYEES.EMAIL.
create end user arao identified by "&END_USER_PASSWORD"
/
create end user vmehta identified by "&END_USER_PASSWORD"
/
create end user niyer identified by "&END_USER_PASSWORD"
/
create end user rkhanna identified by "&END_USER_PASSWORD"
/
create data role employee_role
/
create data role manager_role
/
create data role finance_role
/
create data role hr_admin_role
/
-- A plain role carrying CREATE SESSION, so every data role can log in.
create role tda_connect
/
grant create session to tda_connect
/
grant tda_connect to employee_role
/
grant tda_connect to manager_role
/
grant tda_connect to finance_role
/
grant tda_connect to hr_admin_role
/
grant data role employee_role to arao
/
grant data role employee_role to vmehta
/
grant data role manager_role to vmehta
/
grant data role employee_role to niyer
/
grant data role finance_role to niyer
/
grant data role employee_role to rkhanna
/
grant data role hr_admin_role to rkhanna
/
