# ApexFlow v2

Intelligent workflow automation platform powered by Google Gemini. A web-first rewrite of the original desktop application, built on FastAPI, asyncpg, and AlloyDB.

## Features

- **Multi-phase agent workflows** — DAG-based execution engine with cost tracking, stop requests, and exponential backoff retries
- **RAG system** — Document indexing with hybrid search combining vector cosine similarity and full-text search via Reciprocal Rank Fusion (RRF)
- **Memory management (REMME)** — Smart memory extraction, categorization, and adaptive user profiling from session history
- **Tool routing** — ServiceRegistry dispatches tool calls in OpenAI-compatible format with circuit breaker resilience
- **Real-time streaming** — Server-Sent Events for live client updates via EventBus pub-sub
- **Scheduled workflows** — APScheduler with cron expressions and DB-backed job deduplication
- **Firebase auth** — JWT middleware with production safety (enforced on Cloud Run, optional locally)

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
│   └── sandbox_service.py     # Code execution (stub)
├── routers/                   # API endpoint handlers
├── config/                    # Settings, agent config, model profiles
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
├── docs/                      # Phase documentation
├── scripts/                   # DB init, dev environment scripts
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

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
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
| `ALLOW_LOCAL_WRITES` | Enable settings/prompt writes (`1`) | unset |
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `DB_USER` | Database user | `apexflow` |
| `DB_PASSWORD` | Database password | — |
| `DB_NAME` | Database name | `apexflow` |
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

### Dev Environment (GCE + AlloyDB Omni)

```bash
./scripts/dev-start.sh    # Start VM + SSH tunnel to localhost:5432
./scripts/dev-stop.sh     # Close tunnel + stop VM
```

## API Endpoints

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/liveness` | Liveness probe |
| GET | `/readiness` | Readiness probe (checks DB) |

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
pytest tests/ -v
pytest tests/test_rag.py -v              # single file
pytest tests/test_rag.py::test_name -v   # single test

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
Client Request
    → FastAPI Router (auth middleware)
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

Pipeline: pgvector container → lint (ruff) + typecheck (mypy) → migrate (alembic) → test (pytest).

## Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1 — Bootstrap | Done | Database schema, connection pool, migrations |
| 2 — Core Engine | Done | Execution engine, agent runner, auth, events |
| 3 — Data Layer | Done | Stores, services, routers |
| 4a — RAG | Done | Document indexing, hybrid search |
| 4b — REMME | Done | Memory stores, preference hubs, scan engine |
| 4c — Sandbox | Planned | Secure code execution |
| 5 — Deployment | Planned | Cloud Run, Terraform, monitoring |
