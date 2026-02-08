"""Metrics router -- thin wrapper around MetricsAggregator (now async)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from core.auth import get_user_id
from core.metrics_aggregator import get_aggregator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/dashboard")
async def get_dashboard_metrics(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Get aggregated dashboard metrics."""
    aggregator = get_aggregator()
    return await aggregator.get_dashboard_metrics(user_id)


@router.post("/refresh")
async def refresh_metrics(
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    """Force refresh of metrics cache."""
    aggregator = get_aggregator()
    return await aggregator.get_dashboard_metrics(user_id, force_refresh=True)
