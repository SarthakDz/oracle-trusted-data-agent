-- HR schema. Runs as the admin user (SYS in FREEPDB1, ADMIN on Autonomous AI Database). Column names match the dataclasses in src/tda/seed.py.
create user hr identified by "&APP_PWD" default tablespace &TABLESPACE quota unlimited on &TABLESPACE
/
grant create session to hr
/
create table hr.departments (
  dept_id  number       primary key,
  code     varchar2(10) not null unique,
  name     varchar2(60) not null
)
/
create table hr.employees (
  employee_id    number        primary key,
  first_name     varchar2(40)  not null,
  last_name      varchar2(40)  not null,
  email          varchar2(40)  not null unique,
  dept_id        number        not null references hr.departments,
  manager_email  varchar2(40),
  job            varchar2(60)  not null,
  salary         number(10)    not null,
  ssn            varchar2(11)  not null unique,
  phone          varchar2(20)  not null unique,
  notes          varchar2(400)
)
/
-- employee_email and manager_email are copied from the employee row, so every
-- DDS predicate on expenses is a plain column comparison.
create table hr.expenses (
  expense_id      number        primary key,
  employee_id     number        not null references hr.employees,
  employee_email  varchar2(40)  not null,
  manager_email   varchar2(40),
  amount          number(12,2)  not null,
  category        varchar2(30)  not null,
  status          varchar2(12)  not null,
  submitted_at    date          not null,
  description     varchar2(400) not null
)
/
