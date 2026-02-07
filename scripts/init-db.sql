-- ================================================================
-- ApexFlow AlloyDB Schema
-- Run on both AlloyDB Omni (local dev) and managed AlloyDB (Cloud Run)
-- ================================================================

-- ================================================================
-- KEY DESIGN DECISIONS:
-- 1. TEXT primary keys: IDs are generated externally (UUIDs from the
--    application layer). Consider migrating to UUID type if we standardize.
-- 2. user_id has no default: forces the application layer to always
--    provide a user_id, preventing accidental single-tenant bugs.
--    For local dev convenience, use 'default' explicitly in test fixtures.
-- 3. Status fields use CHECK constraints to catch invalid values early.
-- 4. Monetary values use NUMERIC to avoid floating-point rounding.
-- 5. JSONB fields (graph_data, node_outputs, evidence_log, staging_queue)
--    are intentionally schemaless for Phase 1. Document expected structure
--    in Phase 2 and consider extracting hot-path fields into typed columns
--    if query patterns demand it. Monitor row sizes to prevent bloat.
-- ================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;            -- pgvector: VECTOR data type + distance operators

-- Try to enable ScaNN (AlloyDB Omni / managed AlloyDB only).
-- On vanilla PostgreSQL, this will be skipped and IVFFlat indexes used instead.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'alloydb_scann') THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS alloydb_scann';
        RAISE NOTICE 'alloydb_scann extension enabled — using ScaNN indexes';
    ELSE
        RAISE NOTICE 'alloydb_scann not available — will use IVFFlat indexes (vanilla PostgreSQL)';
    END IF;
END $$;

-- ================================================================
-- TABLE 1: sessions
-- Replaces: memory/session_summaries_index/**/*.json filesystem
-- Used by: routers/runs.py, routers/remme.py (smart scan)
-- ================================================================
CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    query           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    agent_type      TEXT,
    graph_data      JSONB NOT NULL DEFAULT '{}',
    node_outputs    JSONB DEFAULT '{}',
    cost            NUMERIC(10,6) DEFAULT 0.0,
    model_used      TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    remme_scanned   BOOLEAN NOT NULL DEFAULT FALSE,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_sessions_user     ON sessions(user_id);
CREATE INDEX idx_sessions_created  ON sessions(created_at DESC);
CREATE INDEX idx_sessions_status   ON sessions(status);
CREATE INDEX idx_sessions_unscanned ON sessions(user_id) WHERE NOT remme_scanned;

-- ================================================================
-- TABLE 2: jobs
-- Replaces: data/system/jobs.json
-- Used by: core/scheduler.py, routers/cron.py
-- ================================================================
CREATE TABLE jobs (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    agent_type      TEXT NOT NULL DEFAULT 'PlannerAgent',
    query           TEXT NOT NULL,
    skill_id        TEXT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    last_run        TIMESTAMPTZ,
    next_run        TIMESTAMPTZ,
    last_output     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- ================================================================
-- TABLE 2b: job_runs
-- Provides DB-level deduplication for scheduled job executions.
-- Works with both APScheduler (Option B) and Cloud Scheduler (Option A).
-- Used by: core/scheduler.py
-- ================================================================
CREATE TABLE job_runs (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    scheduled_for   TIMESTAMPTZ NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
    output          TEXT,
    error           TEXT,
    UNIQUE(job_id, scheduled_for)   -- prevents duplicate execution
);

CREATE INDEX idx_job_runs_job    ON job_runs(job_id, scheduled_for DESC);

-- ================================================================
-- TABLE 3: notifications
-- Replaces: data/inbox/notifications.db (SQLite)
-- Used by: routers/inbox.py, core/scheduler.py
-- ================================================================
CREATE TABLE notifications (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    source          TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 1,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_notif_user_unread ON notifications(user_id, is_read) WHERE NOT is_read;
CREATE INDEX idx_notif_created     ON notifications(created_at DESC);

-- ================================================================
-- TABLE 4: memories
-- Replaces: remme/store.py FAISS index + memory/remme_index/memories.json
-- Used by: remme/store.py, routers/remme.py
-- ================================================================
CREATE TABLE memories (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    text            TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'general',
    source          TEXT,
    embedding       VECTOR(768) NOT NULL,
    confidence      REAL DEFAULT 1.0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- Vector similarity index (ScaNN on AlloyDB, IVFFlat on vanilla PG)
-- NOTE: ScaNN requires non-empty tables. On AlloyDB Omni, we skip index creation
-- here and create ScaNN indexes after initial data insertion.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'alloydb_scann') THEN
        RAISE NOTICE 'AlloyDB detected — skipping ScaNN index on memories (create after data insertion)';
    ELSE
        EXECUTE 'CREATE INDEX idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)';
    END IF;
END $$;

CREATE INDEX idx_memories_user     ON memories(user_id);
CREATE INDEX idx_memories_category ON memories(user_id, category);

-- ================================================================
-- TABLE 5: documents
-- Replaces: document metadata in mcp_servers/server_rag.py
-- Used by: core/stores/document_store.py, routers/rag.py
-- ================================================================
CREATE TABLE documents (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    filename        TEXT NOT NULL,
    filepath        TEXT,
    doc_type        TEXT,
    file_hash       TEXT,
    total_chunks    INTEGER DEFAULT 0,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}',
    UNIQUE(user_id, file_hash)       -- deduplicate uploads per user
);

CREATE INDEX idx_docs_user     ON documents(user_id);
CREATE INDEX idx_docs_hash     ON documents(file_hash);

-- ================================================================
-- TABLE 6: document_chunks
-- Replaces: FAISS + BM25 in mcp_servers/server_rag.py
-- Used by: core/stores/document_search.py
-- ================================================================
CREATE TABLE document_chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       VECTOR(768) NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)  -- prevent duplicate chunks per document
);

