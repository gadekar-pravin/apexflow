# Phase 4c: Monty Sandbox

**Prerequisites:** Phase 3 complete (ServiceRegistry + sandbox_service stub exists)
**Produces:** Secure code execution via Pydantic Monty (Rust-based Python interpreter)
**Can run in parallel with:** Phase 4a (RAG) and Phase 4b (REMME)
**Reference:** `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/docs/migration/03a-sandbox-monty-integration.md`

---

## Understanding Monty

Pydantic Monty is a **Rust-based Python interpreter** -- NOT a Python-level sandbox. It provides language-level isolation by design:
- No filesystem primitives (no `open()`)
- No OS module (`os`, `subprocess`)
- No network primitives (`socket`)
- No dynamic code loading (no `eval()`, `exec()`, `__import__`)
- Supported modules: `sys`, `typing`, `asyncio`, `json`, `dataclasses`

External functions (MCP/service tools) are registered with Monty. When code calls an external function, Monty pauses and returns a `MontySnapshot`. The host handles the async call and resumes execution with the result.

## Architecture Decision: Sandbox Isolation Model

Monty provides **language-level** isolation (no `open()`, `os`, `socket`, etc.), but NOT **resource-level** isolation. A memory bomb (e.g., `[0] * 10**9` via list comprehension) or CPU spin can still OOM or starve the web service if sandbox runs in-process.

### Isolation options

| Approach | Isolation | Complexity | Phase 4c? |
|----------|-----------|------------|-----------|
| **In-process with limits** | Timeout + step cap only. Memory bombs can OOM the web service. | Low | Yes (dev) |
| **Subprocess with resource limits** | `ulimit` / cgroups. Memory + CPU isolated. | Medium | Recommended |
| **Separate Cloud Run service** | Full isolation: own memory limit, concurrency=1, egress controls | High | Production |

**Phase 4c decision:** Use **subprocess with resource limits** for dev. Document the **separate Cloud Run service** path for production.

```python
# Subprocess isolation sketch — run Monty in a child process with resource limits
import subprocess, resource

def _run_in_subprocess(code: str, timeout: int = 30, max_memory_mb: int = 256) -> dict:
    """Execute Monty code in a subprocess with resource limits."""
    # The child process sets its own memory limit via resource.setrlimit
    # and is killed by the parent if it exceeds the timeout.
    # This prevents memory bombs from affecting the web service.
    ...
```

> **Production path:** Before launch, move sandbox execution to a dedicated Cloud Run service with `--memory=512Mi`, `--concurrency=1`, and strict VPC egress rules (deny all except required APIs). The API service submits code via Cloud Tasks / HTTP and polls for results.

## Create tools/monty_sandbox.py

- **AST preprocessing**: `preprocess_agent_code(code, external_func_names)`
  - Top-level `return` → wrap in `def __agent_main__()`
  - **Minimal, transparent transformations only** — reject code that can't be safely transformed (see below)
- **External function builder**: MCP/service tools → Monty external functions
- **Main executor**: `run_user_code(code, service_registry, ctx: ToolContext)` with start/resume loop
- **Session state**: save/load via `state_store` (AlloyDB) instead of filesystem
- **Security logging**: via `security_logs` table instead of JSONL files (with redaction — see below)
- **DoS protection** (Monty provides language-level isolation but not resource limits):
  - Enforce **execution timeout** (e.g., 30s default) via `asyncio.wait_for()` around the start/resume loop
  - Enforce **maximum steps** (e.g., 100,000 Monty steps) as a loop iteration cap
  - Enforce **output size limit** (e.g., 1MB) to prevent memory bombs via string concatenation
  - Enforce **subprocess memory limit** (e.g., 256MB) via `resource.setrlimit(RLIMIT_AS, ...)`
  - Log and abort executions that hit these limits (log to `security_logs` table)

### AST preprocessing safety rules

**Problem:** "Strip stray `await`" and "Convert keyword args to positional" are brittle transformations that can change code semantics:
- Stripping `await` can mask real logic errors in agent-generated code
- Converting kwargs to positional depends on knowing the exact argument order — dict key order is not reliable

