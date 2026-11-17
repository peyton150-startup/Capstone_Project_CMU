-- Add OEM authorization and page lineage to the Neon knowledge schema.
-- Requires migrations/neon/0001_manual_knowledge.sql from PR #290.
-- Independent of the Supabase live-data schema and the simulator journal.
BEGIN;

ALTER TABLE capstone_knowledge.manual_sections
    ADD COLUMN page_start INTEGER CHECK (page_start >= 1),
    ADD COLUMN page_end INTEGER CHECK (page_end >= page_start);

CREATE TABLE capstone_knowledge.manual_approvals (
    document_id TEXT NOT NULL,
    revision TEXT NOT NULL,
    site_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    controller_family TEXT NOT NULL,
    controller_fingerprint TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approval_reference TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    pdf_sha256 TEXT NOT NULL CHECK (length(pdf_sha256) = 64),
    section_sha256 TEXT NOT NULL CHECK (length(section_sha256) = 64),
    cloud_storage_approved BOOLEAN NOT NULL,
    retrieval_approved BOOLEAN NOT NULL,
    embedding_egress_approved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, revision),
    FOREIGN KEY (document_id, revision)
        REFERENCES capstone_knowledge.manual_documents(document_id, revision)
        ON DELETE RESTRICT
);
CREATE INDEX manual_approvals_machine_scope
    ON capstone_knowledge.manual_approvals(
        site_id, machine_id, controller_family, controller_fingerprint
    );

ALTER TABLE capstone_knowledge.manual_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE capstone_knowledge.manual_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE capstone_knowledge.manual_sections ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON capstone_knowledge.manual_approvals FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA capstone_knowledge FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON capstone_knowledge.manual_approvals FROM anon;
        REVOKE ALL ON capstone_knowledge.manual_documents FROM anon;
        REVOKE ALL ON capstone_knowledge.manual_sections FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON capstone_knowledge.manual_approvals FROM authenticated;
        REVOKE ALL ON capstone_knowledge.manual_documents FROM authenticated;
        REVOKE ALL ON capstone_knowledge.manual_sections FROM authenticated;
    END IF;
END;
$$;
COMMIT;
