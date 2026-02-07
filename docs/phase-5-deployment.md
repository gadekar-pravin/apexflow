# Phase 5: Production Deployment

**Prerequisites:** Phases 4a, 4b, 4c all complete
**Produces:** Deployable Docker image, CI/CD pipeline, data migration, test infrastructure

---

## Step 5.1: Create Dockerfile

```dockerfile
# ---- Builder stage ----
FROM python:3.11-slim AS builder
WORKDIR /app

# Install uv and explicitly create the venv
COPY pyproject.toml uv.lock ./
RUN pip install uv \
    && uv venv /app/.venv \
    && UV_PROJECT_ENVIRONMENT=/app/.venv uv sync --no-dev --frozen

# ---- Runtime stage ----
FROM python:3.11-slim
WORKDIR /app

# Runtime hardening
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

# Copy venv from builder + application code
COPY --from=builder /app/.venv /app/.venv
COPY . .

# Non-root user (production hardening)
RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --no-create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Production server: uvicorn with configurable workers
# Cloud Run sets $PORT; --workers defaults to 1 (appropriate for Cloud Run concurrency model)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

### Dockerfile notes

- **`uv venv /app/.venv` + `UV_PROJECT_ENVIRONMENT`:** Explicitly creates the venv and tells `uv sync` where to install. Without this, `uv sync` may place packages in a system location and `COPY --from=builder /app/.venv` would copy an empty directory.
- **`PYTHONUNBUFFERED=1`:** Ensures logs appear immediately in Cloud Run (no buffering delays).
- **`PYTHONDONTWRITEBYTECODE=1`:** Prevents `.pyc` files in the container (smaller image, no write-to-readonly issues).
- **Non-root user:** Cloud Run doesn't require root; running as `appuser` limits blast radius of container escape.
- **`--workers 1`:** Cloud Run handles scaling via instances, not in-process workers. A single uvicorn worker is appropriate because Cloud Run's concurrency setting controls how many requests reach each instance. For high-throughput scenarios, consider `gunicorn` with `UvicornWorker`:

```dockerfile
# Alternative: gunicorn with UvicornWorker (for high-throughput)
# CMD ["gunicorn", "api:app", "-k", "uvicorn.workers.UvicornWorker", \
#      "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "300"]
```

**Always commit `uv.lock`** to the repo for deterministic builds. The `--frozen` flag ensures `uv sync` uses the lock file exactly without updating it.

## Step 5.2: Create cloudbuild.yaml

### Auth strategy decision

| Approach | How it works | When to use |
|----------|--------------|-------------|
| **Perimeter auth** (`--no-allow-unauthenticated`) | Cloud Run requires IAM token on every request. Frontend uses Identity-Aware Proxy or service-to-service auth. | Service-to-service APIs, admin-only endpoints |
| **In-app auth** (`--allow-unauthenticated` + Firebase JWT) | Cloud Run accepts all requests; FastAPI middleware validates Firebase JWT. Must pair with rate limiting. | User-facing APIs with Firebase Auth (our case) |

**Decision: In-app auth** — Cloud Run is unauthenticated at the perimeter, but the FastAPI auth middleware (Phase 2) validates Firebase JWTs. This requires:
- `AUTH_DISABLED` is **impossible** in production (Phase 2's `K_SERVICE` guard)
- Rate limiting at Cloud Run level (`--max-instances`) and optionally at API level
- CORS restricted to known origins

### Secrets management

**Never put secrets in plaintext env vars, YAML, or source code.** Use Google Secret Manager:

| Secret | Secret Manager key | Used by |
|--------|-------------------|---------|
| AlloyDB password | `apexflow-db-password` | Database connection |
| Firebase service account key | `apexflow-firebase-sa` | JWT validation |
| Gemini API key | `apexflow-gemini-key` | Embeddings, LLM calls |

### cloudbuild.yaml

```yaml
# Use Artifact Registry (recommended over gcr.io)
substitutions:
  _REGION: us-central1
  _REPO: apexflow
  _IMAGE: ${_REGION}-docker.pkg.dev/${PROJECT_ID}/${_REPO}/apexflow-api
  _SERVICE_ACCOUNT: apexflow-api@${PROJECT_ID}.iam.gserviceaccount.com
  _VPC_CONNECTOR: projects/${PROJECT_ID}/locations/${_REGION}/connectors/apexflow-vpc

