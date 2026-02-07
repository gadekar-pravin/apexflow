# Phase 3: Storage Stores + Service Layer + Deferred Refactors

**Prerequisites:** Phase 2 complete (app boots, ServiceRegistry created, core engine compiles, no store dependencies)
**Produces:** All 5 store classes, browser service live, all routers wired to AlloyDB, core files (scheduler/persistence/context) using stores

**IMPORTANT:** This phase includes files deferred from Phase 2 that depend on store classes. The order matters: create stores first (Step 3.1), then refactor core files (Step 3.2), then services (Step 3.3), then routers (Step 3.4), then update api.py (Step 3.5).

---

## Step 3.1: Create store classes

All stores follow the same pattern: stateless classes that use `get_pool()` from `core/database.py`. Every method takes `user_id` as the first parameter (multi-tenant ready).

### Store pattern

> **Multi-tenancy rule:** Every store method takes `user_id` as the first parameter and includes it in every `WHERE` clause. No exceptions. This matches Phase 1's schema where `user_id` has no default.

```python
# core/stores/session_store.py
from core.database import get_pool

class SessionStore:
    async def create(self, user_id: str, session: dict) -> None:
        """Insert a new session. Raises on duplicate ID."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO sessions (id, user_id, query, status, agent_type, model_used)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, session["id"], user_id, session["query"],
                session.get("status", "running"), session.get("agent_type"),
                session.get("model_used"))

    async def update_status(self, user_id: str, run_id: str, status: str,
                            error: str | None = None) -> None:
        """Update status. Sets completed_at on terminal states (idempotent — won't null it out)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sessions SET
                    status = $3,
                    error = COALESCE($4, error),
                    completed_at = CASE
                        WHEN completed_at IS NOT NULL THEN completed_at  -- preserve once set
                        WHEN $3 IN ('completed', 'failed', 'cancelled') THEN NOW()
                        ELSE NULL
                    END
                WHERE id = $1 AND user_id = $2
            """, run_id, user_id, status, error)

    async def update_graph(self, user_id: str, run_id: str,
                           graph_data: dict, node_outputs: dict) -> None:
        """Merge graph data using JSONB concatenation (append, not overwrite)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sessions SET
                    graph_data = sessions.graph_data || $3::jsonb,
                    node_outputs = sessions.node_outputs || $4::jsonb
                WHERE id = $1 AND user_id = $2
            """, run_id, user_id, graph_data, node_outputs)

    async def update_cost(self, user_id: str, run_id: str, cost_delta: float) -> None:
        """Increment cost (not overwrite)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sessions SET cost = cost + $3
                WHERE id = $1 AND user_id = $2
            """, run_id, user_id, cost_delta)

    async def get(self, user_id: str, run_id: str) -> dict | None: ...
    async def list(self, user_id: str, limit: int = 50, offset: int = 0) -> list[dict]: ...
    async def list_unscanned(self, user_id: str) -> list[dict]: ...
    async def exists(self, user_id: str, run_id: str) -> bool: ...
    async def delete(self, user_id: str, run_id: str) -> bool: ...
    async def mark_scanned(self, user_id: str, run_id: str) -> None: ...
```

### Create all 5 basic stores

**`core/stores/session_store.py`** -- sessions table
- Most depended-on store (used by: runs.py, remme.py, metrics.py, context.py)
- Methods: `create()`, `update_status()`, `update_graph()`, `update_cost()`, `get()`, `list()`, `list_unscanned()`, `exists()`, `delete()`, `mark_scanned()`
- **No monolithic `save()` method** — use targeted partial updates to avoid accidental overwrites (see store pattern above)
- `list()` returns `[{id, query, status, agent_type, cost, model_used, created_at, completed_at}]`
- `list_unscanned()` filters on `WHERE NOT remme_scanned` (used by REMME smart scan)
- Every method includes `user_id` in the WHERE clause (including `exists()` and `mark_scanned()`)

**`core/stores/job_store.py`** -- jobs + job_runs tables
- Methods: `load_all()`, `create()`, `update()`, `delete()`, `get()`
- `load_all(user_id)` returns all enabled jobs (replaces JSON file load)
- `update(user_id, job_id, ...)` handles partial updates (last_run, next_run, last_output, enabled)
- All methods take `user_id` as the first parameter

**`core/stores/job_run_store.py`** -- job_runs table (execution dedup)

The `job_runs` table (created in Phase 1) prevents duplicate job execution under Cloud Run scale-out. Without this, concurrent instances can trigger the same scheduled job simultaneously.

```python
class JobRunStore:
    async def try_claim(self, user_id: str, job_id: str, scheduled_for: datetime) -> bool:
        """Attempt to claim a job run. Returns True if claimed, False if already running.
        Uses INSERT ... ON CONFLICT DO NOTHING for atomic dedup."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("""
                INSERT INTO job_runs (job_id, user_id, scheduled_for, status)
                VALUES ($1, $2, $3, 'running')
                ON CONFLICT (job_id, scheduled_for) DO NOTHING
            """, job_id, user_id, scheduled_for)
            return result == "INSERT 0 1"  # True if row was inserted

    async def complete(self, user_id: str, job_id: str, scheduled_for: datetime,
                       status: str, output: str | None = None, error: str | None = None) -> None:
        """Mark a job run as completed/failed."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE job_runs SET status = $4, completed_at = NOW(), output = $5, error = $6
                WHERE job_id = $1 AND user_id = $2 AND scheduled_for = $3
            """, job_id, user_id, scheduled_for, status, output, error)

    async def recent(self, user_id: str, job_id: str, limit: int = 10) -> list[dict]: ...
```

