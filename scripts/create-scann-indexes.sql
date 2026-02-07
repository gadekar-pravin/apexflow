-- ================================================================
-- Create ScaNN indexes on AlloyDB Omni
-- Run AFTER inserting initial data (ScaNN requires non-empty tables)
--
-- Usage:
--   psql -h localhost -U apexflow -d apexflow -f scripts/create-scann-indexes.sql
-- ================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'alloydb_scann') THEN
        RAISE EXCEPTION 'alloydb_scann extension not found — this script is for AlloyDB only';
    END IF;

    -- memories table
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_memories_embedding') THEN
        IF EXISTS (SELECT 1 FROM memories LIMIT 1) THEN
            EXECUTE 'CREATE INDEX idx_memories_embedding ON memories USING scann (embedding cosine) WITH (num_leaves = 50)';
            RAISE NOTICE 'Created ScaNN index on memories';
        ELSE
            RAISE NOTICE 'memories table is empty — skipping ScaNN index (insert data first)';
        END IF;
    ELSE
        RAISE NOTICE 'idx_memories_embedding already exists';
    END IF;

    -- document_chunks table
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_chunks_embedding') THEN
        IF EXISTS (SELECT 1 FROM document_chunks LIMIT 1) THEN
            EXECUTE 'CREATE INDEX idx_chunks_embedding ON document_chunks USING scann (embedding cosine) WITH (num_leaves = 100)';
            RAISE NOTICE 'Created ScaNN index on document_chunks';
        ELSE
            RAISE NOTICE 'document_chunks table is empty — skipping ScaNN index (insert data first)';
        END IF;
    ELSE
        RAISE NOTICE 'idx_chunks_embedding already exists';
    END IF;
END $$;
