# Phase 4a: RAG System (AlloyDB + ScaNN + FTS)

**Prerequisites:** Phase 3 complete (store pattern established, rag_service stub exists)
**Produces:** Working document indexing and hybrid search (vector + full-text)
**Can run in parallel with:** Phase 4b (REMME) and Phase 4c (Sandbox)

---

## Create core/stores/document_store.py

- `index_document(user_id, filename, content, metadata)` -- chunk, embed, store
- `get_document(user_id, doc_id)`, `list_documents(user_id)`, `delete_document(user_id, doc_id)`
- Deduplication via `file_hash` (SHA256) — enforced by `UNIQUE(user_id, file_hash)` from Phase 1 schema
- Cascading delete (document + all chunks)
- All methods take `user_id` as first parameter (consistent with Phase 3 store pattern)

### Dedup with ON CONFLICT

Phase 1 has `UNIQUE(user_id, file_hash)` on the `documents` table. Use `ON CONFLICT` to make re-indexing idempotent:

```python
async def index_document(self, user_id: str, filename: str, content: str,
                         metadata: dict | None = None) -> dict:
    """Index a document. If same file_hash exists for this user, update metadata only (no re-embed)."""
    file_hash = hashlib.sha256(content.encode()).hexdigest()
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Upsert document — ON CONFLICT updates metadata, skips re-embedding
        row = await conn.fetchrow("""
            INSERT INTO documents (id, user_id, filename, file_hash, content, metadata,
                                   embedding_model, embedding_dim)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            ON CONFLICT (user_id, file_hash) DO UPDATE SET
                filename = EXCLUDED.filename,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id, (xmax = 0) AS is_new
        """, doc_id, user_id, filename, file_hash, content,
            json.dumps(metadata or {}), EMBEDDING_MODEL, EMBEDDING_DIM)

        if not row["is_new"]:
            # Same content already indexed — skip chunking and embedding
            return {"id": row["id"], "status": "deduplicated"}

        # Only chunk + embed for genuinely new documents
        chunks = chunk_document(content)
        embeddings = await generate_embeddings(chunks)
        await self._store_chunks(conn, row["id"], user_id, chunks, embeddings)
        return {"id": row["id"], "status": "indexed", "chunks": len(chunks)}
```

> **Key:** `(xmax = 0) AS is_new` is a PostgreSQL trick — `xmax = 0` means the row was inserted (not updated). This avoids a separate `SELECT` to check for duplicates.

## Create core/stores/document_search.py

- `hybrid_search(user_id, query_text, query_embedding, limit)`
- Combines ScaNN cosine similarity with `ts_rank` full-text search
- **Uses Reciprocal Rank Fusion (RRF)** instead of raw-score blending (scores from different modalities are not directly comparable)
- Returns ranked results with RRF score + both component scores for tuning
- **Per-document dedup:** caps results to best chunk per document to avoid one document crowding out diversity

### Why RRF over raw-score blending

| Problem with raw blending | RRF solution |
|---------------------------|--------------|
| `1 - (embedding <=> qvec)` can be negative (cosine range depends on normalization) | RRF uses **rank position**, not raw score |
| `ts_rank` has a totally different scale and distribution | RRF normalizes via `1 / (k + rank)` — always 0-1 range |
| Fixed weight (0.7) is not stable across query types or embedding models | RRF parameter `k` (typically 60) is empirically robust |

