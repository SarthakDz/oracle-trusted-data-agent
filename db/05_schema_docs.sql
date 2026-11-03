-- Schema descriptions with embeddings for retrieval (AI Vector Search). Runs as the admin user (SYS in FREEPDB1, ADMIN on Autonomous AI Database).
-- No DDS grant: end users can't read it. The agent searches it with the service account,
-- because it describes the schema, not anyone's data. Filled by `make index`.
create table hr.schema_docs (
  doc_id       number         primary key,
  table_name   varchar2(30)   not null,
  column_name  varchar2(30),
  content      varchar2(2000) not null,
  embedding    vector(768, float32)
)
/
