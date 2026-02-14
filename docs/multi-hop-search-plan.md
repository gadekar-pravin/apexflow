# Multi-Hop Search Implementation Plan

**Status:** Proposed
**Date:** 2026-02-14
**Prerequisites:** Phase 4a RAG system complete (hybrid search, document ingestion)
**Scope:** Add iterative retrieval (multi-hop) to the existing RAG pipeline — no new infrastructure

---

## Motivation

Single-hop hybrid search (`DocumentSearch.hybrid_search()`) finds chunks matching the query directly. It cannot discover related information that uses different terminology or spans multiple documents. Multi-hop search addresses this by:

1. Running an initial retrieval (hop 1)
2. Extracting key entities/terms from the top results
3. Expanding the query with those entities
4. Running a second retrieval (hop 2) excluding already-seen chunks
5. Merging and re-ranking results from both hops

This gives practical cross-document, cross-terminology retrieval with zero infrastructure changes.

### Tradeoff vs LightRAG

| Dimension | Multi-hop-lite | LightRAG |
|---|---|---|
| Infrastructure | None (AlloyDB only) | Neo4j AuraDB (~$65/mo) |
| Per-query cost | 1 extra LLM call + 1 extra embedding | 0 (pre-computed graph) |
| Per-query latency | ~2-4s (vs ~500ms single-hop) | <1s graph traversal |
| Per-document ingestion cost | 0 extra | 3-5 LLM calls |
| Cross-document entity resolution | No | Yes |
| Schema changes | 0 | New tables or external DB |
| Failure blast radius | Graceful fallback to single-hop | Feature offline if Neo4j down |
| ADR-001 compliance | Full (AlloyDB only) | Partial (adds Neo4j, but scoped to LightRAG) |

Multi-hop-lite is the right choice when query volume is low and document ingestion frequency is high. If cross-document entity resolution becomes critical, LightRAG remains the stronger long-term option.

---

## Architecture

```
User query
    │
    ▼
┌────────────────────────┐
│  search_documents_     │
│  multihop (tool)       │
│  services/rag_service  │
└────────┬───────────────┘
         │
    ┌────▼────┐
    │  Hop 1  │  hybrid_search(query, limit=hop1_limit)
    │         │  → top chunks with rrf_score, vector_score, text_score
    └────┬────┘
         │
    ┌────▼──────────────┐
    │  Entity Extraction │  Gemini flash-lite: extract 3-5 key entities
    │  (LLM or skip)     │  from top-k hop 1 chunks
    └────┬──────────────┘
         │
    ┌────▼────────────────┐
    │  Query Expansion    │  Combine: original query + extracted entities
    │                     │  → expanded query string
    └────┬────────────────┘
         │
    ┌────▼────┐
    │  Hop 2  │  hybrid_search(expanded_query, limit=hop2_limit,
    │         │                exclude_chunks=[...hop1 chunk_ids])
    └────┬────┘
         │
    ┌────▼──────────────┐
    │  Merge & Re-rank  │  Combine hop 1 + hop 2 results
    │                   │  Score = relevance + cross-hop support + diversity
    └────┬──────────────┘
         │
         ▼
    Final results with evidence chain (hop attribution per chunk)
```

---

## Files to Modify

| File | Change | Scope |
|---|---|---|
| `core/stores/document_search.py` | Add `exclude_chunks` parameter to `hybrid_search()` | Small — two `AND id != ALL(...)` clauses in existing CTEs |
| `core/rag/multihop.py` | **New file** — multi-hop orchestrator (entity extraction, query expansion, merge/re-rank) | ~150 lines |
| `services/rag_service.py` | Add `search_documents_multihop` tool definition + handler branch | ~30 lines |
| `routers/rag.py` | Add `POST /api/rag/search/multihop` endpoint + request model | ~25 lines |
| `core/rag/config.py` | Add multi-hop constants | ~5 lines |
| `tests/unit/test_multihop.py` | **New file** — unit tests for entity extraction, query expansion, merge/re-rank | ~200 lines |
| `tests/unit/test_rag.py` | Update `TestRagService.test_registration` — tool count `4→5`, add `search_documents_multihop` assertion | ~3 lines |

