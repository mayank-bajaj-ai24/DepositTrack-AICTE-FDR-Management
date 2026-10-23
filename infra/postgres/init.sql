-- Runs once when the PostgreSQL volume is first created.
-- pgvector is used for clause retrieval (M11, N8).
CREATE EXTENSION IF NOT EXISTS vector;