The scheduler uses `try_claim()` before executing any job. If another instance already claimed it, the duplicate is silently skipped.

**`core/stores/notification_store.py`** -- notifications table
- Methods: `create(user_id, ...)`, `list(user_id, ...)`, `mark_read(user_id, notif_id)`, `delete(user_id, notif_id)`
- `create()` replaces `send_to_inbox()` function from v1
- `list()` supports `unread_only` filter and pagination
- All methods take `user_id` as the first parameter

**`core/stores/chat_store.py`** -- chat_sessions + chat_messages tables

Phase 1 normalized chats into two tables. The store must handle both in a transaction.

- Methods: `list_sessions(user_id, target_type, target_id)`, `get_session(user_id, session_id)`, `create_session(user_id, ...)`, `delete_session(user_id, session_id)`, `add_message(user_id, session_id, role, content)`, `get_messages(user_id, session_id, limit, offset)`
- `list_sessions()` filters by conversation target; returns session metadata only (not messages)
- `get_session()` returns session metadata; use `get_messages()` for message content (paginated)
- **Message strategy: append-only.** Messages get a UUID on insert and are never updated or replaced. This is simpler and safer than delete+re-insert.
- Remove `target_type: 'ide'` branch (desktop-only, does not exist in v2)

```python
class ChatStore:
    async def add_message(self, user_id: str, session_id: str,
                          role: str, content: str, metadata: dict | None = None) -> str:
        """Append a message. Returns the message ID. Updates session.updated_at."""
        msg_id = str(uuid.uuid4())
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO chat_messages (id, session_id, user_id, role, content, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """, msg_id, session_id, user_id, role, content,
                    json.dumps(metadata or {}))
                await conn.execute("""
                    UPDATE chat_sessions SET updated_at = NOW()
                    WHERE id = $1 AND user_id = $2
                """, session_id, user_id)
        return msg_id

    async def get_messages(self, user_id: str, session_id: str,
                           limit: int = 100, offset: int = 0) -> list[dict]:
        """Get messages in chronological order, paginated."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, role, content, created_at, metadata
                FROM chat_messages
                WHERE session_id = $1 AND user_id = $2
                ORDER BY created_at ASC
                LIMIT $3 OFFSET $4
            """, session_id, user_id, limit, offset)
            return [dict(r) for r in rows]
```

**`core/stores/state_store.py`** -- system_state table (key-value)
- Methods: `get(user_id, key)`, `set(user_id, key, value)`, `delete(user_id, key)`
- Simple key-value store using JSONB values
- Table PK is `(user_id, key)` — **every method must include `user_id`**
- Used by: persistence.py for snapshots, metrics_aggregator for cache
- Cache keys must be user-scoped: `state_store.get(user_id, "metrics_cache")`, not `state_store.get("metrics_cache")`

### Scan tracking decision (`scanned_runs` vs `sessions.remme_scanned`)

Phase 1 created both `sessions.remme_scanned` (boolean column) and `scanned_runs` (separate table). **Pick one canonical source to avoid drift:**

| Approach | Pros | Cons |
|----------|------|------|
| `sessions.remme_scanned` only | Single source of truth, simpler queries | Can't track *when* scanned or by which process |
| `scanned_runs` only | Tracks scan timestamp, supports idempotent re-scan | Requires JOIN for "unscanned sessions" query |
| **Both (recommended)** | `remme_scanned` for fast filtering; `scanned_runs` for audit trail | Must update both atomically |

**Decision: Use both, updated atomically.** `mark_scanned()` in `SessionStore` does:

```python
async def mark_scanned(self, user_id: str, run_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE sessions SET remme_scanned = TRUE WHERE id = $1 AND user_id = $2",
                run_id, user_id)
            await conn.execute(
                "INSERT INTO scanned_runs (run_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                run_id, user_id)
```

---

## Architecture Decision: Background Tasks on Cloud Run

Agent runs (`process_run()`) are long-lived operations (10-60+ seconds) that don't fit cleanly into Cloud Run's request/response model.

### The problem

| Concern | Cloud Run behavior |
|---------|--------------------|
| Instance killed mid-run | In-flight agent loop is lost — no graceful shutdown |
| Concurrent requests | May route to different instances — no shared state |
| Instance timeout | Default 300s, max 3600s — long runs may exceed |
| Scale-to-zero | Cold starts add latency on first run |

### Phase 3 decision: "dev-safe background tasks" with production path documented

| Environment | Strategy |
|-------------|----------|
| **Local dev** | `BackgroundTasks` (FastAPI) — works fine on a single instance |
| **Production** | Must move to a worker model before launch (see below) |

**Phase 3 implementation:**
1. `POST /runs/execute` validates input, creates session (`status: 'running'`), returns `run_id` immediately
2. Agent loop runs as a `BackgroundTask` — writes progress via `session_store.update_status()` / `update_graph()`
3. On completion/failure, `session_store.update_status(user_id, run_id, 'completed'|'failed')` persists the final state
4. The run is **resumable** — if the instance dies, the session remains in `status: 'running'` and can be detected/retried