steps:
  # 1. Run linting and type checks
  - name: 'python:3.11-slim'
    entrypoint: bash
    args:
      - '-c'
      - |
        pip install uv
        uv venv /tmp/.venv
        UV_PROJECT_ENVIRONMENT=/tmp/.venv uv sync --frozen
        export PATH="/tmp/.venv/bin:$PATH"
        ruff check .
        mypy --config-file pyproject.toml .

  # 2. Run tests against CI database (uses docker-compose.ci.yml from Phase 1)
  - name: 'docker/compose:latest'
    args: ['-f', 'docker-compose.ci.yml', 'up', '-d', '--wait']

  - name: 'python:3.11-slim'
    entrypoint: bash
    args:
      - '-c'
      - |
        pip install uv
        uv venv /tmp/.venv
        UV_PROJECT_ENVIRONMENT=/tmp/.venv uv sync --frozen
        export PATH="/tmp/.venv/bin:$PATH"
        # Apply schema using psql (reliable multi-statement execution)
        apt-get update && apt-get install -y postgresql-client
        psql "$$DATABASE_TEST_URL" -f scripts/init-db.sql
        # Run tests
        pytest tests/ -v --tb=short
    env:
      - 'DATABASE_TEST_URL=postgresql://apexflow:apexflow@localhost:5432/apexflow_test'

  # 3. Build and push container image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', '${_IMAGE}:${SHORT_SHA}', '-t', '${_IMAGE}:latest', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '--all-tags', '${_IMAGE}']

  # 4. Deploy to Cloud Run
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: gcloud
    args:
      - 'run'
      - 'deploy'
      - 'apexflow-api'
      - '--image=${_IMAGE}:${SHORT_SHA}'
      - '--region=${_REGION}'
      - '--platform=managed'
      - '--allow-unauthenticated'          # In-app auth via Firebase JWT
      - '--service-account=${_SERVICE_ACCOUNT}'
      - '--vpc-connector=${_VPC_CONNECTOR}'  # AlloyDB private IP access
      - '--vpc-egress=private-ranges-only'   # Only route private IPs through VPC
      - '--memory=1Gi'
      - '--cpu=1'
      - '--concurrency=80'
      - '--max-instances=10'
      - '--timeout=300'
      - '--set-secrets=ALLOYDB_PASSWORD=apexflow-db-password:latest'
      - '--set-secrets=FIREBASE_SA_KEY=apexflow-firebase-sa:latest'
      - '--set-secrets=GEMINI_API_KEY=apexflow-gemini-key:latest'
      - '--set-env-vars=ALLOYDB_HOST=10.x.x.x'          # Private IP — fill in actual
      - '--set-env-vars=ALLOYDB_DB=apexflow'
      - '--set-env-vars=ALLOYDB_USER=apexflow'
      - '--set-env-vars=LOG_LEVEL=info'

images:
  - '${_IMAGE}:${SHORT_SHA}'
  - '${_IMAGE}:latest'
```

### Cloud Run networking setup (prerequisite)

Before the first deploy, configure AlloyDB connectivity:

```bash
# 1. Create a Serverless VPC Access connector (one-time)
gcloud compute networks vpc-access connectors create apexflow-vpc \
  --region=us-central1 \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=3

# 2. Create a service account with least privilege (one-time)
gcloud iam service-accounts create apexflow-api \
  --display-name="ApexFlow API Service Account"

# Grant AlloyDB Client role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:apexflow-api@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/alloydb.client"

# Grant Secret Manager accessor role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:apexflow-api@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 3. Store secrets in Secret Manager
echo -n "DB_PASSWORD_HERE" | gcloud secrets create apexflow-db-password --data-file=-
echo -n "GEMINI_KEY_HERE"  | gcloud secrets create apexflow-gemini-key --data-file=-
# Firebase SA key (JSON file):
gcloud secrets create apexflow-firebase-sa --data-file=firebase-sa-key.json
```

### Rollback strategy

Cloud Run keeps previous revisions. To rollback:

```bash
# List revisions
gcloud run revisions list --service=apexflow-api --region=us-central1

