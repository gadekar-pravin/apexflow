# ApexFlow: Web-First Backend Rewrite — Overview

## Context

**ApexFlow v1** (`/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1`) is a desktop-first agentic AI system that orchestrates multiple specialized agents via a graph-based execution model (NetworkX DAGs). It uses Gemini for all LLM operations, MCP (Model Context Protocol) for tool integration, and REMME ("Remember Me") for persistent user memory.

**Goal:** Create a new clean repo at `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow` — a web-first backend targeting **Cloud Run** (backend) + **Firebase Hosting** (frontend). This is a **selective rewrite**: copy and refactor the ~60% of v1 that's web-ready, drop the ~40% that's desktop-bound, and build new storage/auth/deployment layers.

**Why a new repo (not in-place):**
- Clean git history with no dead code
- Fresh `pyproject.toml` with only needed dependencies
- No accidental imports of deleted modules
- v1 stays intact as reference

## Phase Documents

| Phase | Document | Description | Prerequisites |
|-------|----------|-------------|---------------|
| 1 | [phase-1-bootstrap.md](phase-1-bootstrap.md) | Project init, AlloyDB schema, database.py, docker-compose | None |
| 2 | [phase-2-core-engine.md](phase-2-core-engine.md) | Copy AS-IS + refactor core files, ServiceRegistry, auth, api.py | Phase 1 |
| 3 | [phase-3-stores-services.md](phase-3-stores-services.md) | Store classes, service modules, router refactoring | Phase 2 |
| 4a | [phase-4a-rag.md](phase-4a-rag.md) | RAG system (AlloyDB + ScaNN + FTS) | Phase 3 |
| 4b | [phase-4b-remme.md](phase-4b-remme.md) | REMME memory (AlloyDB + ScaNN) | Phase 3 |
| 4c | [phase-4c-sandbox.md](phase-4c-sandbox.md) | Monty sandbox (Rust interpreter) | Phase 3 |
| 5 | [phase-5-deployment.md](phase-5-deployment.md) | Dockerfile, CI/CD, migration, testing | Phases 4a, 4b, 4c |

## Phase Dependency Graph

```
Phase 1 (Bootstrap + DB)
    |
    v
Phase 2 (Core Engine copy + refactor)
    |
    v
Phase 3 (Stores + Services + Routers)
    |
    +---> Phase 4a (RAG)     ──┐
    |                          |
    +---> Phase 4b (REMME)   ──+──> Phase 5 (Deploy)
    |                          |
    +---> Phase 4c (Sandbox) ──┘
```

**Phases 4a, 4b, 4c can run in parallel.**

## Key Decisions

| Decision | Choice |
|----------|--------|
| Desktop features | Drop ALL (explorer, git, IDE agent, python tools) |
| Storage | AlloyDB Omni with ScaNN for all persistent data + vector search |
| Sandbox | Pydantic Monty (Rust interpreter, language-level isolation) |
| Environment detection | Auto-detect (local AlloyDB Omni vs Cloud Run AlloyDB) |
| Authentication | Firebase Auth (JWT verification middleware) |
| MCP replacement | In-process ServiceRegistry (same interface, no subprocesses) |
| Database client | asyncpg (raw SQL, not SQLAlchemy) |
| Text search | PostgreSQL FTS (`to_tsvector` + GIN) replaces BM25 |
| Frontend | Stays in `apexflow-v1/apexflow-ui/`, just update API URL |

## Architectural Decisions Summary

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Database client | `asyncpg` raw SQL | Full control over ScaNN, AlloyDB-specific features. Codebase is async everywhere. |
| 2 | ServiceRegistry | Singleton pattern | Matches existing EventBus, SkillManager, SchedulerService singletons. |
| 3 | Agent config keys | Keep `browser`, `rag`, `sandbox` | Zero changes to agent_config.yaml. ServiceRegistry resolves same names. |
| 4 | Hub storage | JSONB (not normalized) | Hub schemas are nested Pydantic models that change frequently. JSONB avoids migrations. |
| 5 | Text search | PostgreSQL FTS + GIN | Server-side, streaming, handles stemming. Replaces in-memory rank_bm25. |
| 6 | Env detection | Follow gemini_client.py | DATABASE_URL > K_SERVICE > localhost. Proven pattern in codebase. |
| 7 | New repo | Yes (not in-place) | Clean history, fresh deps, no dead imports. v1 stays as reference. |
| 8 | Vector index | ScaNN (not HNSW) | Native to AlloyDB via `alloydb_scann` extension. Better recall at lower latency. Requires AlloyDB Omni or managed AlloyDB (falls back to IVFFlat on vanilla PG). |
| 9 | Auth | Firebase Admin SDK | Frontend already on Firebase Hosting. JWT verification is standard. |
| 10 | Sandbox | Pydantic Monty | Language-level isolation > regex filtering. Comprehensive 03a plan exists. |

