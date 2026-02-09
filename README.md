# ApexFlow v2

Intelligent workflow automation platform powered by Google Gemini. A web-first rewrite of the original desktop application, built on FastAPI, asyncpg, and AlloyDB.

## Features

- **Multi-phase agent workflows** — DAG-based execution engine with cost tracking, stop requests, and exponential backoff retries
- **RAG system** — Document indexing with hybrid search combining vector cosine similarity and full-text search via Reciprocal Rank Fusion (RRF)
- **Memory management (REMME)** — Smart memory extraction, categorization, and adaptive user profiling from session history
- **Secure code execution** — Monty sandbox (pydantic-monty) with language-level isolation, subprocess resource limits, and tool bridging via JSON-lines IPC
- **Tool routing** — ServiceRegistry dispatches tool calls in OpenAI-compatible format with circuit breaker resilience
- **Real-time streaming** — Server-Sent Events for live client updates via EventBus pub-sub
- **Scheduled workflows** — APScheduler with cron expressions and DB-backed job deduplication
- **Firebase auth** — JWT middleware with production safety (enforced on Cloud Run, optional locally). Email allowlist via `ALLOWED_EMAILS` env var (403 for unauthorized emails). Frontend uses Google sign-in via `signInWithRedirect`, token provider pattern, and auth guards on all data-fetching components. Graceful degradation when DB is down via `/api/auth/verify` (no DB access)

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI + Uvicorn |
| Database | AlloyDB Omni (PostgreSQL 15) with ScaNN vector indexes |
| Async DB Driver | asyncpg |
| LLM | Google Gemini (`google-genai` + Vertex AI) |
| Embeddings | `text-embedding-004` (768 dimensions) |
| Vector Search | pgvector (`<=>` cosine distance) |
| Auth | Firebase Admin SDK |
| CI/CD | Google Cloud Build |
| Frontend | React 19 + Vite + TypeScript |
| UI | shadcn/ui + Tailwind CSS + Radix UI |
| Graph Viz | ReactFlow |
| Frontend State | TanStack Query (server) + Zustand (client) |
| Frontend Hosting | Firebase Hosting |
| Python | 3.12+ |

## Project Structure

