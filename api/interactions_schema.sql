CREATE TABLE IF NOT EXISTS cs_interactions (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(64)   NOT NULL,
    question    TEXT,
    answer      TEXT,
    skill       VARCHAR(64),
    tenant_id   VARCHAR(64),
    status      VARCHAR(16),
    num_turns   SMALLINT,
    duration_ms INT,
    cited_urls  TEXT[],
    skills_used VARCHAR(64)[],
    transferred BOOLEAN       DEFAULT FALSE,
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cs_interactions_session ON cs_interactions (session_id);
CREATE INDEX IF NOT EXISTS idx_cs_interactions_created ON cs_interactions (created_at);
