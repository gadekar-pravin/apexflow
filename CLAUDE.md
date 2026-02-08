# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ApexFlow v2 is a web-first rewrite of the desktop-first ApexFlow v1. It's an intelligent workflow automation platform powered by Google Gemini. The backend is FastAPI + asyncpg + AlloyDB (Google's PostgreSQL variant with ScaNN vector indexes).

**Current state:** Phases 1-3 and 4a are complete. Phase 1 covers bootstrap + database. Phase 2 adds the core execution engine, agent runner, auth, event system, and API routers. Phase 3 adds the data access layer (stores), service layer, and remaining routers. Phase 4a adds the RAG system (document indexing + hybrid search). Phases 4b-5 are documented in `docs/` but not yet implemented.

## Common Commands

```bash
# Install dependencies (use venv at .venv/)
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

**Services** (`services/`): Registered via `ServiceRegistry` during app lifespan.

- `BrowserService` — `web_search` and `web_extract_text` tools with SSRF protection (DNS resolution against private IP ranges).
- `RagService` — `index_document`, `search_documents`, `list_documents`, `delete_document` tools. Handler routes to ingestion pipeline and document stores.
- `SandboxService` — Stub raising `ToolExecutionError` (Phase 4c).

**Core ports from v1:**

- `core/scheduler.py` — APScheduler with DB-backed job dedup via `JobRunStore.try_claim()`. Sends notifications on completion/failure.
- `core/persistence.py` — State snapshots via `StateStore` instead of filesystem.
- `core/metrics_aggregator.py` — SQL aggregation (replaces filesystem session walk) with 5-min cache via `StateStore`.

**Phase 3 routers:** `runs`, `chat`, `rag`, `remme`, `inbox`, `cron`, `metrics` — all use `Depends(get_user_id)` and are mounted at `/api` prefix.

### RAG System (Phase 4a)

**Config:** `core/rag/config.py` — constants: `EMBEDDING_MODEL` (`text-embedding-004`), `EMBEDDING_DIM` (768), `INGESTION_VERSION` (1), `RRF_K` (60), `SEARCH_EXPANSION_FACTOR` (3).

**Chunker:** `core/rag/chunker.py` — Rule-based recursive splitting (default) or semantic LLM-driven chunking via Gemini. Configurable chunk size/overlap from settings.

**Ingestion pipeline:** `core/rag/ingestion.py` — `ingest_document()` orchestrates: chunk via `chunk_document()` → batch embed via `get_embedding()` in thread pool (`asyncio.gather` for parallelism) → store via `DocumentStore.index_document()`. Reuses existing `remme/utils.py:get_embedding` (Gemini `text-embedding-004` with L2 normalization).

**Document dedup:** SHA256 hash of content + `UNIQUE(user_id, file_hash)` constraint. Same hash + same `ingestion_version` = skip. Same hash + different version = re-chunk and re-embed.

**Hybrid search:** `DocumentSearch.hybrid_search()` — two CTEs (vector cosine via `<=>` operator, full-text via `ts_rank` + `plainto_tsquery`), `FULL OUTER JOIN`, RRF score = `1/(K+rank_v) + 1/(K+rank_t)`, `DISTINCT ON (document_id)` for per-doc dedup.

**Migration:** `alembic/versions/002_rag_versioning_columns.py` — adds `content`, `embedding_model`, `embedding_dim`, `ingestion_version`, `updated_at` to `documents` table.

**RAG endpoints:**
- `POST /api/rag/index` — index a document (filename + content)
- `POST /api/rag/search` — hybrid search (query + limit 1-50)
- `GET /api/rag/documents` — list indexed documents
- `DELETE /api/rag/documents/{id}` — delete (cascades to chunks)
- `POST /api/rag/reindex` — reindex specific doc or all stale docs

### CI Pipeline

Google Cloud Build (`cloudbuild.yaml`), not GitHub Actions. Trigger fires on **tag pushes** matching `v*` (e.g. `v2.0.0`, `v2.1.0-rc1`). This prevents untrusted fork PRs from executing CI on the GCP project.

**Workflow:** merge PR → tag the merge commit → push tag → CI runs automatically.
```bash
git tag v2.0.0          # after merging to main
git push origin v2.0.0  # triggers CI
```

Steps: start pgvector container → wait for DB → lint (ruff) + typecheck (mypy) in parallel → migrate (alembic) → test (pytest). All steps share the `cloudbuild` Docker network; the DB container is reachable by hostname `postgres`.

### Project Layout

- `core/` — Database pool, execution engine (`loop.py`), ServiceRegistry, Gemini client, skills framework, circuit breaker, event bus, auth middleware, scheduler, persistence, metrics aggregator
- `core/stores/` — Stateless async data-access objects (SessionStore, JobStore, JobRunStore, NotificationStore, ChatStore, StateStore, DocumentStore, DocumentSearch)
- `agents/` — Agent runner (`base_agent.py`) and agent implementations
- `memory/` — Session memory context (`context.py`) with DB-backed persistence via SessionStore
- `remme/` — Memory management system (hubs, engines, sources, extractors)
- `shared/` — Global state container (`state.py`) — holds ServiceRegistry, RemmeStore, active loops
- `core/rag/` — RAG pipeline: chunker (`chunker.py`), config constants (`config.py`), ingestion pipeline (`ingestion.py`)
- `services/` — Service layer (BrowserService, RagService, Sandbox stub) registered via ServiceRegistry
- `routers/` — FastAPI route handlers: Phase 2 (`stream`, `settings`, `skills`, `prompts`, `news`) + Phase 3 (`runs`, `chat`, `rag`, `remme`, `inbox`, `cron`, `metrics`)
- `tools/` — Agent tools (`web_tools_async.py`, `switch_search_method.py`) and code sandbox
- `config/` — Settings loader, `agent_config.yaml`, `models.json`, `profiles.yaml`, `settings.defaults.json`
- `prompts/` — Prompt templates (planner, coder, thinker, retriever, etc.)
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