```
apexflow/
├── api.py                     # FastAPI app with lifespan manager
├── core/
│   ├── database.py            # Async connection pool
│   ├── loop.py                # AgentLoop4 — DAG-based execution engine
│   ├── service_registry.py    # Tool routing & service registration
│   ├── gemini_client.py       # Gemini client (Vertex AI / direct API)
│   ├── auth.py                # Firebase JWT middleware
│   ├── event_bus.py           # Pub-sub event system
│   ├── circuit_breaker.py     # Resilience (CLOSED/OPEN/HALF_OPEN)
│   ├── scheduler.py           # APScheduler with DB-backed dedup
│   ├── rag/                   # RAG pipeline
│   │   ├── config.py          # Embedding config (from settings), RRF constants
│   │   ├── chunker.py         # Rule-based & semantic chunking
│   │   └── ingestion.py       # Chunk → embed → store pipeline
│   └── stores/                # Stateless async data-access objects
│       ├── session_store.py
│       ├── document_store.py
│       ├── document_search.py # Hybrid search (vector + full-text RRF)
│       ├── memory_store.py    # CRUD + vector cosine search on memories
│       ├── preferences_store.py # JSONB hub access on user_preferences
│       ├── chat_store.py
│       └── ...
├── agents/
│   └── base_agent.py          # Agent runner (config, prompts, cost tracking)
├── services/                  # Service layer (registered via ServiceRegistry)
│   ├── browser_service.py     # Web search with SSRF protection
│   ├── rag_service.py         # Document indexing & search
│   └── sandbox_service.py     # Code execution (Monty sandbox)
├── routers/                   # API endpoint handlers
├── tools/
│   ├── monty_sandbox.py       # AST preprocessing, security logging, executor
│   └── _sandbox_worker.py     # Subprocess worker (Monty + IPC)
├── config/                    # Settings, agent config, model profiles, sandbox config
├── prompts/                   # LLM prompt templates
├── memory/                    # Session memory context
├── remme/                     # REMME memory system
│   ├── store.py               # RemmeStore facade (auto-embeds)
│   ├── engine.py              # Scan cycle orchestrator
│   ├── staging.py             # Staging queue
│   ├── extractor.py           # LLM-based memory extraction
│   ├── hubs/base_hub.py       # Async hub adapter
│   └── engines/evidence_log.py # Evidence event log
├── tests/                     # pytest + pytest-asyncio
│   ├── conftest.py            # Shared fixture (test_user_id)
│   ├── unit/                  # Mock-based tests (no DB needed)
│   └── integration/           # DB-dependent tests (graceful skip if unavailable)
├── frontend/                  # React 19 + TypeScript + Vite SPA
│   ├── src/
│   │   ├── components/        # UI components (layout, runs, graph, documents)
│   │   ├── contexts/          # AuthContext, SSEContext, ExecutionMetricsContext
│   │   ├── hooks/             # useApiHealth, useDbHealth, useSSE
│   │   ├── services/          # API services (runs, rag, settings)
│   │   ├── store/             # Zustand stores (useAppStore, useGraphStore)
│   │   ├── pages/             # Route pages (Dashboard, Documents, Settings)
│   │   └── utils/             # Shared utilities
│   └── package.json
├── firebase.json              # Firebase Hosting config (rewrites + caching)
├── .firebaserc                # Firebase project + deploy target mapping
├── docs/                      # Phase documentation
├── scripts/
│   ├── init-db.sql            # Database schema (13 tables)
│   └── migrate.py             # V1 → V2 data migration CLI
├── Dockerfile                 # Multi-stage production build
├── .dockerignore
└── alembic/                   # Database migrations
```

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL 15+ with pgvector extension (or AlloyDB Omni)
- A Gemini API key (for local development)

### Installation

```bash
# Clone the repository
git clone https://github.com/gadekar-pravin/apexflow.git
cd apexflow

# Create and activate virtual environment (uv preferred)
uv venv .venv && source .venv/bin/activate
uv sync --extra dev

# Alternative: pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install
```

### Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `GEMINI_API_KEY` | Gemini API key for local dev | — |
| `AUTH_DISABLED` | Disable Firebase auth (`1`) | unset |
| `ALLOWED_EMAILS` | Comma-separated email allowlist (403 if not listed) | unset (open access) |
| `ALLOW_LOCAL_WRITES` | Enable settings/prompt writes (`1`) | unset |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `DB_USER` | Database user | `apexflow` |
| `DB_PASSWORD` | Database password | — |
| `DB_NAME` | Database name | `apexflow` |
| `CORS_ORIGINS` | Comma-separated allowed origins for CORS | localhost defaults |
| `ALLOYDB_HOST` | AlloyDB VM internal IP (Cloud Run mode) | — |
| `DATABASE_URL` | Full connection string (overrides DB_* vars) | — |

### Database Setup

```bash
# Initialize the schema
psql -U apexflow -d apexflow -f scripts/init-db.sql

# Run migrations
alembic upgrade head
```

### Running Locally

```bash
AUTH_DISABLED=1 uvicorn api:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `/docs`.

### Running with Docker

```bash
docker build -t apexflow-api:local .
docker run -p 8080:8080 -e AUTH_DISABLED=1 apexflow-api:local
```

The API will be available at `http://localhost:8080`.

### Dev Environment (GCE + AlloyDB Omni)

```bash
./scripts/dev-start.sh    # Start VM + SSH tunnel to localhost:5432
./scripts/dev-stop.sh     # Close tunnel + stop VM
```

## Frontend

The React SPA lives in `frontend/` and is hosted on Firebase Hosting. Firebase Authentication (Google sign-in) is integrated via `AuthContext`.

### Local Development

```bash
cd frontend && npm install    # install dependencies
cd frontend && npm run dev    # start dev server on port 5173
```

