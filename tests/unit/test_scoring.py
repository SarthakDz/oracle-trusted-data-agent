from decimal import Decimal

from evals.scoring import results_match


def test_results_match_order_insensitive():
    assert results_match([(1, "a"), (2, "b")], [(2, "b"), (1, "a")])


def test_results_match_decimal_float():
    assert results_match([(Decimal("10.50"),)], [(10.5,)])


def test_results_match_multiset():
    # Duplicates matter: a query that double-counts rows is wrong.
    assert not results_match([(1,), (1,)], [(1,)])


def test_results_match_detects_value_difference():
    assert not results_match([(1, "a")], [(1, "b")])


def test_results_match_strips_strings_and_keeps_none():
    assert results_match([(" a ", None)], [("a", None)])
    assert not results_match([(None,)], [(0,)])


def test_results_match_column_order_insensitive():
    # "count, code" answers the same question as "code, count".
    assert results_match([(1, "a"), (2, "b")], [("a", 1), ("b", 2)])


def test_results_match_rejects_wrong_pairing():
    # Swapping columns is fine; pairing values with the wrong row is not.
    assert not results_match([(1, "a"), (2, "b")], [("b", 1), ("a", 2)])


def test_results_match_extra_column_fails():
    assert not results_match([("a", 1)], [("a",)])
