"""
Centralized Settings Loader

This module provides a single point of access for all runtime configuration.
All backend modules should import settings from here instead of defining their own.

Usage:
    from config.settings_loader import settings, save_settings, reset_settings

    # Access settings
    model = settings["models"]["embedding"]

    # Update settings
    settings["rag"]["top_k"] = 5
    save_settings()

    # Reset to defaults
    reset_settings()
"""

import json
from pathlib import Path
from typing import Any

# Paths
CONFIG_DIR = Path(__file__).parent
SETTINGS_FILE = CONFIG_DIR / "settings.json"
DEFAULTS_FILE = CONFIG_DIR / "settings.defaults.json"

# --- Settings Cache ---
_settings_cache: dict[str, Any] | None = None


def load_settings() -> dict[str, Any]:
    """Load settings from file. Uses cache if already loaded."""
    global _settings_cache
    if _settings_cache is None:
        if SETTINGS_FILE.exists():
            _settings_cache = json.loads(SETTINGS_FILE.read_text())
        elif DEFAULTS_FILE.exists():
            # Fall back to defaults if settings.json doesn't exist
            _settings_cache = json.loads(DEFAULTS_FILE.read_text())
            save_settings()  # Create settings.json from defaults
        else:
            raise FileNotFoundError(f"No settings files found in {CONFIG_DIR}")
    return _settings_cache


def save_settings() -> None:
    """Save current settings to file."""
    global _settings_cache
    if _settings_cache is not None:
        SETTINGS_FILE.write_text(json.dumps(_settings_cache, indent=2))


def reset_settings() -> dict[str, Any]:
    """Reset settings to defaults."""
    global _settings_cache
    if DEFAULTS_FILE.exists():
        _settings_cache = json.loads(DEFAULTS_FILE.read_text())
        save_settings()
    if _settings_cache is None:
        raise FileNotFoundError(f"No defaults file found at {DEFAULTS_FILE}")
    return _settings_cache


def reload_settings() -> dict[str, Any]:
    """Force reload settings from disk (useful after external changes)."""
    global _settings_cache
    _settings_cache = None
    return load_settings()


# --- Convenience Accessors ---
# These provide direct access to commonly used settings


def get_model(purpose: str) -> str:
    """Get model name for a specific purpose."""
    result: str = load_settings()["models"].get(purpose, "gemini-2.5-flash-lite")
    return result


# --- Initialize on import ---
settings = load_settings()