**Rules:**
1. **`return` wrapping:** Safe — mechanical transformation, keep it
2. **`await` stripping:** Remove this transformation. Instead, **reject code containing `await`** with a clear error message ("Monty does not support async/await. Remove `await` from your code.")
3. **Keyword → positional conversion:** Use the **declared `arg_order`** from `ToolDefinition` (added in Phase 2), NOT dict key order. If `arg_order` is not available for a tool, keep keyword args and let the external function builder handle the mapping

```python
def preprocess_agent_code(code: str, external_func_names: list[str]) -> str:
    """Minimal AST preprocessing. Rejects code it can't safely transform."""
    tree = ast.parse(code)

    # 1. Wrap top-level return in __agent_main__
    if _has_top_level_return(tree):
        code = _wrap_in_main(code)

    # 2. Reject unsupported patterns (don't silently transform)
    if _contains_await(tree):
        raise ValueError(
            "Code contains 'await' which is not supported in Monty. "
            "Remove 'await' keywords — external function calls are synchronous in Monty."
        )

    return code
```

## Security logging: redaction and retention

**Problem:** Logging raw code and execution details can store secrets, PII, or sensitive data indefinitely. Agent-generated code may contain API keys, user data, or credentials passed as arguments.

### Redaction policy

```python
# tools/monty_sandbox.py — security log helpers

import hashlib

def _redact_for_logging(code: str, max_length: int = 500) -> str:
    """Redact code for security logging. Store hash + truncated preview."""
    return {
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        "code_preview": code[:max_length] + ("..." if len(code) > max_length else ""),
        "code_length": len(code),
    }

async def log_security_event(user_id: str, event_type: str, code: str,
                              details: dict, ctx: ToolContext) -> None:
    """Log a security event with redacted code."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO security_logs (user_id, event_type, details, created_at)
            VALUES ($1, $2, $3::jsonb, NOW())
        """, user_id, event_type, json.dumps({
            **_redact_for_logging(code),
            **details,
            "trace_id": ctx.trace_id,
        }))
```

### Retention

Phase 1 schema includes a retention comment: `security_logs` → 90 days. Implement via a scheduled cleanup job or database-level TTL:

```sql
-- Cleanup job (run daily via scheduler or Cloud Scheduler)
DELETE FROM security_logs WHERE created_at < NOW() - INTERVAL '90 days';
```

### What to log vs. what NOT to log

| Log | Don't log |
|-----|-----------|
| Event type (bypass attempt, timeout, success) | Full raw code (use hash + preview instead) |
| Code hash (SHA256) | Tool call arguments (may contain user data) |
| Execution duration, step count | External function return values |
| Error type and message | User-provided input passed as tool args |
| Trace ID for correlation | |

## External function tool restrictions

**Problem:** Even though Monty blocks network/filesystem access at the language level, external function calls (MCP/service tools) can reintroduce SSRF, data exfiltration, or unauthorized access. An agent-generated code snippet can call `web_search("company secrets")` or `web_extract_text("http://169.254.169.254/metadata")`.

### Sandbox tool allowlist

Not all registered tools should be available to sandbox code. Restrict which tools sandbox execution can invoke:

```python
# config/sandbox_config.py

# Tools allowed in sandbox context (whitelist approach)
SANDBOX_ALLOWED_TOOLS = {
    "web_search",        # Read-only, has SSRF protection (Phase 3)
    "web_extract_text",  # Read-only, has SSRF protection (Phase 3)
    "search_documents",  # Read-only RAG search
    # Explicitly NOT allowed:
    # "index_document"   — write operation
    # "delete_document"  — destructive
    # "run_code"         — recursive sandbox (must be blocked)
}

def get_sandbox_tools(registry: ServiceRegistry) -> dict:
    """Return only tools allowed in sandbox context."""
    return {
        name: tool for name, tool in registry.tools.items()
        if name in SANDBOX_ALLOWED_TOOLS
    }
```

**Rules:**
1. **No recursive execution:** `run_code` must never be available as an external function inside Monty (prevents sandbox-within-sandbox)
2. **No write tools by default:** Only read-only tools in the allowlist. Write tools require explicit opt-in
3. **SSRF protection inherited:** `web_extract_text` already has IP range blocking from Phase 3's browser_service
4. **Response size limits:** Cap external function return values (e.g., 100KB) before passing back to Monty
5. **Auth scoping:** External functions run with the user's `ToolContext` — tool-level auth can restrict per-user access

## Update services/sandbox_service.py

