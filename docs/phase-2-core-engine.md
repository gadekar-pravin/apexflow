# Phase 2: Core Engine (Copy + Refactor)

**Prerequisites:** Phase 1 complete (AlloyDB running, schema applied)
**Produces:** FastAPI app that boots with empty ServiceRegistry, core engine compiles, no store dependencies yet

**IMPORTANT:** This phase does NOT refactor files that depend on store classes (scheduler, persistence, context, routers, REMME). Those are deferred to Phase 3 where stores are created. Phase 2's goal is: **app boots + core loop runs with empty registry**.

---

## Step 2.1: Copy AS-IS files (no changes)

Copy these directly — verified to have no desktop/MCP/data-dir dependencies:

**Core modules (safe):**

| Source (v1 path) | Destination |
|-----------------|-------------|
| `core/gemini_client.py` | `core/gemini_client.py` |
| `core/event_bus.py` | `core/event_bus.py` |
| `core/circuit_breaker.py` | `core/circuit_breaker.py` |
| `core/graph_adapter.py` | `core/graph_adapter.py` |
| `core/json_parser.py` | `core/json_parser.py` |
| `core/utils.py` | `core/utils.py` |
| `core/skills/base.py` | `core/skills/base.py` |
| `config/settings_loader.py` | `config/settings_loader.py` |
| `config/models.json` | `config/models.json` |
| `config/profiles.yaml` | `config/profiles.yaml` |

(All paths relative to `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/`)

**REMME modules (no filesystem I/O in these):**

| Source | Destination |
|--------|-------------|
| `remme/extractor.py` | `remme/extractor.py` |
| `remme/utils.py` | `remme/utils.py` |
| `remme/hub_schemas.py` | `remme/hub_schemas.py` |
| `remme/normalizer.py` | `remme/normalizer.py` |
| `remme/engines/belief_update.py` | `remme/engines/belief_update.py` |

**Routers (verified safe for dev):**

| Source | Destination | Notes |
|--------|-------------|-------|
| `routers/stream.py` | `routers/stream.py` | Truly safe: event bus only, no filesystem |
| `routers/news.py` | `routers/news.py` | Safe: HTTP-only, settings dep is fine |
| `routers/settings.py` | `routers/settings.py` | Reads/writes config/ files. **Writes gated** (see below). |
| `routers/prompts.py` | `routers/prompts.py` | Reads/writes prompts/ dir. **Writes gated** (see below). |
| `routers/skills.py` | `routers/skills.py` | Reads skills library (exists in v2). skill_manager refactored below. |

**Local-write gating for settings and prompts routers:**

`routers/settings.py` and `routers/prompts.py` write to local disk, which is ephemeral on Cloud Run (writes vanish on instance restart or scale-down). To prevent cross-instance inconsistency and confusing "why didn't my setting persist?" bugs:

- Add an `ALLOW_LOCAL_WRITES=1` environment variable (set in `docker-compose.yml` for local dev, **not set** in Cloud Run)
- Write endpoints (`PUT`, `POST`, `DELETE`) return **403 with a clear message** when `ALLOW_LOCAL_WRITES` is not set
- Read endpoints always work
- Log a warning when a write is attempted in a non-local environment

```python
# shared/env.py (or inline in each router)
import os

def local_writes_allowed() -> bool:
    return os.environ.get("ALLOW_LOCAL_WRITES") == "1"

# In router write endpoints:
@router.put("/settings/{key}")
async def update_setting(key: str, value: dict):
    if not local_writes_allowed():
        logging.warning("Write rejected: ALLOW_LOCAL_WRITES not set (Cloud Run?)")
        raise HTTPException(403, "Writes disabled in this environment. Settings will be DB-backed in Phase 3.")
    # ... existing write logic
```

Add to `docker-compose.yml`:
```yaml
    environment:
      ALLOW_LOCAL_WRITES: "1"   # Local dev only — NOT set in Cloud Run
```

These endpoints move to DB-backed storage in Phase 3.

