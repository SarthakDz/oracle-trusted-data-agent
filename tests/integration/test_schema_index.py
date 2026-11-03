import pytest

from tda.db import service_connection
from tda.schema_docs import schema_docs
from tda.schema_index import EMBED_DIM, build_index, schema_context, search

pytestmark = [pytest.mark.integration, pytest.mark.llm]


@pytest.fixture(scope="module", autouse=True)
def indexed():
    # db-init (run by other tests) recreates HR and empties the index, so build it here.
    with service_connection() as conn:
        build_index(conn)


def test_build_index_counts():
    with service_connection() as conn:
        assert build_index(conn) == len(schema_docs())


def test_vectors_have_expected_dimension():
    with service_connection() as conn:
        dims = conn.cursor().execute("select distinct vector_dimension_count(embedding) from hr.schema_docs").fetchall()
    assert dims == [(EMBED_DIM,)]


def test_search_finds_status_for_approved():
    with service_connection() as conn:
        hits = search(conn, "What is the total amount of approved expenses?", k=3)
    assert ("expenses", "status") in {(h.table, h.column) for h in hits}


def test_schema_context_includes_table_columns():
    with service_connection() as conn:
        context = schema_context(conn, "average salary of my direct reports")
    assert "hr.employees(" in context and "manager_email" in context
