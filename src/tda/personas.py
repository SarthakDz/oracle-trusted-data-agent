"""The four signed-in users the agent serves. Each is a Deep Data Security local end user."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    key: str
    username: str  # DDS end-user name; also the value in HR.EMPLOYEES.EMAIL
    data_roles: tuple[str, ...]


PERSONAS: dict[str, Persona] = {
    p.key: p
    for p in (
        Persona("employee", "arao", ("employee_role",)),
        Persona("manager", "vmehta", ("employee_role", "manager_role")),
        Persona("finance_analyst", "niyer", ("employee_role", "finance_role")),
        Persona("hr_admin", "rkhanna", ("employee_role", "hr_admin_role")),
    )
}