Vite proxies `/api/*`, `/liveness`, and `/readiness` to the backend at `http://localhost:8000`. To override the proxy target:

```bash
VITE_BACKEND_URL=https://apexflow-api-j56xbd7o2a-uc.a.run.app npm run dev
```

### Firebase Hosting (Production)

The frontend deploys to Firebase Hosting in the `apexflow-ai` GCP project — the same project as the Cloud Run backend. This enables Firebase Hosting rewrites to proxy API calls directly to Cloud Run (same-origin, no CORS needed).

| Setting | Value |
|---------|-------|
| Project | `apexflow-ai` |
| Site | `apexflow-console` |
| URL | https://apexflow-console.web.app |
| Deploy target | `console` |
| Public dir | `frontend/dist` |

Firebase Hosting rewrites `/api/**`, `/liveness`, and `/readiness` to Cloud Run `apexflow-api` (us-central1). All other paths fall through to `/index.html` (SPA catch-all). API calls go directly to Cloud Run via `VITE_API_URL` (bypasses Firebase Hosting rewrites which can strip the `Authorization` header).

### Authentication

Firebase Authentication is configured for the `apexflow-ai` project with Google as the sign-in provider. When `VITE_FIREBASE_*` env vars are set (see `frontend/.env.production`), auth is required. When unset (local dev without Firebase), auth is bypassed and all queries run freely.

| Variable | Purpose |
|----------|---------|
| `VITE_FIREBASE_API_KEY` | Firebase Web SDK API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID |
| `VITE_FIREBASE_APP_ID` | Firebase app ID |
| `VITE_SSE_URL` | Direct Cloud Run URL for SSE (bypasses Firebase Hosting) |

### Deploy

```bash
cd frontend && npm run build && cd ..
firebase deploy --only hosting:console
```

## API Endpoints

### Health & Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/liveness` | Liveness probe |
| GET | `/readiness` | Readiness probe (checks DB) |
| GET | `/api/auth/verify` | Auth check (no DB access) |

### Workflows
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/runs/execute` | Execute a workflow |
| GET | `/api/runs` | List runs |
| GET | `/api/runs/{id}` | Get run details |
| POST | `/api/runs/{id}/stop` | Stop execution |

### RAG (Documents)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/rag/index` | Index a document |
| POST | `/api/rag/search` | Hybrid search |
| GET | `/api/rag/documents` | List documents |
| DELETE | `/api/rag/documents/{id}` | Delete document |
| POST | `/api/rag/reindex` | Reindex stale documents |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat/sessions` | Create session |
| GET | `/api/chat/sessions` | List sessions |
| POST | `/api/chat/sessions/{id}/messages` | Send message |
| GET | `/api/chat/sessions/{id}/messages` | Get messages |

### Memory (REMME)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/remme/memories` | List memories |
| POST | `/api/remme/memories` | Add a memory (auto-embeds) |
| DELETE | `/api/remme/memories/{id}` | Delete a memory |
| POST | `/api/remme/memories/search` | Semantic search over memories |
| POST | `/api/remme/scan/smart` | Smart scan sessions for memories |
| GET | `/api/remme/scan/unscanned` | List unscanned sessions |
| GET | `/api/remme/profile` | Get cached user profile |
| POST | `/api/remme/profile/refresh` | Regenerate profile from memories |
| GET | `/api/remme/preferences` | Get user preferences |
| GET | `/api/remme/staging/status` | Get staging queue status |

### Other
| Scope | Prefix | Endpoints |
|-------|--------|-----------|
| Notifications | `/api/inbox` | CRUD for notifications |
| Scheduler | `/api/cron` | Job management + trigger |
| Metrics | `/api/metrics` | Dashboard aggregates |
| Settings | `/api/settings` | Configuration management |
| Events | `/api/events` | SSE real-time stream |

## Development

### Common Commands

