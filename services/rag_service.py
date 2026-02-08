"""RAG service stub -- placeholder tools for Phase 4a."""

from __future__ import annotations

import logging
from typing import Any

from core.service_registry import (
    ServiceDefinition,
    ToolDefinition,
    ToolExecutionError,
)
from core.tool_context import ToolContext

logger = logging.getLogger(__name__)


async def _handler(name: str, args: dict[str, Any], ctx: ToolContext | None) -> Any:
    raise ToolExecutionError(name, NotImplementedError("RAG service not yet implemented (Phase 4a)"))


def create_rag_service() -> ServiceDefinition:
    """Build and return the RAG stub ServiceDefinition."""
    return ServiceDefinition(
        name="rag",
        tools=[
            ToolDefinition(
                name="index_document",
                description="Index a document for RAG retrieval (Phase 4a stub).",
                parameters={
                    "type": "object",
                    "properties": {
                        "filepath": {"type": "string"},
                        "doc_type": {"type": "string"},
                    },
                    "required": ["filepath"],
                },
            ),
            ToolDefinition(
                name="search_documents",
                description="Search indexed documents (Phase 4a stub).",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="list_documents",
                description="List all indexed documents (Phase 4a stub).",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="delete_document",
                description="Delete an indexed document (Phase 4a stub).",
                parameters={
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                    "required": ["doc_id"],
                },
            ),
        ],
        handler=_handler,
    )