**Prompts directory:**
| Source | Destination |
|--------|-------------|
| `prompts/` (entire dir) | `prompts/` |

**NOT copied AS-IS (moved to Copy+Refactor or deferred):**

| File | Reason | Where |
|------|--------|-------|
| `routers/metrics.py` | Reads `data/conversation_history/` which doesn't exist in v2 | **Deferred to Phase 3** (needs session_store) |
| `routers/runs.py` | Uses session_store | Deferred to Phase 3 |
| `routers/chat.py` | Uses chat_store | Deferred to Phase 3 |
| `routers/rag.py` | Uses rag_service | Deferred to Phase 3 |
| `routers/remme.py` | Uses session_store | Deferred to Phase 3 |
| `routers/cron.py` | Uses job_store | Deferred to Phase 3 |
| `routers/inbox.py` | Uses notification_store | Deferred to Phase 3 |

### Pre-copy audit checklist

Before copying any "AS-IS" file, run the per-file check below. If any match, the file is NOT truly AS-IS:

```bash
# Run in apexflow-v1/ — per-file check
grep -l 'mcp_servers\|Path("data/\|Path("memory/\|sqlite3\|subprocess\|psutil\|rich\.' <file>
```

**Important:** The above grep misses several common coupling patterns. After copying all AS-IS files, run this **repo-wide scan** on the v2 directory to catch anything the per-file check missed:

```bash
# Run in apexflow/ (v2) — catches broader coupling patterns
rg -n 'MultiMCP|get_multi_mcp|mcp_servers|open\("data/|os\.path\.join\("data"|Path\("data/|Path\("memory/|pkgutil\.get_data|importlib\.resources|os\.getcwd|Path\("\.\")' \
  --glob '*.py'
```

| Pattern | Why it matters |
|---------|---------------|
| `MultiMCP`, `get_multi_mcp` | Direct MCP coupling (not caught by `mcp_servers` grep) |
| `open("data/...")`  | File I/O using `open()` instead of `Path()` |
| `os.path.join("data"...)` | Legacy path construction |
| `pkgutil.get_data`, `importlib.resources` | Resource loading that may assume package layout |
| `os.getcwd()`, `Path(".")` | Relies on current working directory (fragile in containers) |

**Hard gate:** `python -c "import api"` and `uvicorn api:app` must succeed **before** any further refactoring. Fix import failures first, refactor second.

---

## Step 2.2: Create NEW files (do this before refactoring)

### `core/tool_context.py`

Thread request context through every tool call. This prevents global-state creep and ensures multi-tenant correctness (Phase 1 removed `DEFAULT 'default'` from all `user_id` columns — every DB query now requires an explicit user_id).

```python
# core/tool_context.py

from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class ToolContext:
    """Request-scoped context passed to every tool call."""
    user_id: str                              # Required — no default (matches Phase 1 schema)
    trace_id: str = ""                        # From X-Cloud-Trace-Context or generated UUID
    deadline: Optional[float] = None          # Unix timestamp; None = no timeout
    metadata: dict = field(default_factory=dict)  # Auth scopes, roles, etc.

    @property
    def remaining_seconds(self) -> Optional[float]:
        if self.deadline is None:
            return None
        return max(0, self.deadline - time.time())

    @property
    def is_expired(self) -> bool:
        return self.deadline is not None and time.time() > self.deadline
```

Create `ToolContext` from request state in the middleware/dependency layer:

```python
# In api.py or a FastAPI dependency:
def get_tool_context(request: Request) -> ToolContext:
    return ToolContext(
        user_id=request.state.user_id,          # Set by auth middleware
        trace_id=request.state.trace_id,        # Set by logging middleware
        deadline=time.time() + 30,              # 30s default; tune per endpoint
    )
```

### `core/service_registry.py`

