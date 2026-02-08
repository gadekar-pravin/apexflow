# Repository Guidelines

## Project Structure & Module Organization
- `api.py` is the FastAPI entry point and lifespan wiring.
- `core/` holds the execution engine, DB access, RAG, auth, and shared utilities.
- `core/stores/` contains stateless async data-access objects (see Store Pattern below).
- `core/rag/` contains the RAG pipeline: chunker, config, and ingestion.
- `routers/` defines HTTP endpoints; `services/` implements tool/service logic.
- `agents/` contains the agent runner and agent implementations.
- `remme/` is the memory management system: facade, scan engine, hubs, staging, evidence log.
- `shared/state.py` is the global state container for ServiceRegistry, RemmeStore, and active loops.
- `config/` and `prompts/` store runtime settings and LLM prompt templates.
- `alembic/` is the source of truth for schema migrations; `scripts/` has dev helpers.
- `tests/` contains pytest suites; `docs/` holds phase/architecture notes.

## Architecture

### Database
AlloyDB Omni on a GCE VM; developers connect via SSH tunnel (`localhost:5432`). Schema has 13 tables defined in `scripts/init-db.sql`.

- **Connection priority** (`core/database.py`): `DATABASE_URL` env var → Cloud Run mode (`K_SERVICE` + `ALLOYDB_*`) → local dev (`DB_HOST`/`DB_USER`/`DB_PASSWORD` defaults).
- **Drivers:** asyncpg for all application code; psycopg2 only for Alembic migrations.
- **Primary keys:** TEXT type, generated in application layer.
- **Schemas:** CHECK constraints for status/role enums, JSONB for schemaless fields, NUMERIC(10,6) for monetary values.
- **ScaNN indexes** cannot be created on empty tables in AlloyDB. Use `scripts/create-scann-indexes.sql` after populating data. CI uses pgvector with IVFFlat as fallback.

### Store Pattern (`core/stores/`)
Stateless classes — every method takes `user_id` as the first argument, acquires connections via `get_pool()`, performs no filesystem I/O. Prefer targeted partial updates (`update_status`, `update_cost`) over monolithic saves.

Key stores: `SessionStore`, `JobStore`, `JobRunStore`, `NotificationStore`, `ChatStore`, `StateStore`, `DocumentStore`, `DocumentSearch`, `MemoryStore`, `PreferencesStore`.

### ServiceRegistry & Tool Routing
`ServiceRegistry` (`core/service_registry.py`) registers `ServiceDefinition` objects containing `ToolDefinition` entries. All tool calls route through `ServiceRegistry.route_tool_call(name, args, ctx)`. `ToolContext` (`core/tool_context.py`) carries `user_id`, `trace_id`, and deadline through invocations.

### Global State (`shared/state.py`)
Subsystem singletons are set during `api.py` lifespan and accessed via getters: `get_service_registry()`, `get_remme_store()`, etc. New subsystems follow this pattern.

### RAG System (Phase 4a)
Document indexing + hybrid search. Ingestion: chunk → batch embed (Gemini `text-embedding-004`) → store via `DocumentStore`. Dedup via SHA256 content hash. Hybrid search uses Reciprocal Rank Fusion (vector cosine + full-text `ts_rank`).

### REMME Memory System (Phase 4b)
`RemmeStore` facade wraps `MemoryStore` + `PreferencesStore` + `SessionStore`. Auto-generates embeddings on add, embeds queries on search. `RemmeEngine` orchestrates scan cycles: unscanned sessions → extract → store memories → stage preferences → log evidence → mark scanned.

Hub adapter pattern: `BaseHub` — async `load()`/`commit()` for DB I/O, sync `update()`/`get()` for in-memory access.

### Services
Registered via `ServiceRegistry` during app lifespan:
- `BrowserService` — web search/extract with SSRF protection.
- `RagService` — document indexing, search, deletion.
- `SandboxService` — stub (Phase 4c).

## Build, Test, and Development Commands

### Using uv (preferred)
- `uv venv .venv && source .venv/bin/activate` creates and activates the virtual environment.
- `uv sync --extra dev` installs all dependencies including dev extras (uses `uv.lock` for reproducibility).
- `uv run pytest tests/ -v` runs tests; `uv run pytest tests/test_database.py::test_name -v` runs a single test.
- `uv run ruff check .` runs linting; `uv run ruff format .` formats code.
- `uv run mypy core/` runs strict type checks.

### Using pip (alternative)
- `python -m venv .venv && source .venv/bin/activate` creates and activates the virtual environment.
- `pip install -e ".[dev]"` installs dev dependencies.

### Common commands
- `AUTH_DISABLED=1 uvicorn api:app --reload` runs the API locally with auth bypassed.
- `./scripts/dev-start.sh` starts the GCE VM + SSH tunnel; `./scripts/dev-stop.sh` tears it down.
- `alembic upgrade head` applies database migrations.
- `pre-commit run --all-files` runs the full pre-commit suite.

## Coding Style & Naming Conventions
- Python 3.12+, 120-char line length, Ruff rules `E`, `F`, `I`, `UP`, `B`, `SIM`.
- `mypy` is strict with the `pydantic.mypy` plugin enabled.
- Prefer async-first code paths (asyncpg for app DB access; psycopg2 only in Alembic).
- Use `snake_case` for modules/functions and `PascalCase` for classes.

## Testing Guidelines
- Frameworks: `pytest` + `pytest-asyncio` with `asyncio_mode=auto`.
- Keep tests in `tests/` and name them `test_*.py` with `test_*` functions.
- Add or update tests for new behavior, especially in stores/services and routers.

## CI Pipeline
Google Cloud Build (`cloudbuild.yaml`), triggered on **tag pushes** matching `v*` (not on PRs). Workflow: merge PR → tag the merge commit → push tag → CI runs.

Steps: start pgvector container → wait for DB → lint + typecheck (parallel) → migrate → test.

## Commit & Pull Request Guidelines
- Commit messages in history are short, imperative, sentence case: "Fix …", "Add …", "Update …", "Implement …".
- Prefer one logical change per commit; avoid noisy refactors mixed with behavior changes.
- PRs should include: a concise summary, tests run (copy command names), and migration notes if schema changes.
- Call out new env vars or API changes in the PR description.

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `AUTH_DISABLED` | Disable Firebase auth for local dev (`1`/`true`/`yes`) | unset (auth enabled) |
| `GEMINI_API_KEY` | Gemini API key for local dev (not needed on GCP) | — |
| `DATABASE_URL` | Full DB connection string (overrides all `DB_*` vars) | — |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | Individual DB connection params | `localhost:5432`, user `apexflow` |
| `DB_POOL_MAX` | Max async connection pool size | `5` |
| `K_SERVICE` | Auto-set by Cloud Run; triggers production mode | — |
| `ALLOW_LOCAL_WRITES` | Enable prompt/settings write endpoints | unset (writes disabled) |

## Configuration & Security Notes
- Start from `.env.example` and keep secrets out of the repo.
- `AUTH_DISABLED=1` is for local dev only; production enforces Firebase auth (fails startup if disabled on Cloud Run).