# Route 100% traffic to a previous revision
gcloud run services update-traffic apexflow-api \
  --region=us-central1 \
  --to-revisions=apexflow-api-REVISION=100
```

For canary deploys, use traffic splitting:

```bash
# Route 10% to new, 90% to current
gcloud run services update-traffic apexflow-api \
  --region=us-central1 \
  --to-revisions=apexflow-api-NEW=10,apexflow-api-CURRENT=90
```

## Step 5.3: Add health checks to api.py

```python
import asyncio
import time

_readiness_cache: dict = {"ready": False, "checked_at": 0}
_READINESS_CACHE_TTL = 5  # seconds — avoid hammering DB on every probe

@app.get("/readiness")
async def readiness():
    """Check DB connectivity. Cached for 5s. Fails fast on timeout."""
    now = time.monotonic()
    if _readiness_cache["ready"] and (now - _readiness_cache["checked_at"]) < _READINESS_CACHE_TTL:
        return {"status": "ready", "cached": True}

    try:
        pool = await get_pool()
        # Timeout: 2s total (acquire + execute). A stuck DB should not hang the probe.
        async with asyncio.timeout(2.0):
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
        _readiness_cache["ready"] = True
        _readiness_cache["checked_at"] = now
        return {"status": "ready"}
    except (asyncio.TimeoutError, Exception) as e:
        _readiness_cache["ready"] = False
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "error": type(e).__name__}
        )

@app.get("/liveness")
async def liveness():
    """Always returns 200 — proves the process is alive."""
    return {"status": "alive"}
```

### Health check notes

- **Readiness** is probed by Cloud Run to determine if an instance can receive traffic. A stuck DB connection can hang indefinitely without the 2s timeout.
- **Cache (5s TTL)** reduces DB chatter under load — Cloud Run can probe every 1-10s depending on configuration.
- **Liveness** never touches the DB — it proves the Python process is responsive. Cloud Run uses this to detect hung processes.
- **503 on failure:** Cloud Run will stop routing traffic to this instance until readiness succeeds again.

## Step 5.4: Update frontend config

### Per-environment API URLs

```bash
# apexflow-ui/.env.development
VITE_API_URL=http://localhost:8000
VITE_API_VERSION=v1

# apexflow-ui/.env.staging
VITE_API_URL=https://apexflow-api-staging-HASH-uc.a.run.app
VITE_API_VERSION=v1

# apexflow-ui/.env.production
VITE_API_URL=https://apexflow-api-HASH-uc.a.run.app
VITE_API_VERSION=v1
```

### CORS configuration (api.py)

Cloud Run and Firebase Hosting serve from different origins. Configure CORS to allow only known origins:

```python
# api.py — add CORS middleware
from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "http://localhost:3000",                         # Local dev
    "http://localhost:5173",                         # Vite dev server
    "https://apexflow-PROJECTID.web.app",            # Firebase Hosting
    "https://apexflow-PROJECTID.firebaseapp.com",    # Firebase Hosting alt
    "https://apexflow-api-HASH-uc.a.run.app",        # Cloud Run (same-origin API calls)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

> **Environment-specific origins:** Use an env var (`CORS_ORIGINS`) to configure allowed origins per environment instead of hardcoding. Parse as comma-separated list.

## Step 5.5: Data migration

### User/tenant mapping decision

v1 is single-user (no `user_id` concept). In v2, every table requires `user_id`. **Decision: Map all v1 data to `user_id = 'default'`** — this is the same value used by `AUTH_DISABLED=1` in local dev. After migration, the single-user owner can claim their data by updating `user_id` to their Firebase UID.

```python
# Migration constant
V1_USER_ID = "default"  # All v1 data assigned to this user
```

### Running the migration

