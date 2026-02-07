# Phase 4b: REMME Memory (AlloyDB + ScaNN)

**Prerequisites:** Phase 3 complete (store pattern established)
**Produces:** Working memory system with AlloyDB vector search replacing FAISS
**Can run in parallel with:** Phase 4a (RAG) and Phase 4c (Sandbox)

---

## Create core/stores/memory_store.py

- `add(user_id, text, category, source, embedding, confidence)` -- INSERT into memories
- `search(user_id, query_embedding, limit=10, min_similarity=None)` -- ScaNN vector search (top-k, optional threshold)
- `delete(user_id, memory_id)`, `get_all(user_id)`, `update_text(user_id, memory_id, new_text)`
- All methods take `user_id` as first parameter (consistent with Phase 3 store pattern)

> **Scan tracking:** `mark_run_scanned()` lives in `SessionStore` (Phase 3), not `MemoryStore`. Phase 3 decided to use both `sessions.remme_scanned` and `scanned_runs` updated atomically in a transaction. The REMME memory engine calls `session_store.mark_scanned(user_id, run_id)` after processing a session — do NOT duplicate that logic here.

### Search: top-k with optional dynamic threshold

Hard-coded thresholds (e.g., `threshold=0.3`) are fragile — the threshold's meaning depends on embedding normalization and model. A model change silently shifts what `0.3` means.

**Strategy: prefer top-k, make threshold optional.**

```python
async def search(self, user_id: str, query_embedding: list[float],
                 limit: int = 10, min_similarity: float | None = None) -> list[dict]:
    """Search memories by vector similarity.

    Args:
        limit: Return top-k results (always applied)
        min_similarity: Optional floor — omit results below this similarity.
                        WARNING: value depends on embedding model normalization.
                        Prefer using limit alone; use min_similarity only for
                        precision-critical use cases where you've validated the threshold.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if min_similarity is not None:
            rows = await conn.fetch("""
                SELECT id, text, category, source, confidence, created_at,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM memories
                WHERE user_id = $2
                  AND 1 - (embedding <=> $1::vector) > $3
                ORDER BY similarity DESC
                LIMIT $4
            """, query_embedding, user_id, min_similarity, limit)
        else:
            rows = await conn.fetch("""
                SELECT id, text, category, source, confidence, created_at,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM memories
                WHERE user_id = $2
                ORDER BY similarity DESC
                LIMIT $3
            """, query_embedding, user_id, limit)
        return [dict(r) for r in rows]
```

> **Embedding model dependency:** If you change the embedding model (e.g., from `text-embedding-004` to a newer version), existing memory embeddings become incomparable. See Phase 4a's reindex strategy — memories need the same `embedding_model` / `ingestion_version` tracking. Add `embedding_model` to the `memories` table insert.

## Create core/stores/preferences_store.py

- `get_hub_data(user_id, hub_name) -> dict` -- read from JSONB column
- `save_hub_data(user_id, hub_name, data)` -- write to JSONB column (with concurrency protection)
- `merge_hub_data(user_id, hub_name, partial_data)` -- partial JSONB update (for concurrent-safe field updates)
- `get_staging(user_id)`, `save_staging(user_id, data)`
- `get_evidence(user_id)`, `save_evidence(user_id, data)`
- All methods take `user_id` as first parameter

Hub name to column mapping:

| Hub | Column |
|-----|--------|
| `preferences` | `preferences` |
| `operating_context` | `operating_ctx` |
| `soft_identity` | `soft_identity` |
| `evidence` | `evidence_log` |
| `staging` | `staging_queue` |

### Concurrency protection for JSONB writes

**Problem:** `save_hub_data()` that overwrites the entire JSONB blob will lose updates if two requests write concurrently (last-write-wins). This is likely when the REMME engine processes multiple sessions in parallel.

**Solution: Two complementary approaches:**

1. **`merge_hub_data()` for partial updates** — uses `||` (JSONB concatenation) to merge fields without overwriting unrelated data:

```python
_HUB_COLUMN = {
    "preferences": "preferences",
    "operating_context": "operating_ctx",
    "soft_identity": "soft_identity",
    "evidence": "evidence_log",
    "staging": "staging_queue",
}

async def merge_hub_data(self, user_id: str, hub_name: str, partial_data: dict) -> None:
    """Merge partial data into a hub's JSONB column (concurrent-safe).
    Only updates the keys present in partial_data; leaves other keys untouched."""
    col = _HUB_COLUMN[hub_name]
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"""
            UPDATE user_preferences SET {col} = COALESCE({col}, '{{}}'::jsonb) || $2::jsonb,
                   updated_at = NOW()
            WHERE user_id = $1
        """, user_id, json.dumps(partial_data))
```

2. **`save_hub_data()` with optimistic concurrency** — for full overwrites, check `updated_at` to detect conflicts:

