"""RAG pipeline constants."""

from __future__ import annotations

from config.settings_loader import load_settings

_models = load_settings()["models"]

EMBEDDING_MODEL: str = _models.get("embedding", "text-embedding-004")
EMBEDDING_DIM: int = _models.get("embedding_dim", 768)
INGESTION_VERSION = 1
RRF_K = 60
SEARCH_EXPANSION_FACTOR = 3