```python
# core/service_registry.py -- same interface as MultiMCP, in-process execution

from dataclasses import dataclass
from typing import Callable, Awaitable, Any
from core.tool_context import ToolContext

# ---- Structured exceptions (not string errors) ----

class ToolError(Exception):
    """Base exception for tool call failures."""
    pass

class ToolNotFoundError(ToolError):
    """Raised when a tool name is not in the registry."""
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found in registry")

class ToolExecutionError(ToolError):
    """Raised when a tool handler fails."""
    def __init__(self, tool_name: str, cause: Exception):
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(f"Tool '{tool_name}' failed: {cause}")

# ---- Data classes ----

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict            # JSON Schema (used for function_wrapper arg mapping)
    service_id: str
    arg_order: list[str] | None = None  # Explicit arg order for function_wrapper (see below)

@dataclass
class ServiceDefinition:
    id: str             # "browser", "rag", "sandbox"
    tools: dict[str, ToolDefinition]
    handler: Callable[[str, dict, ToolContext], Awaitable[Any]]

# ---- Registry ----

class ServiceRegistry:
    """Singleton. Same interface as MultiMCP."""

    def __init__(self):
        self._tool_map: dict[str, ToolDefinition] = {}      # tool_name -> definition
        self._services: dict[str, ServiceDefinition] = {}    # service_id -> definition
        self._handlers: dict[str, Callable] = {}             # service_id -> handler

    def register_service(self, service_id: str, tools: list[ToolDefinition], handler: Callable):
        # COLLISION PREVENTION: reject duplicate tool names at startup
        for tool in tools:
            if tool.name in self._tool_map:
                existing = self._tool_map[tool.name].service_id
                raise ValueError(
                    f"Tool '{tool.name}' already registered by service '{existing}'. "
                    f"Cannot register again from '{service_id}'."
                )
            self._tool_map[tool.name] = tool
        self._services[service_id] = ServiceDefinition(
            id=service_id, tools={t.name: t for t in tools}, handler=handler
        )
        self._handlers[service_id] = handler

    async def route_tool_call(self, tool_name: str, arguments: dict, ctx: ToolContext) -> Any:
        """Route a tool call to the appropriate service handler.

        Raises ToolNotFoundError if tool doesn't exist.
        Raises ToolExecutionError if handler fails.
        """
        tool = self._tool_map.get(tool_name)
        if not tool:
            raise ToolNotFoundError(tool_name)
        if ctx.is_expired:
            raise ToolExecutionError(tool_name, TimeoutError("Request deadline exceeded"))
        handler = self._handlers[tool.service_id]
        try:
            return await handler(tool_name, arguments, ctx)
        except ToolError:
            raise  # Re-raise our own exceptions
        except Exception as e:
            raise ToolExecutionError(tool_name, e) from e

    def get_all_tools(self) -> list[dict]:
        """Returns tools in OpenAI function-calling format (same as MultiMCP)."""
        return [
            {"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters
            }} for t in self._tool_map.values()
        ]

    def get_tools_from_servers(self, server_names: list[str]) -> list[dict]:
        """Filter tools by service_id (same as MultiMCP's server_names filter)."""
        tools = []
        for name in server_names:
            svc = self._services.get(name)
            if svc:
                tools.extend([
                    {"type": "function", "function": {
                        "name": t.name, "description": t.description, "parameters": t.parameters
                    }} for t in svc.tools.values()
                ])
        return tools

    async def function_wrapper(self, tool_name: str, ctx: ToolContext, *args) -> str:
        """Legacy positional-arg wrapper (sandbox-only compatibility shim).

        Maps positional args to keyword args. Uses explicit arg_order if
        defined on the tool, otherwise falls back to JSON Schema property
        key order (fragile but matches v1 behavior).

        This is used ONLY by tools/sandbox.py for tool proxies.
        Monty (Phase 4c) replaces the sandbox, making this obsolete.
        """
        tool = self._tool_map.get(tool_name)
        if not tool:
            raise ToolNotFoundError(tool_name)
        arguments = {}
        if tool.parameters and 'properties' in tool.parameters:
            # Prefer explicit arg_order; fall back to schema key order
            keys = tool.arg_order or list(tool.parameters['properties'].keys())
            for i, arg in enumerate(args):
                if i < len(keys):
                    arguments[keys[i]] = arg
        result = await self.route_tool_call(tool_name, arguments, ctx)
        return str(result)

    async def initialize(self):
        """Called during app startup (replaces MultiMCP.start())."""
        pass  # Services register themselves; nothing to start

    async def shutdown(self):
        """Called during app shutdown (replaces MultiMCP.stop())."""
        pass  # No subprocesses to kill
```

