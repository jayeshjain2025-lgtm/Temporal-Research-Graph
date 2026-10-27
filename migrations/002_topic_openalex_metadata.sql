ALTER TABLE topics
    ADD COLUMN IF NOT EXISTS external_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS source VARCHAR(100),
    ADD COLUMN IF NOT EXISTS domain_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS field_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS subfield_name VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS uq_topics_external_id_not_null ON topics(external_id) WHERE external_id IS NOT NULL;
