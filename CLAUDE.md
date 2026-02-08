# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ApexFlow v2 is a web-first rewrite of the desktop-first ApexFlow v1. It's an intelligent workflow automation platform powered by Google Gemini. The backend is FastAPI + asyncpg + AlloyDB (Google's PostgreSQL variant with ScaNN vector indexes).

**Current state:** Phases 1–5 are complete. Phase 1 covers bootstrap + database. Phase 2 adds the core execution engine, agent runner, auth, event system, and API routers. Phase 3 adds the data access layer (stores), service layer, and remaining routers. Phase 4a adds the RAG system (document indexing + hybrid search). Phase 4b adds the REMME memory system (AlloyDB-backed memory stores, preference hubs, scan engine). Phase 4c adds the Monty sandbox (secure code execution via pydantic-monty subprocess with tool bridging). Phase 5 adds production deployment infrastructure (Docker container, Cloud Run CI/CD, CORS hardening, enhanced health checks, v1→v2 migration script, and integration tests for tenant isolation, concurrency, and search quality).

## Common Commands

```bash
# Setup venv and install dependencies (uv preferred)
uv venv .venv && source .venv/bin/activate
uv sync --extra dev

# Alternative: pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
pytest tests/test_database.py -v              # single file
pytest tests/test_database.py::test_name -v   # single test

# Lint and format
ruff check .          # lint
ruff check . --fix    # lint with auto-fix
ruff format .         # format

# Type check
mypy core/

# Pre-commit (runs ruff + mypy + whitespace fixes)
pre-commit run --all-files

# Database migrations
alembic upgrade head        # apply all migrations
alembic stamp 001           # mark migration as applied (if schema already exists)
alembic revision -m "desc"  # create new migration

# Run the API server (local dev)
AUTH_DISABLED=1 uvicorn api:app --reload

# Dev environment (GCE VM with AlloyDB Omni)
./scripts/dev-start.sh      # start VM + SSH tunnel to localhost:5432
./scripts/dev-stop.sh       # close tunnel + stop VM

# Docker (Phase 5)
docker build -t apexflow-api:local .
docker run -p 8080:8080 -e AUTH_DISABLED=1 apexflow-api:local

# V1 → V2 migration
python scripts/migrate.py --source-dir ../apexflow-v1 --dry-run
python scripts/migrate.py --source-dir ../apexflow-v1 --db-url postgresql://... --user-id default
python scripts/migrate.py --source-dir ../apexflow-v1 --validate-only
```

## Architecture

### Database

AlloyDB Omni 15.12.0 runs on a GCE VM (`alloydb-omni-dev`, `n2-standard-4`, `us-central1-a`). Developers connect via SSH tunnel (`localhost:5432`). The schema has 13 tables defined in `scripts/init-db.sql`.

**Connection priority** (`core/database.py`):
1. `DATABASE_URL` env var (explicit override)
2. `K_SERVICE` detected → Cloud Run mode using `ALLOYDB_*` vars
3. Local dev → builds from `DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_PORT`/`DB_NAME` (defaults to `localhost:5432`, user `apexflow`)

**Connection pool:** asyncpg, min_size=1, max_size=5 (configurable via `DB_POOL_MAX`). Each new connection runs an `init` callback that registers the pgvector codec (if the `pgvector` package is installed).

**Alembic** uses psycopg2 (sync driver), not asyncpg. The env.py mirrors the same 3-priority connection logic with a `postgresql+psycopg2://` prefix.

**ScaNN indexes** cannot be created on empty tables in AlloyDB. They are deferred until data insertion. Use `scripts/create-scann-indexes.sql` after populating `memories` and `document_chunks`. CI uses pgvector with IVFFlat as fallback.

### Core Engine (Phase 2)

**Entry point:** `api.py` — FastAPI app with lifespan manager that initializes DB pool, `ServiceRegistry`, and Firebase auth.

**Execution loop:** `AgentLoop4` (`core/loop.py`) orchestrates multi-phase agent workflows using a DAG-based plan graph. Supports cost thresholds (`cost_exceeded` status), stop requests, and exponential backoff retries for transient failures.