```bash
# Run tests
pytest tests/ -v                                  # full suite
pytest tests/unit/ -v                             # unit tests only (no DB needed)
pytest tests/integration/ -v                      # integration tests only
pytest tests/unit/test_rag.py -v                  # single file
pytest tests/unit/test_rag.py::test_name -v       # single test

# Run integration tests against real AlloyDB
./scripts/dev-start.sh                            # start VM + SSH tunnel
pytest tests/integration/ -v                      # 101 tests run against AlloyDB
./scripts/dev-stop.sh                             # stop VM when done

# Lint and format
ruff check .            # lint
ruff check . --fix      # lint with auto-fix
ruff format .           # format

# Type check
mypy core/

# Run all checks
pre-commit run --all-files

# Create a migration
alembic revision -m "description"

# Frontend
cd frontend && npm install        # install dependencies
cd frontend && npm run dev        # dev server (port 5173)
cd frontend && npm run build      # production build
cd frontend && npm run test       # run vitest tests

# Deploy frontend to Firebase Hosting
cd frontend && npm run build && cd ..
firebase deploy --only hosting:console
```

### Code Conventions

- **Async-first** — asyncpg for all application DB access; psycopg2 only in Alembic migrations
- **Stateless stores** — Every method takes `user_id` as first argument, uses `get_pool()`
- **Partial updates** — `update_status()`, `update_cost()` instead of monolithic `save()`
- **Tool routing** — All tool calls go through `ServiceRegistry.route_tool_call()` with `ToolContext`
- **Strict typing** — mypy strict mode with pydantic plugin
- **Ruff** — Rules E, F, I, UP, B, SIM at 120-char line length

## Architecture

### Execution Flow

```
Browser (React SPA on Firebase Hosting)
    → Firebase Hosting Rewrite (/api/**)
    → Cloud Run (FastAPI + auth middleware)
    → AgentLoop4 (DAG-based plan execution)
    → AgentRunner (prompt building, LLM calls)
    → ServiceRegistry (tool dispatch)
    → Store Layer (asyncpg → AlloyDB)
    → EventBus (SSE to client)
```

### Database Connection Priority

1. `DATABASE_URL` environment variable (explicit override)
2. `K_SERVICE` detected → Cloud Run mode using `ALLOYDB_*` vars
3. Local dev → builds from `DB_*` vars (defaults to `localhost:5432`)

### Hybrid Search (RAG)

The RAG system uses Reciprocal Rank Fusion to combine two retrieval strategies:

1. **Vector search** — Cosine similarity via pgvector `<=>` operator
2. **Full-text search** — PostgreSQL `tsvector` + `ts_rank`

Results are merged with `FULL OUTER JOIN`, scored as `1/(K + rank_vector) + 1/(K + rank_text)`, and deduplicated per-document via `DISTINCT ON`.

## CI/CD

Google Cloud Build runs on **tag pushes** matching `v*`:

```bash
git tag v2.0.0
git push origin v2.0.0   # triggers CI
```

Pipeline: pgvector container → lint (ruff) + typecheck (mypy) → migrate (alembic) → unit tests + integration tests (parallel) → Docker build → push to Artifact Registry → deploy to Cloud Run → smoke test.

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Bootstrap | Done | Database schema, connection pool, migrations |
| 2 — Core Engine | Done | Execution engine, agent runner, auth, events |
| 3 — Data Layer | Done | Stores, services, routers |
| 4a — RAG | Done | Document indexing, hybrid search |
| 4b — REMME | Done | Memory stores, preference hubs, scan engine |
| 4c — Sandbox | Done | Secure code execution (pydantic-monty) |
| 5 — Deployment | Done | Docker, Cloud Run CI/CD, CORS hardening, health checks, v1→v2 migration, integration tests |
| 6 — Frontend | Done | React 19 SPA, Firebase Hosting with Cloud Run rewrites, DAG visualization, document management |
| 6a — Auth | Done | Firebase Authentication (Google sign-in), AuthContext, token provider, SSE auth, COOP headers |
| 6b — Allowlist | Done | Email allowlist authorization (`ALLOWED_EMAILS` env var, 403 for unauthorized emails) |
