CREATE TABLE IF NOT EXISTS skill_versions (
    id          BIGSERIAL PRIMARY KEY,
    skill_name  VARCHAR(64)   NOT NULL,
    version     INT           NOT NULL,
    status      VARCHAR(16)   NOT NULL DEFAULT 'draft',  -- draft | published | superseded
    operator    VARCHAR(128),
    reason      TEXT,
    created_at  TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (skill_name, version)
);

CREATE INDEX IF NOT EXISTS idx_skill_versions_name_status ON skill_versions (skill_name, status);

CREATE TABLE IF NOT EXISTS skill_version_files (
    id          BIGSERIAL PRIMARY KEY,
    version_id  BIGINT        NOT NULL REFERENCES skill_versions(id) ON DELETE CASCADE,
    filename    VARCHAR(256)  NOT NULL,   -- 文件名，如 SKILL.md、source-kb-lookup.md
    filepath    VARCHAR(512)  NOT NULL,   -- 相对于 skill 目录的完整路径，如 references/source-kb-lookup.md
    content     TEXT          NOT NULL,
    UNIQUE (version_id, filepath)
);