**No migrations. No new tables. No new dependencies.**

---

## Detailed Implementation

### Step 1: Extend `hybrid_search` with chunk exclusion

**File:** `core/stores/document_search.py`

Add an optional `exclude_chunk_ids` parameter to the existing method signature:

```python
async def hybrid_search(
    self,
    user_id: str,
    query_text: str,
    query_embedding: Any,
    *,
    limit: int = 5,
    exclude_chunk_ids: list[str] | None = None,  # NEW
) -> list[dict[str, Any]]:
```

Add exclusion filters to both CTEs in the SQL. When `exclude_chunk_ids` is `None` or empty, the filter is a no-op (`id != ALL('{}'::text[])` matches everything):

```sql
-- In vector_ranked CTE, after WHERE user_id = $2:
AND id != ALL($6::text[])

-- In text_ranked CTE, after WHERE user_id = $2:
AND id != ALL($6::text[])
```

Pass `exclude_chunk_ids or []` as parameter `$6`.

**Why modify the existing method instead of creating a new one:** The exclusion filter is a general-purpose capability. Other features (e.g., "show me more like this but different") would also benefit from it. Adding it as an optional parameter keeps a single code path to maintain.

---

### Step 2: Create multi-hop orchestrator

**File:** `core/rag/multihop.py` (new)

```python
"""Multi-hop search orchestrator — iterative retrieval with query expansion."""

from __future__ import annotations

import json
import logging
from typing import Any

from core.model_manager import ModelManager
from core.rag.config import (
    MULTIHOP_ENTITY_MODEL,
    MULTIHOP_HOP1_LIMIT,
    MULTIHOP_HOP2_LIMIT,
    MULTIHOP_MAX_ENTITIES,
    MULTIHOP_TOP_K_FOR_EXTRACTION,
)
from core.rag.ingestion import embed_query
from core.stores.document_search import DocumentSearch

logger = logging.getLogger(__name__)

_doc_search = DocumentSearch()


async def multihop_search(
    user_id: str,
    query: str,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Execute a two-hop search with LLM-driven query expansion.

    Returns:
        {
            "results": [...],          # merged, re-ranked chunks
            "hops": [                  # evidence chain
                {"query": str, "result_count": int},
                {"query": str, "expanded_terms": [...], "result_count": int},
            ],
            "total_results": int,
        }
    """
    # --- Hop 1: initial retrieval ---
    hop1_embedding = await embed_query(query)
    hop1_results = await _doc_search.hybrid_search(
        user_id, query, hop1_embedding, limit=MULTIHOP_HOP1_LIMIT,
    )

    hops = [{"hop": 1, "query": query, "result_count": len(hop1_results)}]

    if not hop1_results:
        return {"results": [], "hops": hops, "total_results": 0}

    # --- Entity extraction from top hop 1 chunks ---
    top_chunks = hop1_results[:MULTIHOP_TOP_K_FOR_EXTRACTION]
    entities = await extract_entities(query, top_chunks)

    if not entities:
        # No useful entities found — return hop 1 results directly
        for r in hop1_results:
            r["hop"] = 1
        return {
            "results": hop1_results[:limit],
            "hops": hops,
            "total_results": len(hop1_results),
        }

    # --- Query expansion ---
    expanded_query = f"{query} {' '.join(entities)}"

    # --- Hop 2: expanded retrieval, excluding hop 1 chunks ---
    # Guarded: any hop 2 failure falls back to hop 1 results only
    hop1_chunk_ids = [r["chunk_id"] for r in hop1_results]
    hop2_results: list[dict[str, Any]] = []
    try:
        hop2_embedding = await embed_query(expanded_query)
        hop2_results = await _doc_search.hybrid_search(
            user_id, expanded_query, hop2_embedding,
            limit=MULTIHOP_HOP2_LIMIT,
            exclude_chunk_ids=hop1_chunk_ids,
        )
    except Exception:
        logger.warning("Hop 2 failed, returning hop 1 results only", exc_info=True)

    hops.append({
        "hop": 2,
        "query": expanded_query,
        "expanded_terms": entities,
        "result_count": len(hop2_results),
    })

    # --- Merge and re-rank ---
    merged = _merge_and_rerank(hop1_results, hop2_results, limit)

    return {
        "results": merged,
        "hops": hops,
        "total_results": len(hop1_results) + len(hop2_results),
    }
```