## Source References (Full Absolute Paths)

**V1 Root:** `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1`
**V2 Root:** `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow`

| What | Full Path in v1 |
|------|----------------|
| Main API entry | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/api.py` |
| Agent loop engine | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/loop.py` |
| Gemini client | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/gemini_client.py` |
| Model manager | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/model_manager.py` |
| Event bus | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/event_bus.py` |
| Circuit breaker | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/circuit_breaker.py` |
| Graph adapter | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/graph_adapter.py` |
| JSON parser | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/json_parser.py` |
| Core utils | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/utils.py` |
| Scheduler | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/scheduler.py` |
| Persistence | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/persistence.py` |
| Skills system | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/core/skills/` |
| Agent base | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/agents/base_agent.py` |
| Agent directory | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/agents/` |
| Execution context | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/memory/context.py` |
| Shared state | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/shared/state.py` |
| MCP manager (replaced) | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/mcp_servers/multi_mcp.py` |
| RAG server (replaced) | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/mcp_servers/server_rag.py` |
| Browser server (replaced) | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/mcp_servers/server_browser.py` |
| Sandbox server (replaced) | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/mcp_servers/server_sandbox.py` |
| REMME store (replaced) | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/store.py` |
| REMME extractor | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/extractor.py` |
| REMME utils | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/utils.py` |
| REMME hub schemas | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/hub_schemas.py` |
| REMME normalizer | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/normalizer.py` |
| REMME staging | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/staging.py` |
| REMME hubs | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/hubs/` |
| REMME engines | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/engines/` |
| REMME notes scanner | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/sources/notes_scanner.py` |
| Current sandbox (replaced) | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/tools/sandbox.py` |
| Web tools | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/tools/web_tools_async.py` |
| Search method switcher | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/tools/switch_search_method.py` |
| Config directory | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/config/` |
| Prompts directory | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/prompts/` |
| All routers | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/routers/` |
| Monty migration plan | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/docs/migration/03a-sandbox-monty-integration.md` |
| Data folder architecture | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/docs/data-folder-architecture.md` |
| Frontend | `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/apexflow-ui/` |

## NOT Copied from v1 (desktop-only, dead code)

| File/Directory | Reason |
|---------------|--------|
| `routers/explorer.py` | Local filesystem scanning |
| `routers/git.py` | Local git operations via subprocess |
| `routers/ide_agent.py` | Local IDE integration |
| `routers/python_tools.py` | Local ruff/pyright via subprocess |
| `routers/apps.py` | Local app CRUD |
| `routers/browser_utils.py` | Desktop browser utils |
| `routers/mcp.py` | MCP management UI |
| `routers/tests.py` | Development-only |
| `mcp_servers/` entire directory | Replaced by ServiceRegistry + services/ |
| `tools/sandbox.py` | Replaced by Monty sandbox |
| `ui/visualizer.py` | Rich console (CLI-only) |
| `config/mcp_cache.json` | MCP metadata cache |
| `config/mcp_server_config.yaml` | MCP server config |
| `config/mcp_config.json` | MCP config |
| `config/disabled_tools.json` | MCP tool toggles |
| `data/` directory | Replaced by AlloyDB |
| `memory/debug_logs/` | Replaced by Cloud Logging |
| `memory/remme_index/` | FAISS files, replaced by AlloyDB |
| `memory/session_summaries_index/` | Replaced by AlloyDB sessions table |
| `core/skills/library/system_monitor/` | Desktop-only (psutil metrics meaningless in container) |

## Target Project Structure

```
/Users/pravingadekar/Documents/EAG2-Capstone/apexflow/
├── api.py                          # FastAPI entry point (clean, web-only)
├── pyproject.toml                  # Fresh dependencies
├── uv.lock                         # Lock file (commit for reproducible builds)
├── docker-compose.yml              # AlloyDB Omni for local dev
├── Dockerfile                      # Cloud Run deployment
├── cloudbuild.yaml                 # CI/CD pipeline
├── .env.example                    # Environment template
│
├── core/
│   ├── database.py                 # NEW: asyncpg pool, env auto-detection
│   ├── auth.py                     # NEW: Firebase Auth JWT middleware
│   ├── service_registry.py         # NEW: replaces MultiMCP
│   ├── logging_config.py           # NEW: structured logging for Cloud Logging
│   ├── loop.py                     # COPY+REFACTOR from v1
│   ├── gemini_client.py            # COPY AS-IS from v1
│   ├── model_manager.py            # COPY+REFACTOR from v1
│   ├── event_bus.py                # COPY AS-IS from v1
│   ├── scheduler.py                # COPY+REFACTOR from v1
│   ├── persistence.py              # COPY+REFACTOR from v1
│   ├── circuit_breaker.py          # COPY AS-IS from v1
│   ├── graph_adapter.py            # COPY AS-IS from v1
│   ├── json_parser.py              # COPY AS-IS from v1
│   ├── utils.py                    # COPY AS-IS from v1
│   ├── stores/
│   │   ├── session_store.py        # NEW: replaces filesystem sessions
│   │   ├── job_store.py            # NEW: replaces data/system/jobs.json
│   │   ├── notification_store.py   # NEW: replaces SQLite notifications
│   │   ├── chat_store.py           # NEW: replaces filesystem chats
│   │   ├── state_store.py          # NEW: replaces snapshot.json
│   │   ├── document_store.py       # NEW: replaces FAISS RAG index
│   │   ├── document_search.py      # NEW: hybrid ScaNN + FTS search
│   │   ├── memory_store.py         # NEW: replaces REMME FAISS
│   │   └── preferences_store.py    # NEW: replaces hub JSON files
│   ├── rag/
│   │   ├── chunker.py              # NEW: extracted from server_rag.py
│   │   └── ingestion.py            # NEW: parse -> chunk -> embed -> store
│   └── skills/                     # COPY+REFACTOR from v1
│       ├── manager.py
│       ├── base.py
│       └── library/
│
├── agents/
│   ├── base_agent.py               # COPY+REFACTOR from v1
│   └── ...                         # All agent files, COPY AS-IS
│
├── memory/
│   └── context.py                  # COPY+REFACTOR from v1
│
├── remme/                          # COPY+REFACTOR from v1
│   ├── extractor.py, utils.py, hub_schemas.py, normalizer.py
│   ├── store.py, staging.py
│   ├── hubs/                       # base_hub, preferences, operating_context, soft_identity
│   ├── engines/                    # belief_update, evidence_log
│   └── sources/                    # notes_scanner
│
├── services/
│   ├── browser_service.py          # NEW: wraps web tools
│   ├── rag_service.py              # NEW: wraps document stores
│   └── sandbox_service.py          # NEW: wraps Monty sandbox
│
├── tools/
│   ├── monty_sandbox.py            # NEW: Pydantic Monty
│   ├── web_tools_async.py          # COPY+REFACTOR from v1
│   └── switch_search_method.py     # COPY+REFACTOR from v1
│
├── routers/                        # Mix of COPY AS-IS and COPY+REFACTOR
├── shared/state.py                 # COPY+REFACTOR from v1
├── config/                         # Mix of COPY AS-IS and COPY+REFACTOR
├── prompts/                        # COPY+REFACTOR from v1
├── scripts/
│   ├── init-db.sql                 # NEW: AlloyDB schema DDL
│   └── migrate.py                  # NEW: v1 data migration
└── tests/
```

## Estimated Scope

- Phase 1: ~5 new files, project setup
- Phase 2: ~20 copied files (8 refactored, 12 as-is), 4 new files
- Phase 3: ~5 new store files, 3 new services, ~6 refactored routers
- Phase 4: ~8 new files, ~6 refactored files
- Phase 5: ~3 new files (Dockerfile, cloudbuild, migration)

## Future Roadmap (Post-MVP / Production Hardening)

The following items are **not required for dev/demo** but should be implemented before production deployment. They were identified during architectural reviews.

### Security & Isolation

| Item | Description | Priority |
|------|-------------|----------|
| **Cloud Run Jobs sandbox** | Run agent code in isolated Cloud Run Jobs (or sidecar) for OS-level isolation on top of Monty's language-level isolation. Defense-in-depth. | Medium |
| **Least-privilege IAM** | Ensure the Cloud Run service account has zero IAM permissions beyond DB writes and Cloud Logging. | High |
| **Soft deletes** | Add `is_deleted BOOLEAN DEFAULT FALSE` to `memories` and `documents` tables. | Medium |

### Data Integrity & Multi-Tenancy

| Item | Description | Priority |
|------|-------------|----------|
| **`users` table** | Create a `users` table mapping Firebase UIDs to internal profiles/settings. | Medium |
| **Remove `DEFAULT 'default'`** | Remove `DEFAULT 'default'` from all `user_id` columns. Enforce real `user_id` from Firebase Auth in middleware. Add cross-user isolation tests. | High |
| **Row-level security** | Add PostgreSQL RLS policies for tenant isolation at DB level. | Low |

### API Resilience

| Item | Description | Priority |
|------|-------------|----------|
| **API rate limiting** | Token-bucket rate limiter middleware (e.g., `slowapi`). | High |
| **Idempotency keys** | `Idempotency-Key` header on `/runs/execute`. | Medium |
| **Request timeout** | Per-request timeout middleware. | Medium |

### Observability

| Item | Description | Priority |
|------|-------------|----------|
| **OpenTelemetry tracing** | Distributed tracing with trace IDs through agent graph execution. | High |
| **Structured metrics** | Custom metrics to Cloud Monitoring. | Medium |
| **`PYTHONASYNCIODEBUG=1`** | Detect blocking calls in async loop. Add to CI. | High |

### Schema Evolution

| Item | Description | Priority |
|------|-------------|----------|
| **GIN indexes on JSONB** | Add if node-level queries become common. | Low |
| **Promote hot JSONB fields** | Extract frequently-queried JSONB fields to columns. | Low |

### Scheduling (Cloud Run Production)

| Item | Description | Priority |
|------|-------------|----------|
| **Cloud Scheduler migration** | Replace APScheduler with Cloud Scheduler → HTTP endpoint. | High |
| **Job idempotency** | At-least-once execution with DB deduplication. | Medium |

### Infrastructure & Operations

| Item | Description | Priority |
|------|-------------|----------|
| **VPC connectivity** | Serverless VPC Access for private AlloyDB. | High |
| **Secret Manager** | Move credentials to GCP Secret Manager. | High |
| **Connection pool tuning** | Cap asyncpg pool size per instance. | Medium |
| **Embedding versioning** | Store model/dim in metadata for future model changes. | Low |
| **CORS exact origins** | Replace wildcard with exact frontend origin. | Medium |
| **Payload size limits** | Request body size limits for ingestion. | Medium |

### Background Job Management

| Item | Description | Priority |
|------|-------------|----------|
| **RAG ingestion jobs** | Replace daemon threads with Cloud Tasks/Pub/Sub. | Medium |
| **Large file storage** | Store raw bytes in GCS, metadata+chunks in AlloyDB. | Low |

### ServiceRegistry Hardening

| Item | Description | Priority |
|------|-------------|----------|
| **Per-tool timeouts** | `asyncio.wait_for()` per service (browser: 30s, rag: 60s, sandbox: 30s). | High |
| **Bounded concurrency** | `asyncio.Semaphore` per service. | Medium |
| **Structured tool-call logging** | Log tool name, service, latency, user_id, session_id. | Medium |

### Release & Migration

| Item | Description | Priority |
|------|-------------|----------|
| **Cutover strategy** | v1/v2 parallel validation and rollback plan. | Medium |
| **API contract testing** | OpenAPI schema validation in CI. | Low |
