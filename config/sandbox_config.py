"""Sandbox configuration: constants and tool allowlist."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.service_registry import ServiceRegistry, ToolDefinition

# --- Resource limits ---
DEFAULT_TIMEOUT_SECONDS: int = 30
MAX_STEPS: int = 100_000
MAX_OUTPUT_SIZE: int = 1_048_576  # 1 MB
MAX_MEMORY_MB: int = 256
MAX_EXTERNAL_RESPONSE_SIZE: int = 102_400  # 100 KB

# --- Tool allowlist (read-only tools only) ---
SANDBOX_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "web_search",
        "web_extract_text",
        "search_documents",
    }
)


def get_sandbox_tools(registry: ServiceRegistry) -> dict[str, ToolDefinition]:
    """Return only the tools allowed inside the sandbox."""
    return {name: tool_def for name, (_svc, tool_def) in registry._tool_index.items() if name in SANDBOX_ALLOWED_TOOLS}