#### Entity extraction function

```python
_ENTITY_PROMPT = """\
Given this search query and retrieved text chunks, extract 3-5 key entities, \
concepts, or terms that would help find additional related information. \
Return ONLY a JSON array of strings, nothing else.

Query: {query}

Retrieved chunks:
{chunks_text}

Return format: ["entity1", "entity2", "entity3"]
"""


async def extract_entities(
    query: str,
    chunks: list[dict[str, Any]],
) -> list[str]:
    """Extract key entities from retrieved chunks via Gemini.

    Returns a list of 0-5 entity strings. Returns empty list on failure
    (LLM error, parse error, rate limit) so multi-hop degrades gracefully
    to single-hop.
    """
    chunks_text = "\n---\n".join(c["content"][:500] for c in chunks)
    prompt = _ENTITY_PROMPT.format(query=query, chunks_text=chunks_text)

    try:
        model = ModelManager(model_name=MULTIHOP_ENTITY_MODEL, provider="gemini")
        result = await model.generate_text(prompt)
        entities = json.loads(result.text)
        if isinstance(entities, list):
            return [str(e).strip() for e in entities[:MULTIHOP_MAX_ENTITIES] if e]
    except Exception:
        logger.warning("Entity extraction failed, falling back to single-hop", exc_info=True)

    return []
```

#### Merge and re-rank function

```python
def _merge_and_rerank(
    hop1: list[dict[str, Any]],
    hop2: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Merge hop 1 and hop 2 results with combined scoring.

    Scoring formula per chunk:
        combined_score = rrf_score
                       + hop_bonus        (hop 1 chunks get +0.0005 tiebreaker)
                       + diversity_bonus  (chunks from under-represented docs get +0.0002)

    With RRF_K=60, scores range ~0.013-0.033 (spread ~0.02).
    Adjacent ranks differ by ~0.0005-0.001. The hop bonus (+0.0005) can
    flip at most 1 rank position — verified: rank-5+bonus beats rank-4
    but loses to rank-3. This is a true tiebreaker.
    """
    # Tag hop numbers
    for r in hop1:
        r["hop"] = 1
    for r in hop2:
        r["hop"] = 2

    all_results = hop1 + hop2

    # Deduplicate by chunk_id (hop 1 wins ties)
    seen: dict[str, dict[str, Any]] = {}
    for r in all_results:
        if r["chunk_id"] not in seen:
            seen[r["chunk_id"]] = r
    deduped = list(seen.values())

    # Count documents per hop for diversity scoring
    doc_counts: dict[str, int] = {}
    for r in deduped:
        doc_counts[r["document_id"]] = doc_counts.get(r["document_id"], 0) + 1

    # Score — bonuses calibrated to flip at most 1 adjacent rank position
    for r in deduped:
        hop_bonus = 0.0005 if r["hop"] == 1 else 0.0
        diversity_bonus = 0.0002 if doc_counts[r["document_id"]] == 1 else 0.0
        r["combined_score"] = r["rrf_score"] + hop_bonus + diversity_bonus

    deduped.sort(key=lambda r: r["combined_score"], reverse=True)
    return deduped[:limit]
```

**Design decisions:**
- Hop 1 gets a tiebreaker bonus (+0.0005). With `RRF_K=60`, adjacent ranks differ by ~0.0005-0.001. Verified: rank-5 with bonus beats rank-4 but loses to rank-3, so this can flip at most 1 rank position.
- Diversity bonus (+0.0002) favors chunks from documents that only appear once, breaking ties when RRF scores are otherwise equal.
- Both bonuses are calibrated against measured RRF score ranges (~0.013-0.033 with `RRF_K=60`). At <4% of the minimum score, they act as tiebreakers, not ranking overrides.

---

### Step 3: Add config constants

**File:** `core/rag/config.py`

Add these constants after the existing ones:

