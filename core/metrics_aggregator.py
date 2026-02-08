"""Metrics aggregator -- v2 port, DB-backed via SessionStore + StateStore.

Replaces filesystem session walk with SQL aggregation.
Uses state_store for 5-minute cache instead of cache file.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from core.stores.session_store import SessionStore
from core.stores.state_store import StateStore

logger = logging.getLogger(__name__)


class MetricsAggregator:
    """Aggregate session data into fleet-level telemetry metrics."""

    def __init__(self) -> None:
        self._session_store = SessionStore()
        self._state_store = StateStore()
        self._cache_ttl = 300  # 5 minutes

    async def get_dashboard_metrics(
        self,
        user_id: str,
        *,
        force_refresh: bool = False,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get comprehensive fleet telemetry (cached for 5 min)."""
        cache_key = f"metrics_cache_{days}"

        # Check cache
        if not force_refresh:
            cached = await self._state_store.get(user_id, cache_key)
            if cached:
                last_updated = cached.get("last_updated", "")
                if last_updated:
                    try:
                        updated_dt = datetime.fromisoformat(last_updated)
                        if updated_dt.tzinfo is None:
                            updated_dt = updated_dt.replace(tzinfo=UTC)
                        if (datetime.now(UTC) - updated_dt).total_seconds() < self._cache_ttl:
                            return cached
                    except (ValueError, TypeError):
                        pass

        # Regenerate: use SQL aggregation
        dashboard = await self._session_store.get_dashboard_stats(user_id, days)
        daily = await self._session_store.get_daily_stats(user_id, days)

        total_runs = dashboard.get("total_runs", 0)
        completed = dashboard.get("completed", 0)
        failed = dashboard.get("failed", 0)

        success_rate = round(completed / max(completed + failed, 1) * 100, 1)

        metrics: dict[str, Any] = {
            "last_updated": datetime.now(UTC).isoformat(),
            "totals": {
                "total_runs": total_runs,
                "total_cost": dashboard.get("total_cost", 0),
                "avg_cost": dashboard.get("avg_cost", 0),
                "outcomes": {
                    "success": completed,
                    "failed": failed,
                    "cancelled": dashboard.get("cancelled", 0),
                    "running": dashboard.get("running", 0),
                },
                "success_rate": success_rate,
            },
            "temporal": {
                "daily": [
                    {
                        "date": str(d.get("date", "")),
                        "runs": d.get("runs", 0),
                        "cost": d.get("cost", 0),
                        "completed": d.get("completed", 0),
                        "failed": d.get("failed", 0),
                        "success_rate": round(
                            d.get("completed", 0) / max(d.get("completed", 0) + d.get("failed", 0), 1) * 100,
                            1,
                        ),
                    }
                    for d in daily
                ],
                "total_days": len(daily),
            },
            # Legacy compatibility
            "by_day": [
                {
                    "date": str(d.get("date", "")),
                    "runs": d.get("runs", 0),
                    "cost": d.get("cost", 0),
                }
                for d in daily
            ],
        }

        # Generate insights
        metrics["insights"] = self._generate_insights(metrics)

        # Save to cache
        await self._state_store.set(user_id, cache_key, metrics)
        return metrics

    def _generate_insights(self, metrics: dict[str, Any]) -> list[str]:
        """Generate human-readable insight sentences."""
        insights: list[str] = []
        totals = metrics.get("totals", {})

        success_rate = totals.get("success_rate", 100)
        if success_rate < 90:
            insights.append(f"Overall success rate is {success_rate}% - consider investigating failures.")

        total_cost = totals.get("total_cost", 0)
        if total_cost > 0:
            avg = totals.get("avg_cost", 0)
            runs = totals.get("total_runs", 0)
            insights.append(f"Total cost: ${total_cost:.4f} across {runs} runs (avg ${avg:.4f}).")

        failed = totals.get("outcomes", {}).get("failed", 0)
        if failed > 0:
            insights.append(f"{failed} run(s) failed in the last period.")

        return insights if insights else ["Fleet is running healthy with no major issues detected."]


_aggregator: MetricsAggregator | None = None


def get_aggregator() -> MetricsAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = MetricsAggregator()
    return _aggregator
