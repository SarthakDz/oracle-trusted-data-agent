from evals.smoke import load_cases, score, write_report


def test_score_needs_matching_rows():
    assert score({"rows": [(10,)], "error": None}, [(10,)])
    assert not score({"rows": [(9,)], "error": None}, [(10,)])


def test_score_counts_a_failed_run_as_wrong():
    # A run that ended on an error, or never reached execute (refused, crashed), is wrong.
    assert not score({"rows": [], "error": "ORA-00942: table or view does not exist"}, [(10,)])
    assert not score({"answer": "I can't make changes yet."}, [(10,)])


def test_cases_name_known_personas():
    from tda.personas import PERSONAS

    assert {c["persona"] for c in load_cases()} <= set(PERSONAS)


def test_report_shows_accuracy_and_escapes_tables(tmp_path):
    results = [
        {"id": "e1", "persona": "employee", "correct": True, "attempts": 1, "latency_s": 3.0, "answer": "You have 10."},
        {"id": "e2", "persona": "employee", "correct": False, "attempts": 3, "latency_s": 9.0, "answer": "a | b\nc"},
    ]
    path = tmp_path / "smoke.md"
    write_report(results, path, "A")
    text = path.read_text()
    assert "1/2 correct (50%)" in text
    assert "a \\| b c" in text  # a pipe or newline in an answer must not break the table
