# Phase 1: Project Bootstrap + Database Foundation

**Prerequisites:** None
**Produces:** Initialized repo with AlloyDB schema, database connection pool, Docker Compose for local dev

---

## AlloyDB Omni Overview

**AlloyDB Omni** is Google's downloadable, self-managed version of AlloyDB that runs anywhere — laptop, VM, or on-prem. It uses the same database engine as managed AlloyDB on GCP, providing feature parity for local development.

### Why AlloyDB Omni (not vanilla PostgreSQL)

| Feature | AlloyDB Omni | Vanilla PostgreSQL |
|---------|--------------|-------------------|
| `VECTOR` data type | Yes (`vector` extension, pgvector-compatible) | Yes (via pgvector) |
| **ScaNN indexes** | Yes (`alloydb_scann` extension) | **No** (only HNSW/IVFFlat) |
| Columnar engine | Yes (AMD64 only) | No |
| Adaptive autovacuum | Yes | Manual tuning |
| Compatibility | PostgreSQL 15/16/17 wire-compatible | Native |
| License | Free for dev/non-commercial | Open source |

We need AlloyDB Omni specifically because our schema uses **ScaNN indexes** for vector similarity search. ScaNN provides better recall at lower latency than HNSW/IVFFlat for our workload sizes. On vanilla PostgreSQL, you would need to substitute IVFFlat indexes (see [Fallback](#fallback-vanilla-postgresql) below).

### Extensions Required

```sql
CREATE EXTENSION IF NOT EXISTS vector;           -- VECTOR(768) data type
CREATE EXTENSION IF NOT EXISTS alloydb_scann;    -- ScaNN index support
```

Both are bundled with AlloyDB Omni. The `vector` extension provides the data type; `alloydb_scann` provides the index access method. **Both must be enabled** — `vector` alone does NOT provide ScaNN.

### Docker Image

| Detail | Value |
|--------|-------|
| Image | `google/alloydbomni` |
| **Target version** | **`15.12.0`** (pinned across dev, CI, and production) |
| Latest available | `17.5.0` (PostgreSQL 17 based) |
| AMD64 | Full support |
| ARM64 (Apple Silicon) | Partial — columnar engine not available (doesn't affect us, we only use vector search) |
| Min memory | 2 GB (dev), 8 GB per vCPU (production) |
| Min CPU | 2 vCPUs |

> **Version parity decision:** We pin to PostgreSQL **15** across all environments (local dev, CI, and managed AlloyDB in production). This avoids subtle differences in planner behavior, extension compatibility, and SQL edge cases between major versions. The CI profile uses `pgvector/pgvector:pg15` to match. If we upgrade to PG 17, all environments must move together.

### Apple Silicon (M1/M2/M3/M4) Notes

AlloyDB Omni publishes ARM64 images, so it runs natively on Apple Silicon. The only limitation is the columnar engine (not available on ARM64), which we don't use. Vector search and ScaNN indexes work correctly on ARM64.

If you encounter issues, try:
1. Ensure Docker Desktop has at least 4 GB memory allocated
2. Use Podman as an alternative runtime
3. Fall back to vanilla PostgreSQL + IVFFlat (see [Fallback](#fallback-vanilla-postgresql))

---

## Step 1.1: Initialize the new repo

```bash
mkdir -p /Users/pravingadekar/Documents/EAG2-Capstone/apexflow
cd /Users/pravingadekar/Documents/EAG2-Capstone/apexflow
git init
```

## Step 1.2: Create pyproject.toml

Dependencies (clean list — no legacy):
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
asyncpg>=0.29.0
google-genai>=1.0.0
google-cloud-aiplatform>=1.70.0
networkx>=3.3
apscheduler>=3.10.0
httpx>=0.27.0
firebase-admin>=6.5.0
pydantic>=2.9.0
pydantic-settings>=2.5.0
pydantic-monty>=0.1.0,<0.2.0
pyyaml>=6.0
sse-starlette>=2.0.0
python-multipart>=0.0.12
```

> **Note:** We use `httpx` as the single async HTTP client. `aiohttp` was removed to reduce surface area — `httpx` covers the same use cases with a more consistent API.

Dev dependencies (in `[project.optional-dependencies]` or `[tool.uv.dev-dependencies]`):
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
ruff>=0.6.0
mypy>=1.11.0
pre-commit>=3.8.0
alembic>=1.13.0
psycopg2-binary>=2.9.9        # Required by Alembic for sync migrations
asyncpg-stubs>=0.29.0         # Required by mypy strict mode for core/database.py
```

## Step 1.3: Create docker-compose.yml

```yaml
# docker-compose.yml
version: '3.8'
services:
  alloydb-omni:
    image: google/alloydbomni:15.12.0    # Pin version for reproducible dev environments
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: apexflow
      POSTGRES_PASSWORD: apexflow
      POSTGRES_DB: apexflow
    volumes:
      - alloydb_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/01-schema.sql
    shm_size: '512mb'                    # Required for AlloyDB internal memory management
    # Uncomment ulimits on Linux for production-grade performance.
    # WARNING: These can fail on macOS Docker Desktop and rootless Docker.
    # ulimits:
    #   nice:
    #     soft: -20
    #     hard: -20
    #   memlock:
    #     soft: -1
    #     hard: -1
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U apexflow -d apexflow"]
      interval: 5s
      timeout: 3s
      retries: 10
    # Note: On Apple Silicon (ARM64), the columnar engine is unavailable.
    # This does NOT affect vector search or ScaNN indexes.

volumes:
  alloydb_data:
```

### CI Profile: docker-compose.ci.yml

For CI environments where AlloyDB Omni is unavailable, use a pgvector-enabled PostgreSQL image. The CI container starts with an **empty database** — Alembic applies the schema as the single source of truth.

> **IMPORTANT:** Do NOT mount `init-db.sql` via `docker-entrypoint-initdb.d` in CI. The CI pipeline runs `alembic upgrade head`, whose initial migration executes `init-db.sql`. If the Docker entrypoint also applies the schema, every `CREATE TABLE` statement will fail with `relation already exists` because the SQL uses `CREATE TABLE` (not `CREATE TABLE IF NOT EXISTS`). Alembic must be the sole schema applicator in CI.

```yaml
# docker-compose.ci.yml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg15    # PostgreSQL 15 with pgvector pre-installed
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: apexflow
      POSTGRES_PASSWORD: apexflow
      POSTGRES_DB: apexflow
    # No init-db.sql mount — Alembic applies the schema in CI
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U apexflow -d apexflow"]
      interval: 5s
      timeout: 3s
      retries: 10
```

Usage in CI pipelines:
```bash
docker compose -f docker-compose.ci.yml up -d
# Wait for postgres to be ready, then:
alembic upgrade head
# Expected: all 13 tables created by Alembic, IVFFlat indexes (not ScaNN)
```

### Docker Compose Notes

- **`shm_size: '512mb'`**: AlloyDB Omni uses shared memory for its columnar engine and parallel workers. Without this, you may see "out of shared memory" errors. On Linux you can alternatively mount `/dev/shm:/dev/shm`.
- **`ulimits`** (commented out by default): `nice=-20` lets PostgreSQL critical processes run at kernel-level priority. `memlock=-1` allows AlloyDB's adaptive memory manager to control page swapping. These can fail on macOS Docker Desktop and rootless Docker — only enable on Linux production VMs.
- **`alloydb_data` volume**: Data persists across container restarts. To start fresh: `docker compose down -v` (destroys data).
- **`init-db.sql` only runs on first initialization**: The `docker-entrypoint-initdb.d/` mechanism only applies when the data volume is empty (first `docker compose up`). For schema changes after initial setup, use **Alembic migrations** (see [Step 1.8](#step-18-initialize-alembic-for-schema-migrations)). To reset completely: `docker compose down -v` (destroys data) and re-create.
- **No log rotation by default**: Docker doesn't rotate AlloyDB logs. For long-running dev environments, consider adding `logging: { driver: "json-file", options: { max-size: "10m", max-file: "3" } }`.

### First-Time Setup

```bash
# 1. Start AlloyDB Omni
docker-compose up -d

# 2. Wait for healthy status (~10-15 seconds)
docker-compose ps   # Should show "healthy"

# 3. Verify extensions are available
docker compose exec alloydb-omni psql -U apexflow -d apexflow -c "\dx"
# Should list: vector, alloydb_scann

# 4. Verify schema
docker compose exec alloydb-omni psql -U apexflow -d apexflow -c "\dt"
# Should show all 13 tables

# 5. Connect from host (for psql or DB tools)
psql -h localhost -U apexflow -d apexflow
# Password: apexflow
```

## Step 1.4: Create scripts/init-db.sql

Full AlloyDB schema (13 tables):

```sql
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
-- here and create ScaNN indexes after initial data insertion via
-- scripts/create-scann-indexes.sql.
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
-- here and create ScaNN indexes after initial data insertion via
-- scripts/create-scann-indexes.sql.
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
```

### Multi-Tenancy and Row Level Security

The schema removes `DEFAULT 'default'` from all `user_id` columns to force the application layer to always provide a user_id. This prevents accidental single-tenant bugs where data silently leaks across users.

**Current posture (Phase 1):** Application-level tenant isolation. Every query must include `WHERE user_id = $1`.

**Future consideration (Phase 2+):** If the product is multi-tenant, add PostgreSQL Row Level Security (RLS) as a defense-in-depth layer:

```sql
-- Example RLS policy (do NOT apply in Phase 1 — requires session-level user context)
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON sessions
    USING (user_id = current_setting('app.current_user_id'));
```

RLS requires setting `app.current_user_id` per connection/transaction, which adds complexity to the connection pool. Decide in Phase 2 whether the security benefit justifies the operational cost.

## Step 1.5: Create core/database.py

Async connection pool with environment auto-detection. Key functions:
- `get_pool() -> asyncpg.Pool` — singleton pool with conservative sizing (see [Connection Pool Sizing](#connection-pool-sizing) below)
- `close_pool()` — cleanup on shutdown
- `DatabaseConfig.get_connection_string()` — env detection

### Environment Auto-Detection Strategy

Reference pattern (from v1):
```python
# apexflow-v1/core/gemini_client.py — already implements this:
def is_gcp_environment() -> bool:
    return bool(os.environ.get("K_SERVICE") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))
```

Database connection strategy:
```python
# core/database.py — follows same pattern
class DatabaseConfig:
    @staticmethod
    def get_connection_string() -> str:
        # Priority 1: Explicit override (any environment)
        if url := os.environ.get("DATABASE_URL"):
            return url

        # Priority 2: Cloud Run -> managed AlloyDB
        if os.environ.get("K_SERVICE"):
            host = os.environ.get("ALLOYDB_HOST")       # Private IP or Unix socket
            db = os.environ.get("ALLOYDB_DB", "apexflow")
            user = os.environ.get("ALLOYDB_USER", "apexflow")
            password = os.environ.get("ALLOYDB_PASSWORD", "")
            return f"postgresql://{user}:{password}@{host}/{db}"

        # Priority 3: Local dev -> AlloyDB Omni Docker
        sslmode = os.environ.get('DB_SSLMODE', 'disable')
        return f"postgresql://{os.environ.get('DB_USER', 'apexflow')}:" \
               f"{os.environ.get('DB_PASSWORD', 'apexflow')}@" \
               f"{os.environ.get('DB_HOST', 'localhost')}:" \
               f"{os.environ.get('DB_PORT', '5432')}/" \
               f"{os.environ.get('DB_NAME', 'apexflow')}?sslmode={sslmode}"
```

### Connection Pool Sizing

Pool size must be derived from the Cloud Run deployment model, not chosen arbitrarily.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Server process model** | 1 Uvicorn worker per container | Cloud Run scales by adding instances, not workers within an instance |
| **Cloud Run concurrency** | 80 (default) | Max concurrent requests per instance |
| **Pool min_size** | 1 | Keep 1 warm connection to avoid cold-start latency on first query |
| **Pool max_size** | 5 | With 1 worker and async queries, 5 connections handle 80 concurrent requests (most time is spent awaiting Gemini, not DB) |
| **Max DB connections budget** | ~500 (AlloyDB default) | At max_size=5, this allows 100 Cloud Run instances before hitting the limit |

```python
# core/database.py
pool = await asyncpg.create_pool(
    dsn=DatabaseConfig.get_connection_string(),
    min_size=1,
    max_size=int(os.environ.get("DB_POOL_MAX", "5")),
    command_timeout=30,
)
```

> **When to add a connection pooler (PgBouncer/AlloyDB Auth Proxy):** If you observe connection churn (frequent pool exhaustion logs) or need >100 Cloud Run instances, add a pooler between the app and the database. Don't pre-optimize — monitor first.

## Step 1.6: Create .env.example

```
# Database (local dev defaults)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=apexflow
DB_USER=apexflow
DB_PASSWORD=apexflow
DB_SSLMODE=disable            # Set to "require" for production

# Gemini (required for local dev)
GEMINI_API_KEY=your-key-here

# Firebase (required for auth)
# GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json

# Cloud Run sets these automatically:
# K_SERVICE=apexflow-api
# ALLOYDB_HOST=10.x.x.x
# ALLOYDB_DB=apexflow
```

## Step 1.7: Create directory structure

```bash
mkdir -p core/stores core/rag core/skills
mkdir -p agents memory remme/hubs remme/engines remme/sources
mkdir -p services tools routers shared config prompts scripts tests
mkdir -p alembic/versions
```

## Step 1.8: Initialize Alembic for schema migrations

Relying solely on `docker-entrypoint-initdb.d` + "destroy the volume to re-run" is not a maintainable workflow. We adopt **Alembic** for forward-only, versioned migrations from day one.

```bash
# Initialize Alembic (after installing dev dependencies)
alembic init alembic
```

Configure `alembic/env.py` to use `psycopg2` (sync driver) and read `DATABASE_URL` from the environment (or fall back to building from `DB_HOST`/`DB_USER`/etc env vars). Alembic runs synchronous migrations — using `asyncpg` would require a complex async wrapper that adds no value here.

### Migration workflow

1. **Initial migration:** Convert `init-db.sql` into the first Alembic migration (`alembic revision --autogenerate -m "initial schema"`). Keep `init-db.sql` as a reference but treat the Alembic migration as the source of truth.
2. **New changes:** `alembic revision --autogenerate -m "description"` → review generated SQL → `alembic upgrade head`
3. **CI:** Run `alembic upgrade head` against the CI Postgres (pgvector profile) to verify migrations apply cleanly.
4. **Production deploys:** Run `alembic upgrade head` as a pre-deploy step in the Cloud Run deploy pipeline. For index builds on large tables, use `CREATE INDEX CONCURRENTLY` in manual migrations (Alembic can run raw SQL in `op.execute()`).

### Migration review gates

- Every migration must be reviewed in PR (migrations are code, not scripts)
- Destructive migrations (DROP COLUMN, DROP TABLE) require explicit approval
- Index migrations on tables >100K rows must use `CONCURRENTLY`

### Directory structure

```
alembic/
├── alembic.ini          # Config (DB URL from env)
├── env.py               # Sync engine setup (psycopg2)
├── script.py.mako       # Migration template
└── versions/
    └── 001_initial_schema.py
```

> **Why not Flyway/Sqitch?** Alembic integrates natively with SQLAlchemy/asyncpg and is the standard in the Python ecosystem. Since we already use asyncpg, Alembic minimizes tool sprawl.

---

## Fallback: Vanilla PostgreSQL

If AlloyDB Omni is unavailable (CI environments, constrained machines, etc.), the app works on vanilla PostgreSQL 15+ with pgvector **using the same `init-db.sql` script** — no manual edits needed.

The schema uses `DO $$ ... $$;` blocks that check `pg_available_extensions` at runtime:
- **AlloyDB Omni**: Detects `alloydb_scann` → **skips** vector index creation (ScaNN requires non-empty tables). Run `scripts/create-scann-indexes.sql` after inserting initial data.
- **Vanilla PostgreSQL**: `alloydb_scann` missing → creates IVFFlat indexes immediately (IVFFlat works on empty tables)

Use the [CI docker-compose profile](#ci-profile-docker-composeciyml) (`docker-compose.ci.yml` with `pgvector/pgvector:pg15`) for CI environments. This ensures `CREATE EXTENSION vector` succeeds without AlloyDB Omni.

**Trade-offs**: IVFFlat has lower recall at the same query speed compared to ScaNN. For dev/demo workloads (< 100K vectors), the difference is negligible. For production, use AlloyDB (managed or Omni).

**Runtime detection** (for `core/database.py`): At startup, query `SELECT extname FROM pg_extension WHERE extname = 'alloydb_scann'` to detect the environment and log which index type is in use.

---

## ADR: AlloyDB Omni Licensing

AlloyDB Omni is **not open-source PostgreSQL**. It is commercial software with specific license terms that must be understood before use.

### Key license constraints (AlloyDB Omni Developer Edition)

| Constraint | Detail |
|-----------|--------|
| **Development/evaluation** | Free, no restrictions |
| **Non-commercial production** | Permitted |
| **Commercial production** | Requires a paid subscription (AlloyDB Omni Enterprise) |
| **Hosted/managed service** | **Prohibited** — you may not offer Omni as a database-as-a-service |
| **Benchmark disclosure** | Restricted — cannot publish benchmark results without Google's written consent |

Source: [AlloyDB Omni Developer Edition License Terms](https://cloud.google.com/terms/alloydb-omni-marketplace-terms)

### Decision

| Environment | Database | License path |
|------------|----------|-------------|
| Local dev | AlloyDB Omni (Docker) | Free (development use) |
| CI | PostgreSQL 15 + pgvector | Open source (no Omni) |
| Production | **Managed AlloyDB on GCP** | GCP service agreement (pay-per-use) |
| Budget prod/demo | AlloyDB Omni on GCE VM | Free if non-commercial; **requires Enterprise license for commercial use** |

> **Action required before launch:** If the "Budget Production" (Omni on GCE) path is used for a commercial product, confirm the licensing path with Google Cloud sales. If this is a non-commercial/internal tool, no action needed.

---

## Production: Managed AlloyDB on GCP

When deploying to Cloud Run, use **managed AlloyDB** (not Omni). AlloyDB instances only have **private IPs** — Cloud Run needs VPC connectivity to reach them.

**VPC connectivity options:**
- **Direct VPC egress** (preferred if available in your org/project) — no additional infrastructure needed
- **Serverless VPC Access connector** (legacy, works everywhere) — adds a small VM (~$7/month)

The setup below uses a VPC connector. If Direct VPC egress is enabled, skip step 4 and use `--network=default --subnet=default` instead of `--vpc-connector`.

### Architecture

```
Cloud Run Service
    │
    ▼
Serverless VPC Access Connector (same region)
    │
    ▼
VPC Network (Private Services Access enabled)
    │
    ▼
AlloyDB Instance (Private IP: 10.x.x.x)
```

### Setup Steps (one-time)

1. **Create AlloyDB cluster** in the same region as Cloud Run (e.g., `us-central1`)
   ```bash
   # Note: AlloyDB commands may require the beta component
   gcloud beta alloydb clusters create apexflow-cluster \
     --region=us-central1 \
     --password=<db-password> \
     --network=default
   ```

2. **Create primary instance**
   ```bash
   gcloud beta alloydb instances create apexflow-primary \
     --cluster=apexflow-cluster \
     --region=us-central1 \
     --instance-type=PRIMARY \
     --cpu-count=2
   # Verify available flags with: gcloud beta alloydb instances create --help
   ```

3. **Apply schema** (from a VM or Cloud Shell in the same VPC)
   ```bash
   psql -h <ALLOYDB_PRIVATE_IP> -U postgres -d apexflow -f scripts/init-db.sql
   ```

4. **Create Serverless VPC Access Connector**
   ```bash
   gcloud compute networks vpc-access connectors create apexflow-connector \
     --region=us-central1 \
     --network=default \
     --range=10.8.0.0/28
   ```

5. **Deploy Cloud Run with VPC connector**
   ```bash
   gcloud run deploy apexflow-api \
     --image=gcr.io/$PROJECT_ID/apexflow-api \
     --region=us-central1 \
     --vpc-connector=apexflow-connector \
     --set-env-vars="ALLOYDB_HOST=<PRIVATE_IP>,ALLOYDB_DB=apexflow,ALLOYDB_USER=postgres,ALLOYDB_PASSWORD=<password>"
   ```

### Required IAM Roles

For the Cloud Run service account:
- `roles/alloydb.client` — connect and query
- `roles/vpcaccess.user` — use VPC connector

### Connection from core/database.py

The existing `DatabaseConfig.get_connection_string()` handles this automatically:
- Cloud Run sets `K_SERVICE` → triggers Priority 2 (reads `ALLOYDB_HOST` etc.)
- Private IP connection, no Auth Proxy needed for same-VPC

### Cost Notes (dev/demo)

| Component | Approx. Cost |
|-----------|-------------|
| AlloyDB primary (2 vCPU) | ~$200/month |
| VPC connector (e2-micro) | ~$7/month |
| Cloud Run (per-use) | Pay per request |

For dev/demo, consider using AlloyDB Omni on a GCE VM instead (see below) to avoid the managed AlloyDB minimum cost.

---

## Alternative: AlloyDB Omni on GCE VM (Budget Production)

For dev/demo deployments where managed AlloyDB's ~$200/month minimum is too high, run AlloyDB Omni on a GCE VM. This gives you full ScaNN support at a fraction of the cost.

### Recommended VM Configuration

| Setting | Recommended | Budget Minimum |
|---------|------------|----------------|
| **Machine Family** | **N2** (Intel Ice Lake) | E2 (mixed hardware) |
| **Machine Type** | `n2-standard-2` (2 vCPU, 8 GB) | `e2-standard-2` (2 vCPU, 8 GB) |
| **Boot Disk** | 50 GB SSD (`pd-ssd`) | 50 GB SSD (`pd-ssd`) |
| **OS** | Ubuntu 22.04 LTS or Debian 11 | Same |
| **Approx. Cost** | ~$71/month | ~$50/month |

### Why N2 (not E2) for ScaNN

**This is the single most important hardware decision for vector search performance.**

ScaNN uses **AVX2 SIMD instructions** for fast distance computation. The CPU must support these instructions for ScaNN to run at hardware-accelerated speed.

| Machine Family | CPU Guarantee | AVX2 Support | ScaNN Performance |
|---------------|---------------|--------------|-------------------|
| **N2** | Intel Ice Lake (or newer) | Guaranteed AVX2 + AVX-512 | Full speed (<10ms search) |
| **C3** | Intel Sapphire Rapids | Guaranteed AVX2 + AVX-512 | Full speed (overkill for dev) |
| **E2** | Mixed hardware pool | **Not guaranteed** | May fall back to scalar mode (200ms+) |

If you use E2 and get assigned an older processor, ScaNN silently falls back to scalar (non-SIMD) mode. Queries that should take <10ms will take 200ms+. **You won't get an error — just slow performance.**

### Why 16 GB RAM

AlloyDB Omni runs three memory-hungry components simultaneously:

1. **PostgreSQL engine** — shared buffers for query caching
2. **Columnar engine** — separate memory pool (AMD64 only)
3. **ScaNN vector index** — **memory-resident** (loaded into RAM for fast search)

With 8 GB, you risk OOM kills when building indexes while serving queries. 16 GB provides headroom for the OS, Docker, and all three components.

### Why SSD Storage

Vector index building is **write-heavy** — AlloyDB reads raw vectors and writes a structured tree to disk. Standard persistent disk (`pd-standard`) has low IOPS, making index builds painfully slow. SSD (`pd-ssd` or `pd-balanced`) prevents disk from becoming the bottleneck during data ingestion.

### GCE VM Setup

```bash
# 1. Create the VM
gcloud compute instances create alloydb-omni-dev \
  --zone=us-central1-a \
  --machine-type=n2-standard-2 \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --tags=alloydb

# 2. SSH in and install Docker
gcloud compute ssh alloydb-omni-dev --zone=us-central1-a
sudo apt update && sudo apt install -y docker.io docker-compose
sudo systemctl enable docker

# 3. Copy schema and start AlloyDB Omni
# (scp your docker-compose.yml and scripts/init-db.sql to the VM)
sudo docker-compose up -d

# 4. Create firewall rule for Cloud Run (or SSH tunnel)
gcloud compute firewall-rules create allow-alloydb \
  --allow=tcp:5432 \
  --source-ranges=10.8.0.0/28 \  # VPC connector range
  --target-tags=alloydb
```

### Budget Minimum (E2)

If you're **only testing functionality** (not benchmarking performance):
- `e2-standard-2` (2 vCPU, 8 GB) works for < 10K vectors
- ScaNN may fall back to scalar mode — expect 200ms+ queries instead of <10ms
- **Do not benchmark performance on this configuration**

---

## Verification

### Local Dev (AlloyDB Omni)

```bash
# 1. Start
docker-compose up -d

# 2. Verify container health
docker-compose ps
# Expected: alloydb-omni ... healthy

# 3. Connect and check extensions
psql -h localhost -U apexflow -d apexflow -c "\dx"
# Expected output includes: vector, alloydb_scann

# 4. Check tables
psql -h localhost -U apexflow -d apexflow -c "\dt"
# Expected: 13 tables (sessions, jobs, job_runs, notifications,
#   memories, documents, document_chunks, chat_sessions,
#   chat_messages, user_preferences, system_state,
#   scanned_runs, security_logs)

# 5. Check indexes
psql -h localhost -U apexflow -d apexflow -c "\di"
# Expected: GIN index (idx_chunks_fts), plus B-tree indexes.
# NOTE: ScaNN indexes (idx_memories_embedding, idx_chunks_embedding) are NOT
# created yet — ScaNN requires non-empty tables. They will be created after
# initial data insertion via scripts/create-scann-indexes.sql.

# 6. Test vector search (insert data, create ScaNN index, then query)
psql -h localhost -U apexflow -d apexflow -c "
  INSERT INTO memories (id, user_id, text, embedding)
  VALUES ('test1', 'default', 'test memory', '[' || array_to_string(array(SELECT random() FROM generate_series(1,768)), ',') || ']');
"
psql -h localhost -U apexflow -d apexflow -f scripts/create-scann-indexes.sql
psql -h localhost -U apexflow -d apexflow -c "
  SELECT id, 1 - (embedding <=> (SELECT embedding FROM memories WHERE id='test1')) AS similarity
  FROM memories ORDER BY embedding <=> (SELECT embedding FROM memories WHERE id='test1') LIMIT 1;
  DELETE FROM memories WHERE id='test1';
"
# Expected: returns test1 with similarity = 1.0
```

### CI (PostgreSQL + pgvector)

```bash
# 1. Start CI profile (empty database — no init-db.sql mount)
docker compose -f docker-compose.ci.yml up -d

# 2. Apply schema via Alembic (sole schema applicator in CI)
DB_HOST=localhost alembic upgrade head
# Expected: all 13 tables created, no errors

# 3. Verify tables exist
docker compose -f docker-compose.ci.yml exec postgres psql -U apexflow -d apexflow -c "\dt"
# Expected: 13 tables

# 4. Verify IVFFlat indexes (not ScaNN)
docker compose -f docker-compose.ci.yml exec postgres psql -U apexflow -d apexflow -c "\di"
# Expected: idx_memories_embedding and idx_chunks_embedding using IVFFlat
```

### Production (Cloud Run + AlloyDB)

- `gcloud run deploy` succeeds
- Health check `GET /readiness` returns `{"status": "ready"}` (verifies DB connection)
- `psql` from Cloud Shell (same VPC) connects to AlloyDB and shows all tables
- `alembic upgrade head` runs without errors in the deploy pipeline

---

## Dev Tooling (required in Phase 1)

These prevent the new codebase from becoming the next legacy system:

### Formatting and linting

```toml
# pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```

### Pre-commit hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic>=2.9.0]
```

### Test harness

```bash
# Run tests
pytest tests/ -v

# Run with async support
pytest tests/ -v --asyncio-mode=auto
```

### Minimal CI pipeline (Google Cloud Build)

We use Google Cloud Build (`cloudbuild.yaml`), not GitHub Actions. The CI pipeline must validate at minimum:
1. `ruff check .` — linting passes
2. `mypy core/` — type checking passes
3. Schema applies cleanly on pgvector Postgres via `alembic upgrade head` (Alembic is the sole schema applicator — no Docker entrypoint init)
4. `pytest tests/` — unit tests pass

> **Cloud Build networking note:** Each Cloud Build step runs in a separate Docker container. To allow steps to reach the database, start the pgvector container on the shared `cloudbuild` network (`docker run --network=cloudbuild --name=postgres ...`) and connect via hostname `postgres`, **not** `localhost`. Using `docker compose` creates a separate Docker network that other steps cannot reach.

---

## Phase 1 Exit Criteria

Phase 1 is **done** when all of the following are true:

- [ ] **Schema verified on both profiles:**
  - AlloyDB Omni (local, ScaNN indexes) — `docker compose up` + verify 13 tables
  - PostgreSQL + pgvector (CI, IVFFlat indexes) — `docker compose -f docker-compose.ci.yml up` + verify 13 tables
- [ ] **Migration mechanism exists:** Alembic initialized with at least the initial migration; `alembic upgrade head` succeeds on both profiles
- [ ] **Version parity documented:** Target PostgreSQL major version (15) declared and consistent across dev, CI, and production environments
- [ ] **Tenancy posture decided:** `user_id` has no default value; application layer always provides it; RLS decision documented for Phase 2
- [ ] **Licensing ADR written:** AlloyDB Omni usage constraints understood; production path (managed AlloyDB) confirmed
- [ ] **Operational hooks in place:**
  - `/readiness` endpoint checks DB connectivity
  - Structured logging configured (JSON format for Cloud Run)
  - Retention plan documented for high-volume tables (security_logs, chat_messages, sessions, job_runs)
- [ ] **Schema quality baseline:** TEXT PK decision documented, CHECK constraints on all status/role fields, UNIQUE constraints on dedup columns, JSONB fields catalogued with expected structure notes
- [ ] **Dev tooling active:** ruff, mypy, pre-commit hooks, pytest all configured and passing
- [ ] **CI pipeline runs:** schema apply + lint + type check + tests all green