**ServiceRegistry** (`core/service_registry.py`) replaces v1's MultiMCP. Registers `ServiceDefinition` objects (each containing `ToolDefinition` entries), indexes tools by name, and routes calls via `route_tool_call(name, args, ctx)`. Returns OpenAI-compatible function-calling format via `get_all_tools()`.

**Agent runner:** `AgentRunner` (`agents/base_agent.py`) loads agent configs from `config/agent_config.yaml`, builds LLM prompts from `prompts/*.md` templates, executes tool calls through ServiceRegistry, and tracks token costs.

**LLM client:** `core/gemini_client.py` provides a cached Gemini client singleton. Auto-detects environment: Vertex AI with ADC on GCP (`K_SERVICE` or `GOOGLE_APPLICATION_CREDENTIALS`), or `GEMINI_API_KEY` for local dev. `ModelManager` (`core/model_manager.py`) loads model configs from `config/models.json` + `config/profiles.yaml` and enforces rate limiting (~15 RPM).

**Auth:** Firebase JWT middleware (`core/auth.py`). Skips `/liveness`, `/readiness`, `/docs`, `/openapi.json`. Disabled locally via `AUTH_DISABLED=1`. Fails startup if disabled on Cloud Run (production safety).

**Event system:** `EventBus` singleton (`core/event_bus.py`) with pub-sub pattern. Keeps last 100 events in a deque. Clients subscribe via SSE at `GET /events` (`routers/stream.py`).

**Resilience:** `CircuitBreaker` (`core/circuit_breaker.py`) with CLOSED/OPEN/HALF_OPEN states (threshold=5, recovery=60s). `ToolContext` (`core/tool_context.py`) carries user_id, trace_id, and monotonic deadline through tool invocations.

### Data Access Layer (Phase 3)

**Stores** (`core/stores/`): Stateless data-access objects — every method takes `user_id` first, uses `get_pool()` for asyncpg connections. No monolithic `save()` — uses targeted partial updates (`update_status`, `update_graph`, `update_cost`).

- `SessionStore` — CRUD + SQL aggregation for dashboard metrics (`COUNT FILTER`, `SUM`, `GROUP BY`). `mark_scanned()` uses an atomic transaction across `sessions` + `scanned_runs`. Method `list_sessions()` (not `list()`, to avoid shadowing the builtin type).
- `JobStore` / `JobRunStore` — Job CRUD and execution dedup via `INSERT ON CONFLICT DO NOTHING`.
- `NotificationStore` — Notifications with UUID generation on create.
- `ChatStore` — Append-only messages with transaction wrapping (insert message + update `session.updated_at`).
- `StateStore` — User-scoped key-value pairs (`system_state` table) with JSONB UPSERT.
- `DocumentStore` — Document CRUD with SHA256 content-hash dedup (`INSERT ... ON CONFLICT DO UPDATE` with `xmax = 0` trick), version-aware ingestion skip/re-index, and batch chunk insertion via `executemany`. Cascading delete via `ON DELETE CASCADE`.
- `DocumentSearch` — Hybrid search using Reciprocal Rank Fusion (RRF): vector cosine similarity CTE + full-text `ts_rank` CTE, `FULL OUTER JOIN`, per-document dedup via `DISTINCT ON`. Returns `rrf_score`, `vector_score`, `text_score`.
- `MemoryStore` — CRUD + vector cosine search on `memories` table. `add()` stores text + embedding + category, `search()` returns top-k by `1 - (embedding <=> query)` with optional `min_similarity` threshold, `update_text()` re-embeds. Tracks `embedding_model` per row.
- `PreferencesStore` — JSONB access on `user_preferences` table. Five hub columns (`preferences`, `operating_ctx`, `soft_identity`, `evidence_log`, `staging_queue`) mapped via a hardcoded allowlist (prevents SQL injection). `merge_hub_data()` uses atomic UPSERT with `COALESCE(col, '{}') || $2::jsonb`. `save_hub_data()` supports optional optimistic locking via `expected_updated_at`.

**Services** (`services/`): Registered via `ServiceRegistry` during app lifespan.

