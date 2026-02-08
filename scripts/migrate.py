#!/usr/bin/env python3
"""ApexFlow v1 → v2 data migration script.

Usage:
    python scripts/migrate.py --source-dir ../apexflow-v1 --db-url postgresql://...
    python scripts/migrate.py --source-dir ../apexflow-v1 --dry-run
    python scripts/migrate.py --source-dir ../apexflow-v1 --validate-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")

BATCH_SIZE = 100

# Valid v2 session statuses (matches CHECK constraint)
VALID_STATUSES = {"running", "completed", "failed", "cancelled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate ApexFlow v1 data to v2 database")
    parser.add_argument("--source-dir", required=True, help="Path to apexflow-v1 directory")
    parser.add_argument(
        "--db-url",
        default="postgresql://apexflow:apexflow@localhost:5432/apexflow",
        help="v2 database URL",
    )
    parser.add_argument("--user-id", default="default", help="User ID for all migrated data")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report without writing to DB")
    parser.add_argument("--validate-only", action="store_true", help="Count and validate existing v2 data")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Source parsers
# ---------------------------------------------------------------------------


def load_sessions(source_dir: Path) -> list[dict[str, Any]]:
    """Parse session summaries from v1 NetworkX graph JSON files."""
    sessions: list[dict[str, Any]] = []
    session_dir = source_dir / "memory" / "session_summaries_index"
    if not session_dir.exists():
        logger.warning("Session directory not found: %s", session_dir)
        return sessions

    for json_file in session_dir.rglob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            graph = data if isinstance(data, dict) else {}
            session_id = graph.get("session_id", json_file.stem)
            status = graph.get("status", "completed")
            if status not in VALID_STATUSES:
                logger.warning("Invalid status '%s' for session %s, mapping to 'completed'", status, session_id)
                status = "completed"
            sessions.append(
                {
                    "id": session_id,
                    "query": graph.get("original_query", ""),
                    "status": status,
                    "agent_type": graph.get("agent_type"),
                    "graph_data": json.dumps(graph),
                    "cost": float(graph.get("total_cost", 0)),
                    "model_used": graph.get("model_used"),
                    "created_at": graph.get("created_at"),
                }
            )
        except Exception as e:
            logger.error("Failed to parse session file %s: %s", json_file, e)

    logger.info("Parsed %d sessions from v1", len(sessions))
    return sessions


def load_jobs(source_dir: Path) -> list[dict[str, Any]]:
    """Parse jobs from v1 jobs.json."""
    jobs_file = source_dir / "data" / "system" / "jobs.json"
    if not jobs_file.exists():
        logger.warning("Jobs file not found: %s", jobs_file)
        return []

    try:
        data = json.loads(jobs_file.read_text())
        jobs = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        logger.info("Parsed %d jobs from v1", len(jobs))
        return jobs
    except Exception as e:
        logger.error("Failed to parse jobs: %s", e)
        return []


def load_notifications(source_dir: Path) -> list[dict[str, Any]]:
    """Parse notifications from v1 SQLite database."""
    db_path = source_dir / "data" / "inbox" / "notifications.db"
    if not db_path.exists():
        logger.warning("Notifications DB not found: %s", db_path)
        return []

    notifications = []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM notifications")
        for row in cursor:
            d = dict(row)
            notifications.append(
                {
                    "id": str(d.get("id", "")),
                    "source": d.get("source", "v1-migration"),
                    "title": d.get("title", ""),
                    "body": d.get("body", d.get("message", "")),
                    "priority": d.get("priority", 1),
                    "is_read": bool(d.get("is_read", False)),
                    "created_at": d.get("timestamp", d.get("created_at")),
                }
            )
        conn.close()
    except Exception as e:
        logger.error("Failed to parse notifications: %s", e)

    logger.info("Parsed %d notifications from v1", len(notifications))
    return notifications


def load_memories(source_dir: Path) -> list[dict[str, Any]]:
    """Parse memories from v1 memories.json (ignoring FAISS index.bin)."""
    mem_file = source_dir / "memory" / "remme_index" / "memories.json"
    if not mem_file.exists():
        logger.warning("Memories file not found: %s", mem_file)
        return []

    try:
        data = json.loads(mem_file.read_text())
        memories = data if isinstance(data, list) else list(data.values()) if isinstance(data, dict) else []
        logger.info("Parsed %d memories from v1 (will re-embed)", len(memories))
        return memories
    except Exception as e:
        logger.error("Failed to parse memories: %s", e)
        return []


def load_scanned_runs(source_dir: Path) -> list[str]:
    """Parse scanned run IDs from v1."""
    scan_file = source_dir / "memory" / "remme_index" / "scanned_runs.json"
    if not scan_file.exists():
        logger.warning("Scanned runs file not found: %s", scan_file)
        return []

    try:
        data = json.loads(scan_file.read_text())
        runs = data if isinstance(data, list) else []
        logger.info("Parsed %d scanned run IDs from v1", len(runs))
        return runs
    except Exception as e:
        logger.error("Failed to parse scanned runs: %s", e)
        return []


def load_preferences(source_dir: Path) -> dict[str, Any]:
    """Load staging queue and hub files from v1."""
    prefs: dict[str, Any] = {}

    staging_file = source_dir / "memory" / "remme_staging.json"
    if staging_file.exists():
        try:
            prefs["staging_queue"] = json.loads(staging_file.read_text())
        except Exception as e:
            logger.error("Failed to parse staging: %s", e)

    # Look for hub files
    hub_dir = source_dir / "memory" / "remme_index"
    for hub_name in ["preferences", "operating_context", "soft_identity"]:
        hub_file = hub_dir / f"{hub_name}.json"
        if hub_file.exists():
            try:
                prefs[hub_name] = json.loads(hub_file.read_text())
            except Exception as e:
                logger.error("Failed to parse hub %s: %s", hub_name, e)

    logger.info("Loaded preference hubs: %s", list(prefs.keys()))
    return prefs


# ---------------------------------------------------------------------------
# Migration writers
# ---------------------------------------------------------------------------


async def migrate_sessions(pool: Any, user_id: str, sessions: list[dict[str, Any]]) -> int:
    """Insert sessions into v2. Idempotent via ON CONFLICT DO NOTHING."""
    count = 0
    for i in range(0, len(sessions), BATCH_SIZE):
        batch = sessions[i : i + BATCH_SIZE]
        rows = []
        for s in batch:
            rows.append(
                (
                    s["id"],
                    user_id,
                    s.get("query", ""),
                    s.get("status", "completed"),
                    s.get("agent_type"),
                    s.get("graph_data", "{}"),
                    float(s.get("cost", 0)),
                    s.get("model_used"),
                )
            )
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO sessions (id, user_id, query, status, agent_type, graph_data, cost, model_used)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                rows,
            )
        count += len(batch)
    return count


async def migrate_jobs(pool: Any, user_id: str, jobs: list[dict[str, Any]]) -> int:
    """Insert jobs into v2."""
    count = 0
    for i in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[i : i + BATCH_SIZE]
        rows = []
        for j in batch:
            rows.append(
                (
                    j.get("id", j.get("job_id", "")),
                    user_id,
                    j.get("name", "unnamed"),
                    j.get("cron_expression", j.get("schedule", "0 * * * *")),
                    j.get("agent_type", "PlannerAgent"),
                    j.get("query", ""),
                    j.get("skill_id"),
                    j.get("enabled", True),
                    json.dumps(j.get("metadata", {})),
                )
            )
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO jobs (id, user_id, name, cron_expression, agent_type, query, skill_id, enabled, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                ON CONFLICT (id) DO NOTHING
                """,
                rows,
            )
        count += len(batch)
    return count