```sql
-- Hybrid search with Reciprocal Rank Fusion (RRF)
-- k=60 is the standard RRF smoothing constant (from Cormack et al. 2009)
WITH vector_ranked AS (
    SELECT id, content, document_id, metadata,
           1 - (embedding <=> $1::vector) AS vector_score,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS vector_rank
    FROM document_chunks
    WHERE user_id = $2
    ORDER BY embedding <=> $1::vector
    LIMIT $3 * 3
),
text_ranked AS (
    SELECT id, content, document_id, metadata,
           ts_rank(content_tsv, plainto_tsquery('english', $4)) AS text_score,
           ROW_NUMBER() OVER (ORDER BY ts_rank(content_tsv, plainto_tsquery('english', $4)) DESC) AS text_rank
    FROM document_chunks
    WHERE user_id = $2
      AND content_tsv @@ plainto_tsquery('english', $4)
    ORDER BY text_score DESC
    LIMIT $3 * 3
),
fused AS (
    SELECT COALESCE(v.id, t.id) AS id,
           COALESCE(v.content, t.content) AS content,
           COALESCE(v.document_id, t.document_id) AS document_id,
           COALESCE(v.metadata, t.metadata) AS metadata,
           -- RRF score: 1/(k+rank) from each stream, summed
           COALESCE(1.0 / (60 + v.vector_rank), 0) + COALESCE(1.0 / (60 + t.text_rank), 0) AS rrf_score,
           -- Keep component scores for debugging/tuning
           v.vector_score,
           t.text_score,
           v.vector_rank,
           t.text_rank
    FROM vector_ranked v
    FULL OUTER JOIN text_ranked t ON v.id = t.id
),
-- Per-document dedup: keep only the best chunk per document
deduped AS (
    SELECT DISTINCT ON (document_id) *
    FROM fused
    ORDER BY document_id, rrf_score DESC
)
SELECT id, content, document_id, metadata, rrf_score, vector_score, text_score
FROM deduped
ORDER BY rrf_score DESC
LIMIT $3;
```

> **Tuning:** The response includes `vector_score`, `text_score`, and `rrf_score`. Log these in development to evaluate search quality. If RRF isn't sufficient, min-max normalization per-stream is the next step up, but RRF is a strong default that doesn't require score distribution knowledge.

> **DISTINCT ON (document_id):** Prevents a single document's chunks from dominating the results. If you need multiple chunks from the same document, use "top 2 chunks per doc" by replacing `DISTINCT ON` with `ROW_NUMBER() OVER (PARTITION BY document_id ORDER BY rrf_score DESC) <= 2`.

## Create core/rag/chunker.py

- Source: `/Users/pravingadekar/Documents/EAG2-Capstone/apexflow-v1/mcp_servers/server_rag.py`
- Key function: `chunk_document(text, method="rule_based", chunk_size=512, chunk_overlap=50) -> list[str]`

### Chunking strategy decision

| Method | Pros | Cons |
|--------|------|------|
| **`rule_based` (default)** | Deterministic, fast, free, reproducible boundaries | May split mid-paragraph |
| `semantic` (opt-in) | Better boundaries, context-aware splits | Gemini API cost + latency, nondeterministic (impacts dedup/reindex debugging) |

**Default to `rule_based`** — deterministic paragraph/token-based splitting. Make semantic chunking opt-in via a flag for high-value documents.

```python
# core/rag/chunker.py

def chunk_document(text: str, method: str = "rule_based",
                   chunk_size: int = 512, chunk_overlap: int = 50) -> list[str]:
    """Chunk a document into segments for embedding.

    Args:
        method: 'rule_based' (default, deterministic) or 'semantic' (Gemini-based, opt-in)
    """
    if method == "semantic":
        return _chunk_semantic(text)  # Gemini-based — extracted from v1
    return _chunk_rule_based(text, chunk_size, chunk_overlap)

def _chunk_rule_based(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Deterministic paragraph/token-based chunking."""
    # Split by paragraph first, then merge or split to target chunk_size
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > chunk_size and current:
            chunks.append(current.strip())
            # Overlap: keep tail of previous chunk
            current = current[-chunk_overlap:] + "\n\n" + para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks

async def _chunk_semantic(text: str) -> list[str]:
    """Gemini-based semantic chunking — preserve from v1. Async due to API call."""
    # Extract from apexflow-v1/mcp_servers/server_rag.py
    ...
```

> **Why deterministic by default?** Nondeterministic chunk boundaries cause: (1) different chunk IDs on re-index of same content, breaking dedup; (2) unpredictable search behavior; (3) difficult debugging. Reserve semantic chunking for cases where boundary quality materially impacts retrieval.

## Embedding/Model Versioning

Dedup ("same hash = no-op") breaks if the embedding model changes — old embeddings are incomparable with new ones. Track versioning explicitly:

```python
# core/rag/config.py
EMBEDDING_MODEL = "text-embedding-004"   # Current model
EMBEDDING_DIM = 768                       # Must match Phase 1 schema vector(768)
INGESTION_VERSION = 1                     # Bump when changing model/chunking/normalization
```

**Stored in `documents` table** (add columns if not in Phase 1 schema):