- `BrowserService` — `web_search` and `web_extract_text` tools with SSRF protection (DNS resolution against private IP ranges).
- `RagService` — `index_document`, `search_documents`, `list_documents`, `delete_document` tools. Handler routes to ingestion pipeline and document stores.
- `SandboxService` — Executes Python code via pydantic-monty subprocess sandbox.

**Core ports from v1:**

- `core/scheduler.py` — APScheduler with DB-backed job dedup via `JobRunStore.try_claim()`. Sends notifications on completion/failure.
- `core/persistence.py` — State snapshots via `StateStore` instead of filesystem.
- `core/metrics_aggregator.py` — SQL aggregation (replaces filesystem session walk) with 5-min cache via `StateStore`.

**Phase 3 routers:** `runs`, `chat`, `rag`, `remme`, `inbox`, `cron`, `metrics` — all use `Depends(get_user_id)` and are mounted at `/api` prefix.

### RAG System (Phase 4a)

**Config:** `core/rag/config.py` — `EMBEDDING_MODEL` and `EMBEDDING_DIM` derived from `settings.json` via `load_settings()["models"]` (defaults: `text-embedding-004`, 768). Hardcoded constants: `INGESTION_VERSION` (1), `RRF_K` (60), `SEARCH_EXPANSION_FACTOR` (3).

**Chunker:** `core/rag/chunker.py` — Rule-based recursive splitting (default) or semantic LLM-driven chunking via Gemini. Configurable chunk size/overlap from settings.

**Ingestion pipeline:** `core/rag/ingestion.py` — `ingest_document()` orchestrates: chunk via `chunk_document()` → batch embed via `get_embedding()` in thread pool (`asyncio.gather` for parallelism) → store via `DocumentStore.index_document()`. Reuses existing `remme/utils.py:get_embedding` (Gemini `text-embedding-004` with L2 normalization).

**Document dedup:** SHA256 hash of content + `UNIQUE(user_id, file_hash)` constraint. Same hash + same `ingestion_version` = skip. Same hash + different version = re-chunk and re-embed.

**Hybrid search:** `DocumentSearch.hybrid_search()` — two CTEs (vector cosine via `<=>` operator, full-text via `ts_rank` + `plainto_tsquery`), `FULL OUTER JOIN`, RRF score = `1/(K+rank_v) + 1/(K+rank_t)`, `DISTINCT ON (document_id)` for per-doc dedup.

**Migration:** `alembic/versions/002_rag_versioning_columns.py` — adds `content`, `embedding_model`, `embedding_dim`, `ingestion_version`, `updated_at` to `documents` table.

**RAG endpoints:**
- `POST /api/rag/index` — index a document (filename + content, rejects blank content)
- `POST /api/rag/search` — hybrid search (query + limit 1-50, rejects blank/whitespace queries)
- `GET /api/rag/documents` — list indexed documents
- `DELETE /api/rag/documents/{id}` — delete (cascades to chunks)
- `POST /api/rag/reindex` — reindex specific doc or all stale docs (skips whitespace-only content and empty chunk results to prevent data-loss)

### REMME Memory System (Phase 4b)

**Stores:** `MemoryStore` (`core/stores/memory_store.py`) provides CRUD + vector cosine search on `memories` table. `PreferencesStore` (`core/stores/preferences_store.py`) provides JSONB access on `user_preferences` table with atomic merge via `COALESCE || $2::jsonb` UPSERT.

**Hub adapter:** `BaseHub` (`remme/hubs/base_hub.py`) — async adapter pattern: `load(user_id)` reads JSONB from DB into `_data` dict, sync `update()`/`get()` for in-memory access, `commit(user_id)` writes back via `merge_hub_data`. `commit_partial(user_id, keys)` writes only specified keys.

**Staging + Evidence:** `StagingQueue` (`remme/staging.py`) — in-memory queue with async `load()`/`save()` via `PreferencesStore.get_staging()`/`save_staging()`. `EvidenceLog` (`remme/engines/evidence_log.py`) — same pattern via `get_evidence()`/`save_evidence()`.

**Facade:** `RemmeStore` (`remme/store.py`) — high-level facade wrapping `MemoryStore` + `PreferencesStore` + `SessionStore`. `add()` auto-generates embeddings via `remme.utils.get_embedding(text, "RETRIEVAL_DOCUMENT")`. `search()` embeds the query with `"RETRIEVAL_QUERY"` then delegates to `MemoryStore.search()`. Scan tracking delegates to `SessionStore.mark_scanned()`.