**Production worker model (implement before launch):**
- Separate Cloud Run service (or Cloud Run Jobs) for agent execution
- API service submits work via Cloud Tasks or Pub/Sub
- Worker service pulls from queue, executes agent loop, writes results to DB
- API service queries session status from DB

> **Why not decide this now?** The worker model requires queue infrastructure (Cloud Tasks/Pub/Sub), IAM configuration, and a separate deployment. This is operational complexity that blocks Phase 3 progress. The dev-safe approach works correctly for single-instance dev and lets Phase 3 focus on store correctness.

---

## Step 3.2: Copy + Refactor core files (deferred from Phase 2)

These files were deferred from Phase 2 because they import store classes that didn't exist yet. Now that stores are created in Step 3.1, these can be refactored.

### `core/scheduler.py`

- Source: `apexflow-v1/core/scheduler.py`
- Depends on: `job_store`, `job_run_store`, `notification_store`

**Remove:**
```python
# Line 16: JOBS_FILE = Path("data/system/jobs.json")
# Lines 46-47: JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
# Lines 56-60: if not JOBS_FILE.exists(): ... json.loads(JOBS_FILE.read_text())
# Lines 72-73: JOBS_FILE.write_text(json.dumps(...))
```

**Add:**
```python
from core.stores.job_store import JobStore
from core.stores.job_run_store import JobRunStore
from core.stores.notification_store import NotificationStore
```

**Add dedup to job execution:**
```python
# Before executing any job:
claimed = await job_run_store.try_claim(user_id, job_id, scheduled_for)
if not claimed:
    logging.info(f"Job {job_id} already claimed for {scheduled_for}, skipping")
    return
# ... execute job ...
await job_run_store.complete(user_id, job_id, scheduled_for, status="completed", output=result)
```

**Change:**
| v1 code | v2 replacement |
|---------|----------------|
| `json.loads(JOBS_FILE.read_text())` (line 60) | `await job_store.load_all(user_id)` |
| `JOBS_FILE.write_text(json.dumps(...))` (line 72-73) | `await job_store.update(user_id, job_def)` |
| Every `self.save_jobs()` call (lines 102, 145, 203, 231, 254) | Individual `job_store.create()` / `update()` / `delete()` calls |
| `send_to_inbox(...)` via filesystem (lines 156-166, 180-185) | `await notification_store.create(user_id, notif_dict)` |

**Key structural change:** `SchedulerService` methods become `async` since store calls are async. The singleton pattern stays the same.

### `core/persistence.py`

- Source: `apexflow-v1/core/persistence.py`
- Depends on: `state_store`

**Remove:**
```python
# Line 14: SNAPSHOT_FILE = Path("data/system/snapshot.json")
# Lines 53-54: SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
# Line 56: SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=2))
# Line 65: if not SNAPSHOT_FILE.exists()
# Line 69: json.loads(SNAPSHOT_FILE.read_text())
```

**Add:**
```python
from core.stores.state_store import StateStore
```

**Change:**
| v1 code | v2 replacement |
|---------|----------------|
| `SNAPSHOT_FILE.write_text(json.dumps(snapshot))` | `await state_store.set(user_id, "snapshot", snapshot)` |
| `json.loads(SNAPSHOT_FILE.read_text())` | `await state_store.get(user_id, "snapshot")` |

**Note:** `save_snapshot()` and `load_snapshot()` become async.

### `memory/context.py`

- Source: `apexflow-v1/memory/context.py`
- Depends on: `session_store`

**Remove:**
```python
# Lines 3-4: pathlib, json filesystem imports (keep json for serialization)
# Lines 611-614: Date directory creation (base_dir / YYYY / MM / DD / mkdir)
# Lines 617-622: JSON file write (open(session_file, 'w') ... json.dump(graph_data))
# Lines 627-630: JSON file read (open(session_file, 'r') ... json.load(f))
```

**Also remove** (from Phase 2 deferred list):
```python
# Rich imports: from rich.console import Console, from rich.panel import Panel, from rich.prompt import Prompt
```

**Add:**
```python
from core.stores.session_store import SessionStore
```

**Change:**
| v1 code | v2 replacement |
|---------|----------------|
| `_save_session()` filesystem write (lines 609-622) | `await session_store.save(user_id, graph_data)` |
| `load_session()` filesystem read (lines 624-635) | `await session_store.get(user_id, session_id)` |

**Key structural change:** `_save_session()` and `load_session()` become async. The `_auto_save()` wrapper (line 600-607) must also become async.

### `core/metrics_aggregator.py`

- Source: `apexflow-v1/core/metrics_aggregator.py`
- Depends on: `session_store`, `state_store` (for cache)
- Required by: `routers/metrics.py`

**Remove:**
```python
# Line 18: self.sessions_dir = self.base_dir / "data" / "conversation_history"
# Line 19: self.cache_dir = self.base_dir / "memory" / "metrics"
# Line 20: self.cache_file = self.cache_dir / "dashboard_cache.json"
# Lines 26-29: sessions_dir.rglob("session_*.json") directory walk
# Lines 528-530: cache_file.exists() + json.loads(cache_file.read_text())
# Lines 563-564: cache_file.write_text(json.dumps(metrics))
```

**Add:**
```python
from core.stores.session_store import SessionStore
from core.stores.state_store import StateStore
```