### Error handling in the agent loop

The agent loop (`core/loop.py`) must translate `ToolError` exceptions into model-visible error responses in **one place**:

```python
# In core/loop.py — tool call dispatch
try:
    result = await self.service_registry.route_tool_call(tool_name, tool_args, ctx)
    tool_response = {"ok": True, "data": result}
except ToolNotFoundError as e:
    tool_response = {"ok": False, "error": str(e)}
    logging.warning(f"Tool not found: {e.tool_name}", extra={"trace_id": ctx.trace_id})
except ToolExecutionError as e:
    tool_response = {"ok": False, "error": str(e)}
    logging.error(f"Tool execution failed: {e.tool_name}", extra={"trace_id": ctx.trace_id})
```

This keeps error semantics structured and testable — agents never see a string that "looks like" valid output but is actually an error.

### Agent config compatibility

The existing `config/agent_config.yaml` uses `mcp_servers: [browser, rag, sandbox]`. Support **both keys** with backward compatibility:

```python
# In agent config loader (agents/base_agent.py or config loader):
services = agent_config.get('services') or agent_config.get('mcp_servers', [])
```

This avoids a breaking rename. You can migrate configs at your own pace.

### `core/auth.py`

```python
# Firebase Auth JWT middleware
# - Verify Firebase ID token from Authorization header
# - Extract user_id, attach to request.state.user_id
# - Skip auth for health check endpoints (/readiness, /liveness)
# - Cache Firebase app initialization (initialize once at startup, not per-request)
# - AUTH_DISABLED=1 env var for local dev bypass (avoids blocking Phase 2 on Firebase setup)
```

**Implementation constraints:**
- Initialize `firebase_admin.initialize_app()` once in app lifespan, not per-request
- Cache decoded certs/public keys (Firebase Admin SDK handles this internally)
- Add `AUTH_DISABLED=1` environment variable for local dev testing
- **Production safety:** Fail startup if `K_SERVICE` is set (Cloud Run) AND `AUTH_DISABLED=1` — this prevents accidentally deploying with auth disabled
- Return 401 with clear error message for invalid/expired tokens

```python
# In core/auth.py startup:
if os.environ.get("K_SERVICE") and os.environ.get("AUTH_DISABLED") == "1":
    raise RuntimeError(
        "AUTH_DISABLED=1 is not allowed in Cloud Run. "
        "Remove AUTH_DISABLED from your Cloud Run env vars."
    )
```

### `core/logging_config.py`

Keep it simple — do not over-engineer:

```python
# Structured JSON logging (minimal)
# - Use python-json-logger or plain logging with JSON formatter
# - Include trace_id from X-Cloud-Trace-Context header when present (Cloud Run injects this)
# - Falls back to standard logging for local dev (no JSON)
# - Do NOT build a custom logging framework — use stdlib
```

**Content logging policy (important — prevents PII/secret leaks):**

| What to log | Default | Opt-in |
|-------------|---------|--------|
| Tool name, latency, success/failure | Always | — |
| Token counts, model name | Always | — |
| Prompt hash (SHA-256 of first 500 chars) | Always | — |
| trace_id, user_id, request_id | Always | — |
| **Prompt/response content** | **Never** | `LOG_PROMPTS=1` (local dev only) |
| **Tool arguments/results** | **Never** | `LOG_TOOL_IO=1` (local dev only) |

