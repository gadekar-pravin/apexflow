from __future__ import annotations

import logging
from typing import Any

import numpy as np
from dotenv import load_dotenv
from google import genai

load_dotenv()

from config.settings_loader import get_model  # noqa: E402
from core.gemini_client import get_gemini_client  # noqa: E402

logger = logging.getLogger(__name__)

EMBED_MODEL = get_model("embedding")

# Initialize Gemini client (cached singleton via factory)
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = get_gemini_client()
    return _client


# Map legacy Nomic/Ollama task types to Gemini task types
TASK_TYPE_MAP = {
    # Legacy Nomic prefixes
    "search_document": "RETRIEVAL_DOCUMENT",
    "search_query": "RETRIEVAL_QUERY",
    # Already correct Gemini values (pass through)
    "RETRIEVAL_DOCUMENT": "RETRIEVAL_DOCUMENT",
    "RETRIEVAL_QUERY": "RETRIEVAL_QUERY",
    "SEMANTIC_SIMILARITY": "SEMANTIC_SIMILARITY",
    "CLASSIFICATION": "CLASSIFICATION",
    "CLUSTERING": "CLUSTERING",
}


def get_embedding(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> Any:
    """Generate embedding for text using Gemini text-embedding-004.

    Args:
        text: The text to embed
        task_type: Task type for the embedding. Accepts both legacy Nomic values
                   (search_document, search_query) and Gemini values:
                   - RETRIEVAL_DOCUMENT: for documents being indexed
                   - RETRIEVAL_QUERY: for search queries
                   - SEMANTIC_SIMILARITY, CLASSIFICATION, CLUSTERING
    """
    # Map legacy task types to Gemini task types
    gemini_task_type = TASK_TYPE_MAP.get(task_type)
    if gemini_task_type is None:
        logger.warning("Unknown task_type '%s', defaulting to RETRIEVAL_DOCUMENT", task_type)
        gemini_task_type = "RETRIEVAL_DOCUMENT"

    try:
        client = _get_client()

        # Gemini uses task_type parameter instead of text prefixes
        response = client.models.embed_content(model=EMBED_MODEL, contents=text, config={"task_type": gemini_task_type})

        # Extract embedding from response
        assert response.embeddings is not None, "Embedding response was empty"
        embedding = response.embeddings[0].values
        vec = np.array(embedding, dtype=np.float32)

        # L2 Normalization (ensures distances are in [0, 4] range for IndexFlatL2)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec
    except Exception as e:
        # Prominent warning about zero vector fallback - this can degrade search quality
        logger.warning("EMBEDDING FAILED: %s — returning zero vector", e)
        return np.zeros(768, dtype=np.float32)