**Engine:** `RemmeEngine` (`remme/engine.py`) — orchestrates the scan cycle: get unscanned sessions → load staging + evidence → for each session: extract via `RemmeExtractor.extract()`, add memories, stage preferences, log evidence, mark scanned → commit staging + evidence.

**Initialization:** `api.py` lifespan step 3c creates `RemmeStore()` and registers it via `set_remme_store()` in `shared/state.py`.

**Migration:** `alembic/versions/004_add_memory_embedding_model.py` — adds `embedding_model TEXT DEFAULT 'text-embedding-004'` to `memories` table.

**REMME endpoints:**
- `GET /api/remme/memories` — list all memories for the user
- `POST /api/remme/memories` — add a memory (auto-embeds text)
- `DELETE /api/remme/memories/{id}` — delete a memory
- `POST /api/remme/memories/search` — semantic search (query + limit)
- `POST /api/remme/scan/smart` — run full scan cycle via `RemmeEngine`
- `GET /api/remme/scan/unscanned` — list unscanned sessions
- `GET /api/remme/profile` — get cached user profile
- `POST /api/remme/profile/refresh` — regenerate profile from memories
- `GET /api/remme/preferences` — get user preferences hub data
- `GET /api/remme/staging/status` — get staging queue status

### Monty Sandbox (Phase 4c)

