"""Embed the schema docs into HR.SCHEMA_DOCS and search them with VECTOR_DISTANCE.

nomic-embed-text expects task prefixes: "search_document: " for stored text and
"search_query: " for questions.
"""

import array

import oracledb

from tda.llm import embed
from tda.schema_docs import SchemaDoc, schema_docs

EMBED_DIM = 768


def _vector(values: list[float]) -> array.array:
    if len(values) != EMBED_DIM:
        raise ValueError(f"expected a {EMBED_DIM}-dim embedding, got {len(values)}")
    return array.array("f", values)


def build_index(conn: oracledb.Connection) -> int:
    docs = schema_docs()
    vectors = embed([f"search_document: {d.text}" for d in docs])
    rows = [(i + 1, d.table, d.column, d.text, _vector(v)) for i, (d, v) in enumerate(zip(docs, vectors))]
    with conn.cursor() as cur:
        cur.execute("delete from hr.schema_docs")
        cur.executemany(
            "insert into hr.schema_docs (doc_id, table_name, column_name, content, embedding) values (:1, :2, :3, :4, :5)",
            rows,
        )
    conn.commit()
    return len(rows)


def search(conn: oracledb.Connection, question: str, k: int = 8) -> list[SchemaDoc]:
    (query,) = embed([f"search_query: {question}"])
    with conn.cursor() as cur:
        cur.execute(
            "select table_name, column_name, content from hr.schema_docs "
            "order by vector_distance(embedding, :v, cosine) fetch first :k rows only",
            v=_vector(query),
            k=k,
        )
        return [SchemaDoc(table, column, text) for table, column, text in cur]


def schema_context(conn: oracledb.Connection, question: str, k: int = 8) -> str:
    """Every table's column list (only 3 short lines), plus the column notes retrieval finds relevant."""
    tables = [d.text for d in schema_docs() if d.column is None]
    hits = search(conn, question, k)
    if not hits:  # db-init leaves the index empty; without notes the agent would degrade silently
        raise RuntimeError("HR.SCHEMA_DOCS is empty: run `make index`")
    notes = [h.text for h in hits if h.column is not None]
    return "\n".join(["Tables:", *tables, "", "Relevant column notes:", *notes])


def main() -> None:
    from tda.db import service_connection

    with service_connection() as conn:
        print(f"indexed {build_index(conn)} schema docs")


if __name__ == "__main__":
    main()