-- Vector similarity index (ScaNN on AlloyDB, IVFFlat on vanilla PG)
-- NOTE: ScaNN requires non-empty tables. On AlloyDB Omni, we skip index creation
-- here and create ScaNN indexes after initial data insertion.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'alloydb_scann') THEN
        RAISE NOTICE 'AlloyDB detected — skipping ScaNN index on document_chunks (create after data insertion)';
    ELSE
        EXECUTE 'CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
    END IF;
END $$;

CREATE INDEX idx_chunks_doc    ON document_chunks(document_id);
CREATE INDEX idx_chunks_user   ON document_chunks(user_id);

-- Full-text search (replaces BM25)
ALTER TABLE document_chunks ADD COLUMN content_tsv TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX idx_chunks_fts ON document_chunks USING GIN(content_tsv);

-- ================================================================
-- TABLE 7: chat_sessions
-- Replaces: data/.meta/chats/ filesystem
-- Used by: routers/chat.py
-- ================================================================
CREATE TABLE chat_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT 'New Chat',
    model           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chats_user_target ON chat_sessions(user_id, target_type, target_id);

-- ================================================================
-- TABLE 7b: chat_messages
-- Normalized from chat_sessions.messages JSONB array
-- Allows per-message search, pagination, and bounded queries
-- ================================================================
CREATE TABLE chat_messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'      -- tokens, tool calls, etc.
);

CREATE INDEX idx_chat_msg_session ON chat_messages(user_id, session_id, created_at);
CREATE INDEX idx_chat_msg_role    ON chat_messages(session_id, role);

-- ================================================================
-- TABLE 8: user_preferences
-- Replaces: remme/hubs/*.json files + staging + evidence log
-- Used by: remme/hubs/*.py, remme/staging.py, remme/engines/evidence_log.py
-- ================================================================
CREATE TABLE user_preferences (
    user_id         TEXT PRIMARY KEY,
    preferences     JSONB NOT NULL DEFAULT '{}',
    operating_ctx   JSONB NOT NULL DEFAULT '{}',
    soft_identity   JSONB NOT NULL DEFAULT '{}',
    evidence_log    JSONB NOT NULL DEFAULT '{}',
    staging_queue   JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ================================================================
-- TABLE 9: system_state
-- Replaces: data/system/snapshot.json
-- Used by: core/persistence.py, tools/monty_sandbox.py (session state)
-- ================================================================
CREATE TABLE system_state (
    user_id         TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);

-- ================================================================
-- TABLE 10: scanned_runs (REMME tracking)
-- Replaces: memory/remme_index/scanned_runs.json
-- Used by: remme/store.py
-- ================================================================
CREATE TABLE scanned_runs (
    run_id          TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    scanned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ================================================================
-- TABLE 11: security_logs
-- Replaces: data/security_logs/*.jsonl
-- Used by: tools/monty_sandbox.py
-- ================================================================
CREATE TABLE security_logs (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    session_id      TEXT,
    action          TEXT NOT NULL,
    detail          TEXT,
    code_snippet    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_security_created ON security_logs(created_at DESC);

-- ================================================================
-- RETENTION POLICY (apply via scheduled job or migration)
-- These tables grow without bound and need periodic cleanup.
-- Implement as a cron job in core/scheduler.py or via pg_cron.
-- ================================================================
-- Suggested retention periods:
--   security_logs:  90 days  (DELETE FROM security_logs WHERE created_at < NOW() - INTERVAL '90 days')
--   chat_messages:  365 days (or archive to cold storage)
--   sessions:       180 days for completed sessions
--   job_runs:       90 days
-- TODO: Implement retention job in Phase 2 (core/scheduler.py)
