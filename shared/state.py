"""Shared State Module for ApexFlow v2.

Holds global state shared across all routers.
Replaces v1's MultiMCP with ServiceRegistry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Project root for path resolution in routers
PROJECT_ROOT: Path = Path(__file__).parent.parent

# === Lazy-loaded dependencies ===
# These will be initialized when first accessed or during api.py lifespan

# Global state - shared across routers
active_loops: dict[str, Any] = {}

# ServiceRegistry instance - will be created in api.py lifespan
_service_registry: Any | None = None


def get_service_registry() -> Any:
    """Get the ServiceRegistry singleton."""
    global _service_registry
    if _service_registry is None:
        from core.service_registry import ServiceRegistry

        _service_registry = ServiceRegistry()
    return _service_registry


def set_service_registry(registry: Any) -> None:
    """Set the ServiceRegistry singleton (called from api.py lifespan)."""
    global _service_registry
    _service_registry = registry


# RemMe store instance (Phase 3)
_remme_store: Any | None = None


def get_remme_store() -> Any | None:
    """Get the RemmeStore instance.

    Returns None with a log warning until Phase 3.
    """
    global _remme_store
    if _remme_store is None:
        logger.warning("RemmeStore not yet available (Phase 3)")
        return None
    return _remme_store


# RemMe extractor instance (Phase 3)
_remme_extractor: Any | None = None


def get_remme_extractor() -> Any | None:
    """Get the RemmeExtractor instance.

    Returns None with a log warning until Phase 3.
    """
    global _remme_extractor
    if _remme_extractor is None:
        logger.warning("RemmeExtractor not yet available (Phase 3)")
        return None
    return _remme_extractor


def set_remme_store(store: Any) -> None:
    """Set the RemmeStore singleton (called from api.py lifespan)."""
    global _remme_store
    _remme_store = store


def set_remme_extractor(extractor: Any) -> None:
    """Set the RemmeExtractor singleton (called from api.py lifespan)."""
    global _remme_extractor
    _remme_extractor = extractor


# Global settings state
settings: dict[str, Any] = {}
