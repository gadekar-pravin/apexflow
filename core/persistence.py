"""Persistence manager -- v2 port, DB-backed via StateStore.

Replaces data/system/snapshot.json with state_store.get/set.
"""

from __future__ import annotations

import logging
from typing import Any

from core.event_bus import event_bus
from core.stores.state_store import StateStore
from shared.state import active_loops

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Handles saving and loading system state snapshots."""

    def __init__(self) -> None:
        self._state_store = StateStore()

    async def save_snapshot(self, user_id: str = "dev-user") -> None:
        """Capture current state to DB."""
        try:
            active_runs: list[dict[str, Any]] = []
            for run_id, loop in active_loops.items():
                status = "unknown"
                query = "unknown"
                if loop.context and loop.context.plan_graph:
                    status = loop.context.plan_graph.graph.get("status", "running")
                    query = loop.context.plan_graph.graph.get("original_query", "")
                active_runs.append({"run_id": run_id, "status": status, "query": query})

            snapshot: dict[str, Any] = {
                "active_runs": active_runs,
                "event_history_count": len(event_bus._history),
            }

            await self._state_store.set(user_id, "snapshot", snapshot)
            logger.info("System snapshot saved (%d runs)", len(active_runs))
        except Exception as e:
            logger.error("Failed to save snapshot: %s", e)

    async def load_snapshot(self, user_id: str = "dev-user") -> None:
        """Restore state on startup."""
        try:
            data = await self._state_store.get(user_id, "snapshot")
            if not data:
                return
            runs = data.get("active_runs", [])
            logger.info("Restoring snapshot: %d previous runs found", len(runs))
            for run in runs:
                if run.get("status") == "running":
                    logger.warning(
                        "Run %s was interrupted. Query: %s",
                        run["run_id"],
                        run.get("query"),
                    )
        except Exception as e:
            logger.error("Failed to load snapshot: %s", e)


persistence_manager = PersistenceManager()
