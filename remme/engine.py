"""RemmeEngine -- orchestrates the scan cycle: load hubs → process sessions → commit."""

from __future__ import annotations

import logging
from typing import Any

from remme.engines.evidence_log import EvidenceLog
from remme.extractor import RemmeExtractor
from remme.staging import StagingQueue
from remme.store import RemmeStore

logger = logging.getLogger(__name__)


class RemmeEngine:
    """Orchestrates REMME scan cycles.

    1. Get unscanned sessions
    2. Load staging queue + evidence log
    3. For each session: extract memories + preferences, store, stage, log evidence
    4. Mark each session scanned
    5. Commit staging + evidence log
    """

    def __init__(self, store: RemmeStore, extractor: RemmeExtractor | None = None) -> None:
        self.store = store
        self.extractor = extractor or RemmeExtractor()

    async def run_scan(self, user_id: str) -> dict[str, Any]:
        """Run a full scan cycle and return a summary."""
        sessions = await self.store.list_unscanned(user_id)
        if not sessions:
            return {"scanned": 0, "memories_added": 0, "preferences_staged": 0}

        staging = StagingQueue()
        evidence = EvidenceLog()
        await staging.load(user_id)
        await evidence.load(user_id)

        scanned = 0
        memories_added = 0
        preferences_staged = 0

        for session in sessions:
            session_id = session["id"]
            try:
                # Build conversation history from session data
                history = self._build_history(session)
                query = session.get("query", "")

                # Mark scanned early so a failure during processing won't
                # cause duplicate memories on the next scan cycle.
                await self.store.mark_scanned(user_id, session_id)

                # Refresh after each session so earlier inserts are visible
                existing_memories = await self.store.list_all(user_id)

                # Extract memories and preferences
                memory_commands, preferences = await self.extractor.extract(query, history, existing_memories)

                # Process memory commands
                for cmd in memory_commands:
                    action = cmd.get("action", "add")
                    text = cmd.get("text", "")
                    if not text:
                        continue

                    if action == "add":
                        await self.store.add(
                            user_id,
                            text,
                            category=cmd.get("category", "general"),
                            source=f"session:{session_id}",
                        )
                        memories_added += 1
                    elif action == "update" and cmd.get("id"):
                        await self.store.update_text(user_id, cmd["id"], text)

                # Stage preferences
                if preferences:
                    staging.add(
                        {
                            "session_id": session_id,
                            "preferences": preferences,
                        }
                    )
                    preferences_staged += len(preferences)

                # Log evidence
                evidence.add_event(
                    source_type="session_scan",
                    raw_excerpt=query[:200] if query else "",
                    session_id=session_id,
                    category="auto_scan",
                    metadata={
                        "memories_extracted": len(memory_commands),
                        "preferences_extracted": len(preferences),
                    },
                )

                scanned += 1

            except Exception:
                logger.exception("Failed to process session %s", session_id)

        # Commit staging queue and evidence log
        await staging.save(user_id)
        await evidence.save(user_id)

        return {
            "scanned": scanned,
            "memories_added": memories_added,
            "preferences_staged": preferences_staged,
        }

    @staticmethod
    def _build_history(session: dict[str, Any]) -> list[dict[str, Any]]:
        """Build a conversation history list from session data."""
        history: list[dict[str, Any]] = []
        node_outputs = session.get("node_outputs") or {}
        if isinstance(node_outputs, dict):
            for _node, output in node_outputs.items():
                if isinstance(output, dict) and output.get("response"):
                    history.append({"role": "assistant", "content": str(output["response"])})
        query = session.get("query", "")
        if query:
            history.insert(0, {"role": "user", "content": query})
        return history
