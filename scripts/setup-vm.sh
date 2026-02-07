#!/bin/bash
set -euo pipefail

echo "========================================="
echo "ApexFlow GCE VM Setup - AlloyDB Omni"
echo "========================================="

# 1. Install Docker Engine + Docker Compose plugin
echo "[1/6] Installing Docker Engine..."
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 2. Enable Docker on boot
echo "[2/6] Enabling Docker service..."
systemctl enable docker
systemctl start docker

# 3. Create app directory
echo "[3/6] Creating /opt/apexflow directory..."
mkdir -p /opt/apexflow/scripts

# 4. Write docker-compose.vm.yml
echo "[4/6] Writing docker-compose.vm.yml..."
cat > /opt/apexflow/docker-compose.vm.yml << 'COMPOSE_EOF'
version: '3.8'
services:
  alloydb-omni:
    image: google/alloydbomni:15.12.0
    restart: always
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: apexflow
      POSTGRES_PASSWORD: apexflow
      POSTGRES_DB: apexflow
    volumes:
      - alloydb_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/01-schema.sql
    shm_size: '512mb'
    ulimits:
      nice:
        soft: -20
        hard: -20
      memlock:
        soft: -1
        hard: -1
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U apexflow -d apexflow"]
      interval: 5s
      timeout: 3s
      retries: 10
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  alloydb_data:
COMPOSE_EOF

# 5. Write init-db.sql (full 13-table schema)
echo "[5/6] Writing init-db.sql..."
cat > /opt/apexflow/scripts/init-db.sql << 'SQL_EOF'
-- ================================================================
-- ApexFlow AlloyDB Schema
-- ================================================================

CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'alloydb_scann') THEN
        EXECUTE 'CREATE EXTENSION IF NOT EXISTS alloydb_scann';
        RAISE NOTICE 'alloydb_scann extension enabled';
    ELSE
        RAISE NOTICE 'alloydb_scann not available — using IVFFlat indexes';
    END IF;
END $$;

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
    UNIQUE(job_id, scheduled_for)
);
CREATE INDEX idx_job_runs_job ON job_runs(job_id, scheduled_for DESC);

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
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'alloydb_scann') THEN
        RAISE NOTICE 'AlloyDB detected — skipping ScaNN index (create after data insertion)';
    ELSE
        EXECUTE 'CREATE INDEX idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)';
    END IF;
END $$;
CREATE INDEX idx_memories_user     ON memories(user_id);
CREATE INDEX idx_memories_category ON memories(user_id, category);

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
    UNIQUE(user_id, file_hash)
);
CREATE INDEX idx_docs_user ON documents(user_id);
CREATE INDEX idx_docs_hash ON documents(file_hash);

CREATE TABLE document_chunks (
    id              TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       VECTOR(768) NOT NULL,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(document_id, chunk_index)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'alloydb_scann') THEN
        RAISE NOTICE 'AlloyDB detected — skipping ScaNN index (create after data insertion)';
    ELSE
        EXECUTE 'CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
    END IF;
END $$;
CREATE INDEX idx_chunks_doc  ON document_chunks(document_id);
CREATE INDEX idx_chunks_user ON document_chunks(user_id);
ALTER TABLE document_chunks ADD COLUMN content_tsv TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX idx_chunks_fts ON document_chunks USING GIN(content_tsv);

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

CREATE TABLE chat_messages (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);
CREATE INDEX idx_chat_msg_session ON chat_messages(user_id, session_id, created_at);
CREATE INDEX idx_chat_msg_role    ON chat_messages(session_id, role);

CREATE TABLE user_preferences (
    user_id         TEXT PRIMARY KEY,
    preferences     JSONB NOT NULL DEFAULT '{}',
    operating_ctx   JSONB NOT NULL DEFAULT '{}',
    soft_identity   JSONB NOT NULL DEFAULT '{}',
    evidence_log    JSONB NOT NULL DEFAULT '{}',
    staging_queue   JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE system_state (
    user_id         TEXT NOT NULL,
    key             TEXT NOT NULL,
    value           JSONB NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, key)
);

CREATE TABLE scanned_runs (
    run_id          TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    scanned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
SQL_EOF

# 6. Start AlloyDB Omni
echo "[6/6] Starting AlloyDB Omni..."
cd /opt/apexflow
docker compose -f docker-compose.vm.yml up -d

# 7. Wait for healthy
echo "Waiting for AlloyDB Omni to become healthy..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.vm.yml ps --format '{{.Health}}' | grep -qw healthy; then
        echo "AlloyDB Omni is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "WARNING: Timed out waiting for AlloyDB Omni to become healthy"
        docker compose -f docker-compose.vm.yml logs
    fi
    sleep 5
done

# 8. Log the VM's external IP
EXTERNAL_IP=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip 2>/dev/null || echo "unknown")
echo "========================================="
echo "AlloyDB Omni is running on this VM."
echo "External IP: ${EXTERNAL_IP}"
echo "Connection:  psql -h ${EXTERNAL_IP} -U apexflow -d apexflow"
echo "Password:    apexflow"
echo "========================================="
