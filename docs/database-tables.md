# Database Tables Reference

AlloyDB Omni 15.12.0 running on GCE VM (`alloydb-omni-dev`, `us-central1-a`). Schema defined in `scripts/init-db.sql` with 13 application tables in the `public` schema.

## Connecting to the Database

### Via SSH Tunnel (local tools like DataGrip)

1. Start the dev environment: `./scripts/dev-start.sh`
2. Connect with:
   - **Host:** `localhost`
   - **Port:** `5432`
   - **User:** `apexflow`
   - **Database:** `apexflow`
   - **Password:** retrieve via `gcloud secrets versions access latest --secret=apexflow-db-password --project=apexflow-ai`
3. Stop when done: `./scripts/dev-stop.sh`

**DataGrip note:** Ensure auto-commit is **ON** (click the "TX" button in the console toolbar). If auto-commit is off, DataGrip opens a transaction with a stale snapshot and you may see empty tables even when data exists.

### Via Cloud Run

Cloud Run connects via VPC connector to the VM's internal IP (`10.128.0.3:5432`). Connection config is set via `ALLOYDB_*` env vars and the `apexflow-db-password` secret.

## Tables

| Table | Populated When | Description |
|---|---|---|
| `sessions` | Agent runs are started via the frontend or API | Stores agent run metadata: status, plan graph, cost, timestamps. Core table for dashboard metrics. |
| `chat_messages` | Users send messages during a session's chat | Append-only message log. Inserting a message also updates `sessions.updated_at` atomically. |
| `jobs` | Cron jobs are created via `POST /api/cron` | Job definitions with schedule and configuration. |
| `job_runs` | Scheduler executes a job | Execution records with dedup via `INSERT ON CONFLICT DO NOTHING`. |
| `notifications` | Scheduler generates them on job completion or failure | Notifications with UUID, read/unread status, priority, and metadata. |
| `documents` | Documents are indexed via `POST /api/rag/index` | Document metadata with SHA256 content-hash dedup (`UNIQUE(user_id, file_hash)`). Tracks ingestion version for re-indexing. |
| `document_chunks` | Document ingestion pipeline chunks and embeds content | Chunked text with vector embeddings for hybrid search (cosine similarity + full-text). Cascading delete from `documents`. |
| `memories` | REMME adds them — manually via `POST /api/remme/memories` or automatically via `POST /api/remme/scan/smart` | Text + vector embedding + category. Supports cosine similarity search with `min_similarity` threshold. |
| `user_preferences` | REMME scan stages preferences, or profile is refreshed via `POST /api/remme/profile/refresh` | JSONB columns for five preference hubs: `preferences`, `operating_ctx`, `soft_identity`, `evidence_log`, `staging_queue`. Supports atomic merge via `COALESCE || jsonb` UPSERT. |
| `system_state` | Metrics aggregator caches dashboard stats, or persistence layer snapshots state | User-scoped key-value store with JSONB values. Composite PK `(user_id, key)` with UPSERT semantics. |
| `scanned_runs` | REMME scan marks sessions as processed | Tracks which sessions have been scanned to prevent re-processing. Written atomically with `sessions` in a transaction. |
| `security_logs` | Monty sandbox executes code | Security event log with JSONB `details` column for sandbox execution audit trail. |
| `alembic_version` | Alembic migrations are applied | Tracks the current migration revision. Not an application table — used by the migration framework. |

## RAG Hybrid Search Scaling

The RAG system uses **Reciprocal Rank Fusion (RRF)** combining two search methods on `document_chunks`:

1. **Vector search** — cosine similarity (`<=>` operator) on 768-dim embeddings (`text-embedding-004`)
2. **Full-text search** — `ts_rank` on a GIN-indexed `content_tsv` generated column

Results are fused via `1/(K + vector_rank) + 1/(K + text_rank)` (K=60), deduplicated per document, and ranked by combined RRF score. See `core/stores/document_search.py` for the full query.

### Infrastructure

| Factor | Value |
|---|---|
| VM | `n2-standard-2` — 2 vCPU, 8 GB RAM |
| Embedding dimensions | 768 (`text-embedding-004`) |
| Vector index | ScaNN on AlloyDB (must be created after first data insertion) |
| FTS index | GIN on `content_tsv` (auto-maintained generated column) |
| Query scoping | All queries filtered by `user_id` |

### Vector Index: ScaNN vs Brute-Force

ScaNN indexes cannot be created on empty tables in AlloyDB. Until the index is created, vector search does a **brute-force sequential scan**. After inserting initial data, create the indexes:

```bash
psql -h localhost -U apexflow -d apexflow -f scripts/create-scann-indexes.sql
```

This creates ScaNN indexes with `num_leaves = 100` on `document_chunks` and `num_leaves = 50` on `memories`.

### Latency Estimates (per user's data)

| Document chunks | Without ScaNN | With ScaNN |
|---|---|---|
| ~1K chunks (~50-100 docs) | < 50ms | < 50ms |
| ~10K chunks (~500-1K docs) | ~100-200ms | < 50ms |
| ~50K chunks (~2-5K docs) | ~500ms-1s | < 100ms |
| ~100K+ chunks | Multiple seconds | < 100ms |

With 16 GB RAM, the VM can hold ~5M 768-dim vectors in memory (~15 GB).

### Scaling Considerations

- **Full-text search scales well** — the GIN index handles millions of rows efficiently and won't be the bottleneck.
- **`num_leaves` tuning** — the current value of 100 is appropriate for up to ~100K chunks. For 1M+ chunks, increase to 500-1000.
- **No retention policy is active yet** — the schema includes suggested retention periods (see `scripts/init-db.sql`) but no cleanup job is implemented. Without cleanup, `document_chunks` grows unbounded.

## Internal AlloyDB Tables

AlloyDB Omni creates internal tables in the `google_ml` and `google_db_advisor` schemas (e.g., `g_columnar_whatif_relations`). These require the columnar engine module and will error if queried directly. They can be safely ignored.

## Quick Row Count Query

```sql
SELECT 'sessions' AS table_name, count(*) FROM sessions
UNION ALL SELECT 'chat_messages', count(*) FROM chat_messages
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'job_runs', count(*) FROM job_runs
UNION ALL SELECT 'notifications', count(*) FROM notifications
UNION ALL SELECT 'documents', count(*) FROM documents
UNION ALL SELECT 'document_chunks', count(*) FROM document_chunks
UNION ALL SELECT 'memories', count(*) FROM memories
UNION ALL SELECT 'user_preferences', count(*) FROM user_preferences
UNION ALL SELECT 'system_state', count(*) FROM system_state
UNION ALL SELECT 'scanned_runs', count(*) FROM scanned_runs
UNION ALL SELECT 'security_logs', count(*) FROM security_logs
ORDER BY 1;
```
