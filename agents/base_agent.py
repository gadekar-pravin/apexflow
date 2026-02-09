"""AgentRunner – v2 with ServiceRegistry (replaces MultiMCP).

Changes from v1:
- self.multi_mcp → self.service_registry
- Removed debug_log file writes
- PIL.Image import is conditional (try/except)
- Tool description builder adapted for ServiceRegistry format
- config['mcp_servers'] → config.get('services') with backward compat
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.json_parser import parse_llm_json
from core.model_manager import ModelManager
from core.service_registry import ServiceRegistry
from core.utils import log_error, log_step

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)

# Gemini pricing per million tokens: (input_cost, output_cost)
_GEMINI_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash-lite": (0.075, 0.30),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}
_DEFAULT_PRICING = (0.075, 0.30)


class AgentRunner:
    def __init__(self, service_registry: ServiceRegistry) -> None:
        self.service_registry = service_registry
        self._root = Path(__file__).parent.parent

        # Load agent configurations
        config_path = self._root / "config" / "agent_config.yaml"
        with open(config_path) as f:
            self.agent_configs: dict[str, Any] = yaml.safe_load(f)["agents"]

    def calculate_cost(self, input_tokens: int, output_tokens: int, model_name: str = "") -> dict[str, float | int]:
        """Calculate cost from actual token counts and model-specific pricing."""
        input_rate, output_rate = _GEMINI_PRICING.get(model_name, _DEFAULT_PRICING)

        input_cost = (input_tokens / 1_000_000) * input_rate
        output_cost = (output_tokens / 1_000_000) * output_rate

        return {
            "cost": input_cost + output_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    async def run_agent(
        self, agent_type: str, input_data: dict[str, Any], image_path: str | None = None
    ) -> dict[str, Any]:
        """Run a specific agent with input data and optional image."""
        if agent_type not in self.agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")

        config: dict[str, Any] = self.agent_configs[agent_type]

        try:
            # 1. Load prompt template
            prompt_template = (self._root / config["prompt_file"]).read_text(encoding="utf-8")

            # 2. Get tools from specified services (backward compat: services or mcp_servers)
            tools_text = ""
            services: list[str] = config.get("services") or config.get("mcp_servers", [])
            if services:
                tools: list[dict[str, Any]] = self.service_registry.get_tools_from_servers(services)
                if tools:
                    tool_descriptions: list[str] = []
                    for tool_entry in tools:
                        # ServiceRegistry returns {"type": "function", "function": {...}}
                        func_def: dict[str, Any] = tool_entry.get("function", {})
                        name: str = func_def.get("name", "unknown")
                        description: str = func_def.get("description", "")
                        params: dict[str, Any] = func_def.get("parameters", {})

                        props: dict[str, Any] = params.get("properties", {})
                        arg_types: list[str] = []
                        for param_name, v in props.items():
                            t: str = v.get("type", "any")
                            arg_types.append(f"{param_name}: {t}")

                        signature_str = ", ".join(arg_types)
                        tool_descriptions.append(f"- `{name}({signature_str})` # {description}")

                    tools_text = "\n\n### Available Tools\n\n" + "\n".join(tool_descriptions)

            # 3. Build full prompt
            current_date = datetime.now().strftime("%Y-%m-%d")

            # 3a. Inject user preferences (compact format)
            try:
                from remme.preferences import get_compact_policy

                scope_map: dict[str, str] = {
                    "PlannerAgent": "planning",
                    "CoderAgent": "coding",
                    "DistillerAgent": "coding",
                    "FormatterAgent": "formatting",
                    "RetrieverAgent": "research",
                    "ThinkerAgent": "reasoning",
                }
                scope = scope_map.get(agent_type, "general")
                user_prefs_text = f"\n---\n## User Preferences\n{get_compact_policy(scope)}\n---\n"
            except Exception as e:
                logger.debug("Could not load user preferences: %s", e)
                user_prefs_text = ""

            full_prompt = (
                f"CURRENT_DATE: {current_date}\n\n"
                f"{prompt_template.strip()}{user_prefs_text}{tools_text}\n\n"
                f"```json\n{json.dumps(input_data, indent=2)}\n```"
            )

            logger.debug("Generated tools text for %s: %s", agent_type, tools_text)
            log_step(
                f"{agent_type} invoked",
                payload={"prompt_file": config["prompt_file"], "input_keys": list(input_data.keys())},
            )

            # 4. Create model manager with user's selected model from settings
            from config.settings_loader import reload_settings

            fresh_settings = reload_settings()
            agent_settings: dict[str, Any] = fresh_settings.get("agent", {})

            # Check for per-agent overrides
            overrides: dict[str, Any] = agent_settings.get("overrides", {})
            if agent_type in overrides:
                override: dict[str, Any] = overrides[agent_type]
                model_provider: str = override.get("model_provider", "gemini")
                model_name: str = override.get("model", "gemini-2.5-flash")
                log_step(f"Override for {agent_type}: {model_provider}:{model_name}")
            else:
                model_provider = agent_settings.get("model_provider", "gemini")
                model_name = agent_settings.get("default_model", "gemini-2.5-flash")

            log_step(f"Using {model_provider}:{model_name}")
            model_manager = ModelManager(model_name, provider=model_provider)

            # 5. Generate response (with or without image)
            if image_path and os.path.exists(image_path) and Image is not None:
                log_step(f"{agent_type} (with image)")
                with Image.open(image_path) as image:
                    result = await model_manager.generate_content([full_prompt, image])
            else:
                result = await model_manager.generate_text(full_prompt)

            # 6. Parse JSON response dynamically
            output: Any = parse_llm_json(result.text)

            # Robustness: Some models wrap JSON in a list
            if isinstance(output, list) and len(output) > 0 and isinstance(output[0], dict):
                output = output[0]

            log_step(
                f"{agent_type} finished",
                payload={"output_keys": list(output.keys()) if isinstance(output, dict) else "raw_string"},
            )

            # Calculate cost from actual Gemini API token counts
            cost_data = self.calculate_cost(result.input_tokens, result.output_tokens, model_name)

            if isinstance(output, dict):
                output.update(cost_data)
                output["executed_model"] = f"{model_provider}:{model_name}"

            return {"success": True, "agent_type": agent_type, "output": output}

        except Exception as e:
            log_error(f"{agent_type}: {e!s}")
            return {
                "success": False,
                "agent_type": agent_type,
                "error": str(e),
                "cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }

    def get_available_agents(self) -> list[str]:
        """Return list of available agent types."""
        return list(self.agent_configs.keys())