**Runtime:** [Pydantic Monty](https://github.com/pydantic/monty) — a Rust-based Python interpreter with language-level isolation (no `open()`, `os`, `socket`, `eval`, `__import__`). Runs in a subprocess with resource limits (memory, timeout, step count) for DoS protection.

**Config:** `config/sandbox_config.py` — constants (`DEFAULT_TIMEOUT_SECONDS=30`, `MAX_STEPS=100_000`, `MAX_MEMORY_MB=256`, `MAX_OUTPUT_SIZE=1MB`, `MAX_EXTERNAL_RESPONSE_SIZE=100KB`) and `SANDBOX_ALLOWED_TOOLS` allowlist (read-only tools: `web_search`, `web_extract_text`, `search_documents`). `get_sandbox_tools(registry)` filters registry to allowed tools.

**Worker:** `tools/_sandbox_worker.py` — standalone subprocess script. Creates `pydantic_monty.Monty(code, inputs, external_functions)`, runs start/resume loop. Communicates via JSON-lines IPC over stdin/stdout. Sets `RLIMIT_AS` on Linux.

**Executor:** `tools/monty_sandbox.py` — AST preprocessing (`preprocess_agent_code()` wraps top-level returns, rejects `await`), security logging (`log_security_event()` writes to `security_logs` with JSONB `details`), and main executor (`run_user_code()`) that spawns the worker subprocess. Tool calls from sandbox are bridged via IPC: positional args mapped to named params using `ToolDefinition.arg_order`, then routed through `ServiceRegistry.route_tool_call()`.

**Service:** `services/sandbox_service.py` — `create_sandbox_service()` registers the `run_code` tool. Handler validates ToolContext, extracts code, calls `run_user_code()`.

**Migration:** `alembic/versions/005_sandbox_security_logs.py` — adds `details JSONB` column to `security_logs`.

### Production Deployment (Phase 5)

**Docker:** Multi-stage `Dockerfile` — builder stage uses `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` for dependency installation, runtime stage uses `python:3.12-slim-bookworm` with non-root `appuser` (uid 1001). Exposes port 8080. `.dockerignore` excludes tests, docs, scripts, alembic, etc.

**CORS:** `api.py` reads `CORS_ORIGINS` env var as comma-separated origins. Falls back to `localhost:3000,5173,8000` for local dev. Production sets specific origins via Cloud Run env vars.

**Readiness:** Enhanced `/readiness` endpoint with 5-second TTL cache and 2-second `asyncio.timeout()`. Returns `503` with error type name on failure. Cache prevents DB polling storms from orchestrators.

**Migration script:** `scripts/migrate.py` — standalone CLI for one-time v1→v2 data migration. Supports `--dry-run` (parse-only), `--validate-only` (count comparison), and full migration with batched inserts (`BATCH_SIZE=100`). Re-embeds memories via `remme/utils.py:get_embedding()` with rate throttling. All inserts use `ON CONFLICT DO NOTHING` for idempotency.

**Integration tests:** 12 test files (101 tests) requiring a real database (gracefully skip when DB is unavailable):
- `tests/test_tenant_isolation.py` — 8 tests verifying user_id scoping across all stores
- `tests/test_concurrency.py` — concurrent preference merge (both keys survive) + job dedup race (exactly one wins)
- `tests/test_search_quality.py` — golden queries with synthetic embeddings against hybrid search
- `tests/test_schema_constraints.py` — 12 tests for CHECK, UNIQUE, FK, NOT NULL constraint enforcement via raw SQL
- `tests/test_document_dedup.py` — 12 tests for SHA256 dedup, `xmax=0` trick, cascading deletes, executemany, FTS generated column
- `tests/test_session_lifecycle.py` — 14 tests for SQL aggregation (`COUNT FILTER`, `SUM`), `mark_scanned` atomic txn, COALESCE(completed_at)
- `tests/test_preferences_optimistic_lock.py` — 10 tests for optimistic locking, JSONB merge vs overwrite, hub column allowlist
- `tests/test_chat_lifecycle.py` — 9 tests for add_message + update session atomicity, CASCADE delete, role CHECK
- `tests/test_memory_lifecycle.py` — 9 tests for vector cosine search, min_similarity threshold, update_text re-embedding
- `tests/test_job_lifecycle.py` — 8 tests for dynamic SET clause, FK cascade to job_runs, try_claim dedup
- `tests/test_state_store_lifecycle.py` — 7 tests for UPSERT semantics, composite PK, complex JSONB roundtrip
- `tests/test_notification_lifecycle.py` — 7 tests for mark_read, unread_only filter, pagination, priority/metadata

**Shared fixtures:** `tests/conftest.py` provides `mock_pool()` helper (canonical version with `executemany`), `db_pool` (session-scoped real asyncpg pool, graceful skip), `clean_tables` (truncates all 13 tables), and `test_user_id`.

**pytest-asyncio config:** `pyproject.toml` sets `asyncio_default_fixture_loop_scope = "session"` and `asyncio_default_test_loop_scope = "session"` so that session-scoped fixtures (like `db_pool`) share an event loop with tests.

### CI/CD Pipeline

Google Cloud Build (`cloudbuild.yaml`), not GitHub Actions. Trigger fires on **tag pushes** matching `v*` (e.g. `v2.0.0`, `v2.1.0-rc1`). This prevents untrusted fork PRs from executing CI on the GCP project.

**Workflow:** merge PR → tag the merge commit → push tag → CI runs automatically.
```bash
git tag v2.0.0          # after merging to main
git push origin v2.0.0  # triggers CI
```

**Steps (9 total):** start pgvector container → wait for DB → lint (ruff) + typecheck (mypy) in parallel → migrate (alembic) → test (pytest) → Docker build (tagged `SHORT_SHA` + `latest`) → push to Artifact Registry → deploy to Cloud Run.

**Cloud Run deploy config:** `--allow-unauthenticated` (in-app Firebase auth), `--vpc-connector` for AlloyDB access, `--set-secrets` for DB password/Firebase SA/Gemini key, `--memory=1Gi --cpu=1 --concurrency=80 --max-instances=10`.

**Substitutions:** `_REGION`, `_REPO`, `_IMAGE`, `_SERVICE_ACCOUNT`, `_VPC_CONNECTOR` — configurable per environment.

### Project Layout

- `core/` — Database pool, execution engine (`loop.py`), ServiceRegistry, Gemini client, skills framework, circuit breaker, event bus, auth middleware, scheduler, persistence, metrics aggregator
- `core/stores/` — Stateless async data-access objects (SessionStore, JobStore, JobRunStore, NotificationStore, ChatStore, StateStore, DocumentStore, DocumentSearch, MemoryStore, PreferencesStore)
- `agents/` — Agent runner (`base_agent.py`) and agent implementations
- `memory/` — Session memory context (`context.py`) with DB-backed persistence via SessionStore
- `remme/` — Memory management system: `RemmeStore` facade (`store.py`), `RemmeEngine` scan orchestrator (`engine.py`), `BaseHub` adapter (`hubs/base_hub.py`), `StagingQueue` (`staging.py`), `EvidenceLog` (`engines/evidence_log.py`), `RemmeExtractor` (`extractor.py`), embedding utils (`utils.py`)
- `shared/` — Global state container (`state.py`) — holds ServiceRegistry, RemmeStore, active loops
- `core/rag/` — RAG pipeline: chunker (`chunker.py`), config (`config.py`, loads embedding settings from `settings.json`), ingestion pipeline (`ingestion.py`)
- `services/` — Service layer (BrowserService, RagService, SandboxService) registered via ServiceRegistry
- `routers/` — FastAPI route handlers: Phase 2 (`stream`, `settings`, `skills`, `prompts`, `news`) + Phase 3 (`runs`, `chat`, `rag`, `remme`, `inbox`, `cron`, `metrics`)
- `tools/` — Agent tools (`web_tools_async.py`, `switch_search_method.py`), Monty sandbox (`monty_sandbox.py` executor, `_sandbox_worker.py` subprocess)
- `config/` — Settings loader, `agent_config.yaml`, `models.json`, `profiles.yaml`, `settings.defaults.json`
- `prompts/` — Prompt templates (planner, coder, thinker, retriever, etc.)
- `scripts/migrate.py` — V1→V2 data migration CLI (sessions, jobs, notifications, memories, scanned runs, preferences)
- `Dockerfile` — Multi-stage production build (uv builder + Python 3.12 slim runtime)
- `docs/` — Phase documentation (7 phase docs + rewrite plan)

## Code Conventions

- **Python 3.12+**, strict mypy with pydantic plugin
- **Ruff rules:** E, F, I, UP, B, SIM at 120-char line length
- **Primary keys:** TEXT type, generated in application layer
- **Async:** asyncpg for all DB access in application code; psycopg2 only for Alembic migrations
- **Schema:** CHECK constraints for status/role enums, JSONB for schemaless fields, NUMERIC(10,6) for monetary values
- **Stores:** Stateless classes in `core/stores/` — every method takes `user_id` as first arg, uses `get_pool()`, no filesystem I/O. Prefer partial updates over monolithic saves.
- **Tool routing:** All tool calls go through `ServiceRegistry.route_tool_call()` with a `ToolContext` carrying user/trace/deadline
- **Event-driven:** `EventBus` singleton for internal pub-sub; SSE for client streaming

## GCP Configuration

- **Project:** `apexflow-ai`
- **VM:** `alloydb-omni-dev` in `us-central1-a`
- **Cloud Scheduler:** `vm-auto-stop` stops the VM nightly at 10 PM ET
- **Cloud Build SA:** `cloudbuild-ci@apexflow-ai.iam.gserviceaccount.com`

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `AUTH_DISABLED` | Disable Firebase auth for local dev (`1`/`true`/`yes`) | unset (auth enabled) |
| `GEMINI_API_KEY` | Gemini API key for local dev (not needed on GCP) | — |
| `GOOGLE_CLOUD_PROJECT` | GCP project for Vertex AI | `apexflow-ai` |
| `GOOGLE_CLOUD_LOCATION` | GCP region for Vertex AI | `us-central1` |
| `ALLOW_LOCAL_WRITES` | Enable prompt/settings write endpoints (`1`/`true`/`yes`) | unset (writes disabled) |
| `DATABASE_URL` | Full database connection string (overrides all DB_* vars) | — |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | Individual DB connection params | `localhost:5432`, user `apexflow` |
| `DB_POOL_MAX` | Max async connection pool size | `5` |
| `K_SERVICE` | Auto-set by Cloud Run; triggers production mode (Vertex AI, auth enforced) | — |
| `CORS_ORIGINS` | Comma-separated allowed origins for CORS | `http://localhost:3000,http://localhost:5173,http://localhost:8000` |
| `DATABASE_TEST_URL` | Test database URL for integration tests | `postgresql://apexflow:apexflow@localhost:5432/apexflow` |