| Column | Type | Purpose |
|--------|------|---------|
| `embedding_model` | `TEXT` | Model name at time of indexing |
| `embedding_dim` | `INTEGER` | Vector dimension used |
| `ingestion_version` | `INTEGER` | Composite version (model + chunking + normalization) |

**Dedup rule:** same `file_hash` + same `ingestion_version` = skip. If `ingestion_version` differs, re-chunk and re-embed.

### Reindex strategy

When the embedding model changes:

1. Bump `INGESTION_VERSION` in config
2. Run reindex job: `POST /rag/admin/reindex` (or background job)
3. Reindex iterates all documents where `ingestion_version < CURRENT`, re-chunks, re-embeds, and updates chunks
4. Old chunks are deleted and replaced atomically (within a transaction per document)

```python
async def reindex_document(self, user_id: str, doc_id: str) -> dict:
    """Re-chunk and re-embed a document with current model/version."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            doc = await conn.fetchrow(
                "SELECT id, content FROM documents WHERE id = $1 AND user_id = $2",
                doc_id, user_id)
            if not doc:
                return {"status": "not_found"}
            # Delete old chunks
            await conn.execute(
                "DELETE FROM document_chunks WHERE document_id = $1 AND user_id = $2",
                doc_id, user_id)
            # Re-chunk and re-embed with current model
            chunks = chunk_document(doc["content"])
            embeddings = await generate_embeddings(chunks)
            await self._store_chunks(conn, doc_id, user_id, chunks, embeddings)
            # Update document version
            await conn.execute("""
                UPDATE documents SET embedding_model = $3, embedding_dim = $4,
                       ingestion_version = $5, updated_at = NOW()
                WHERE id = $1 AND user_id = $2
            """, doc_id, user_id, EMBEDDING_MODEL, EMBEDDING_DIM, INGESTION_VERSION)
            return {"status": "reindexed", "chunks": len(chunks)}
```

## Create core/rag/ingestion.py

Pipeline: `ingest_document(user_id, filename, content)` ->
1. Compute SHA256 hash for dedup
2. Check if existing document has same hash + same `ingestion_version` → skip if so
3. Chunk content (using `method` from request, default `rule_based`)
4. Generate embeddings (batch, via `remme/utils.py` or Gemini directly)
5. Store document metadata (including `embedding_model`, `embedding_dim`, `ingestion_version`) + chunks in AlloyDB

## Asyncpg + pgvector type handling

Passing vectors reliably with `asyncpg` requires a registered codec. Without it, you end up string-building vectors (slow, error-prone, and breaks parameterized queries).

**Standardize on one serialization path and test it early (insert + search roundtrip).**

```python
# core/database.py — add to pool initialization (init_pool)
from pgvector.asyncpg import register_vector

async def init_pool():
    pool = await asyncpg.create_pool(...)
    # Register pgvector codec for all connections in the pool
    async with pool.acquire() as conn:
        await register_vector(conn)
    # Also register for new connections created by the pool
    pool._init = register_vector  # or use pool's setup callback
    return pool
```

**Dependencies:** Add `pgvector` to project dependencies (Python package: `pgvector`). This provides `register_vector()` which handles the codec for `asyncpg` so you can pass `list[float]` or `numpy.ndarray` directly as query parameters.

**Smoke test:** Before proceeding with any RAG functionality, verify a roundtrip:

```python
# Test: insert a vector and retrieve it via cosine similarity
async def test_vector_roundtrip():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO document_chunks (id, user_id, document_id, chunk_index, content, embedding) VALUES ($1, $2, $3, $4, $5, $6)",
            "test-id", "test-user", "test-doc", 0, "test content", [0.1] * 768)
        row = await conn.fetchrow(
            "SELECT 1 - (embedding <=> $1::vector) AS sim FROM document_chunks WHERE id = 'test-id'",
            [0.1] * 768)
        assert row["sim"] > 0.99, f"Roundtrip failed: similarity={row['sim']}"
        await conn.execute("DELETE FROM document_chunks WHERE id = 'test-id'")
```

## Update services/rag_service.py

- Wire tool handlers to `document_store` and `document_search`
- Complete the stub from Phase 3
- Tools: `index_document`, `search_documents`, `list_documents`, `delete_document`
- All handlers accept `ctx: ToolContext` (consistent with Phase 3 service pattern)

## Scope note

