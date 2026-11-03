from tda.personas import PERSONAS
from tda.policy import ROLE_RULES, identity_line, rules_for


def test_every_persona_role_has_rules():
    roles = {role for p in PERSONAS.values() for role in p.data_roles}
    assert roles <= set(ROLE_RULES)


def test_manager_rules_mention_ssn():
    assert "ssn" in ROLE_RULES["manager_role"].lower()


def test_rules_for_combines_roles():
    text = rules_for("manager")
    assert ROLE_RULES["employee_role"] in text
    assert ROLE_RULES["manager_role"] in text


def test_identity_line_names_username():
    line = identity_line("employee")
    assert "arao" in line and "employee" in line


def test_manager_team_means_direct_reports():
    # Day 3 mj06: my team was read as the manager plus the reports.
    assert "their team means these direct reports, not themselves" in ROLE_RULES["manager_role"]