**Change:**
| v1 code | v2 replacement |
|---------|----------------|
| `self.sessions_dir.rglob("session_*.json")` (line 29) | SQL aggregation (see below) |
| `json.loads(session_file.read_text())` (line 30) | Not needed — aggregation computed in DB |
| `json.loads(self.cache_file.read_text())` (line 530) | `await state_store.get(user_id, "metrics_cache")` |
| `self.cache_file.write_text(json.dumps(metrics))` (line 564) | `await state_store.set(user_id, "metrics_cache", metrics)` |

**Note:** `get_dashboard_metrics()` becomes async.

**Important: Use SQL aggregation, not Python loops.** Pulling all sessions into Python to compute metrics won't scale. Add purpose-built queries in `SessionStore`:

```python
# core/stores/session_store.py — metrics-specific queries
async def get_dashboard_stats(self, user_id: str, days: int = 30) -> dict:
    """Compute dashboard metrics in SQL — no Python loops."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) AS total_runs,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                COALESCE(SUM(cost), 0) AS total_cost,
                COUNT(DISTINCT DATE(created_at)) AS active_days
            FROM sessions
            WHERE user_id = $1 AND created_at > NOW() - make_interval(days => $2)
        """, user_id, days)
        return dict(row)

async def get_daily_stats(self, user_id: str, days: int = 30) -> list[dict]:
    """Time-bucketed daily aggregation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DATE(created_at) AS day,
                   COUNT(*) AS runs,
                   COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                   COALESCE(SUM(cost), 0) AS cost
            FROM sessions
            WHERE user_id = $1 AND created_at > NOW() - make_interval(days => $2)
            GROUP BY DATE(created_at)
            ORDER BY day DESC
        """, user_id, days)
        return [dict(r) for r in rows]
```

The `MetricsAggregator` calls these SQL methods and caches the result in `state_store` with a user-scoped key. Cache invalidation: re-compute when cache is older than 5 minutes (timestamp in cached value).

---

## Step 3.3: Create service modules

These register tools with the ServiceRegistry so the agent loop can invoke them.

### `services/browser_service.py`

```python
from core.service_registry import ServiceRegistry, ToolDefinition, ToolExecutionError
from core.tool_context import ToolContext
from tools.web_tools_async import smart_search, smart_web_extract
import ipaddress
from urllib.parse import urlparse

# ---- SSRF protection ----
_DENIED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("127.0.0.0/8"),
]

def _is_safe_url(url: str) -> bool:
    """Block internal/metadata IPs. Returns False for unsafe URLs."""
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        # Resolve hostname and check against denied networks
        import socket
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if any(addr in net for net in _DENIED_NETWORKS):
                return False
    except (ValueError, socket.gaierror):
        return False
    return True

MAX_CONTENT_LENGTH = 500_000  # 500KB max extracted content

async def register(registry: ServiceRegistry):
    registry.register_service(
        service_id="browser",
        tools=[
            ToolDefinition(
                name="web_search",
                description="Search the web and return results",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of results", "default": 5}
                    },
                    "required": ["query"]
                },
                service_id="browser",
                arg_order=["query", "num_results"],
            ),
            ToolDefinition(
                name="web_extract_text",
                description="Extract text content from a URL",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to extract text from"}
                    },
                    "required": ["url"]
                },
                service_id="browser",
                arg_order=["url"],
            ),
        ],
        handler=handle_tool
    )

async def handle_tool(tool_name: str, arguments: dict, ctx: ToolContext) -> str:
    if tool_name == "web_search":
        return await smart_search(arguments["query"], arguments.get("num_results", 5))
    elif tool_name == "web_extract_text":
        url = arguments["url"]
        if not _is_safe_url(url):
            raise ToolExecutionError(tool_name, ValueError(f"URL blocked by SSRF policy: {url}"))
        result = await smart_web_extract(url)
        return result[:MAX_CONTENT_LENGTH]
    raise ToolExecutionError(tool_name, ValueError(f"Unknown tool: {tool_name}"))
```

### `services/rag_service.py` (stub -- completed in Phase 4a)

```python
from core.service_registry import ServiceRegistry, ToolDefinition, ToolExecutionError
from core.tool_context import ToolContext

async def register(registry: ServiceRegistry):
    registry.register_service(
        service_id="rag",
        tools=[
            ToolDefinition(name="index_document", description="...", parameters={...}, service_id="rag"),
            ToolDefinition(name="search_documents", description="...", parameters={...}, service_id="rag"),
            ToolDefinition(name="list_documents", description="...", parameters={...}, service_id="rag"),
            ToolDefinition(name="delete_document", description="...", parameters={...}, service_id="rag"),
        ],
        handler=handle_tool
    )

async def handle_tool(tool_name: str, arguments: dict, ctx: ToolContext) -> str:
    raise ToolExecutionError(tool_name, NotImplementedError(
        f"RAG service not yet implemented (Phase 4a). Tool: {tool_name}"
    ))
```

### `services/sandbox_service.py` (stub -- completed in Phase 4c)

```python
from core.service_registry import ServiceRegistry, ToolDefinition, ToolExecutionError
from core.tool_context import ToolContext

async def register(registry: ServiceRegistry):
    registry.register_service(
        service_id="sandbox",
        tools=[
            ToolDefinition(name="run_code", description="...", parameters={...}, service_id="sandbox"),
        ],
        handler=handle_tool
    )

async def handle_tool(tool_name: str, arguments: dict, ctx: ToolContext) -> str:
    raise ToolExecutionError(tool_name, NotImplementedError(
        "Sandbox service not yet available (Phase 4c)."
    ))
```