```python
async def save_hub_data(self, user_id: str, hub_name: str, data: dict,
                        expected_updated_at: datetime | None = None) -> bool:
    """Full overwrite of hub data. If expected_updated_at is provided,
    returns False if the row was modified since that timestamp (optimistic lock)."""
    col = _HUB_COLUMN[hub_name]
    pool = await get_pool()
    async with pool.acquire() as conn:
        if expected_updated_at:
            result = await conn.execute(f"""
                UPDATE user_preferences SET {col} = $2::jsonb, updated_at = NOW()
                WHERE user_id = $1 AND updated_at = $3
            """, user_id, json.dumps(data), expected_updated_at)
            return result != "UPDATE 0"  # False = conflict detected
        else:
            await conn.execute(f"""
                UPDATE user_preferences SET {col} = $2::jsonb, updated_at = NOW()
                WHERE user_id = $1
            """, user_id, json.dumps(data))
            return True
```

> **Prefer `merge_hub_data()` for most hub operations** — it's inherently concurrent-safe. Reserve `save_hub_data()` with optimistic locking for cases where you need to replace the entire blob (e.g., staging queue clear-and-replace).

## Refactor remme/store.py

- Source: `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/store.py`
- Remove: `import faiss`, FAISS index loading/saving
- Remove: JSON file persistence (`memories.json`, `scanned_runs.json`)
- Change: All vector operations → `memory_store` queries
- Change: Scan tracking → `session_store.mark_scanned(user_id, run_id)` (Phase 3 atomic approach)
- Keep: `RemmeStore` class name and public API for backward compatibility
- Add: `embedding_model` to memory inserts for versioning (see Phase 4a)

## Refactor remme/hubs/base_hub.py

- Source: `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/hubs/base_hub.py`
- Remove: JSON file `_load()` and `save()` methods

### Async adapter strategy (blast radius control)

**Problem:** Turning `_load()` and `save()` into `async` cascades across every hub subclass and every caller of hub methods. The REMME engine has many hub interactions, and making everything `await` at once balloons the Phase 4b scope.

**Strategy: Keep hub logic synchronous in-memory; persist at well-defined commit points.**

```python
# remme/hubs/base_hub.py — async adapter pattern

class BaseHub:
    def __init__(self, hub_name: str):
        self.hub_name = hub_name
        self._data: dict | None = None  # In-memory cache

    # --- Sync in-memory API (used by hub subclass logic) ---
    @property
    def data(self) -> dict:
        """Access hub data. Must call load() first."""
        if self._data is None:
            raise RuntimeError(f"Hub '{self.hub_name}' not loaded. Call await hub.load() first.")
        return self._data

    def update(self, key: str, value) -> None:
        """Update a field in-memory. Does NOT persist until commit()."""
        self.data[key] = value

    # --- Async persistence boundary (called at well-defined points) ---
    async def load(self, user_id: str) -> None:
        """Load hub data from DB into memory. Call once at the start of a REMME scan."""
        self._data = await preferences_store.get_hub_data(user_id, self.hub_name) or {}

    async def commit(self, user_id: str) -> None:
        """Persist in-memory data to DB. Call once at the end of a REMME scan."""
        if self._data is not None:
            await preferences_store.merge_hub_data(user_id, self.hub_name, self._data)

    async def commit_partial(self, user_id: str, keys: list[str]) -> None:
        """Persist only specific fields (concurrent-safe via JSONB merge)."""
        partial = {k: self._data[k] for k in keys if k in (self._data or {})}
        if partial:
            await preferences_store.merge_hub_data(user_id, self.hub_name, partial)
```

**Usage in REMME engine:**
```python
# remme/engine.py — well-defined async boundaries
async def run_scan(user_id: str, sessions: list[dict]):
    # 1. Load all hubs (async boundary: start)
    for hub in all_hubs:
        await hub.load(user_id)

    # 2. Process sessions (sync hub logic — no await inside)
    for session in sessions:
        for hub in all_hubs:
            hub.process(session)  # Sync — updates in-memory only

    # 3. Commit all hubs (async boundary: end)
    for hub in all_hubs:
        await hub.commit(user_id)
```

> **Why this approach?** It limits `await` to exactly 2 points (load and commit) instead of converting every hub method to async. Hub subclass logic stays synchronous and testable without an event loop. The blast radius is contained to the REMME engine entry point.

## Refactor remme/staging.py

- Source: `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/staging.py`
- Remove: JSON file storage
- Change: -> `preferences_store.get_staging()` / `save_staging()`

## Refactor remme/engines/evidence_log.py

- Source: `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/remme/engines/evidence_log.py`
- Remove: JSON file storage
- Change: -> `preferences_store.get_evidence()` / `save_evidence()`

## Verification

### Basic functionality

- Memories persist across API restarts (in AlloyDB, not FAISS)
- `POST /remme/memories` adds a memory with vector embedding
- `POST /remme/search` returns semantically similar memories (top-k, with similarity scores)
- Hub data (preferences, operating context, soft identity) persists in `user_preferences` table
- Staging queue and evidence log persist across restarts

