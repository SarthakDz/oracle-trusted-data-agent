-- Deep Data Security grants: which rows, columns and cells each data role may read or change.
-- Runs as the admin user (SYS in FREEPDB1, ADMIN on Autonomous AI Database). A user holding several data roles gets the union of their grants.
create or replace data grant hr.employee_self
as select, update(phone)
on hr.employees
where lower(email) = lower(ORA_END_USER_CONTEXT.username)
to employee_role
/
create or replace data grant hr.employee_own_expenses
as select
on hr.expenses
where lower(employee_email) = lower(ORA_END_USER_CONTEXT.username)
to employee_role
/
create or replace data grant hr.all_departments
as select
on hr.departments
to employee_role
/
create or replace data grant hr.manager_reports
as select(all columns except ssn), update(salary)
on hr.employees
where lower(manager_email) = lower(ORA_END_USER_CONTEXT.username)
to manager_role
/
create or replace data grant hr.manager_report_expenses
as select, update(status)
on hr.expenses
where lower(manager_email) = lower(ORA_END_USER_CONTEXT.username)
to manager_role
/
create or replace data grant hr.finance_expenses
as select
on hr.expenses
to finance_role
/
create or replace data grant hr.finance_directory
as select(employee_id, first_name, last_name, dept_id)
on hr.employees
to finance_role
/
create or replace data grant hr.hr_admin_directory
as select(all columns except ssn)
on hr.employees
to hr_admin_role
/