> **Stub behavior in agent configs:** In Phase 3, the `rag` and `sandbox` services are registered but return `ToolExecutionError(NotImplementedError)`. The agent loop handles this via the error-translation pattern from Phase 2. If you want to prevent agents from calling stub tools entirely, remove `rag` and `sandbox` from `config/agent_config.yaml` `mcp_servers` lists for Phase 3, and re-add them in Phase 4.

---

## Step 3.4: Copy + Refactor routers

All routers deferred from Phase 2 are refactored here. Each router replaces filesystem I/O with store calls and MCP calls with service registry calls.

### `routers/runs.py`

- Source: `apexflow-v1/routers/runs.py`
- Depends on: `session_store`

**Remove:**
```python
# Line 15: PROJECT_ROOT import (no longer needed for filesystem paths)
# Lines 182-227: data/Notes/Arcturus/ auto-save logic (v1-specific)
# Lines 352-401: summaries_dir.glob("*/*/*") recursive directory walk
# Lines 416-437: summaries_dir.rglob(f"session_{run_id}.json") search + JSON read
# Lines 518-521: Brute-force file search + path.unlink() for delete
```

**Change:**
| v1 code (approx lines) | v2 replacement |
|------------------------|----------------|
| `summaries_dir.glob("*/*/*")` + JSON reads (352-401) | `await session_store.list(user_id)` |
| `summaries_dir.rglob(f"session_{run_id}.json")` + read (416-437) | `await session_store.get(user_id, run_id)` |
| `path.unlink()` for session delete (518-521) | `await session_store.delete(user_id, run_id)` |
| `json.dump(graph_data, f)` for session save (928-930) | `await session_store.update_graph(user_id, run_id, graph_data, node_outputs)` |
| Notes auto-save (937-967) | Drop entirely (or defer to RAG service in Phase 4a) |

**Keep:** `process_run()` background task logic (agent execution). Wire it to partial updates:
- Start: `await session_store.create(user_id, {...})`
- During: `await session_store.update_graph(user_id, run_id, ...)` and `update_cost(user_id, run_id, delta)`
- End: `await session_store.update_status(user_id, run_id, 'completed'|'failed')`

