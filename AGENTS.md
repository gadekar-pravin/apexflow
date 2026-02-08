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
- `tests/unit/` contains mock-based pytest suites (no DB needed); `tests/integration/` contains DB-dependent tests.
- `frontend/` is the React 19 + TypeScript + Vite SPA. Service layer in `frontend/src/services/` calls the v2 backend at `/api/*` via Vite proxy. Components use TanStack Query for server state, Zustand for client state, ReactFlow for DAG visualization, Tailwind CSS + Radix UI for styling. Firebase Authentication via `AuthContext` (Google sign-in with `signInWithPopup`, token provider pattern decoupled from API layer). Every data-fetching component uses `!auth.isConfigured || auth.isAuthenticated` guard. SSE auth via `?token=` query param. Production builds deploy to Firebase Hosting (site `apexflow-console` in project `apexflow-ai`).
- `firebase.json` configures Firebase Hosting: rewrites `/api/**`, `/liveness`, `/readiness` to Cloud Run `apexflow-api`, SPA catch-all, cache headers, and `Cross-Origin-Opener-Policy: same-origin-allow-popups` on HTML responses (required for Firebase `signInWithPopup`).
- `.firebaserc` maps the deploy target `console` → site `apexflow-console` in project `apexflow-ai`.
- `docs/` holds phase/architecture notes.

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
- `uv run pytest tests/ -v` runs the full suite; `uv run pytest tests/unit/ -v` runs unit tests only; `uv run pytest tests/integration/ -v` runs integration tests only.
- `uv run pytest tests/unit/test_database.py::test_name -v` runs a single test.
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

### Frontend commands
- `cd frontend && npm install` installs frontend dependencies.
- `cd frontend && npm run dev` starts the Vite dev server on port 5173 (proxies `/api`, `/liveness`, `/readiness` to `localhost:8000`).
- `cd frontend && npm run build` creates a production build (runs `tsc -b && vite build`).
- `cd frontend && npx vitest run` runs the frontend test suite (94 tests across 8 files).
- Frontend + backend together: run the backend in one terminal, `cd frontend && npm run dev` in another, then open `http://localhost:5173`.

### Firebase Hosting (frontend deployment)
- `cd frontend && npm run build && cd .. && firebase deploy --only hosting:console` builds and deploys to `https://apexflow-console.web.app`.
- Firebase Hosting rewrites route `/api/**`, `/liveness`, `/readiness` to Cloud Run `apexflow-api` (same project `apexflow-ai`, same-origin — no CORS needed).
- Config: `firebase.json` (hosting rules), `.firebaserc` (project + deploy target mapping).
- Cache policy: `/assets/**` gets 1-year immutable cache (Vite content-hashed filenames); `*.html` gets `no-cache` + `Cross-Origin-Opener-Policy: same-origin-allow-popups`.

## Coding Style & Naming Conventions
- Python 3.12+, 120-char line length, Ruff rules `E`, `F`, `I`, `UP`, `B`, `SIM`.
- `mypy` is strict with the `pydantic.mypy` plugin enabled.
- Prefer async-first code paths (asyncpg for app DB access; psycopg2 only in Alembic).
- Use `snake_case` for modules/functions and `PascalCase` for classes.

## Testing Guidelines
- Frameworks: `pytest` + `pytest-asyncio` with `asyncio_mode=auto`.
- **Unit tests** go in `tests/unit/`, **integration tests** go in `tests/integration/`. Name files `test_*.py` with `test_*` functions.
- Add or update tests for new behavior, especially in stores/services and routers.
- **Unit tests** (221 tests across 15 files) are mock-based and require no database. Run with `pytest tests/unit/ -v`.
- **Integration tests** (101 tests across 12 files) run against a real database and gracefully skip when DB is unavailable. To run: `./scripts/dev-start.sh && pytest tests/integration/ -v`.
- **Shared fixtures (3 conftest files):**
  - `tests/conftest.py` — `test_user_id` (shared by both unit and integration tests)
  - `tests/integration/conftest.py` — `db_pool` (session-scoped asyncpg pool), `clean_tables` (truncates all 13 tables)
  - `tests/unit/conftest.py` — empty placeholder (unit tests define local mock helpers)
- Integration tests use `db_pool` and `clean_tables` fixtures from `tests/integration/conftest.py`. Patch the store's `get_pool` with the `db_pool` fixture (e.g., `patch("core.stores.session_store.get_pool", AsyncMock(return_value=db_pool))`).
- **pytest-asyncio loop scope:** `pyproject.toml` sets both `asyncio_default_fixture_loop_scope` and `asyncio_default_test_loop_scope` to `"session"` so session-scoped fixtures share an event loop with tests.
- JSONB columns returned via `SELECT *` come back as strings from asyncpg — use `json.loads(val) if isinstance(val, str) else val` when asserting on metadata fields.

## CI Pipeline
Google Cloud Build (`cloudbuild.yaml`), triggered on **tag pushes** matching `v*` (not on PRs). Workflow: merge PR → tag the merge commit → push tag → CI runs.

Steps (11 total): start pgvector container → wait for DB → lint + typecheck (parallel) → migrate → unit tests + integration tests (parallel) → Docker build → push → deploy → smoke test.

## Commit & Pull Request Guidelines
- Commit messages in history are short, imperative, sentence case: "Fix …", "Add …", "Update …", "Implement …".
- Prefer one logical change per commit; avoid noisy refactors mixed with behavior changes.
- PRs should include: a concise summary, tests run (copy command names), and migration notes if schema changes.
- Call out new env vars or API changes in the PR description.

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `AUTH_DISABLED` | Disable Firebase auth for local dev (`1`/`true`/`yes`) | unset (auth enabled) |
| `ALLOWED_EMAILS` | Comma-separated email allowlist for authorization (403 if not listed) | unset (all authenticated users allowed) |
| `GEMINI_API_KEY` | Gemini API key for local dev (not needed on GCP) | — |
| `DATABASE_URL` | Full DB connection string (overrides all `DB_*` vars) | — |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | Individual DB connection params | `localhost:5432`, user `apexflow` |
| `DB_POOL_MAX` | Max async connection pool size | `5` |
| `K_SERVICE` | Auto-set by Cloud Run; triggers production mode | — |
| `ALLOW_LOCAL_WRITES` | Enable prompt/settings write endpoints | unset (writes disabled) |
| `CORS_ORIGINS` | Comma-separated allowed origins for CORS | localhost defaults |
| `ALLOYDB_HOST` | AlloyDB VM internal IP (Cloud Run mode) | — |
| `VITE_BACKEND_URL` | Override Vite proxy target for frontend dev | `http://localhost:8000` |
| `VITE_SSE_URL` | Direct Cloud Run URL for SSE (bypasses Firebase Hosting) | `API_URL` |
| `VITE_FIREBASE_API_KEY` | Firebase Web SDK API key (frontend) | — |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain (frontend) | — |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID (frontend) | — |
| `VITE_FIREBASE_APP_ID` | Firebase app ID (frontend) | — |

## Configuration & Security Notes
- Start from `.env.example` and keep secrets out of the repo.
- `AUTH_DISABLED=1` is for local dev only; production enforces Firebase auth (fails startup if disabled on Cloud Run).