```python
# In core/loop.py — safe logging pattern:
import hashlib

# DEFAULT: log metadata, not content
logging.info("Agent prompt", extra={
    "trace_id": ctx.trace_id,
    "user_id": ctx.user_id,
    "prompt_hash": hashlib.sha256(prompt[:500].encode()).hexdigest(),
    "prompt_tokens": token_count,
})

# OPT-IN: content logging for local debugging only
if os.environ.get("LOG_PROMPTS") == "1":
    logging.debug(f"Agent prompt content: {prompt[:500]}")
```

> **Why this matters:** Centralized logging (Cloud Logging, Datadog, etc.) is searchable by anyone with access. Prompt content may contain user PII, API keys, or confidential business data. Log metadata by default; opt in to content only in local dev.

### `api.py`

```python
# Clean FastAPI entry point
# Lifespan:
#   startup: init DB pool + ServiceRegistry + (optionally) Firebase Admin
#   shutdown: close DB pool
# Middleware: Firebase Auth (with AUTH_DISABLED bypass), CORS
# Routers: only the ones that compile (Phase 2 AS-IS + Phase 2 refactored)
#   Include: stream, settings, skills, prompts, news
#   Exclude until Phase 3: runs, chat, rag, remme, cron, inbox, metrics
# Health: /readiness (DB check), /liveness (always 200)
```

---

## Step 2.3: Copy + Refactor (core engine only — NO store dependencies)

These refactors only replace MCP imports with ServiceRegistry imports and remove Rich/debug-log dependencies. They do NOT import any store classes.

**`core/loop.py`**
- Source: `apexflow-v1/core/loop.py`
- Remove: `from rich.live import Live`, `from rich.console import Console`, `from rich.panel import Panel`, `from rich.markdown import Markdown`
- Remove: Any `console.print()` calls -> replace with `logging.info()`
- Remove: `Path("memory/debug_logs/").mkdir()` and all debug log file writes
- Change: `self.multi_mcp` -> `self.service_registry` (method calls now take `ctx: ToolContext` as last arg)
- Add: Accept `ToolContext` in loop entry point and pass through to `route_tool_call`

**`core/model_manager.py`**
- Source: `apexflow-v1/core/model_manager.py`
- Remove: Ollama deprecation warnings (around lines 46-50)
- Remove: Any references to Ollama models

**`agents/base_agent.py`**
- Source: `apexflow-v1/agents/base_agent.py`
- Remove: All `Path("memory/debug_logs/")` file writes (lines ~106-141)
- Replace: File-based debug logging with `logging.debug()`
- Change: `self.multi_mcp` -> `self.service_registry`
- Add: Accept `ToolContext` and pass through to service_registry calls
- Config key: Use `agent_config.get('services') or agent_config.get('mcp_servers', [])` for backward compat

**`shared/state.py`**
- Source: `apexflow-v1/shared/state.py`
- Remove: `from mcp_servers.multi_mcp import MultiMCP` and `get_multi_mcp()`
- Add: `from core.service_registry import ServiceRegistry` and `get_service_registry()`
- Keep: `active_loops`, `get_remme_store()`, `get_remme_extractor()` (update imports)

**`core/skills/manager.py`**
- Replace hardcoded `Path("core/skills/library")` -> `Path(__file__).parent / "library"`
- Replace `Path("core/skills/registry.json")` -> `Path(__file__).parent / "registry.json"`

**`core/skills/library/web_clipper/skill.py`**
- Replace `Path("data/Notes/Clips/...").write_text(report)` with returning the report content (let the agent loop handle persistence)

**`core/skills/library/market_analyst/skill.py`**
- Replace `Path("data/Notes/Briefing/...").write_text(report)` with returning the report content

**`core/skills/library/system_monitor/`**
- **DROP entirely** — uses `psutil` for local CPU/RAM/disk metrics which are meaningless in a container

**`tools/web_tools_async.py`** and **`tools/switch_search_method.py`**
- Copy from v1, remove any desktop-specific references

**`config/agent_config.yaml`**
- Copy from v1
- Remove references to `yahoo_finance`, `new_server` MCP servers
- Keep `mcp_servers: [browser, rag, sandbox]` key name (backward compat)

