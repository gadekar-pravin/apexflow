"""Schema constraint tests -- verify CHECK, UNIQUE, FK, NOT NULL enforcement.

Uses raw SQL to test constraint enforcement at the database level.
Requires a real database. Tests are skipped when DB is unavailable.
"""

from __future__ import annotations

import uuid
from datetime import UTC

import asyncpg
import pytest


@pytest.mark.asyncio
class TestSchemaConstraints:
    """Verify that the AlloyDB schema enforces constraints correctly."""

    # -- CHECK constraints (status enums) ------------------------------------

    async def test_session_status_check_constraint(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Sessions reject invalid status values."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO sessions (id, user_id, query, status) VALUES ($1, $2, $3, $4)",
                    f"s-{uuid.uuid4()}",
                    test_user_id,
                    "test query",
                    "invalid",
                )

    async def test_chat_message_role_check_constraint(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Chat messages reject invalid role values."""
        async with db_pool.acquire() as conn:
            # Create a chat session first
            sid = f"cs-{uuid.uuid4()}"
            await conn.execute(
                "INSERT INTO chat_sessions (id, user_id, target_type, target_id) VALUES ($1, $2, $3, $4)",
                sid,
                test_user_id,
                "rag",
                "doc1",
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO chat_messages (id, session_id, user_id, role, content) VALUES ($1, $2, $3, $4, $5)",
                    f"m-{uuid.uuid4()}",
                    sid,
                    test_user_id,
                    "moderator",
                    "hello",
                )

    async def test_job_run_status_check_constraint(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Job runs reject invalid status values."""
        async with db_pool.acquire() as conn:
            # Create a parent job first
            jid = f"j-{uuid.uuid4()}"
            await conn.execute(
                "INSERT INTO jobs (id, user_id, name, cron_expression, query) VALUES ($1, $2, $3, $4, $5)",
                jid,
                test_user_id,
                "Test Job",
                "0 * * * *",
                "do something",
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO job_runs (job_id, user_id, scheduled_for, status) VALUES ($1, $2, NOW(), $3)",
                    jid,
                    test_user_id,
                    "pending",
                )

    # -- UNIQUE constraints --------------------------------------------------

    async def test_document_chunks_unique_doc_chunk_index(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Duplicate (document_id, chunk_index) is rejected."""
        import numpy as np

        embedding = np.random.default_rng(42).random(768).astype(np.float32).tolist()

        async with db_pool.acquire() as conn:
            doc_id = f"d-{uuid.uuid4()}"
            await conn.execute(
                "INSERT INTO documents (id, user_id, filename, file_hash) VALUES ($1, $2, $3, $4)",
                doc_id,
                test_user_id,
                "test.txt",
                f"hash-{uuid.uuid4()}",
            )
            await conn.execute(
                "INSERT INTO document_chunks (id, document_id, user_id, chunk_index, content, embedding) "
                "VALUES ($1, $2, $3, $4, $5, $6::vector)",
                f"c-{uuid.uuid4()}",
                doc_id,
                test_user_id,
                0,
                "chunk content",
                embedding,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO document_chunks (id, document_id, user_id, chunk_index, content, embedding) "
                    "VALUES ($1, $2, $3, $4, $5, $6::vector)",
                    f"c-{uuid.uuid4()}",
                    doc_id,
                    test_user_id,
                    0,
                    "duplicate chunk",
                    embedding,
                )

    async def test_documents_unique_user_file_hash(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Duplicate (user_id, file_hash) is rejected on plain INSERT."""
        file_hash = f"hash-{uuid.uuid4()}"
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO documents (id, user_id, filename, file_hash) VALUES ($1, $2, $3, $4)",
                f"d-{uuid.uuid4()}",
                test_user_id,
                "file1.txt",
                file_hash,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO documents (id, user_id, filename, file_hash) VALUES ($1, $2, $3, $4)",
                    f"d-{uuid.uuid4()}",
                    test_user_id,
                    "file2.txt",
                    file_hash,
                )

    async def test_job_runs_unique_job_scheduled(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Duplicate (job_id, scheduled_for) is rejected on plain INSERT."""
        from datetime import datetime

        async with db_pool.acquire() as conn:
            jid = f"j-{uuid.uuid4()}"
            await conn.execute(
                "INSERT INTO jobs (id, user_id, name, cron_expression, query) VALUES ($1, $2, $3, $4, $5)",
                jid,
                test_user_id,
                "Test Job",
                "0 * * * *",
                "do something",
            )
            sched_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
            await conn.execute(
                "INSERT INTO job_runs (job_id, user_id, scheduled_for) VALUES ($1, $2, $3)",
                jid,
                test_user_id,
                sched_time,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO job_runs (job_id, user_id, scheduled_for) VALUES ($1, $2, $3)",
                    jid,
                    test_user_id,
                    sched_time,
                )

    async def test_system_state_composite_pk(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Duplicate (user_id, key) is rejected on plain INSERT."""
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO system_state (user_id, key, value) VALUES ($1, $2, $3::jsonb)",
                test_user_id,
                "my_key",
                '{"a": 1}',
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    "INSERT INTO system_state (user_id, key, value) VALUES ($1, $2, $3::jsonb)",
                    test_user_id,
                    "my_key",
                    '{"b": 2}',
                )

    # -- FOREIGN KEY constraints ---------------------------------------------

    async def test_chat_messages_fk_requires_session(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Chat messages require an existing chat session."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    "INSERT INTO chat_messages (id, session_id, user_id, role, content) VALUES ($1, $2, $3, $4, $5)",
                    f"m-{uuid.uuid4()}",
                    "nonexistent-session",
                    test_user_id,
                    "user",
                    "hello",
                )

    async def test_job_runs_fk_requires_job(self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str) -> None:
        """Job runs require an existing job."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    "INSERT INTO job_runs (job_id, user_id, scheduled_for) VALUES ($1, $2, NOW())",
                    "nonexistent-job",
                    test_user_id,
                )

    async def test_document_chunks_fk_requires_document(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Document chunks require an existing document."""
        import numpy as np

        embedding = np.random.default_rng(42).random(768).astype(np.float32).tolist()
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    "INSERT INTO document_chunks (id, document_id, user_id, chunk_index, content, embedding) "
                    "VALUES ($1, $2, $3, $4, $5, $6::vector)",
                    f"c-{uuid.uuid4()}",
                    "nonexistent-doc",
                    test_user_id,
                    0,
                    "orphan chunk",
                    embedding,
                )

    # -- NOT NULL constraints ------------------------------------------------

    async def test_session_user_id_not_null(self, db_pool: asyncpg.Pool, clean_tables: None) -> None:
        """Sessions reject NULL user_id."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.NotNullViolationError):
                await conn.execute(
                    "INSERT INTO sessions (id, user_id, query) VALUES ($1, NULL, $2)",
                    f"s-{uuid.uuid4()}",
                    "test query",
                )

    async def test_notifications_source_not_null(
        self, db_pool: asyncpg.Pool, clean_tables: None, test_user_id: str
    ) -> None:
        """Notifications reject NULL source."""
        async with db_pool.acquire() as conn:
            with pytest.raises(asyncpg.NotNullViolationError):
                await conn.execute(
                    "INSERT INTO notifications (id, user_id, source, title, body) VALUES ($1, $2, NULL, $3, $4)",
                    f"n-{uuid.uuid4()}",
                    test_user_id,
                    "Test",
                    "body",
                )