```bash
# Dry run (read-only, prints what would be migrated)
python scripts/migrate.py \
  --source-dir /Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1 \
  --db-url postgresql://apexflow:apexflow@localhost:5432/apexflow \
  --dry-run

# Full migration (resumable — safe to re-run)
python scripts/migrate.py \
  --source-dir /Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1 \
  --db-url postgresql://apexflow:apexflow@localhost:5432/apexflow \
  --user-id default

# Validate after migration
python scripts/migrate.py \
  --source-dir /Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1 \
  --db-url postgresql://apexflow:apexflow@localhost:5432/apexflow \
  --validate-only
```

### Migration script (scripts/migrate.py)

```python
"""
One-time migration: apexflow-v1 filesystem data -> AlloyDB

Usage:
  python scripts/migrate.py --source-dir ../apexflow-v1 --db-url postgresql://... --user-id default
  python scripts/migrate.py --source-dir ../apexflow-v1 --dry-run
  python scripts/migrate.py --source-dir ../apexflow-v1 --validate-only

Features:
  - Resumable: tracks progress in migration_state table. Safe to re-run.
  - Idempotent: INSERT ON CONFLICT DO NOTHING (but also reports skipped rows).
  - Batched: bulk inserts with configurable batch size for large datasets.
  - Validated: post-migration row counts + sample spot checks.
"""
import argparse
import asyncio
import asyncpg
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime

BATCH_SIZE = 100  # rows per INSERT batch

# Migration targets:
# 1. memory/session_summaries_index/**/*.json -> sessions table
# 2. data/system/jobs.json -> jobs table
# 3. data/inbox/notifications.db (SQLite) -> notifications table
# 4. data/.meta/chats/**/*.json -> chat_sessions + chat_messages tables
# 5. memory/remme_index/memories.json -> memories table (re-embed from text)
# 6. remme hubs JSON files -> user_preferences table
# 7. memory/remme_index/scanned_runs.json -> scanned_runs table
# 8. RAG documents -> re-ingest (re-chunk + re-embed) into documents + document_chunks


async def migrate_sessions(conn, source_dir: Path, user_id: str, dry_run: bool) -> dict:
    """Migrate session JSON files to sessions table. Uses executemany for bulk insert."""
    summaries = list((source_dir / "memory" / "session_summaries_index").rglob("session_*.json"))
    migrated, skipped, failed = 0, 0, 0
    batch = []
    for path in summaries:
        try:
            data = json.loads(path.read_text())
            batch.append((data["id"], user_id, data.get("query", ""),
                          data.get("status", "completed"), ...))
            if len(batch) >= BATCH_SIZE:
                if not dry_run:
                    result = await conn.executemany("""
                        INSERT INTO sessions (id, user_id, query, status, ...)
                        VALUES ($1, $2, $3, $4, ...)
                        ON CONFLICT (id) DO NOTHING
                    """, batch)
                migrated += len(batch)
                batch = []
        except Exception as e:
            logging.error(f"Failed to migrate {path}: {e}")
            failed += 1
    # Flush remaining batch
    if batch and not dry_run:
        await conn.executemany(..., batch)
        migrated += len(batch)
    return {"total": len(summaries), "migrated": migrated, "skipped": skipped, "failed": failed}


# ... similar for jobs, notifications, chats, preferences, scanned_runs ...
```

### Memory migration: re-embed from text (not FAISS extraction)

**Problem:** FAISS `index.bin` stores internal index structures, not raw embedding vectors in a portable format. Extracting vectors from FAISS is fragile and depends on index type (FlatL2 vs IVF vs HNSW).

**Strategy: Re-embed from text.** `memories.json` contains the memory text — re-generate embeddings using the current embedding model. This guarantees dimension/normalization compatibility with the v2 schema.

