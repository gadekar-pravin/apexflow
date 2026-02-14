# ADR-001: Keep All ApexFlow Data in AlloyDB (No Neo4j)

**Status:** Accepted
**Date:** 2026-02-14
**Deciders:** Project maintainers
**Context:** Evaluation of `tmp/gcp-alloydb-deployment-guide.md` Neo4j migration proposal

## Context

A deployment guide for RAG-Anything/LightRAG on GCP (`tmp/gcp-alloydb-deployment-guide.md`) proposed migrating three categories of ApexFlow data to Neo4j AuraDB:

1. **Execution graph data** — `sessions.graph_data` + `sessions.node_outputs`
2. **REMME evidence/staging data** — `user_preferences.evidence_log`, `user_preferences.staging_queue`
3. **Memory provenance links** — session-to-memory-to-preference chains

The rationale was that graph-shaped data belongs in a graph database.

## Decision

**Do not add Neo4j for ApexFlow's core 13 tables.** All data remains in AlloyDB.

If LightRAG is integrated in the future, Neo4j AuraDB may be used **exclusively for LightRAG's knowledge graph** (entity-relationship extraction from documents). ApexFlow's tables stay in AlloyDB with clean separation of concerns.

## Evidence (Verified Against Codebase)

### Execution DAG: Blob Storage, Not Graph Queries

The database is purely a persistence layer for opaque JSONB blobs. All graph logic runs in-memory via NetworkX.

| Code Path | What It Does |
|---|---|
| `routers/runs.py:74` | `nx.node_link_data()` — serialize entire graph to JSONB |
| `routers/runs.py:182` | `nx.node_link_graph()` — deserialize JSONB back to NetworkX |
| `memory/context.py:129` | `self.plan_graph.predecessors(node_id)` — only traversal, 1-hop check |
| `memory/context.py:530` | `nx.node_link_data()` — session persistence |
| `core/graph_adapter.py` | `nx.topological_generations()` — layout only (visualization) |

**Zero JSONB graph queries exist in SQL** — no `@>`, `->`, `->>`, `jsonb_path_query`, or joins on graph fields. Estimated DAG size: 5-15 nodes, <30 edges (based on agent config step counts, not measured).

### REMME Evidence/Staging: Flat Arrays, Not Graphs

| Code Path | What It Does |
|---|---|
| `core/stores/preferences_store.py:105` | `COALESCE(col, '{}') || $2::jsonb` — atomic document merge |
| `remme/engine.py:86-96` | `evidence.add_event(...)` — simple append, no traversal |
| `remme/staging.py` | Queue loaded/saved in full, no partial queries |

Evidence entries are timestamped events, not a relationship graph. No code path ever traverses evidence relationships.

### Memory Provenance: Text Strings, Not Foreign Keys

| Code Path | What It Does |
|---|---|
| `remme/engine.py:70` | `source=f"session:{session_id}"` — opaque text string |
| `remme/store.py:34` | `source: str = "manual"` — default for manual memories |

No code path queries "which sessions produced this memory" or "which memories influenced this preference." Memory search uses vector cosine similarity (`MemoryStore.search()`), never relationship traversal.

## Costs Avoided

| Cost | Impact |
|---|---|
| Operational complexity | No second database to monitor, backup, scale |
| Dual-write consistency | No distributed transaction coordination needed |
| New query language | No Cypher alongside SQL |
| Deployment surface | No AuraDB network dependency, TLS management |
| Migration risk | No JSONB-to-graph data transformation |
| Migration tooling | No need for separate Neo4j schema management (Alembic only covers PostgreSQL) |
| Monthly cost | No AuraDB Professional (~$65/month minimum) |

## When to Revisit

Neo4j becomes worth reconsidering if ApexFlow adds features requiring **multi-hop relationship queries across entities**:

1. **Knowledge graph from RAG documents** — entities extracted from documents linked by relationships (this is what LightRAG does natively, and is the legitimate use case for Neo4j alongside ApexFlow)
2. **Workflow template matching** — "Show me all sessions that match this DAG pattern" (subgraph isomorphism)
3. **Cross-session analytics** — "Which agent-to-agent transitions correlate with failures?" (bipartite graph analysis)
4. **Recommendation engine** — "Users who ran this agent also ran..." (collaborative filtering)
5. **Provenance tracking with traversal** — "Trace back from this output through every tool call and memory that contributed to it"

## Alternative: Medium-Term Improvements in AlloyDB

If graph-like queries emerge without justifying a second database:

- Add a `memory_provenance` junction table (FK-based, not JSONB) for explicit session-to-memory links
- Use PostgreSQL recursive CTEs for multi-hop queries
- Add GIN indexes on JSONB fields if querying graph structure in SQL becomes necessary

## LightRAG Integration Guidance

If integrating LightRAG: run Neo4j AuraDB for **LightRAG's knowledge graph only**. Keep all 13 ApexFlow tables in AlloyDB. Two databases with clean separation:

- **AlloyDB** owns: sessions, jobs, job_runs, notifications, chat_sessions, chat_messages, system_state, documents, document_chunks, memories, user_preferences, security_logs, scanned_runs
- **Neo4j** owns: LightRAG entity nodes, relationship edges, community structures (if applicable)

No dual-write needed — LightRAG manages its own graph lifecycle independently from ApexFlow's transactional data.

## Verification Commands

```bash
# Confirm minimal graph algorithm usage
grep -r "predecessors\|successors\|neighbors\|shortest_path\|bfs\|dfs" --include="*.py" core/ agents/ memory/ remme/ routers/ tools/ services/

# Confirm no JSONB graph queries in stores
grep -r "@>\|jsonb_path\|->>" --include="*.py" core/stores/

# Confirm evidence is append-only
grep -rn "add_event" --include="*.py" remme/

# Confirm memory provenance is text-based
grep -rn "source=" --include="*.py" remme/
```
