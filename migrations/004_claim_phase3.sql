-- Migration 004: Phase 3 schema additions
-- Additive only. No existing tables are dropped or modified destructively.
--
-- Changes
-- -------
-- 1. Add claim_type column to claims (VARCHAR 30, nullable initially so
--    existing rows are unaffected; Phase 3 pipeline sets it on insert).
-- 2. Add unique constraint to claim_relations so upsert is idempotent.
-- 3. Add unique constraint on (source_claim_id, target_claim_id, relation_type)
--    so concurrent ingestion cannot produce duplicate relation rows.

-- 1. claim_type column on claims
ALTER TABLE claims ADD COLUMN IF NOT EXISTS claim_type VARCHAR(30);

-- 2. Unique constraint on claim_relations
--    Guard: only add if it does not already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_constraint
        WHERE  conname = 'uq_claim_relation'
    ) THEN
        ALTER TABLE claim_relations
            ADD CONSTRAINT uq_claim_relation
            UNIQUE (source_claim_id, target_claim_id, relation_type);
    END IF;
END;
$$;