```python
async def migrate_memories(conn, source_dir: Path, user_id: str, dry_run: bool) -> dict:
    """Migrate memories by RE-EMBEDDING text (not extracting FAISS vectors)."""
    memories_file = source_dir / "memory" / "remme_index" / "memories.json"
    if not memories_file.exists():
        return {"total": 0, "migrated": 0, "note": "No memories.json found"}

    memories = json.loads(memories_file.read_text())
    migrated, failed = 0, 0
    batch_texts = []
    batch_records = []

    for mem in memories:
        batch_texts.append(mem["text"])
        batch_records.append(mem)

        if len(batch_texts) >= BATCH_SIZE:
            if not dry_run:
                # Batch embed — respects rate limits
                embeddings = await generate_embeddings_batch(batch_texts)
                await _insert_memories_batch(conn, user_id, batch_records, embeddings)
            migrated += len(batch_texts)
            batch_texts, batch_records = [], []

    # Flush remaining
    if batch_texts and not dry_run:
        embeddings = await generate_embeddings_batch(batch_texts)
        await _insert_memories_batch(conn, user_id, batch_records, embeddings)
        migrated += len(batch_texts)

    return {"total": len(memories), "migrated": migrated, "failed": failed,
            "note": "Re-embedded from text (FAISS index.bin ignored)"}
```

> **Why not extract FAISS vectors?** (1) FAISS index types differ — `faiss.read_index()` + `index.reconstruct()` only works for some index types. (2) Even if extraction works, the vectors may have different normalization than the current model. (3) Re-embedding is deterministic and guarantees compatibility.

### RAG re-ingest: throttled and resumable

```python
async def migrate_rag_documents(conn, source_dir: Path, user_id: str, dry_run: bool) -> dict:
    """Re-ingest RAG documents. Throttled to avoid embedding API rate limits."""
    # ... find document files ...
    migrated, skipped, failed = 0, 0, 0
    for doc_path in document_paths:
        content = doc_path.read_text()
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check if already migrated (resumability)
        existing = await conn.fetchrow(
            "SELECT id FROM documents WHERE user_id = $1 AND file_hash = $2",
            user_id, file_hash)
        if existing:
            skipped += 1
            continue

        if not dry_run:
            # Chunk + embed (expensive — throttle)
            chunks = chunk_document(content, method="rule_based")
            embeddings = await generate_embeddings_batch([c for c in chunks])
            await _store_document_and_chunks(conn, user_id, doc_path.name, content,
                                             file_hash, chunks, embeddings)
            # Throttle: avoid embedding API rate limits
            await asyncio.sleep(0.5)  # Adjust based on API quotas

        migrated += 1

    return {"total": len(document_paths), "migrated": migrated, "skipped": skipped, "failed": failed}
```

### Post-migration validation

```python
async def validate_migration(conn, source_dir: Path, user_id: str) -> dict:
    """Validate migrated data: row counts + sample spot checks."""
    report = {}

    # Row counts
    for table in ["sessions", "jobs", "notifications", "chat_sessions",
                  "chat_messages", "memories", "documents", "document_chunks",
                  "user_preferences", "scanned_runs"]:
        count = await conn.fetchval(f"SELECT COUNT(*) FROM {table} WHERE user_id = $1", user_id)
        report[f"{table}_count"] = count

    # Source counts (for comparison)
    source_sessions = len(list((source_dir / "memory" / "session_summaries_index").rglob("session_*.json")))
    report["source_sessions"] = source_sessions
    report["sessions_match"] = report["sessions_count"] >= source_sessions

    # Sample spot check: random 10 sessions
    samples = await conn.fetch(
        "SELECT id, query, status FROM sessions WHERE user_id = $1 ORDER BY RANDOM() LIMIT 10",
        user_id)
    report["sample_sessions"] = [dict(r) for r in samples]

    # Embedding dimension consistency
    dim_check = await conn.fetchrow("""
        SELECT MIN(array_length(embedding::real[], 1)) AS min_dim,
               MAX(array_length(embedding::real[], 1)) AS max_dim
        FROM document_chunks WHERE user_id = $1
    """, user_id)
    if dim_check and dim_check["min_dim"]:
        report["embedding_dims"] = {"min": dim_check["min_dim"], "max": dim_check["max_dim"]}
        report["embedding_dim_consistent"] = dim_check["min_dim"] == dim_check["max_dim"]

    return report
```

### Migration report

The migration script prints a final report:

