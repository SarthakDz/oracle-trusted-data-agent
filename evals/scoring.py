"""Execution accuracy: compare two result sets the way a person reading them would."""

from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from itertools import permutations

MAX_PERMUTED_COLUMNS = 6  # 720 orderings at most


def _normalize(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    if isinstance(value, str):
        return value.strip()
    return value


def results_match(actual: Sequence[Sequence[object]], expected: Sequence[Sequence[object]]) -> bool:
    """Rows compared as a multiset: row order, column order and column names are ignored, duplicates count."""

    def bag(rows: Sequence[Sequence[object]]) -> Counter:
        return Counter(tuple(_normalize(v) for v in row) for row in rows)

    target = bag(expected)
    if bag(actual) == target:
        return True
    width = len(actual[0]) if actual else 0
    # shortcut: wider results compare in their own column order; raise the cap if a gold query ever returns more than 6 columns.
    if width < 2 or width > MAX_PERMUTED_COLUMNS:
        return False
    return any(bag([[row[i] for i in order] for row in actual]) == target for order in permutations(range(width)))