### Scan tracking

```bash
# Verify mark_scanned updates BOTH sessions.remme_scanned AND scanned_runs atomically:
python -c "
import asyncio
from core.stores.session_store import SessionStore

async def test():
    store = SessionStore()
    # Create a test session, then mark it scanned
    await store.create('test-user', {'id': 'scan-test', 'query': 'test', 'status': 'completed'})
    await store.mark_scanned('test-user', 'scan-test')
    # Verify both are updated
    from core.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        sess = await conn.fetchrow('SELECT remme_scanned FROM sessions WHERE id = \$1', 'scan-test')
        assert sess['remme_scanned'] == True, 'remme_scanned not set'
        scan = await conn.fetchrow('SELECT * FROM scanned_runs WHERE run_id = \$1', 'scan-test')
        assert scan is not None, 'scanned_runs row not inserted'
    print('Scan tracking: PASS')

asyncio.run(test())
"
```

### Concurrent preferences writes

```bash
# Verify merge_hub_data doesn't clobber concurrent writes:
python -c "
import asyncio
from core.stores.preferences_store import PreferencesStore

async def test():
    store = PreferencesStore()
    # Two concurrent partial updates to different keys
    await asyncio.gather(
        store.merge_hub_data('test-user', 'preferences', {'theme': 'dark'}),
        store.merge_hub_data('test-user', 'preferences', {'language': 'en'}),
    )
    data = await store.get_hub_data('test-user', 'preferences')
    assert data.get('theme') == 'dark', f'theme lost: {data}'
    assert data.get('language') == 'en', f'language lost: {data}'
    print('Concurrent preferences: PASS')

asyncio.run(test())
"
```

### Hub async adapter

```bash
# Verify hub load/commit cycle works without await inside processing:
python -c "
import asyncio
from remme.hubs.base_hub import BaseHub

async def test():
    hub = BaseHub('preferences')
    await hub.load('test-user')
    # Sync operations — no await
    hub.update('test_key', 'test_value')
    assert hub.data['test_key'] == 'test_value'
    await hub.commit('test-user')
    # Reload and verify persistence
    hub2 = BaseHub('preferences')
    await hub2.load('test-user')
    assert hub2.data.get('test_key') == 'test_value', 'Hub data not persisted'
    print('Hub async adapter: PASS')

asyncio.run(test())
"
```

### Memory search quality

```bash
# Verify top-k returns results without hard threshold:
python -c "
import asyncio
from core.stores.memory_store import MemoryStore

async def test():
    store = MemoryStore()
    # Add test memories
    embedding = [0.1] * 768
    await store.add('test-user', 'I like Python', 'preference', 'test', embedding, 0.8)
    await store.add('test-user', 'I prefer dark mode', 'preference', 'test', embedding, 0.9)
    # Search with top-k only (no threshold)
    results = await store.search('test-user', embedding, limit=5)
    assert len(results) >= 2, f'Expected >= 2 results, got {len(results)}'
    # Search with optional threshold
    results_t = await store.search('test-user', embedding, limit=5, min_similarity=0.99)
    print(f'Top-k results: {len(results)}, with threshold: {len(results_t)}')
    print('Memory search: PASS')

asyncio.run(test())
"
```

---

## Phase 4b Exit Criteria

### Scan tracking
- [ ] `mark_scanned()` uses Phase 3's atomic approach (both `sessions.remme_scanned` + `scanned_runs` in one transaction)
- [ ] REMME engine calls `session_store.mark_scanned()`, not a separate `memory_store.mark_run_scanned()`
- [ ] `list_unscanned(user_id)` correctly returns only sessions where `remme_scanned = FALSE`

### Search quality
- [ ] `memory_store.search()` uses top-k by default (no hard-coded threshold in WHERE)
- [ ] `min_similarity` parameter is optional with documented model-dependency warning
- [ ] `embedding_model` stored per memory for versioning (matches Phase 4a strategy)
- [ ] Reindex path documented for model changes

### Preferences concurrency
- [ ] `merge_hub_data()` uses JSONB `||` concatenation (concurrent-safe partial updates)
- [ ] `save_hub_data()` supports optimistic concurrency via `expected_updated_at`
- [ ] Concurrent write test passes (two parallel merges to different keys both survive)

### Async blast radius
- [ ] Hub subclass logic remains synchronous (no `await` inside `process()` methods)
- [ ] `await` limited to exactly 2 boundary points: `hub.load()` and `hub.commit()`
- [ ] REMME engine entry point (`run_scan`) manages async boundaries
- [ ] Hub subclasses do not need modification to become async-compatible

### Store pattern
- [ ] All `memory_store` methods take `user_id` as first parameter
- [ ] All `preferences_store` methods take `user_id` as first parameter
- [ ] No FAISS imports, no JSON file persistence in any REMME module
- [ ] Memories, preferences, staging, and evidence survive API restart (AlloyDB)
