CREATE TABLE IF NOT EXISTS agent_v2.run_reviews (
    owner_id TEXT NOT NULL,
    pipeline_run_id UUID NOT NULL REFERENCES agent_v2.pipeline_runs(id) ON DELETE CASCADE,
    decision TEXT NOT NULL DEFAULT 'undecided',
    rating INTEGER NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
    notes TEXT NOT NULL DEFAULT '',
    is_final BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (owner_id, pipeline_run_id)
);

ALTER TABLE agent_v2.comments ADD COLUMN IF NOT EXISTS rating DOUBLE PRECISION;
ALTER TABLE agent_v2.comments ADD COLUMN IF NOT EXISTS commented_at TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_v2.comments ADD COLUMN IF NOT EXISTS product_variant TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_v2.comments ADD COLUMN IF NOT EXISTS source_channel TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_v2.comments ADD COLUMN IF NOT EXISTS user_segment TEXT NOT NULL DEFAULT '';

ALTER TABLE agent_v2.run_reviews ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS idx_v2_run_reviews_owner_updated
    ON agent_v2.run_reviews(owner_id, updated_at DESC);

REVOKE ALL ON agent_v2.run_reviews FROM anon, authenticated;
