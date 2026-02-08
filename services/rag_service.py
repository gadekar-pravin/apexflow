"""RAG service -- document indexing and hybrid search tools."""

from __future__ import annotations

import logging
from typing import Any

from core.rag.ingestion import embed_query, ingest_document
from core.service_registry import (
    ServiceDefinition,
    ToolDefinition,
    ToolExecutionError,
)
from core.stores.document_search import DocumentSearch
from core.stores.document_store import DocumentStore
from core.tool_context import ToolContext

logger = logging.getLogger(__name__)

_doc_store = DocumentStore()
_doc_search = DocumentSearch()


async def _handler(name: str, args: dict[str, Any], ctx: ToolContext | None) -> Any:
    if ctx is None:
        raise ToolExecutionError(name, ValueError("ToolContext is required for RAG tools (user_id must be known)"))
    user_id = ctx.user_id

    try:
        if name == "index_document":
            return await ingest_document(
                user_id,
                args["filename"],
                args["content"],
                doc_type=args.get("doc_type"),
                chunk_method=args.get("chunk_method", "rule_based"),
                metadata=args.get("metadata"),
            )

        if name == "search_documents":
            query_emb = await embed_query(args["query"])
            limit = min(max(int(args.get("limit", 5)), 1), 50)
            return await _doc_search.hybrid_search(
                user_id,
                args["query"],
                query_emb,
                limit=limit,
            )

        if name == "list_documents":
            return await _doc_store.list_documents(user_id)

        if name == "delete_document":
            deleted = await _doc_store.delete(user_id, args["doc_id"])
            return {"deleted": deleted, "doc_id": args["doc_id"]}

    except Exception as exc:
        raise ToolExecutionError(name, exc) from exc

    raise ToolExecutionError(name, ValueError(f"Unknown RAG tool: {name}"))


def create_rag_service() -> ServiceDefinition:
    """Build and return the RAG ServiceDefinition."""
    return ServiceDefinition(
        name="rag",
        tools=[
            ToolDefinition(
                name="index_document",
                description="Index a document for RAG retrieval.",
                parameters={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Document filename"},
                        "content": {"type": "string", "description": "Full document text"},
                        "doc_type": {"type": "string", "description": "Document type (optional)"},
                        "chunk_method": {
                            "type": "string",
                            "enum": ["rule_based", "semantic"],
                            "default": "rule_based",
                        },
                        "metadata": {"type": "object", "description": "Additional metadata (optional)"},
                    },
                    "required": ["filename", "content"],
                },
            ),
            ToolDefinition(
                name="search_documents",
                description="Search indexed documents using hybrid vector + full-text search.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "default": 5, "description": "Max results (1-50)"},
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="list_documents",
                description="List all indexed documents.",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name="delete_document",
                description="Delete an indexed document and its chunks.",
                parameters={
                    "type": "object",
                    "properties": {"doc_id": {"type": "string", "description": "Document ID"}},
                    "required": ["doc_id"],
                },
            ),
        ],
        handler=_handler,
    )
