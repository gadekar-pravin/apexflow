"""Tests for Phase 3 service modules."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.service_registry import ServiceRegistry, ToolExecutionError

# ---------------------------------------------------------------------------
# Browser service
# ---------------------------------------------------------------------------


class TestBrowserService:
    def test_registration(self) -> None:
        from services.browser_service import create_browser_service

        svc = create_browser_service()
        assert svc.name == "browser"
        assert len(svc.tools) == 2
        tool_names = {t.name for t in svc.tools}
        assert "web_search" in tool_names
        assert "web_extract_text" in tool_names

    def test_registers_with_service_registry(self) -> None:
        from services.browser_service import create_browser_service

        registry = ServiceRegistry()
        svc = create_browser_service()
        registry.register_service(svc)
        tools = registry.get_all_tools()
        names = {t["function"]["name"] for t in tools}
        assert "web_search" in names
        assert "web_extract_text" in names

    def test_ssrf_blocks_internal_ips(self) -> None:
        from services.browser_service import _validate_url_ssrf

        # Should block private IPs
        with (
            patch(
                "socket.getaddrinfo",
                return_value=[
                    (2, 1, 6, "", ("10.0.0.1", 0)),
                ],
            ),
            pytest.raises(ValueError, match="internal"),
        ):
            _validate_url_ssrf("http://evil.com")

        with (
            patch(
                "socket.getaddrinfo",
                return_value=[
                    (2, 1, 6, "", ("172.16.0.1", 0)),
                ],
            ),
            pytest.raises(ValueError, match="internal"),
        ):
            _validate_url_ssrf("http://evil.com")

        with (
            patch(
                "socket.getaddrinfo",
                return_value=[
                    (2, 1, 6, "", ("192.168.1.1", 0)),
                ],
            ),
            pytest.raises(ValueError, match="internal"),
        ):
            _validate_url_ssrf("http://evil.com")

        with (
            patch(
                "socket.getaddrinfo",
                return_value=[
                    (2, 1, 6, "", ("169.254.169.254", 0)),
                ],
            ),
            pytest.raises(ValueError, match="internal"),
        ):
            _validate_url_ssrf("http://metadata.google.internal")

        with (
            patch(
                "socket.getaddrinfo",
                return_value=[
                    (2, 1, 6, "", ("127.0.0.1", 0)),
                ],
            ),
            pytest.raises(ValueError, match="internal"),
        ):
            _validate_url_ssrf("http://localhost")

    def test_ssrf_allows_public_ips(self) -> None:
        from services.browser_service import _validate_url_ssrf

        with patch(
            "socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("142.250.80.46", 0)),
            ],
        ):
            # Should not raise
            _validate_url_ssrf("http://google.com")

    def test_ssrf_rejects_non_http(self) -> None:
        from services.browser_service import _validate_url_ssrf

        with pytest.raises(ValueError, match="http"):
            _validate_url_ssrf("ftp://example.com")


# ---------------------------------------------------------------------------
# RAG service stub
# ---------------------------------------------------------------------------


class TestRagService:
    def test_registration(self) -> None:
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.name == "rag"
        assert len(svc.tools) == 4
        tool_names = {t.name for t in svc.tools}
        assert "index_document" in tool_names
        assert "search_documents" in tool_names

    @pytest.mark.asyncio
    async def test_handler_wraps_errors(self) -> None:
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None
        # Missing required keys triggers KeyError -> ToolExecutionError
        with pytest.raises(ToolExecutionError):
            await svc.handler("index_document", {}, None)

    @pytest.mark.asyncio
    async def test_handler_unknown_tool_raises(self) -> None:
        from services.rag_service import create_rag_service

        svc = create_rag_service()
        assert svc.handler is not None
        with pytest.raises(ToolExecutionError):
            await svc.handler("nonexistent_tool", {}, None)

    @pytest.mark.asyncio
    async def test_routes_through_registry(self) -> None:
        from services.rag_service import create_rag_service

        registry = ServiceRegistry()
        registry.register_service(create_rag_service())
        # Missing args will cause ToolExecutionError
        with pytest.raises(ToolExecutionError):
            await registry.route_tool_call("search_documents", {})


# ---------------------------------------------------------------------------
# Sandbox service stub
# ---------------------------------------------------------------------------


class TestSandboxService:
    def test_registration(self) -> None:
        from services.sandbox_service import create_sandbox_service

        svc = create_sandbox_service()
        assert svc.name == "sandbox"
        assert len(svc.tools) == 1
        assert svc.tools[0].name == "run_code"

    @pytest.mark.asyncio
    async def test_handler_raises(self) -> None:
        from services.sandbox_service import create_sandbox_service

        svc = create_sandbox_service()
        assert svc.handler is not None
        with pytest.raises(ToolExecutionError):
            await svc.handler("run_code", {"code": "print(1)"}, None)