**`config/settings.json`** and **`config/settings.defaults.json`**
- Copy from v1, remove MCP-specific settings

**`prompts/coder.md`** and **`prompts/retriever.md`**
- Update for Monty compatibility (see Phase 4c)

---

## DEFERRED to Phase 3 (depend on stores)

The following refactors are listed here for completeness but are **NOT done in Phase 2**. They move to Phase 3 once store classes exist.

**Core files needing stores:**
- `core/scheduler.py` — needs `job_store` (Phase 3)
- `core/persistence.py` — needs `state_store` (Phase 3)
- `memory/context.py` — needs `session_store` (Phase 3)

**Routers needing stores:**
- `routers/runs.py` — needs `session_store`
- `routers/chat.py` — needs `chat_store`
- `routers/rag.py` — needs `rag_service`
- `routers/remme.py` — needs `session_store`
- `routers/cron.py` — needs `job_store`
- `routers/inbox.py` — needs `notification_store`
- `routers/metrics.py` — needs `session_store` (currently reads `data/conversation_history/`)

**REMME files needing stores:**
- `remme/store.py` — needs `memory_store`
- `remme/staging.py` — needs `preferences_store`
- `remme/hubs/*.py` — need `preferences_store`
- `remme/engines/evidence_log.py` — needs `preferences_store`
- `remme/sources/notes_scanner.py` — needs path changes

---

## Key Refactoring Details

### core/loop.py

v1 imports to REMOVE:
```python
from rich.live import Live
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
```

v1 code patterns to CHANGE:
```python
# v1: self.multi_mcp.route_tool_call(tool_name, tool_args)
# v2: self.service_registry.route_tool_call(tool_name, tool_args, ctx)
#     (ctx = ToolContext from request state)

# v1: self.multi_mcp.get_all_tools()
# v2: self.service_registry.get_all_tools()

# v1: Path("memory/debug_logs/latest_prompt.txt").write_text(prompt)
# v2: log metadata by default, content only with LOG_PROMPTS=1 (see logging policy)
#     logging.info("Agent prompt", extra={"prompt_hash": ..., "prompt_tokens": ...})
```

### shared/state.py

```python
# REMOVE:
from mcp_servers.multi_mcp import MultiMCP
_multi_mcp = None
def get_multi_mcp():
    global _multi_mcp
    if _multi_mcp is None:
        _multi_mcp = MultiMCP()
    return _multi_mcp

# REPLACE WITH:
from core.service_registry import ServiceRegistry
_service_registry = None
def get_service_registry():
    global _service_registry
    if _service_registry is None:
        _service_registry = ServiceRegistry()
    return _service_registry
```

### function_wrapper semantics (reference)

v1's `function_wrapper` (multi_mcp.py:302-332) is a **generic, schema-driven** positional-to-keyword mapper. It:
1. Looks up the tool's `inputSchema`
2. Extracts property keys as an ordered list
3. Maps `args[0]` -> `keys[0]`, `args[1]` -> `keys[1]`, etc.
4. Calls `route_tool_call()` with the constructed dict

It is used **only** by `tools/sandbox.py` for tool proxies in the sandbox execution environment. Since Monty (Phase 4c) replaces the sandbox with external functions, `function_wrapper` is a compatibility shim.

**Arg order safeguard:** The v2 `ToolDefinition` includes an optional `arg_order: list[str]` field. When defined, `function_wrapper` uses it instead of relying on JSON Schema property key order (which is not a semantic contract). For sandbox-registered tools, populate `arg_order` explicitly:

```python
ToolDefinition(
    name="browser_navigate",
    description="Navigate to URL",
    parameters={"properties": {"url": {...}, "wait": {...}}},
    service_id="browser",
    arg_order=["url", "wait"],  # Explicit — not dependent on dict ordering
)
```

For all **non-sandbox** tool call paths, use keyword arguments only (no positional mapping).

---

## Verification

### Basic boot checks

