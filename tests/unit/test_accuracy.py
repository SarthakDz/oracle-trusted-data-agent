import json

import pytest

import evals.accuracy as accuracy
from evals.accuracy import result_path, summarize
from evals.report import write_report


def _case(cid, persona, category, correct, error=None, latency=1.0, attempts=1):
    return {
        "id": cid,
        "persona": persona,
        "category": category,
        "question": f"question {cid}",
        "correct": correct,
        "error": error,
        "latency_s": latency,
        "attempts": attempts,
    }


CASES = [
    _case("es01", "employee", "simple", True, latency=1.0),
    _case("ej01", "employee", "join", False, error="ORA-00904: invalid identifier", latency=3.0, attempts=3),
    _case("ms01", "manager", "simple", True, latency=2.0),
    _case("mt01", "manager", "time", False, latency=4.0, attempts=2),
]


def test_summarize_by_category_and_persona():
    s = summarize(CASES)
    assert s["accuracy"] == 0.5
    assert s["by_category"] == {"join": 0.0, "simple": 1.0, "time": 0.0}
    assert s["by_persona"] == {"employee": 0.5, "manager": 0.5}
    assert s["error_rate"] == 0.25
    assert s["p50_latency_s"] == 2.5
    assert s["mean_attempts"] == 1.75


def test_result_path_slug():
    path = result_path("2026-10-29", "A", "qwen3:8b")
    assert (path.parent.name, path.name) == ("2026-10-29", "A-qwen3_8b.json")


def test_run_counts_crash_as_wrong(monkeypatch):
    # One crashed agent run costs one case, not the hour-long eval.
    cases = [_case("es01", "employee", "simple", None), _case("ms01", "manager", "simple", None)]
    monkeypatch.setattr(accuracy, "load_cases", lambda: cases)
    monkeypatch.setattr(accuracy, "model_digest", lambda model: "sha256:d1")
    monkeypatch.setattr(accuracy, "expected_rows", lambda cs: {c["id"]: [(1,)] for c in cs})
    monkeypatch.setattr(accuracy, "chat", lambda *a, **k: "OK")
    monkeypatch.setattr(accuracy, "default_deps", lambda model: None)

    def crash(*args, approver=None, **kwargs):
        # A read eval must never write: every proposed change is rejected (Day 6).
        assert approver is not None and approver({"sql": "update hr.employees set phone = 'x'", "columns": [], "rows": []}) == "reject"
        raise RuntimeError("graph blew up")

    monkeypatch.setattr(accuracy, "ask", crash)
    run = accuracy.run("A", "fake:1b")
    assert (run["model"], run["digest"], run["config"]) == ("fake:1b", "sha256:d1", "A")
    assert [c["correct"] for c in run["cases"]] == [False, False]
    assert all("RuntimeError" in c["error"] for c in run["cases"])


def test_run_stops_before_any_case_when_model_missing(monkeypatch):
    from tda.llm import LLMError

    def missing(model):
        raise LLMError(f"{model}: not pulled")

    monkeypatch.setattr(accuracy, "model_digest", missing)
    monkeypatch.setattr(accuracy, "ask", lambda *a, **k: pytest.fail("ran a case"))
    with pytest.raises(LLMError, match="not pulled"):
        accuracy.run("A", "ornith-1.5:9b")


def test_report_lists_runs_and_misses(tmp_path):
    for model in ("m1:1b", "m2:2b"):
        run = {"config": "A", "model": model, "digest": "sha256:0123456789abcdef", "date": "2026-10-29", "cases": CASES}
        result_path_in = tmp_path / f"A-{model.replace(':', '_')}.json"
        result_path_in.write_text(json.dumps(run))
    text = write_report(tmp_path).read_text()
    assert "m1:1b" in text and "m2:2b" in text
    assert "50.0%" in text
    assert "ej01" in text and "ORA-00904" in text  # a miss with its error
    assert "mt01" in text and "rows differ" in text  # a miss without one


def test_ungrounded_measured_only_on_answers_from_rows():
    from evals.accuracy import ungrounded

    assert ungrounded({"rows": [(8,)], "answer": "There are 9.", "error": None}, "q") == ["9"]
    assert ungrounded({"rows": [], "answer": "failed after 3 attempts", "error": "ORA-00942"}, "q") == []
    assert ungrounded({"answer": "I can only answer questions about HR and expense data."}, "q") == []