See [Architecture Decision: Background Tasks on Cloud Run](#architecture-decision-background-tasks-on-cloud-run) for production limitations.

### `routers/chat.py`

- Source: `apexflow-v1/routers/chat.py`
- Depends on: `chat_store`

**Remove:**
```python
# Lines 40-63: get_chat_storage_path() (filesystem path computation)
# Lines 65-81: find_session_file() (filesystem search)
# All shutil, os, pathlib imports used for filesystem ops
# target_type: 'ide' branch (desktop-only)
```

**Change:**
| v1 code (approx lines) | v2 replacement |
|------------------------|----------------|
| `get_chat_storage_path()` + directory creation (46-62) | Remove -- store handles |
| `find_session_file()` search (70-81) | `await chat_store.find(user_id, session_id)` |
| Directory scan for sessions (92-119) | `await chat_store.list_sessions(user_id, target_type, target_id)` |
| `session_file.write_text()` (168) | `await chat_store.save(user_id, session_object)` |
| `session_file.unlink()` (178-181) | `await chat_store.delete(user_id, session_id)` |

### `routers/rag.py`

- Source: `apexflow-v1/routers/rag.py`
- Depends on: `rag_service` (Phase 4a completes the implementation)
- **Most complex router** -- 16+ filesystem operations

**Phase 3 approach:** Create a thin `rag_service` wrapper that the router calls. The actual implementation (document_store, document_search, chunker, ingestion) is completed in Phase 4a. For Phase 3, the router compiles and endpoints return stub responses.

**Remove:**
```python
# All direct Path() operations (data/ directory reads, writes, rglob, iterdir)
# get_multi_mcp() import -- replaced by rag_service
# Lines 27-84: Filesystem tree walking for document listing
# Lines 94-235: File/folder CRUD (create, delete, rename, move, copy)
# Lines 334-383: File write + upload operations
# Lines 635-770: Document content reads + deep search
```

**Change:** Every filesystem operation becomes a `rag_service` method call. The rag_service interface is:
```python
class RagService:
    async def list_documents(self, user_id: str) -> list[dict]: ...
    async def get_document_content(self, user_id: str, path: str) -> str: ...
    async def search(self, user_id: str, query: str, limit: int = 10) -> list[dict]: ...
    async def index_document(self, user_id: str, filename: str, content: str) -> dict: ...
    async def delete_document(self, user_id: str, doc_id: str) -> bool: ...
    # File management (stubs in Phase 3, may be dropped in favor of index-only API)
    async def create_file(self, user_id: str, path: str, content: str) -> dict: ...
    async def upload_file(self, user_id: str, filename: str, content: bytes) -> dict: ...
```

**Decision point:** The v1 RAG router exposes a full filesystem browser (create folder, rename, move, copy). In v2, documents are stored in AlloyDB, not a filesystem tree. Consider whether to:
- **(A)** Keep the tree UI by storing folder structure in document metadata
- **(B)** Simplify to flat document list (index, search, delete)

Recommendation: **(B)** for Phase 3 (simpler), add tree view later if needed.

### `routers/remme.py`

- Source: `apexflow-v1/routers/remme.py`
- Depends on: `session_store`, `state_store` (for profile cache)

**Remove:**
```python
# Line 42-43: summaries_dir = PROJECT_ROOT / "memory" / "session_summaries_index"
# Lines 70, 168, 188-190, 223-224: All summaries_dir.rglob() filesystem searches
# Lines 291-301, 442: Profile cache read/write to memory/remme_index/
```

**Change:**
| v1 code (approx lines) | v2 replacement |
|------------------------|----------------|
| `summaries_dir.rglob("session_*.json")` (42-43) | `await session_store.list_unscanned(user_id)` |
| `json.loads(sess_path.read_text())` (70) | `await session_store.get(user_id, run_id)` |
| `summaries_dir.rglob(f"session_{run_id}.json")` existence check (168, 188, 223) | `await session_store.exists(user_id, run_id)` |
| Profile cache read (295-301) | `await state_store.get(user_id, "remme_profile_cache")` |
| Profile cache write (442) | `await state_store.set(user_id, "remme_profile_cache", content)` |

### `routers/inbox.py`

- Source: `apexflow-v1/routers/inbox.py`
- Depends on: `notification_store`

**Remove entirely:**
```python
# Line 12: DB_PATH = Path("data/inbox/notifications.db")
# Lines 34-37: get_db_connection() SQLite factory
# Lines 39-62: init_db() SQLite schema creation
# Lines 65-82: send_to_inbox() function with raw SQL
# All sqlite3 import and usage
```

**Replace with:**
```python
from core.stores.notification_store import NotificationStore
from core.auth import get_user_id

# Use a dependency provider instead of a module-level singleton.
# NotificationStore is stateless (just uses the DB pool), so instantiation is cheap.
def get_notification_store() -> NotificationStore:
    return NotificationStore()

# Endpoints become thin wrappers:
@router.get("/notifications")
async def get_notifications(
    user_id: str = Depends(get_user_id),
    store: NotificationStore = Depends(get_notification_store),
    unread_only: bool = False,
):
    return await store.list(user_id, unread_only=unread_only)

@router.post("/notifications")
async def create_notification(
    req: CreateNotificationRequest,
    user_id: str = Depends(get_user_id),
    store: NotificationStore = Depends(get_notification_store),
):
    return await store.create(user_id, req.model_dump())

@router.patch("/notifications/{notif_id}/read")
async def mark_as_read(
    notif_id: str,
    user_id: str = Depends(get_user_id),
    store: NotificationStore = Depends(get_notification_store),
):
    return await store.mark_read(user_id, notif_id)

@router.delete("/notifications/{notif_id}")
async def delete_notification(
    notif_id: str,
    user_id: str = Depends(get_user_id),
    store: NotificationStore = Depends(get_notification_store),
):
    return await store.delete(user_id, notif_id)
```

**Also export** `send_to_inbox()` as a convenience function that other modules (scheduler) can call:
```python
async def send_to_inbox(user_id: str, source: str, title: str, body: str, priority: int = 1):
    """Called by scheduler and other internal modules."""
    store = NotificationStore()
    await store.create(user_id, {
        "source": source, "title": title, "body": body, "priority": priority
    })
```

> **Why not a module-level singleton?** Module-level singletons create hidden shared state that makes testing harder and can cause issues with uvicorn reload. Since stores are stateless (they just use the DB pool from `get_pool()`), instantiation is cheap and dependency injection via `Depends()` is the standard FastAPI pattern.

### `routers/cron.py`

- Source: `apexflow-v1/routers/cron.py`
- Depends on: `scheduler_service` (which now uses `job_store` from Step 3.2)
- **Minimal changes** -- cron.py is a thin wrapper around scheduler_service

**Change:**
- No direct filesystem ops (delegates to scheduler_service)
- Ensure scheduler_service is imported from updated `core/scheduler.py` (now async)
- Endpoint handlers may need `await` added since scheduler methods are now async

### `routers/metrics.py`

- Source: `apexflow-v1/routers/metrics.py`
- Depends on: `core/metrics_aggregator.py` (refactored in Step 3.2)
- **Minimal changes** -- metrics.py is a thin wrapper around MetricsAggregator

**Change:**
- Ensure `get_aggregator()` returns the refactored `MetricsAggregator`
- Endpoint handlers may need `await` since `get_dashboard_metrics()` is now async

---

## Step 3.5: Update api.py

After Phase 2, `api.py` only includes Phase 2 routers (stream, settings, skills, prompts, news). Now add Phase 3 routers.

```python
# api.py additions for Phase 3:

# Import Phase 3 routers
from routers import runs, chat, rag, remme, inbox, cron, metrics

# In lifespan startup (after ServiceRegistry init):
from services import browser_service, rag_service, sandbox_service
from shared.state import get_service_registry

registry = get_service_registry()
await browser_service.register(registry)
await rag_service.register(registry)      # Stub for now
await sandbox_service.register(registry)  # Stub for now

# Include Phase 3 routers
app.include_router(runs.router, prefix="/runs", tags=["runs"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(rag.router, prefix="/rag", tags=["rag"])
app.include_router(remme.router, prefix="/remme", tags=["remme"])
app.include_router(inbox.router, prefix="/inbox", tags=["inbox"])
app.include_router(cron.router, prefix="/cron", tags=["cron"])
app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
```

After Phase 3, `http://localhost:8000/docs` should show ALL endpoints (Phase 2 + Phase 3).

### Startup ordering and idempotency

- **Order matters:** DB pool must be initialized before any store usage or service registration
- **Idempotent registration:** `uvicorn --reload` can trigger startup multiple times. `ServiceRegistry.register_service()` already rejects duplicates (raises ValueError), so either: (a) create a fresh `ServiceRegistry` on each startup, or (b) add a `clear()` method for reload
- **Scheduler safety:** Do NOT run periodic scheduling (APScheduler) inside the web service in production — Cloud Run may have multiple instances and you cannot guarantee single-instance execution. In production, use Cloud Scheduler to trigger `/cron/run` endpoints via HTTP instead

```python
# api.py lifespan — correct ordering
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB pool first (stores depend on it)
    await init_pool()

    # 2. Service registration (idempotent via fresh registry)
    registry = ServiceRegistry()
    set_service_registry(registry)
    await browser_service.register(registry)
    await rag_service.register(registry)
    await sandbox_service.register(registry)

    # 3. Scheduler (local dev only — production uses Cloud Scheduler)
    if not os.environ.get("K_SERVICE"):
        scheduler = SchedulerService(...)
        scheduler.start()

    yield

    # Shutdown
    await close_pool()
```

---

## Step 3.6: Wire user_id through endpoints

All store methods take `user_id` as the first parameter. In Phase 2, auth middleware attaches `user_id` to `request.state`. Create a FastAPI dependency to extract it:

```python
# core/auth.py (add to existing file)
from fastapi import Request, Depends

async def get_user_id(request: Request) -> str:
    """Extract user_id from auth middleware. Returns 'default' if AUTH_DISABLED."""
    return getattr(request.state, "user_id", "default")
```

Every router endpoint that touches a store should use:
```python
@router.get("/runs")
async def list_runs(user_id: str = Depends(get_user_id)):
    return await session_store.list(user_id)
```

This is a mechanical change across all Phase 3 routers. In local dev with `AUTH_DISABLED=1`, all requests use `user_id="default"`.

---

## Verification

### 1. Import and boot checks

```bash
# Import check (all Phase 3 modules)
python -c "from core.stores.session_store import SessionStore; print('stores ok')"
python -c "from core.stores.job_run_store import JobRunStore; print('job_run_store ok')"
python -c "from core.stores.chat_store import ChatStore; print('chat_store ok')"
python -c "from services.browser_service import register; print('services ok')"
python -c "import api; print('api ok')"

# Start the app
uv run uvicorn api:app --reload --port 8000

# Verify ALL endpoints appear in OpenAPI docs
# http://localhost:8000/docs
# Expected: stream, settings, skills, prompts, news (Phase 2)
#         + runs, chat, rag, remme, inbox, cron, metrics (Phase 3)
```

### 2. CRUD smoke tests

```bash
# Session store:
curl -X POST http://localhost:8000/runs/execute \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "agent_type": "PlannerAgent"}'
curl http://localhost:8000/runs

# Notification store:
curl -X POST http://localhost:8000/inbox/notifications \
  -H "Content-Type: application/json" \
  -d '{"source": "test", "title": "Hello", "body": "Test notification"}'
curl http://localhost:8000/inbox/notifications

# Chat store:
curl -X POST http://localhost:8000/chat/sessions \
  -H "Content-Type: application/json" \
  -d '{"target_type": "run", "target_id": "test123", "title": "Test Chat"}'
curl http://localhost:8000/chat/sessions?target_type=run&target_id=test123

# ServiceRegistry routes browser tool calls
# Start a run that requires web search -- browser_service should handle it

# Verify data in AlloyDB
psql -h localhost -U apexflow -d apexflow -c "SELECT COUNT(*) FROM sessions;"
psql -h localhost -U apexflow -d apexflow -c "SELECT COUNT(*) FROM notifications;"
psql -h localhost -U apexflow -d apexflow -c "SELECT COUNT(*) FROM chat_sessions;"

# RAG and Sandbox return stub responses (not implemented until Phase 4)
curl -X POST http://localhost:8000/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}'
# Expected: "RAG service not yet implemented (Phase 4a)"
```

### 3. Tenant safety tests

Verify that no store method can leak data across users.

```bash
# Create sessions for two different users (requires AUTH_DISABLED=0 or test helper)
# User A creates a session:
curl -X POST http://localhost:8000/runs/execute \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user-a" \
  -d '{"query": "user A run", "agent_type": "PlannerAgent"}'

# User B should NOT see user A's sessions:
curl -H "X-User-Id: user-b" http://localhost:8000/runs
# Expected: empty list []

# User B should NOT be able to access user A's session by ID:
curl -H "X-User-Id: user-b" http://localhost:8000/runs/<user-a-run-id>
# Expected: 404

# Verify at DB level — every store query includes user_id in WHERE:
psql -h localhost -U apexflow -d apexflow -c \
  "SELECT id, user_id FROM sessions ORDER BY created_at DESC LIMIT 5;"
```

### 4. Scheduler dedup test

Verify that concurrent instances cannot execute the same job twice.

```bash
# Simulate two concurrent claim attempts for the same job+timestamp:
python -c "
import asyncio
from core.stores.job_run_store import JobRunStore
from datetime import datetime

async def test():
    store = JobRunStore()
    ts = datetime(2025, 1, 1, 12, 0, 0)
    r1 = await store.try_claim('user-a', 'job-1', ts)
    r2 = await store.try_claim('user-a', 'job-1', ts)
    assert r1 == True,  f'First claim should succeed, got {r1}'
    assert r2 == False, f'Second claim should fail, got {r2}'
    print('Scheduler dedup: PASS')

asyncio.run(test())
"
```

### 5. Chat correctness test

Verify append-only message semantics and pagination.

```bash
# Create a chat session, add messages, verify ordering and pagination:
python -c "
import asyncio
from core.stores.chat_store import ChatStore

async def test():
    store = ChatStore()
    # Create session
    sid = await store.create_session('user-a', target_type='run', target_id='test', title='Test')
    # Add messages
    m1 = await store.add_message('user-a', sid, 'user', 'Hello')
    m2 = await store.add_message('user-a', sid, 'assistant', 'Hi there')
    m3 = await store.add_message('user-a', sid, 'user', 'How are you?')
    # Get all messages — should be in chronological order
    msgs = await store.get_messages('user-a', sid)
    assert len(msgs) == 3, f'Expected 3 messages, got {len(msgs)}'
    assert msgs[0]['role'] == 'user' and msgs[0]['content'] == 'Hello'
    assert msgs[1]['role'] == 'assistant'
    assert msgs[2]['role'] == 'user' and msgs[2]['content'] == 'How are you?'
    # Pagination
    page = await store.get_messages('user-a', sid, limit=2, offset=0)
    assert len(page) == 2, f'Expected 2 messages in page, got {len(page)}'
    # Cross-tenant isolation
    other_msgs = await store.get_messages('user-b', sid)
    assert len(other_msgs) == 0, f'User B should see 0 messages, got {len(other_msgs)}'
    print('Chat correctness: PASS')

asyncio.run(test())
"
```

### 6. Metrics scalability check

Verify that dashboard metrics use SQL aggregation, not Python loops.

```bash
# After creating several test sessions, check that get_dashboard_stats returns correct aggregation:
python -c "
import asyncio
from core.stores.session_store import SessionStore

async def test():
    store = SessionStore()
    stats = await store.get_dashboard_stats('user-a', days=30)
    assert 'total_runs' in stats, 'Missing total_runs key'
    assert 'completed' in stats, 'Missing completed key'
    assert 'total_cost' in stats, 'Missing total_cost key'
    print(f'Dashboard stats: {stats}')
    print('Metrics scalability: PASS')

asyncio.run(test())
"

# Verify no Python-loop aggregation pattern exists:
rg "for.*in.*session_store.list\|for.*in.*sessions" core/metrics_aggregator.py
# Expected: no matches (aggregation should be in SQL, not Python)
```

---

## Phase 3 Exit Criteria

Phase 3 is complete when all of the following are true:

### Tenant safety
- [ ] Every store method takes `user_id` as its first parameter
- [ ] Every SQL `SELECT`, `UPDATE`, `DELETE` includes `WHERE user_id = $N`
- [ ] Cross-tenant data leak test passes (user B cannot see user A's sessions, messages, notifications, or jobs)
- [ ] `state_store` keys are user-scoped (`get(user_id, key)`, not `get(key)`)

### Scheduler dedup
- [ ] `job_runs` table exists with `UNIQUE(job_id, scheduled_for)` constraint
- [ ] `try_claim()` returns `False` on duplicate INSERT (ON CONFLICT DO NOTHING)
- [ ] Scheduler calls `try_claim()` before every job execution
- [ ] `complete()` marks job run with terminal status and timestamp

### Run execution reliability
- [ ] `POST /runs/execute` creates a session, returns `run_id`, and starts agent loop as background task
- [ ] Agent loop uses partial updates: `update_status()`, `update_graph()`, `update_cost()` — no monolithic `save()`
- [ ] `completed_at` is preserved once set (idempotent terminal state)
- [ ] Cost uses increment (`cost + delta`), not overwrite
- [ ] Failed runs set `status='failed'` with error message in DB (not lost silently)

### Chat correctness
- [ ] Messages are append-only (INSERT, never UPDATE)
- [ ] `add_message()` wraps insert + session `updated_at` in a transaction
- [ ] `get_messages()` returns chronological order with pagination support
- [ ] Chat sessions are user-scoped (user B cannot read user A's chat)

### Metrics scalability
- [ ] `get_dashboard_stats()` uses SQL `COUNT/SUM/FILTER` aggregation
- [ ] `get_daily_stats()` uses SQL `GROUP BY DATE(created_at)` — no Python loops over session rows
- [ ] Metrics cache keys are user-scoped in `state_store`
- [ ] Cache TTL is checked on read (re-compute if older than 5 minutes)

### Service layer
- [ ] `browser_service` registers tools with correct parameter names (`query`, `num_results`)
- [ ] `browser_service` handler accepts `ToolContext` and includes SSRF protection
- [ ] `rag_service` and `sandbox_service` stubs raise `ToolExecutionError(NotImplementedError)`, not string returns
- [ ] All service handlers accept `ctx: ToolContext` as third parameter

### Boot and integration
- [ ] `api.py` lifespan starts DB pool → registers services → starts scheduler (dev only)
- [ ] All Phase 3 routers appear in `/docs` OpenAPI spec
- [ ] `uvicorn --reload` does not crash on duplicate service registration
- [ ] No `import Path`, `open()`, `json.dump(file)`, or `sqlite3` in Phase 3 modules (all I/O via stores)