```bash
# 1. Import check (catches import cycles and missing modules)
python -c "import api; print('import ok')"

# 2. Start the app
uv run uvicorn api:app --reload --port 8000

# 3. Verify health endpoints (no auth required)
curl http://localhost:8000/liveness    # {"status": "alive"}
curl http://localhost:8000/readiness   # {"status": "ready"} (if DB is up)

# 4. Verify OpenAPI docs show only Phase 2 routers
# http://localhost:8000/docs
# Expected: stream, settings, skills, prompts, news, health endpoints
# NOT expected: runs, chat, rag, remme, cron, inbox, metrics (Phase 3)

# 5. Verify ServiceRegistry initializes empty
# Check logs for: "ServiceRegistry initialized (0 services)"
```

### Router smoke tests (empty registry)

Each included router must return a sensible response even when no tools are registered:

```bash
# 6. Skills router — should list skills, not crash on empty registry
curl http://localhost:8000/api/skills
# Expected: 200 with skill list (skills don't depend on ServiceRegistry tools)

# 7. Settings read — should work
curl http://localhost:8000/api/settings
# Expected: 200 with current settings

# 8. Settings write — should be gated
curl -X PUT http://localhost:8000/api/settings/test -d '{"value": 1}'
# Expected: 200 if ALLOW_LOCAL_WRITES=1, 403 otherwise

# 9. Stream endpoint — should accept connection (even if no events)
# (Manual test — SSE endpoint)
```

### Readiness degradation

```bash
# 10. Stop the database and verify readiness degrades
docker compose stop alloydb-omni
curl http://localhost:8000/readiness
# Expected: 503 with {"status": "unavailable", "detail": "database connection failed"}
# NOT: 500 with unhandled exception traceback

docker compose start alloydb-omni
# Wait for healthy, then re-check readiness -> 200
```

### Repo-wide coupling scan

```bash
# 11. Verify no hidden MCP/filesystem coupling leaked through
rg -n 'MultiMCP|get_multi_mcp|mcp_servers|open\("data/|os\.path\.join\("data"|Path\("data/|Path\("memory/' \
  --glob '*.py' .
# Expected: zero matches (all references should have been replaced or deferred)
```

---

## Phase 2 Exit Criteria

Phase 2 is **done** when all of the following are true:

### Boot contract
- [ ] `python -c "import api"` succeeds (no import errors)
- [ ] `uvicorn api:app` starts without errors
- [ ] `/liveness` returns 200 always
- [ ] `/readiness` returns 200 when DB is up, **503 with structured error** when DB is down (degrades cleanly, no unhandled exceptions)

### Registry contract
- [ ] `ServiceRegistry` supports tool listing (`get_all_tools`) and routing (`route_tool_call`)
- [ ] Missing tool raises `ToolNotFoundError` (not a string return)
- [ ] Tool handler failure raises `ToolExecutionError` with cause
- [ ] `route_tool_call` accepts `ToolContext(user_id, trace_id, deadline)`
- [ ] Agent loop has one error-translation point that converts exceptions to `{ok, data, error}` dicts

### Router contract
- [ ] Only boot-safe routers are included (stream, settings, skills, prompts, news)
- [ ] Phase 3 routers are NOT imported (runs, chat, rag, remme, cron, inbox, metrics)
- [ ] Write endpoints in settings/prompts return 403 when `ALLOW_LOCAL_WRITES` is not set
- [ ] Each included router returns a sensible response with empty registry (smoke tested)

### Safety / maintainability
- [ ] No prompt or tool I/O content in logs by default (metadata only: hashes, token counts, latency)
- [ ] `LOG_PROMPTS=1` opt-in works for local debugging
- [ ] `AUTH_DISABLED=1` fails startup when `K_SERVICE` is set (cannot accidentally deploy with auth off)
- [ ] Repo-wide coupling scan (`rg` command above) returns zero matches for MCP/filesystem patterns
- [ ] `function_wrapper` uses explicit `arg_order` for sandbox tools (not relying on schema key order alone)
