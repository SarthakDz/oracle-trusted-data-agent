"""The README's headline table must say what the matrix says: the numbers can't drift."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "results" / "2026-11-01" / "matrix.md"


def _table(text: str) -> dict[str, dict[str, str]]:
    """The first markdown table whose header starts with Config, as {config: {column: cell}}."""
    lines = text[text.index("| Config |"):].splitlines()
    rows = []
    for line in lines:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    header, body = rows[0], rows[2:]  # rows[1] is the |---| separator
    return {row[0]: dict(zip(header, row)) for row in body}


def test_readme_table_matches_matrix():
    matrix, readme = _table(MATRIX.read_text()), _table((ROOT / "README.md").read_text())
    assert readme.keys() == matrix.keys()
    for config, row in readme.items():
        # The README may drop columns (p50 there is cache replay time), never change a cell.
        assert row == {column: matrix[config][column] for column in row}, config