async def migrate_notifications(pool: Any, user_id: str, notifications: list[dict[str, Any]]) -> int:
    """Insert notifications into v2."""
    count = 0
    for i in range(0, len(notifications), BATCH_SIZE):
        batch = notifications[i : i + BATCH_SIZE]
        rows = []
        for n in batch:
            rows.append(
                (
                    n["id"],
                    user_id,
                    n.get("source", "v1-migration"),
                    n.get("title", ""),
                    n.get("body", ""),
                    n.get("priority", 1),
                    n.get("is_read", False),
                )
            )
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO notifications (id, user_id, source, title, body, priority, is_read)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO NOTHING
                """,
                rows,
            )
        count += len(batch)
    return count


async def migrate_memories(pool: Any, user_id: str, memories: list[dict[str, Any]]) -> int:
    """Insert memories into v2 with re-embedding via Gemini."""
    # Import here so script can be loaded without Gemini configured (for --dry-run)
    from remme.utils import get_embedding

    count = 0
    for i in range(0, len(memories), BATCH_SIZE):
        batch = memories[i : i + BATCH_SIZE]
        rows = []
        for m in batch:
            text = m.get("text", m.get("content", ""))
            if not text.strip():
                logger.warning("Skipping memory with empty text: %s", m.get("id", "?"))
                continue
            embedding = get_embedding(text, "RETRIEVAL_DOCUMENT")
            vec = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
            memory_id = m.get("id", str(uuid.uuid4()))
            rows.append(
                (
                    memory_id,
                    user_id,
                    text,
                    m.get("category", "general"),
                    m.get("source", "v1-migration"),
                    vec,
                    float(m.get("confidence", 1.0)),
                    "text-embedding-004",
                    json.dumps(m.get("metadata", {})),
                )
            )
        if rows:
            async with pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO memories
                        (id, user_id, text, category, source, embedding,
                         confidence, embedding_model, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, $9::jsonb)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    rows,
                )
        count += len(rows)
        # Throttle to avoid Gemini rate limits
        if i + BATCH_SIZE < len(memories):
            await asyncio.sleep(0.5)

    return count


async def migrate_scanned_runs(pool: Any, user_id: str, run_ids: list[str]) -> int:
    """Insert scanned run IDs into v2."""
    count = 0
    for i in range(0, len(run_ids), BATCH_SIZE):
        batch = run_ids[i : i + BATCH_SIZE]
        rows = [(rid, user_id) for rid in batch]
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO scanned_runs (run_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT (run_id) DO NOTHING
                """,
                rows,
            )
        count += len(batch)
    return count