```python
# Multi-hop search
MULTIHOP_HOP1_LIMIT = 5           # chunks retrieved in hop 1
MULTIHOP_HOP2_LIMIT = 5           # chunks retrieved in hop 2
MULTIHOP_TOP_K_FOR_EXTRACTION = 3  # top hop 1 chunks sent to LLM for entity extraction
MULTIHOP_MAX_ENTITIES = 5          # max entities extracted per query
MULTIHOP_ENTITY_MODEL = "gemini-2.5-flash-lite"  # fast/cheap model for extraction
```

**Why `gemini-2.5-flash-lite`:** Entity extraction is a simple structured-output task (JSON array of strings). It doesn't need the full flash model. Flash-lite is ~5x cheaper and ~2x faster, keeping multi-hop latency closer to 2s than 4s.

---

### Step 4: Add tool definition to RAG service

**File:** `services/rag_service.py`

Add a new `ToolDefinition` to the `create_rag_service()` function's tools list:

```python
ToolDefinition(
    name="search_documents_multihop",
    description=(
        "Search documents using multi-hop retrieval. "
        "Finds initial results, extracts key entities, then searches again "
        "with expanded terms. Better than single search for complex queries "
        "that span multiple topics or use varied terminology."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {
                "type": "integer",
                "default": 5,
                "description": "Max final results (1-20)",
            },
        },
        "required": ["query"],
    },
),
```

Add a handler branch in `_handler()`:

```python
if name == "search_documents_multihop":
    query = (args.get("query") or "").strip()
    if not query:
        raise ToolExecutionError(name, ValueError("Search query must not be blank"))
    limit = min(max(int(args.get("limit", 5)), 1), 20)
    from core.rag.multihop import multihop_search
    return await multihop_search(user_id, query, limit=limit)
```

**Why limit capped at 20 (not 50 like single search):** Multi-hop already fetches `HOP1_LIMIT + HOP2_LIMIT = 10` chunks internally. Requesting more than 20 final results would require increasing internal limits, multiplying cost.

---

### Step 5: Add HTTP endpoint

**File:** `routers/rag.py`

Add request model and endpoint:

```python
class MultihopSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


@router.post("/search/multihop")
async def search_multihop(
    request: MultihopSearchRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Multi-hop search: iterative retrieval with LLM query expansion."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query must not be blank")
    from core.rag.multihop import multihop_search
    return await multihop_search(user_id, query, limit=request.limit)
```

---

### Step 6: Unit tests

**File:** `tests/unit/test_multihop.py` (new)

Test categories:

| Test | What it verifies |
|---|---|
| `test_multihop_returns_hop_metadata` | Response includes `hops` list with query, expanded_terms, result_count per hop |
| `test_multihop_empty_hop1_returns_empty` | When hop 1 finds nothing, returns `[]` without attempting hop 2 |
| `test_multihop_entity_extraction_failure_falls_back` | When LLM fails, returns hop 1 results only (graceful degradation) |
| `test_multihop_excludes_hop1_chunks_from_hop2` | Hop 2 receives `exclude_chunk_ids` from hop 1 |
| `test_merge_rerank_deduplicates` | Same chunk_id from both hops appears once, hop 1 version kept |
| `test_merge_rerank_hop1_priority` | Equal-RRF chunks: hop 1 ranks higher |
| `test_merge_rerank_diversity_bonus` | Single-doc chunks get diversity bonus |
| `test_merge_rerank_respects_limit` | Returns at most `limit` results |
| `test_extract_entities_returns_list` | Valid JSON array parsed from LLM response |
| `test_extract_entities_truncates_to_max` | More than `MULTIHOP_MAX_ENTITIES` entities truncated |
| `test_extract_entities_handles_malformed_json` | Non-JSON LLM response returns `[]` |
| `test_hybrid_search_exclude_chunks` | SQL exclusion filter works (mock asyncpg) |
| `test_multihop_hop2_failure_returns_hop1` | When hop 2 DB/embed call raises, returns hop 1 results (graceful degradation) |

All tests mock `ModelManager.generate_text()` and `DocumentSearch.hybrid_search()` — no DB or LLM needed.

**Existing test update** (`tests/unit/test_rag.py`):

Update `TestRagService.test_registration`:
```python
# Before:
assert len(svc.tools) == 4
# After:
assert len(svc.tools) == 5
assert "search_documents_multihop" in tool_names
```

