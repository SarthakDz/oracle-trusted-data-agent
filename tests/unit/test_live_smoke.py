"""The live smoke: Day 2's smoke questions through the public API (no network, no database)."""

import pytest

from evals import live_smoke

URL = "https://203.0.113.7"


@pytest.fixture
def offline(monkeypatch):
    cases = [{"id": "e1", "persona": "employee", "question": "q1"}, {"id": "m1", "persona": "manager", "question": "q2"}]
    monkeypatch.setattr(live_smoke, "load_cases", lambda: cases)
    monkeypatch.setattr(live_smoke, "expected_rows", lambda cs: {"e1": [(10,)], "m1": [(3,)]})
    return monkeypatch


def test_live_case_scored_by_rows(offline):
    replies = {
        "q1": {"answer": "You have 10.", "rows": [[10]], "pending": None},
        "q2": {"answer": None, "rows": [[3]], "pending": {"sql": "update hr.employees set phone = 'x'"}},
    }
    offline.setattr(live_smoke, "ask_live", lambda url, token, persona, question, timeout_s=900: replies[question])
    e1, m1 = live_smoke.run_live(URL, "t")
    assert e1["correct"] and e1["persona"] == "employee"
    assert not m1["correct"]  # a write preview is not an answer


def test_a_failed_request_costs_one_case(offline):
    def ask(url, token, persona, question, timeout_s=900):
        if question == "q1":
            raise TimeoutError("timed out")
        return {"answer": "3", "rows": [[3]], "pending": None}

    offline.setattr(live_smoke, "ask_live", ask)
    e1, m1 = live_smoke.run_live(URL, "t")
    assert not e1["correct"] and "TimeoutError" in e1["error"] and m1["correct"]


def test_token_comes_from_the_environment(offline, capsys):
    # Never on the command line: argv lands in the shell history and in ps.
    offline.delenv("TDA_DEMO_TOKEN", raising=False)
    assert live_smoke.main(["--url", URL]) != 0
    assert "TDA_DEMO_TOKEN" in capsys.readouterr().err


def test_live_report_states_what_latency_covers(offline, tmp_path):
    # The live run makes no warm-up call, so the report must not claim one.
    offline.setenv("TDA_DEMO_TOKEN", "t")
    offline.setattr(live_smoke, "RESULTS", tmp_path)
    offline.setattr(live_smoke, "ask_live", lambda *a, **k: {"answer": "10", "rows": [[10]], "pending": None})
    assert live_smoke.main(["--url", URL]) == 0
    report = next(tmp_path.glob("cloud-smoke-*.md")).read_text()
    assert "excludes one untimed warm-up" not in report and "public URL" in report


def test_refuses_cases_the_api_truncates(offline):
    # The API returns 20 rows; a longer gold result could never match.
    offline.setattr(live_smoke, "expected_rows", lambda cs: {"e1": [(i,) for i in range(21)], "m1": [(3,)]})
    offline.setattr(live_smoke, "ask_live", lambda *a, **k: pytest.fail("no request before the check"))
    with pytest.raises(ValueError, match="e1"):
        live_smoke.run_live(URL, "t")