```
=== Migration Report ===
User ID: default
Sessions:      142 migrated, 0 skipped, 0 failed (source: 142)
Jobs:            5 migrated, 0 skipped, 0 failed
Notifications:  23 migrated, 0 skipped, 0 failed
Chat sessions:  18 migrated, 0 skipped, 0 failed
Chat messages: 247 migrated, 0 skipped, 0 failed
Memories:       89 migrated, 0 skipped, 0 failed (re-embedded from text)
Documents:      12 migrated, 3 skipped (dedup), 0 failed
Doc chunks:    156 migrated, 0 skipped, 0 failed
Preferences:     1 migrated, 0 skipped, 0 failed
Scanned runs:   98 migrated, 0 skipped, 0 failed
Embedding dims: 768/768 (consistent)
========================
```

---

## Testing Strategy

### Prerequisites

**Required packages (add to dev dependencies):**
```toml
# pyproject.toml [tool.uv.dev-dependencies]
pytest = ">=8.0"
pytest-asyncio = ">=0.23"
httpx = ">=0.27"           # For FastAPI TestClient async support
```

**Required config:**
```ini
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"      # Auto-detect async test functions — no manual markers needed
```

### CI database provisioning

Tests require a running PostgreSQL with pgvector. Use the CI docker-compose from Phase 1:

```bash
# In CI (Cloud Build step or GitHub Actions):
docker compose -f docker-compose.ci.yml up -d --wait

# Apply schema using psql (NOT asyncpg conn.execute — asyncpg rejects multi-statement SQL)
psql "postgresql://apexflow:apexflow@localhost:5432/apexflow_test" -f scripts/init-db.sql
```

> **Why not `conn.execute(schema)`?** asyncpg does not support executing multiple SQL statements in a single call. The `init-db.sql` file contains `CREATE TABLE`, `CREATE INDEX`, `DO $$ ... $$` blocks, and `CREATE EXTENSION` — these require proper multi-statement execution via `psql` or a driver that splits statements.

### Test Infrastructure

```python
# tests/conftest.py
import pytest
import pytest_asyncio
import asyncpg
from pgvector.asyncpg import register_vector

@pytest_asyncio.fixture(scope="session")
async def db_pool():
    """Create a connection pool for tests. Schema already applied via psql in CI."""
    pool = await asyncpg.create_pool(
        "postgresql://apexflow:apexflow@localhost:5432/apexflow_test",
        init=register_vector,  # Register pgvector codec for all connections
    )
    yield pool
    await pool.close()

@pytest_asyncio.fixture(autouse=True)
async def clean_tables(db_pool):
    """Truncate all tables between tests for isolation."""
    async with db_pool.acquire() as conn:
        # Single TRUNCATE with all tables — faster and handles FK dependencies
        await conn.execute("""
            TRUNCATE chat_messages, job_runs, sessions, jobs,
                     notifications, memories, documents,
                     document_chunks, chat_sessions,
                     user_preferences, system_state,
                     scanned_runs, security_logs
            CASCADE
        """)
    yield

@pytest_asyncio.fixture
async def test_user_id():
    """Standard test user ID."""
    return "test-user-001"
```

### Test Categories

| Category | Focus | Files |
|----------|-------|-------|
| Store tests | CRUD for each store class | `tests/test_stores/test_session_store.py`, etc. |
| Service tests | ServiceRegistry routing, tool resolution | `tests/test_services/test_registry.py` |
| Sandbox tests | Monty security bypass + DoS vectors | `tests/test_sandbox/test_monty_security.py` |
| RAG tests | Ingest + hybrid search quality | `tests/test_stores/test_document_search.py` |
| API tests | Endpoint request/response | `tests/test_api/test_runs.py`, etc. |
| Integration | End-to-end agent execution | `tests/test_integration.py` |
| **Tenant isolation** | **user_id scoping across all stores** | **`tests/test_stores/test_tenant_isolation.py`** |
| **Concurrency** | **JSONB concurrent writes, job dedup** | **`tests/test_stores/test_concurrency.py`** |
| **Search quality** | **Golden queries, RRF correctness** | **`tests/test_stores/test_search_quality.py`** |

### Additional test types (from review)

**Tenant isolation tests** — verify user_id scoping in every store:

