-- Manual-specific Neon migration, intentionally outside the shared Alembic chain
-- (PR #289 owns the Supabase journal Alembic revision). Apply explicitly,
-- after backup/review; never run automatically during API startup.
BEGIN;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS capstone_knowledge;
REVOKE ALL ON SCHEMA capstone_knowledge FROM PUBLIC;

CREATE TABLE capstone_knowledge.manual_documents (
    document_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    source_scope TEXT NOT NULL CHECK (source_scope IN ('simulator', 'pilot')),
    title TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    source_object_key TEXT,
    approval_reference TEXT,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, revision),
    CHECK (source_scope = 'simulator' OR approval_reference IS NOT NULL),
    CHECK (length(document_id) BETWEEN 1 AND 128),
    CHECK (length(revision) BETWEEN 1 AND 64)
);
CREATE UNIQUE INDEX manual_one_published_revision
ON capstone_knowledge.manual_documents(document_id)
WHERE is_published;

CREATE TABLE capstone_knowledge.manual_sections (
    document_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    section_id TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    embedding_model TEXT,
    embedding vector(2048),
    PRIMARY KEY (document_id, revision, section_id),
    FOREIGN KEY (document_id, revision)
        REFERENCES capstone_knowledge.manual_documents(document_id, revision)
        ON DELETE RESTRICT,
    CHECK (length(body) > 0),
    CHECK ((embedding IS NULL) = (embedding_model IS NULL))
);
CREATE INDEX manual_sections_lexical
ON capstone_knowledge.manual_sections
USING GIN (to_tsvector('english', title || ' ' || body));

-- Database owner / explicitly granted server role only. No Data API/browser grants.
REVOKE ALL ON ALL TABLES IN SCHEMA capstone_knowledge FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON SCHEMA capstone_knowledge FROM anon;
        REVOKE ALL ON ALL TABLES IN SCHEMA capstone_knowledge FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON SCHEMA capstone_knowledge FROM authenticated;
        REVOKE ALL ON ALL TABLES IN SCHEMA capstone_knowledge FROM authenticated;
    END IF;
END;
$$;
COMMIT;