---

## Graceful Degradation

Multi-hop degrades to single-hop in these scenarios (no errors raised):

| Scenario | Behavior |
|---|---|
| Hop 1 returns 0 results | Return empty results immediately |
| Entity extraction LLM call fails | Return hop 1 results with `hop: 1` tags |
| Entity extraction returns empty list | Same — hop 1 results only |
| Hop 2 returns 0 new results | Return hop 1 results (hop 2 just found nothing new) |
| Gemini rate limit hit during extraction | `ModelManager._wait_for_rate_limit()` queues the call (~4.5s sleep). If the LLM call itself fails (network error, server error), the `try/except` in `extract_entities()` catches it and returns `[]` |

The `hops` metadata in the response always reveals what actually happened, so the caller (agent or frontend) knows whether multi-hop actually expanded the search.

---

## Latency Budget

| Step | Estimated time | Notes |
|---|---|---|
| Hop 1 embed | ~300ms | `embed_query()` via thread pool |
| Hop 1 search | ~200ms | Existing `hybrid_search` SQL |
| Entity extraction | ~800-1500ms | `gemini-2.5-flash-lite`, ~200 tokens in, ~50 out |
| Hop 2 embed | ~300ms | Same as hop 1 |
| Hop 2 search | ~200ms | Same SQL + exclusion filter |
| Merge/re-rank | <5ms | Pure Python, ~10 items |
| **Total** | **~1.8-2.5s** | vs ~500ms for single-hop |

The entity extraction step dominates. If latency is critical, a future optimization can replace the LLM call with TF-IDF term extraction (no API call, ~5ms) at the cost of lower entity quality.

---

## API Response Format

```json
{
  "results": [
    {
      "chunk_id": "abc123",
      "document_id": "doc456",
      "content": "The gradient descent optimizer...",
      "chunk_index": 3,
      "rrf_score": 0.028,
      "vector_score": 0.82,
      "text_score": 0.15,
      "hop": 1,
      "combined_score": 0.0287
    },
    {
      "chunk_id": "def789",
      "document_id": "doc012",
      "content": "Adam optimizer extends SGD with...",
      "chunk_index": 7,
      "rrf_score": 0.024,
      "vector_score": 0.78,
      "text_score": 0.11,
      "hop": 2,
      "combined_score": 0.0242
    }
  ],
  "hops": [
    {
      "hop": 1,
      "query": "how does the optimizer work",
      "result_count": 5
    },
    {
      "hop": 2,
      "query": "how does the optimizer work gradient descent Adam learning rate",
      "expanded_terms": ["gradient descent", "Adam", "learning rate"],
      "result_count": 4
    }
  ],
  "total_results": 9
}
```

---

## Implementation Order

1. **`core/rag/config.py`** — add constants (no dependencies)
2. **`core/stores/document_search.py`** — add `exclude_chunk_ids` parameter (used by step 3)
3. **`core/rag/multihop.py`** — create orchestrator (depends on steps 1-2)
4. **`services/rag_service.py`** — add tool definition + handler (depends on step 3)
5. **`routers/rag.py`** — add endpoint (depends on step 3)
6. **`tests/unit/test_multihop.py`** — new tests (depends on steps 1-5)
7. **`tests/unit/test_rag.py`** — update `test_registration` assertion: tool count `4→5`, add `search_documents_multihop` (depends on step 4)

Steps 4 and 5 are independent of each other (tool route vs HTTP route) and can be done in parallel. Steps 6 and 7 are also independent of each other.

---

## Future Enhancements (Out of Scope)

These are explicitly **not** part of this implementation but noted for future reference:

- **3+ hops:** Configurable hop count with diminishing-returns cutoff
- **TF-IDF fallback:** Replace LLM entity extraction with statistical term extraction when latency budget is tight
- **Caching extracted entities:** Store entities per chunk in `document_chunks.metadata` during ingestion, skip LLM at query time
- **Frontend integration:** Show hop attribution in the Chat page's search results (hop 1 vs hop 2 badge)
- **Agent auto-selection:** Let the agent choose between `search_documents` (fast) and `search_documents_multihop` (thorough) based on query complexity