```python
# tests/test_stores/test_tenant_isolation.py
async def test_session_store_tenant_isolation(db_pool, test_user_id):
    """User B cannot see User A's sessions."""
    store = SessionStore()
    # User A creates a session
    await store.create("user-a", {"id": "sess-1", "query": "test", "status": "running"})
    # User B should see nothing
    sessions = await store.list("user-b")
    assert len(sessions) == 0
    # User B cannot get User A's session by ID
    result = await store.get("user-b", "sess-1")
    assert result is None

# Repeat pattern for: chat_store, notification_store, job_store, memory_store, preferences_store
```

**Concurrency tests** — verify JSONB concurrent writes and job dedup:

```python
# tests/test_stores/test_concurrency.py
async def test_preferences_concurrent_merge(db_pool):
    """Two concurrent merges to different keys should both survive."""
    store = PreferencesStore()
    # Ensure user exists
    await store.merge_hub_data("user-a", "preferences", {"initial": True})
    # Concurrent writes
    await asyncio.gather(
        store.merge_hub_data("user-a", "preferences", {"theme": "dark"}),
        store.merge_hub_data("user-a", "preferences", {"language": "en"}),
    )
    data = await store.get_hub_data("user-a", "preferences")
    assert data["theme"] == "dark"
    assert data["language"] == "en"

async def test_job_dedup_concurrent_claims(db_pool):
    """Two concurrent claims for same job+timestamp: exactly one wins."""
    store = JobRunStore()
    ts = datetime(2025, 6, 1, 12, 0, 0)
    results = await asyncio.gather(
        store.try_claim("user-a", "job-1", ts),
        store.try_claim("user-a", "job-1", ts),
    )
    assert sorted(results) == [False, True]  # Exactly one succeeds
```

**Search quality tests** — golden queries with expected results:

```python
# tests/test_stores/test_search_quality.py
GOLDEN_DOCS = [
    {"filename": "ml-intro.txt", "content": "Machine learning is a subset of artificial intelligence..."},
    {"filename": "auth-guide.txt", "content": "API authentication uses JWT tokens for secure access..."},
]

GOLDEN_QUERIES = [
    {"query": "machine learning basics", "expected_in_top_3": "ml-intro.txt"},
    {"query": "how to authenticate API requests", "expected_in_top_3": "auth-guide.txt"},
]

async def test_search_golden_queries(db_pool):
    """Index golden docs, run queries, verify expected docs in top 3."""
    doc_store = DocumentStore()
    search = DocumentSearch()
    # Index
    for doc in GOLDEN_DOCS:
        await doc_store.index_document("user-a", doc["filename"], doc["content"])
    # Query
    for gq in GOLDEN_QUERIES:
        results = await search.hybrid_search("user-a", gq["query"], limit=3)
        filenames = [r["filename"] for r in results]
        assert gq["expected_in_top_3"] in filenames, \
            f"Expected {gq['expected_in_top_3']} in top 3, got {filenames}"
```

---

## Verification

### Local

```bash
# Full stack (DB + API)
docker-compose up -d && uv run uvicorn api:app --port 8000

# Health checks
curl http://localhost:8000/liveness
# Expected: {"status": "alive"}

curl http://localhost:8000/readiness
# Expected: {"status": "ready"}

# All endpoints visible
curl http://localhost:8000/docs
# Expected: OpenAPI spec with all Phase 2-4 endpoints
```

### CI pipeline

```bash
# Lint + type check
ruff check . && mypy .

# Tests against CI database
docker compose -f docker-compose.ci.yml up -d --wait
psql "$DATABASE_TEST_URL" -f scripts/init-db.sql
pytest tests/ -v --tb=short

# Expected: all test categories pass (stores, services, sandbox, RAG, API, integration,
#           tenant isolation, concurrency, search quality)
```

### Cloud deployment

```bash
# Deploy via Cloud Build
gcloud builds submit --config=cloudbuild.yaml

# Verify deployment
gcloud run services describe apexflow-api --region=us-central1

# Health checks on Cloud Run
curl https://apexflow-api-HASH-uc.a.run.app/liveness
curl https://apexflow-api-HASH-uc.a.run.app/readiness

# Verify AlloyDB connectivity (readiness should return "ready", not 503)
# If 503: check VPC connector, AlloyDB private IP, service account permissions
```

