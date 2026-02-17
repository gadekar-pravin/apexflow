from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, NamedTuple

import yaml
from google.genai.errors import ClientError, ServerError

from core.gemini_client import get_gemini_client

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent


class GenerateResult(NamedTuple):
    """Result from a Gemini generation call with actual token counts."""

    text: str
    input_tokens: int
    output_tokens: int


MODELS_JSON = ROOT / "config" / "models.json"
PROFILE_YAML = ROOT / "config" / "profiles.yaml"


class ModelManager:
    _last_call: float = 0
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, model_name: str | None = None, provider: str | None = None) -> None:
        """
        Initialize ModelManager with flexible model specification.

        Args:
            model_name: The model to use. Can be:
                - A key from models.json (e.g., "gemini")
                - An actual model name (e.g., "gemini-2.5-flash-lite")
            provider: Optional explicit provider ("gemini").
                      If provided, bypasses models.json lookup.
        """
        self.config: dict[str, Any] = json.loads(MODELS_JSON.read_text())
        self.profile: dict[str, Any] = yaml.safe_load(PROFILE_YAML.read_text())

        # Support explicit provider specification (from settings)
        if provider:
            # Validate provider - only "gemini" is supported
            if provider.lower() != "gemini":
                logger.warning(
                    "Provider '%s' is not supported. Only 'gemini' is available. Falling back to Gemini.",
                    provider,
                )

            self.model_type = "gemini"
            self.text_model_key = model_name or "gemini-2.5-flash-lite"

            # Gemini: model_name is the actual Gemini model like "gemini-2.5-flash-lite"
            self.model_info: dict[str, Any] = {
                "type": "gemini",
                "model": self.text_model_key,
                "api_key_env": "GEMINI_API_KEY",
            }
            self.client = get_gemini_client()
        else:
            # Lookup in models.json by key
            if model_name:
                self.text_model_key = model_name
            else:
                self.text_model_key = self.profile["llm"]["text_generation"]

            # Validate that the model exists in config
            if self.text_model_key not in self.config["models"]:
                available_models = list(self.config["models"].keys())
                raise ValueError(
                    f"Model '{self.text_model_key}' not found in models.json. Available: {available_models}"
                )

            self.model_info = self.config["models"][self.text_model_key]
            self.model_type = self.model_info["type"]

            # Initialize Gemini client
            self.client = get_gemini_client()

    async def generate_text(self, prompt: str) -> GenerateResult:
        return await self._gemini_generate(prompt)

    async def generate_content(self, contents: list[Any]) -> GenerateResult:
        """Generate content with support for text and images.

        Contents can contain:
        - str: Text content
        - PIL.Image: Image to process
        """
        return await self._gemini_generate_content(contents)

    async def _wait_for_rate_limit(self) -> None:
        """Enforce ~15 RPM limit for Gemini (4s interval)"""
        async with ModelManager._lock:
            now = time.time()
            elapsed = now - ModelManager._last_call
            if elapsed < 4.5:  # 4.5s buffer for safety
                sleep_time = 4.5 - elapsed
                await asyncio.sleep(sleep_time)
            ModelManager._last_call = time.time()

    def _extract_usage(self, response: Any) -> tuple[int, int]:
        """Extract actual token counts from Gemini response usage_metadata."""
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return 0, 0
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        return input_tokens, output_tokens

    async def _call_with_retry(self, contents: Any, label: str = "generation") -> GenerateResult:
        """Call Gemini with retry logic for rate-limit (429) and transient server errors.

        Retries up to 3 times with escalating delays: 10s → 30s → 60s.
        """
        max_retries = 3
        retry_delays = [10, 30, 60]

        for attempt in range(max_retries + 1):
            await self._wait_for_rate_limit()
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=self.model_info["model"],
                    contents=contents,
                )
                result_text = (response.text or "").strip()
                input_tokens, output_tokens = self._extract_usage(response)
                return GenerateResult(text=result_text, input_tokens=input_tokens, output_tokens=output_tokens)

            except ClientError as e:
                if e.code == 429 and attempt < max_retries:
                    delay = retry_delays[attempt]
                    logger.warning(
                        "Gemini 429 rate limit hit, retrying in %ds (attempt %d/%d)",
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                if e.code == 429:
                    raise RuntimeError("Gemini API rate limit exceeded. Please try again in a few minutes.") from e
                raise RuntimeError(f"Gemini {label} failed: {e!s}") from e

            except ServerError as e:
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    logger.warning(
                        "Gemini server error (%s), retrying in %ds (attempt %d/%d)",
                        e,
                        delay,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            except Exception as e:
                raise RuntimeError(f"Gemini {label} failed: {e!s}") from e

        # Should not be reached, but satisfies type checker
        raise RuntimeError(f"Gemini {label} failed after {max_retries} retries")

    async def _gemini_generate(self, prompt: str) -> GenerateResult:
        return await self._call_with_retry(prompt, label="generation")

    async def _gemini_generate_content(self, contents: list[Any]) -> GenerateResult:
        """Generate content with support for text and images using Gemini SDK"""
        return await self._call_with_retry(contents, label="content generation")
