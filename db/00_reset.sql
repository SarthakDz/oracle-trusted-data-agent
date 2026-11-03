-- Drop everything db/01..06 create, so `make db-init` can run any number of times.
-- Runs as the admin user (SYS in FREEPDB1, ADMIN on Autonomous AI Database). Only "does not exist" errors are ignored; anything else stops the run.
declare
  procedure drop_if_exists(p_sql varchar2) is
  begin
    execute immediate p_sql;
  exception
    when others then
      -- Does not exist: ORA-01918 user, ORA-01919 role, ORA-00942 table or view, ORA-04043 object,
      -- ORA-52515 end user, ORA-52507 data role, ORA-52552 data grant, ORA-52553 data grant owner.
      if sqlcode not in (-1918, -1919, -942, -4043, -52515, -52507, -52552, -52553) then
        raise;
      end if;
  end;
begin
  for g in (select column_value as name from table(sys.odcivarchar2list(
              'employee_self', 'employee_own_expenses', 'all_departments', 'manager_reports',
              'manager_report_expenses', 'finance_expenses', 'finance_directory', 'hr_admin_directory'))) loop
    drop_if_exists('drop data grant hr.' || g.name);
  end loop;
  for u in (select column_value as name from table(sys.odcivarchar2list('arao', 'vmehta', 'niyer', 'rkhanna'))) loop
    drop_if_exists('drop end user ' || u.name);
  end loop;
  for r in (select column_value as name from table(sys.odcivarchar2list(
              'employee_role', 'manager_role', 'finance_role', 'hr_admin_role'))) loop
    drop_if_exists('drop data role ' || r.name);
  end loop;
  drop_if_exists('drop role tda_connect');
  drop_if_exists('drop user tda_memory cascade');
  drop_if_exists('drop user hr cascade');
end;
/
