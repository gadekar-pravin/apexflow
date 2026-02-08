"""
Centralized Gemini client factory with automatic credential detection.

Supports:
- Vertex AI with Application Default Credentials (ADC) on Cloud Run/GCP
- API Key authentication for local development

Environment variables for GCP/Vertex AI:
- GOOGLE_CLOUD_PROJECT: GCP project ID (default: apexflow-ai)
- GOOGLE_CLOUD_LOCATION: GCP region (default: us-central1)
"""

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from google import genai

load_dotenv()

# Vertex AI configuration with defaults
VERTEX_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "apexflow-ai")
VERTEX_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")


def is_gcp_environment() -> bool:
    """Detect if running on GCP (Cloud Run, GCE, etc.)"""
    return bool(
        os.getenv("K_SERVICE")  # Cloud Run
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # Explicit ADC file
    )


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Get cached Gemini client with automatic credential detection.

    On GCP (Cloud Run, GCE, etc.): Uses Vertex AI with ADC
    Locally: Uses GEMINI_API_KEY environment variable

    Returns:
        genai.Client: Configured Gemini client

    Raises:
        ValueError: If running locally without GEMINI_API_KEY set
    """
    if is_gcp_environment():
        # Vertex AI with ADC - requires project and location
        return genai.Client(vertexai=True, project=VERTEX_PROJECT, location=VERTEX_LOCATION)
    else:
        # Local development: Use API key
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set. Set it for local development or run on GCP for ADC.")
        return genai.Client(api_key=api_key)


def get_langchain_llm(model: str = "gemini-2.5-flash-lite") -> Any:
    """Get LangChain LLM instance with auto credential detection.

    Args:
        model: The Gemini model name to use

    Returns:
        ChatVertexAI or ChatGoogleGenerativeAI: Configured LangChain LLM

    Raises:
        ValueError: If running locally without GEMINI_API_KEY set
    """
    if is_gcp_environment():
        # Vertex AI with ADC
        from langchain_google_vertexai import ChatVertexAI

        return ChatVertexAI(model=model, project=VERTEX_PROJECT, location=VERTEX_LOCATION)
    else:
        # Local development: Use API key with Gemini Developer API
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set for local development")
        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key)