Stick with **flat document APIs** (index/search/list/delete) — no filesystem-like folder tree. This matches the Phase 3 decision to simplify from v1's filesystem browser. Add folder/tree UI only if user demand proves the need.

## Verification

### Basic CRUD

- `POST /rag/index` a document → stored in `documents` + `document_chunks` tables
- `POST /rag/search` with a query → returns ranked results with `rrf_score`, `vector_score`, `text_score`
- `GET /rag/documents` → lists all indexed documents for the authenticated user
- `DELETE /rag/documents/{id}` → cascading delete removes document + chunks

### Dedup and versioning

```bash
# Index a document
curl -X POST http://localhost:8000/rag/index \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.txt", "content": "Hello world"}'
# Expected: {"id": "...", "status": "indexed", "chunks": N}

# Re-index same content — should deduplicate
curl -X POST http://localhost:8000/rag/index \
  -H "Content-Type: application/json" \
  -d '{"filename": "test.txt", "content": "Hello world"}'
# Expected: {"id": "...", "status": "deduplicated"}

# Verify embedding_model and ingestion_version are stored
psql -h localhost -U apexflow -d apexflow -c \
  "SELECT id, filename, embedding_model, ingestion_version FROM documents LIMIT 5;"
```

### Search quality

```bash
# Search and verify response includes component scores
curl -X POST http://localhost:8000/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "hello"}'
# Expected: results with rrf_score, vector_score, text_score fields

# Verify per-document dedup (no single document dominates top results):
# Index a long document that produces many chunks, then search —
# result should show at most 1 chunk per document (DISTINCT ON behavior)
```

### Vector roundtrip

```bash
# Run the asyncpg vector codec test before any other RAG tests
python -c "
import asyncio
from core.database import init_pool, get_pool

async def test():
    await init_pool()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO document_chunks (id, user_id, document_id, chunk_index, content, embedding)
            VALUES (\$1, \$2, \$3, \$4, \$5, \$6)
        ''', 'test-vec', 'test-user', 'test-doc', 0, 'test', [0.1]*768)
        row = await conn.fetchrow('''
            SELECT 1 - (embedding <=> \$1::vector) AS sim
            FROM document_chunks WHERE id = 'test-vec'
        ''', [0.1]*768)
        assert row['sim'] > 0.99, f'Vector roundtrip failed: {row[\"sim\"]}'
        await conn.execute(\"DELETE FROM document_chunks WHERE id = 'test-vec'\")
        print('Vector roundtrip: PASS')

asyncio.run(test())
"
```

### Golden query tests

Create a small set of golden queries with known-good results for regression testing:

```python
GOLDEN_QUERIES = [
    {"query": "machine learning basics", "expected_doc_ids": ["ml-intro-doc"]},
    {"query": "API authentication", "expected_doc_ids": ["auth-guide-doc"]},
]
# Index golden documents, run searches, verify expected documents appear in top-3
```

---

## Phase 4a Exit Criteria

### Search quality
- [ ] Hybrid search uses RRF (not raw-score blending) with component scores in response
- [ ] Per-document dedup prevents chunk dominance (`DISTINCT ON (document_id)` or equivalent)
- [ ] Golden query test suite passes (expected documents in top-3 for each query)
- [ ] RRF parameter `k=60` documented; tuning pathway clear

### Dedup and versioning
- [ ] `UNIQUE(user_id, file_hash)` constraint enforced — concurrent inserts don't create duplicates
- [ ] `ON CONFLICT` handles race conditions gracefully (update metadata, skip re-embed)
- [ ] `embedding_model`, `embedding_dim`, `ingestion_version` stored per document
- [ ] Reindex endpoint/job exists for re-embedding when model changes
- [ ] Dedup is version-aware: same hash + different `ingestion_version` triggers re-embed

### Chunking
- [ ] Default chunker is `rule_based` (deterministic paragraph/token splitting)
- [ ] Semantic chunking (Gemini-based) is opt-in via `method="semantic"` flag
- [ ] Chunk boundaries are reproducible for same content + same method

### Infrastructure
- [ ] `pgvector` asyncpg codec registered at pool init — vector roundtrip test passes
- [ ] All store methods take `user_id` as first parameter
- [ ] Cascading delete removes document + all chunks in a transaction
- [ ] `rag_service.py` stub replaced with working handlers accepting `ToolContext`
