import json

import evals.attacks as attacks
from evals.attacks import result_path, summarize_attacks, summarize_controls
from evals.report import write_attacks_report, write_report


def _attack(cid, category, leaks=(), refused=False, error=None):
    return {"id": cid, "persona": "employee", "category": category, "question": f"q {cid}", "leaks": list(leaks),
            "leaked": bool(leaks), "refused": refused, "error": error, "answer": "a"}


ROWS_LEAK = {"kind": "ssn", "where": "rows", "value": "123-45-6789"}
ANSWER_LEAK = {"kind": "salary", "where": "answer", "value": "87431"}
ATTACKS = [
    _attack("ed01", "direct", [ROWS_LEAK, ANSWER_LEAK]),
    _attack("ed02", "direct", error="model returned no SQL"),
    _attack("er01", "roleplay", refused=True),
    _attack("es01", "sql_trick", [ROWS_LEAK], error=None),
]
CONTROLS = [
    {"id": "ce01", "persona": "employee", "question": "q", "over_refused": False, "correct": True, "leaked": False,
     "error": None, "answer": "INR 87,431"},
    {"id": "ce02", "persona": "employee", "question": "q", "over_refused": True, "correct": False, "leaked": False,
     "error": None, "answer": "I can only answer questions about HR and expense data."},
]


def test_summarize_attacks():
    s = summarize_attacks(ATTACKS)
    assert s["leak_rate"] == 0.5
    assert s["by_category"] == {"direct": 0.5, "roleplay": 0.0, "sql_trick": 1.0}
    assert (s["rows_leak_rate"], s["answer_leak_rate"], s["refused_rate"]) == (0.5, 0.25, 0.25)


def test_summarize_controls():
    assert summarize_controls(CONTROLS) == {"over_refusal_rate": 0.5, "accuracy": 0.5, "leak_rate": 0.0}


def test_run_scores_leaks_refusals_and_crashes(monkeypatch):
    cases = {
        attacks.ATTACKS: [_attack("ed01", "direct"), _attack("ed02", "direct")],
        attacks.CONTROLS: [{"id": "ce01", "persona": "employee", "question": "q ce01", "gold_sql": "x"}],
    }
    states = {
        "q ed01": {"intent": "read", "rows": [("123-45-6789",)], "answer": "here", "error": None},
        "q ce01": {"intent": "out_of_scope", "answer": "I can only answer..."},
    }

    def fake_ask(question, persona, config, deps, approver=None):
        # A read eval must never write: every proposed change is rejected (Day 6).
        assert approver is not None and approver({"sql": "update hr.employees set phone = 'x'", "columns": [], "rows": []}) == "reject"
        if question not in states:
            raise RuntimeError("graph blew up")
        return states[question]

    monkeypatch.setattr(attacks, "load", lambda path: cases[path])
    monkeypatch.setattr(attacks, "model_digest", lambda model: "sha256:d1")
    monkeypatch.setattr(attacks, "expected_rows", lambda cs: {"ce01": [(1,)]})
    monkeypatch.setattr(attacks, "forbidden_values", lambda persona: {"ssn": {"123-45-6789"}})
    monkeypatch.setattr(attacks, "chat", lambda *a, **k: "OK")
    monkeypatch.setattr(attacks, "default_deps", lambda model: None)
    monkeypatch.setattr(attacks, "ask", fake_ask)
    run = attacks.run("A", "fake:1b")
    leaked, crashed = run["attacks"]
    assert leaked["leaked"] and leaked["leaks"] == [{"kind": "ssn", "where": "rows", "value": "123-45-6789"}]
    assert not crashed["leaked"] and "RuntimeError" in crashed["error"]
    (control,) = run["controls"]
    assert control["refused"] and control["over_refused"] and not control["correct"]


def test_attacks_report_and_accuracy_report_stay_apart(tmp_path):
    run = {"config": "A", "model": "m1:1b", "digest": "sha256:0123456789abcdef", "date": "2026-10-30",
           "attacks": ATTACKS, "controls": CONTROLS}
    (tmp_path / result_path("2026-10-30", "A", "m1:1b").name).write_text(json.dumps(run))
    text = write_attacks_report(tmp_path).read_text()
    assert "| A | m1:1b | `0123456789ab` | **50.0%** |" in text
    assert "| 25% | 25% | 50% | 50% |" in text  # refused, errors, over-refusal, control accuracy
    assert "`ed01`" in text and "`ce02`" in text and "`ed02`" not in text
    assert "## Misses" not in write_report(tmp_path).read_text()  # the accuracy report ignores attack files


def test_matrix_joins_accuracy_and_attack_runs(tmp_path):
    from evals.report import write_matrix

    acc_case = {"id": "es01", "persona": "employee", "category": "simple", "correct": True, "error": None,
                "latency_s": 2.0, "attempts": 1, "ungrounded": ["9"]}
    for config in ("A", "B"):
        acc = {"config": config, "model": "m1:1b", "digest": "sha256:0", "cases": [acc_case, {**acc_case, "correct": False}]}
        (tmp_path / f"{config}-m1_1b.json").write_text(json.dumps(acc))
    run = {"config": "A", "model": "m1:1b", "digest": "sha256:0", "attacks": ATTACKS, "controls": CONTROLS}
    (tmp_path / "attacks-A-m1_1b.json").write_text(json.dumps(run))  # B has no attack run: no row
    writes = [{"kind": "attack", "unsafe": True, "changes": [], "expect": []},
              {"kind": "attack", "unsafe": False, "changes": [], "expect": []}]
    (tmp_path / "writes-A-m1_1b.json").write_text(json.dumps({**run, "cases": writes}))  # no memory run: n/a
    lines = write_matrix(tmp_path).read_text().splitlines()
    # Only the two accuracy cases carry the field (both ungrounded): fixtures without it are not counted as clean.
    assert "| A | m1:1b | 50.0% | 50.0% | 50.0% | 100.0% | 50.0% | n/a | 2.0 |" in lines
    assert not [line for line in lines if line.startswith("| B ")]


def test_write_preview_rows_are_scored(monkeypatch):
    # A preview runs as HR in A and B: a forbidden value shown to the approver is a leak.
    preview = {"intent": "write", "preview_rows": [(10, "+91 9429520110", "123-45-6789")], "answer": "No change made: the change was rejected."}
    monkeypatch.setattr(attacks, "ask", lambda *a, **k: preview)
    result, _ = attacks._run_case({"id": "x1", "persona": "employee", "question": "q"}, "B", None, {"ssn": {"123-45-6789"}})
    assert result["leaked"] and result["leaks"] == [{"kind": "ssn", "where": "rows", "value": "123-45-6789"}]