- Wire `run_code` tool to `monty_sandbox.run_user_code()`
- Complete the stub from Phase 3
- Handler accepts `ctx: ToolContext` (consistent with Phase 3 service pattern)
- Use `get_sandbox_tools()` to restrict which tools are available inside sandbox execution

## Refactor prompts for Monty compatibility

**`prompts/coder.md`**:
- Remove: "Data Science: `numpy`, `pandas` are GUARANTEED"
- Remove: `os.path.join(DATA_DIR, ...)` pattern
- Remove: `open()` for file creation
- Remove: `math`, `re`, `datetime`, `random`, `collections`, `itertools`, `statistics` from stdlib list
- Add: "Available modules: `json`, `sys`, `typing`, `dataclasses`"

**`prompts/retriever.md`**:
- Replace: `import ast` + `ast.literal_eval()` -> `json.loads()`
- Verify: all examples use only `json` from stdlib

## Security Test Vectors

```python
BYPASS_ATTEMPTS = [
    ("__import__('os').system('echo pwned')", "Dynamic os import"),
    ("getattr(__builtins__, 'open')('/etc/passwd')", "Builtins getattr bypass"),
    ("import subprocess; subprocess.run(['ls'])", "Subprocess"),
    ("import socket; socket.socket()", "Socket creation"),
    ("open('/etc/passwd').read()", "Direct file read"),
    ("__import__('importlib').import_module('os')", "Importlib bypass"),
    ("import os; os.listdir('/')", "Directory listing"),
    ("with open('/tmp/test', 'w') as f: f.write('x')", "File write"),
]
# ALL must return status="error"
```

## DoS Test Vectors

```python
DOS_ATTEMPTS = [
    ("while True: pass", "Infinite loop"),
    ("'x' * (10**9)", "Memory bomb via string"),
    ("def f(n): return f(n+1)\nf(0)", "Deep recursion"),
]
# ALL must be terminated by timeout/step cap
```

## Verification

### Security bypass tests

```bash
# Run all 8 bypass vectors — ALL must return status="error"
python -c "
from tools.monty_sandbox import run_user_code
from tests.sandbox_vectors import BYPASS_ATTEMPTS

async def test():
    for code, desc in BYPASS_ATTEMPTS:
        result = await run_user_code(code, registry=None, ctx=test_ctx)
        assert result['status'] == 'error', f'BYPASS SUCCEEDED: {desc}'
        print(f'  BLOCKED: {desc}')
    print('Security bypass: ALL 8 BLOCKED')

import asyncio; asyncio.run(test())
"
```

### DoS protection tests

```bash
# Run all 3 DoS vectors — ALL must be terminated within timeout
python -c "
from tools.monty_sandbox import run_user_code
from tests.sandbox_vectors import DOS_ATTEMPTS
import time

async def test():
    for code, desc in DOS_ATTEMPTS:
        start = time.time()
        result = await run_user_code(code, registry=None, ctx=test_ctx)
        elapsed = time.time() - start
        assert result['status'] == 'error', f'DoS not caught: {desc}'
        assert elapsed < 35, f'DoS took too long ({elapsed}s): {desc}'
        print(f'  TERMINATED ({elapsed:.1f}s): {desc}')
    print('DoS protection: ALL 3 TERMINATED')

import asyncio; asyncio.run(test())
"
```

### Process isolation test

```bash
# Verify sandbox runs in subprocess (memory bomb doesn't crash web service)
python -c "
import os, psutil

async def test():
    web_process = psutil.Process(os.getpid())
    mem_before = web_process.memory_info().rss
    # Run a memory-heavy sandbox task
    result = await run_user_code('[0] * (10**8)', registry=None, ctx=test_ctx)
    mem_after = web_process.memory_info().rss
    # Web service memory should not have grown significantly
    growth_mb = (mem_after - mem_before) / 1024 / 1024
    assert growth_mb < 50, f'Web service memory grew by {growth_mb:.0f}MB — sandbox not isolated'
    print(f'Process isolation: PASS (web service memory growth: {growth_mb:.1f}MB)')

import asyncio; asyncio.run(test())
"
```

### Valid code execution

