CREATE SCHEMA IF NOT EXISTS agent_v2;
REVOKE ALL ON SCHEMA agent_v2 FROM anon, authenticated;

CREATE TABLE IF NOT EXISTS agent_v2.products (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL DEFAULT 'private',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, name)
);

CREATE TABLE IF NOT EXISTS agent_v2.comment_batches (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    product_id BIGINT NOT NULL REFERENCES agent_v2.products(id) ON DELETE CASCADE,
    source_filename TEXT NOT NULL DEFAULT '',
    comment_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_v2.comments (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    product_id BIGINT NOT NULL REFERENCES agent_v2.products(id) ON DELETE CASCADE,
    batch_id BIGINT NOT NULL REFERENCES agent_v2.comment_batches(id) ON DELETE CASCADE,
    comment_original TEXT NOT NULL,
    clean_comment TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, product_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS agent_v2.requirements (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    product_id BIGINT NOT NULL REFERENCES agent_v2.products(id) ON DELETE CASCADE,
    batch_id BIGINT REFERENCES agent_v2.comment_batches(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '',
    evidence_text TEXT NOT NULL DEFAULT '',
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS agent_v2.pipeline_runs (
    id UUID PRIMARY KEY,
    owner_id TEXT NOT NULL,
    target_product TEXT NOT NULL,
    demand_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL,
    error_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS agent_v2.generation_runs (
    id UUID PRIMARY KEY,
    owner_id TEXT NOT NULL,
    pipeline_run_id UUID REFERENCES agent_v2.pipeline_runs(id) ON DELETE CASCADE,
    context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    quality_status TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, pipeline_run_id)
);

CREATE TABLE IF NOT EXISTS agent_v2.stage_runs (
    id UUID PRIMARY KEY,
    owner_id TEXT NOT NULL,
    pipeline_run_id UUID NOT NULL REFERENCES agent_v2.pipeline_runs(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_hash TEXT NOT NULL DEFAULT '',
    error_summary TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    UNIQUE (owner_id, pipeline_run_id, stage_id)
);

CREATE TABLE IF NOT EXISTS agent_v2.artifacts (
    id UUID PRIMARY KEY,
    owner_id TEXT NOT NULL,
    pipeline_run_id UUID REFERENCES agent_v2.pipeline_runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, storage_path)
);

CREATE TABLE IF NOT EXISTS agent_v2.artifact_blobs (
    owner_id TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    data BYTEA NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (owner_id, storage_path)
);

CREATE TABLE IF NOT EXISTS agent_v2.migration_ledger (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    sha256 TEXT NOT NULL DEFAULT '',
    migrated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (owner_id, source_type, source_id, sha256)
);

CREATE TABLE IF NOT EXISTS agent_v2.login_audit (
    id BIGSERIAL PRIMARY KEY,
    owner_id TEXT NOT NULL,
    session_fingerprint TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE agent_v2.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.comment_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.generation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.stage_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.artifact_blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.migration_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_v2.login_audit ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_v2_comments_owner_product ON agent_v2.comments(owner_id, product_id);
CREATE INDEX IF NOT EXISTS idx_v2_requirements_owner_product ON agent_v2.requirements(owner_id, product_id);
CREATE INDEX IF NOT EXISTS idx_v2_runs_owner_updated ON agent_v2.pipeline_runs(owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_v2_artifacts_owner_run ON agent_v2.artifacts(owner_id, pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_v2_artifact_blobs_owner_sha ON agent_v2.artifact_blobs(owner_id, sha256);

REVOKE ALL ON ALL TABLES IN SCHEMA agent_v2 FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA agent_v2 FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA agent_v2 REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA agent_v2 REVOKE ALL ON SEQUENCES FROM anon, authenticated;
