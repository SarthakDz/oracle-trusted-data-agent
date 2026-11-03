from tda import cli


def test_cli_asks_before_a_write(monkeypatch, capsys):
    decisions = []

    def fake_ask(question, persona, config, approver=None):
        decisions.append(approver({"sql": "update hr.employees set phone = 'x' where email = 'arao'", "columns": ["ID"], "rows": [(10,)], "count": 1}))
        return {"intent": "write", "answer": "Done: 1 row(s) changed.", "changed": 1}

    monkeypatch.setattr(cli, "ask", fake_ask)
    monkeypatch.setattr(cli.tracing, "setup_tracing", lambda: None)
    monkeypatch.setattr(cli.tracing, "shutdown_tracing", lambda: None)
    for reply, expected in (("y", "approve"), ("", "reject")):
        monkeypatch.setattr("builtins.input", lambda prompt, r=reply: r)
        cli.main(["--persona", "employee", "Change my phone"])
        assert decisions[-1] == expected
    assert "update hr.employees" in capsys.readouterr().out


def test_cli_tells_the_total_row_count(monkeypatch, capsys):
    preview = {"sql": "update hr.expenses set status = 'approved' where status = 'submitted'", "columns": ["ID"], "rows": [(i,) for i in range(25)], "count": 612}
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert cli._ask_person(preview) == "reject"
    assert "showing 20 of 612 rows" in capsys.readouterr().out