```bash
# Basic functionality
python -c "
async def test():
    # Arithmetic
    r1 = await run_user_code('return 2 + 2', registry=None, ctx=test_ctx)
    assert r1['status'] == 'success' and r1['result'] == 4

    # String operations
    r2 = await run_user_code('return \"hello\".upper()', registry=None, ctx=test_ctx)
    assert r2['status'] == 'success' and r2['result'] == 'HELLO'

    # JSON processing
    r3 = await run_user_code('import json; return json.loads(\'{\"a\": 1}\')[\"a\"]', registry=None, ctx=test_ctx)
    assert r3['status'] == 'success' and r3['result'] == 1

    print('Valid execution: PASS')

import asyncio; asyncio.run(test())
"
```

### External function tool restrictions

```bash
# Verify sandbox tool allowlist:
python -c "
from config.sandbox_config import get_sandbox_tools, SANDBOX_ALLOWED_TOOLS

# run_code must NOT be in sandbox tools (no recursive execution)
assert 'run_code' not in SANDBOX_ALLOWED_TOOLS, 'run_code must not be available in sandbox'

# index_document must NOT be available (write operation)
assert 'index_document' not in SANDBOX_ALLOWED_TOOLS, 'write tools must not be in sandbox'

# web_search should be available (read-only with SSRF protection)
assert 'web_search' in SANDBOX_ALLOWED_TOOLS

print('Tool restrictions: PASS')
"
```

### Security logging verification

```bash
# Verify security events are logged with redaction:
python -c "
import asyncio
from core.database import get_pool

async def test():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT event_type, details FROM security_logs
            ORDER BY created_at DESC LIMIT 5
        ''')
        for row in rows:
            details = row['details']
            # Verify redaction: should have code_hash, NOT full raw code
            assert 'code_hash' in details, 'Missing code_hash in security log'
            assert len(details.get('code_preview', '')) <= 503, 'Code preview not truncated'
            print(f'  {row[\"event_type\"]}: hash={details[\"code_hash\"][:12]}...')
        print('Security logging: PASS')

asyncio.run(test())
"

# Verify retention: no logs older than 90 days
psql -h localhost -U apexflow -d apexflow -c \
  "SELECT COUNT(*) AS stale FROM security_logs WHERE created_at < NOW() - INTERVAL '90 days';"
# Expected: 0
```

### AST preprocessing safety

```bash
# Verify await rejection (not silent stripping):
python -c "
from tools.monty_sandbox import preprocess_agent_code
try:
    preprocess_agent_code('result = await web_search(\"test\")', ['web_search'])
    assert False, 'Should have raised ValueError for await'
except ValueError as e:
    assert 'await' in str(e)
    print(f'Await rejection: PASS ({e})')
"
```

---

## Phase 4c Exit Criteria

### Sandbox isolation
- [ ] Sandbox code runs in a subprocess with resource limits (not in-process with web service)
- [ ] Subprocess has memory limit (e.g., 256MB via `RLIMIT_AS`)
- [ ] Memory bomb test passes: web service memory does not grow significantly during sandbox execution
- [ ] Production deployment path documented (separate Cloud Run service with strict limits)

### Security
- [ ] ALL 8 bypass vectors return `status="error"` (no exceptions)
- [ ] ALL 3 DoS vectors terminated within timeout (step cap + asyncio timeout)
- [ ] `run_code` is NOT available as an external function inside Monty (no recursive execution)
- [ ] Sandbox tool allowlist restricts to read-only tools only
- [ ] External function return values capped at 100KB before passing to Monty

### AST preprocessing
- [ ] `return` wrapping works (top-level `return` → `def __agent_main__()`)
- [ ] `await` is **rejected** (not silently stripped) with a clear error message
- [ ] Keyword → positional conversion uses `arg_order` from `ToolDefinition`, not dict key order
- [ ] Code that can't be safely transformed is rejected, not silently mangled

### Security logging
- [ ] Security events logged to `security_logs` table (not JSONL files)
- [ ] Raw code is **redacted** (hash + truncated preview, not full source)
- [ ] Tool call arguments are NOT logged (may contain PII/secrets)
- [ ] Retention: logs older than 90 days are cleaned up (scheduled job or TTL)
- [ ] Trace ID included in logs for correlation with request context

### External function safety
- [ ] SSRF protection active for `web_extract_text` (inherited from Phase 3 browser_service)
- [ ] Tool availability tied to `SANDBOX_ALLOWED_TOOLS` allowlist
- [ ] Write operations (`index_document`, `delete_document`) excluded from sandbox
- [ ] External functions run with user's `ToolContext` for auth scoping
