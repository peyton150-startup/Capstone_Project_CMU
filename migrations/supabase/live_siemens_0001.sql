-- Separately applied Supabase live Siemens ingestion migration.
-- Independent of the simulator journal Alembic chain in PR #289.
-- Apply only after IT/OT approvals, backup and private-role review.
BEGIN;
CREATE SCHEMA IF NOT EXISTS capstone_ingest;
REVOKE ALL ON SCHEMA capstone_ingest FROM PUBLIC;

CREATE TABLE capstone_ingest.streams (
    site_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    stream_id UUID NOT NULL,
    server_uri TEXT NOT NULL,
    controller_fingerprint TEXT NOT NULL,
    scope_fingerprint TEXT NOT NULL CHECK (length(scope_fingerprint) = 64),
    next_line BIGINT NOT NULL DEFAULT 0 CHECK (next_line >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_accepted_at TIMESTAMPTZ,
    PRIMARY KEY (site_id, machine_id, stream_id)
);

CREATE TABLE capstone_ingest.batches (
    site_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    stream_id UUID NOT NULL,
    digest TEXT NOT NULL CHECK (length(digest) = 64),
    first_line BIGINT NOT NULL,
    next_line BIGINT NOT NULL CHECK (next_line > first_line),
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, machine_id, stream_id, digest),
    FOREIGN KEY (site_id, machine_id, stream_id)
        REFERENCES capstone_ingest.streams(site_id, machine_id, stream_id)
);

CREATE TABLE capstone_ingest.records (
    site_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    stream_id UUID NOT NULL,
    line_number BIGINT NOT NULL CHECK (line_number >= 0),
    server_uri TEXT NOT NULL,
    record_type TEXT NOT NULL CHECK (record_type IN ('data_change', 'opcua_session')),
    event_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ,
    quality TEXT CHECK (quality IN ('good', 'uncertain', 'bad')),
    analysis_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    retained_until TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, machine_id, stream_id, line_number),
    FOREIGN KEY (site_id, machine_id, stream_id)
        REFERENCES capstone_ingest.streams(site_id, machine_id, stream_id)
);
CREATE INDEX siemens_records_observed
    ON capstone_ingest.records(site_id, machine_id, event_at, line_number);
CREATE INDEX siemens_records_retention
    ON capstone_ingest.records(retained_until);

-- Backend is a private PostgreSQL role. No browser/Data API role is granted.
ALTER TABLE capstone_ingest.streams ENABLE ROW LEVEL SECURITY;
ALTER TABLE capstone_ingest.batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE capstone_ingest.records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA capstone_ingest FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON SCHEMA capstone_ingest FROM anon;
        REVOKE ALL ON ALL TABLES IN SCHEMA capstone_ingest FROM anon;
    END IF;
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON SCHEMA capstone_ingest FROM authenticated;
        REVOKE ALL ON ALL TABLES IN SCHEMA capstone_ingest FROM authenticated;
    END IF;
END;
$$;
COMMIT;