### Data migration

```bash
# Dry run
python scripts/migrate.py --source-dir ../apexflow-v1 --db-url postgresql://... --dry-run

# Full migration
python scripts/migrate.py --source-dir ../apexflow-v1 --db-url postgresql://... --user-id default

# Validate
python scripts/migrate.py --source-dir ../apexflow-v1 --db-url postgresql://... --validate-only
# Expected: row counts match source, embedding dimensions consistent, sample spot checks pass
```

### Frontend

```bash
# Firebase Hosting connects to Cloud Run backend
# Verify CORS headers present in response:
curl -v -H "Origin: https://apexflow-PROJECTID.web.app" \
  https://apexflow-api-HASH-uc.a.run.app/runs
# Expected: Access-Control-Allow-Origin header matches the origin
```

---

## Phase 5 Exit Criteria

### Secure deployment
- [ ] Secrets stored in Google Secret Manager (DB password, Firebase SA key, Gemini API key)
- [ ] No plaintext secrets in cloudbuild.yaml, Dockerfile, or env files committed to repo
- [ ] `AUTH_DISABLED` impossible in production (Phase 2's `K_SERVICE` guard verified)
- [ ] Cloud Run service account has least privilege (AlloyDB Client + Secret Manager Accessor only)
- [ ] Rate limiting configured (Cloud Run `--max-instances` at minimum)

### Networking
- [ ] Serverless VPC Access connector created and wired to Cloud Run service
- [ ] Cloud Run can reach AlloyDB via private IP (readiness check returns "ready")
- [ ] `--vpc-egress=private-ranges-only` configured (only private IPs routed through VPC)
- [ ] AlloyDB connection string uses private IP / Cloud SQL Auth Proxy as appropriate

### Container
- [ ] Dockerfile uses explicit `uv venv` + `UV_PROJECT_ENVIRONMENT` for deterministic builds
- [ ] `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1` set
- [ ] Non-root user in production container
- [ ] `uv.lock` committed to repo; `--frozen` flag used in build

### CI pipeline
- [ ] Lint (ruff) and type check (mypy) run before tests
- [ ] Tests run against real PostgreSQL + pgvector container (docker-compose.ci.yml)
- [ ] Schema applied via `psql -f scripts/init-db.sql` (not asyncpg `conn.execute`)
- [ ] All test categories pass: stores, services, sandbox, RAG, API, integration
- [ ] Tenant isolation tests pass (user_id scoping)
- [ ] Concurrency tests pass (JSONB merge, job dedup)
- [ ] Search quality tests pass (golden queries in top-3)

### Health checks
- [ ] `/readiness` has 2s timeout (fails fast on stuck DB)
- [ ] `/readiness` caches result for 5s (reduces DB chatter)
- [ ] `/readiness` returns 503 on failure (Cloud Run stops routing traffic)
- [ ] `/liveness` never touches the DB

### Data migration
- [ ] Migration is resumable (safe to re-run, tracks progress)
- [ ] Memories re-embedded from text (FAISS `index.bin` not used)
- [ ] RAG documents re-ingested with throttling (respects embedding API rate limits)
- [ ] All v1 data mapped to `user_id = 'default'` (documented)
- [ ] Post-migration validation passes: row counts match, embedding dimensions consistent
- [ ] Migration produces a report (counts, skipped, failed per table)

### Frontend
- [ ] Per-environment `.env` files (development, staging, production)
- [ ] CORS middleware configured with known origins (not `*` in production)
- [ ] Firebase Hosting serves frontend, connects to Cloud Run API

### Operational readiness
- [ ] `trace_id` propagated from request to logs (from Phase 2's ToolContext)
- [ ] Timeouts set: HTTP client, DB acquire (2s), sandbox execution (30s)
- [ ] Rollback strategy documented (Cloud Run revision routing)
- [ ] Canary deploy possible via traffic splitting
