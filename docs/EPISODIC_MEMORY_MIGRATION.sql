BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_episodic_memory

CREATE TABLE episodic_memories (
    memory_id UUID NOT NULL,
    investigation_id UUID NOT NULL,
    category VARCHAR(128) NOT NULL,
    source_tick INTEGER NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (memory_id),
    UNIQUE (investigation_id),
    UNIQUE (fingerprint)
);

CREATE INDEX ix_episodic_memories_category ON episodic_memories (category);

INSERT INTO alembic_version (version_num) VALUES ('0001_episodic_memory') RETURNING alembic_version.version_num;

COMMIT;