async def migrate_preferences(pool: Any, user_id: str, prefs: dict[str, Any]) -> int:
    """Merge v1 preferences into v2 user_preferences table."""
    if not prefs:
        return 0

    # Column mapping from v1 hub names
    hub_column_map = {
        "preferences": "preferences",
        "operating_context": "operating_ctx",
        "soft_identity": "soft_identity",
        "staging_queue": "staging_queue",
    }

    async with pool.acquire() as conn:
        # Ensure row exists
        await conn.execute(
            "INSERT INTO user_preferences (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user_id,
        )
        for hub_name, data in prefs.items():
            col = hub_column_map.get(hub_name)
            if col and data:
                await conn.execute(
                    f"UPDATE user_preferences SET {col} = COALESCE({col}, '{{}}'::jsonb) || $2::jsonb, "  # noqa: S608
                    "updated_at = NOW() WHERE user_id = $1",
                    user_id,
                    json.dumps(data),
                )

    return len(prefs)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def validate(pool: Any, user_id: str, source_counts: dict[str, int]) -> None:
    """Compare v2 row counts against source counts and check data integrity."""
    tables = {
        "sessions": "SELECT COUNT(*) FROM sessions WHERE user_id = $1",
        "jobs": "SELECT COUNT(*) FROM jobs WHERE user_id = $1",
        "notifications": "SELECT COUNT(*) FROM notifications WHERE user_id = $1",
        "memories": "SELECT COUNT(*) FROM memories WHERE user_id = $1",
        "scanned_runs": "SELECT COUNT(*) FROM scanned_runs WHERE user_id = $1",
    }

    logger.info("--- Validation Report ---")
    async with pool.acquire() as conn:
        for table, query in tables.items():
            v2_count = await conn.fetchval(query, user_id)
            v1_count = source_counts.get(table)
            match = "UNKNOWN" if v1_count is None else "OK" if v2_count == v1_count else "MISMATCH"
            logger.info(
                "  %-20s v1=%s  v2=%s  [%s]",
                table,
                v1_count if v1_count is not None else "?",
                v2_count,
                match,
            )

        # Check embedding dimension consistency
        dim_check = await conn.fetchval(
            "SELECT COUNT(DISTINCT array_length(embedding::real[], 1)) FROM memories WHERE user_id = $1",
            user_id,
        )
        logger.info("  Embedding dimensions: %s unique (should be 1)", dim_check)

        # Sample sessions
        samples = await conn.fetch(
            "SELECT id, query, status FROM sessions WHERE user_id = $1 ORDER BY RANDOM() LIMIT 10",
            user_id,
        )
        if samples:
            logger.info("  Sample sessions:")
            for s in samples:
                logger.info("    %s | %s | %s", s["id"], s["status"], s["query"][:60])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)

    if not source_dir.exists():
        logger.error("Source directory does not exist: %s", source_dir)
        sys.exit(1)

    # Parse all sources
    sessions = load_sessions(source_dir)
    jobs = load_jobs(source_dir)
    notifications = load_notifications(source_dir)
    memories = load_memories(source_dir)
    scanned_runs = load_scanned_runs(source_dir)
    preferences = load_preferences(source_dir)

    logger.info("No chat data to migrate (v1 has no separate chat storage)")

    source_counts = {
        "sessions": len(sessions),
        "jobs": len(jobs),
        "notifications": len(notifications),
        "memories": len(memories),
        "scanned_runs": len(scanned_runs),
    }
    logger.info("Source counts: %s", source_counts)

    if args.dry_run:
        logger.info("DRY RUN — no data written to database")
        return

    # Connect to v2 database
    import asyncpg

    pool = await asyncpg.create_pool(args.db_url, min_size=1, max_size=5)

    # Register pgvector codec
    try:
        from pgvector.asyncpg import register_vector

        async with pool.acquire() as conn:
            await register_vector(conn)
    except Exception:
        pass

    try:
        if args.validate_only:
            await validate(pool, args.user_id, source_counts)
            return

        # Run migrations
        logger.info("Starting migration to %s (user_id=%s)...", args.db_url.split("@")[-1], args.user_id)

        n = await migrate_sessions(pool, args.user_id, sessions)
        logger.info("Migrated %d sessions", n)

        n = await migrate_jobs(pool, args.user_id, jobs)
        logger.info("Migrated %d jobs", n)

        n = await migrate_notifications(pool, args.user_id, notifications)
        logger.info("Migrated %d notifications", n)

        n = await migrate_memories(pool, args.user_id, memories)
        logger.info("Migrated %d memories (re-embedded)", n)

        n = await migrate_scanned_runs(pool, args.user_id, scanned_runs)
        logger.info("Migrated %d scanned runs", n)

        n = await migrate_preferences(pool, args.user_id, preferences)
        logger.info("Migrated %d preference hubs", n)

        # Validate
        await validate(pool, args.user_id, source_counts)
        logger.info("Migration complete.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
