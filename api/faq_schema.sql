CREATE TABLE IF NOT EXISTS faq_items (
    id          SERIAL PRIMARY KEY,
    category    VARCHAR(64)  NOT NULL,
    type        VARCHAR(16)  NOT NULL DEFAULT 'qa',   -- qa / section
    question    TEXT         NOT NULL,
    answer      TEXT         NOT NULL,
    submitter   VARCHAR(64)  NOT NULL,
    status      VARCHAR(16)  NOT NULL DEFAULT 'pending',
    reviewer    VARCHAR(64)  DEFAULT '',
    comment     TEXT         DEFAULT '',
    sort_order  INTEGER      NOT NULL DEFAULT 1000,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_faq_category   ON faq_items(category);
CREATE INDEX IF NOT EXISTS idx_faq_status     ON faq_items(status);
CREATE INDEX IF NOT EXISTS idx_faq_sort_order ON faq_items(category, sort_order);

-- 迁移：为已有表添加新字段（幂等）
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='faq_items' AND column_name='type') THEN
        ALTER TABLE faq_items ADD COLUMN type VARCHAR(16) NOT NULL DEFAULT 'qa';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='faq_items' AND column_name='sort_order') THEN
        ALTER TABLE faq_items ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 1000;
    END IF;
END $$;
