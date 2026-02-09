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
