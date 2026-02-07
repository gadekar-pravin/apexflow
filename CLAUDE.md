# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ApexFlow v2 is a web-first rewrite of the desktop-first ApexFlow v1. It's an intelligent workflow automation platform powered by Google Gemini. The backend is FastAPI + asyncpg + AlloyDB (Google's PostgreSQL variant with ScaNN vector indexes).

**Current state:** Phases 1-2 are complete. Phase 1 covers bootstrap + database. Phase 2 adds the core execution engine, agent runner, auth, event system, and API routers. Phases 3-5 are documented in `docs/` but not yet implemented.

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

**Connection pool:** asyncpg, min_size=1, max_size=5 (configurable via `DB_POOL_MAX`).

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

### CI Pipeline

Google Cloud Build (`cloudbuild.yaml`), not GitHub Actions. Trigger fires on PRs to `main` only, with path filters (skips docs, scripts, config-only changes).

Steps: start pgvector container → wait for DB → lint (ruff) + typecheck (mypy) in parallel → migrate (alembic) → test (pytest). All steps share the `cloudbuild` Docker network; the DB container is reachable by hostname `postgres`.

### Project Layout

- `core/` — Database pool, execution engine (`loop.py`), ServiceRegistry, Gemini client, skills framework, circuit breaker, event bus, auth middleware
- `agents/` — Agent runner (`base_agent.py`) and agent implementations
- `memory/` — Session memory context (`context.py`) and REMME indexing
- `remme/` — Memory management system (hubs, engines, sources, extractors)
- `shared/` — Global state container (`state.py`) — holds ServiceRegistry, RemmeStore, active loops
- `services/` — Business logic layer
- `routers/` — FastAPI route handlers (`stream`, `settings`, `skills`, `prompts`, `news`)
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
