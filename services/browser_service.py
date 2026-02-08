"""Browser service -- registers web_search and web_extract_text tools."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

from core.service_registry import (
    ServiceDefinition,
    ToolDefinition,
    ToolExecutionError,
)
from core.tool_context import ToolContext

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 500_000

# Private/internal IP ranges to block (SSRF protection)
_BLOCKED_NETWORKS = [
    # IPv4
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    # IPv6
    ipaddress.ip_network("::1/128"),  # loopback
    ipaddress.ip_network("fc00::/7"),  # unique local (private)
    ipaddress.ip_network("fe80::/10"),  # link-local
]


def _validate_url_ssrf(url: str) -> None:
    """Block internal/metadata IPs via DNS resolution."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: no hostname")
    try:
        for _family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(sockaddr[0])
            for net in _BLOCKED_NETWORKS:
                if ip in net:
                    raise ValueError("URLs pointing to internal/private networks are not allowed")
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname: {hostname}") from exc


async def _handler(name: str, args: dict[str, Any], ctx: ToolContext | None) -> Any:
    """Route tool calls to the appropriate function."""
    if name == "web_search":
        return await _web_search(args, ctx)
    if name == "web_extract_text":
        return await _web_extract_text(args, ctx)
    raise ToolExecutionError(name, Exception(f"Unknown tool: {name}"))


async def _web_search(args: dict[str, Any], ctx: ToolContext | None) -> Any:
    from tools.switch_search_method import smart_search

    query = args.get("query", "")
    num_results = args.get("num_results", 5)
    if not query:
        raise ToolExecutionError("web_search", ValueError("query is required"))
    urls = await smart_search(query, limit=num_results)
    return {"query": query, "urls": urls, "count": len(urls)}


async def _web_extract_text(args: dict[str, Any], ctx: ToolContext | None) -> Any:
    from tools.web_tools_async import smart_web_extract

    url = args.get("url", "")
    if not url:
        raise ToolExecutionError("web_extract_text", ValueError("url is required"))
    _validate_url_ssrf(url)
    result = await smart_web_extract(url, ssrf_validator=_validate_url_ssrf)
    text = result.get("best_text", "")
    if len(text) > MAX_CONTENT_LENGTH:
        text = text[:MAX_CONTENT_LENGTH]
    return {
        "url": url,
        "title": result.get("title", ""),
        "text": text,
        "source": result.get("best_text_source", ""),
    }


def create_browser_service() -> ServiceDefinition:
    """Build and return the browser ServiceDefinition."""
    return ServiceDefinition(
        name="browser",
        tools=[
            ToolDefinition(
                name="web_search",
                description="Search the web and return a list of URLs.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "Max number of results",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="web_extract_text",
                description="Extract the main text content from a URL.",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to extract text from",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ],
        handler=_handler,
    )
